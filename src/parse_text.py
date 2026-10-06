"""Extract per-page PDF text and word boxes, with a Tesseract fallback."""
import argparse
import csv
import json
import re
from pathlib import Path
from statistics import mean
from tempfile import TemporaryDirectory

import pdfplumber
import pytesseract
import yaml
from pdf2image import convert_from_path

JUNK = re.compile(r"\(cid:\d+\)|\ufffd")
LOG_FIELDS = ["doc_id", "stem", "page", "ocr", "reason", "char_count", "junk_ratio",
              "engine", "mean_confidence", "text_chars"]


def ocr_reason(text, params):
    tokens = text.split()
    chars = len(re.sub(r"\s", "", text))
    junk_ratio = sum(bool(JUNK.search(token)) for token in tokens) / len(tokens) if tokens else 0.0
    reasons = []
    if chars < params["min_chars"]:
        reasons.append("low_char_count")
    if junk_ratio > params["junk_ratio"]:
        reasons.append("high_junk_ratio")
    return ";".join(reasons), chars, junk_ratio


def ocr_page(pdf_path, number, width, height, params):
    image = convert_from_path(str(pdf_path), dpi=params["dpi"], first_page=number,
                              last_page=number)[0]
    try:
        data = pytesseract.image_to_data(image, lang=params["language"],
                                         output_type=pytesseract.Output.DICT)
        sx, sy = width / image.width, height / image.height
        words, lines = [], {}
        for i, value in enumerate(data["text"]):
            value = value.strip()
            confidence = float(data["conf"][i])
            if not value or confidence < 0:
                continue
            x, y = data["left"][i], data["top"][i]
            words.append({"text": value,
                          "bbox": [x * sx, y * sy, (x + data["width"][i]) * sx,
                                   (y + data["height"][i]) * sy],
                          "ocr_conf": confidence})
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines.setdefault(key, []).append(value)
        text = "\n".join(" ".join(line) for line in lines.values())
        confidence = mean(w["ocr_conf"] for w in words) if words else None
        return text, words, confidence
    finally:
        image.close()


def extract_page_text(pdf_path, ocr_params=None):
    """Yield page text, top-left point boxes, and the native/OCR decision."""
    if ocr_params is None:
        ocr_params = yaml.safe_load(Path("params.yaml").read_text())["ocr"]
    with pdfplumber.open(pdf_path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            reason, chars, junk_ratio = ocr_reason(text, ocr_params)
            confidence = None
            if reason:
                text, words, confidence = ocr_page(pdf_path, number, page.width, page.height, ocr_params)
            else:
                x0, top = page.bbox[:2]
                words = [{"text": w["text"], "bbox": [w["x0"] - x0, w["top"] - top,
                          w["x1"] - x0, w["bottom"] - top], "ocr_conf": None}
                         for w in page.extract_words()]
            yield {"page": number, "text": text, "words": words, "ocr": bool(reason),
                   "reason": reason or "native_text", "char_count": chars,
                   "junk_ratio": junk_ratio, "engine": "tesseract" if reason else "pdfplumber",
                   "mean_confidence": confidence, "text_chars": len(text.strip())}


def main(params_path, input_dir, output_dir):
    params = yaml.safe_load(Path(params_path).read_text())["ocr"]
    if params["dpi"] <= 0 or params["min_chars"] < 0 or not 0 <= params["junk_ratio"] <= 1:
        raise ValueError("OCR requires positive DPI, nonnegative min_chars, and junk_ratio in [0, 1]")
    source, output = Path(input_dir), Path(output_dir)
    pdfs = sorted(source.glob("*.pdf"))
    if not pdfs:
        raise ValueError(f"no PDFs under {source}")
    manifest = source / "manifest.csv"
    doc_ids = {}
    if manifest.exists():
        with manifest.open(newline="") as f:
            for row in csv.DictReader(f):
                if row["stem"] in doc_ids:
                    raise ValueError(f"duplicate manifest stem: {row['stem']}")
                doc_ids[row["stem"]] = row["doc_id"]
        if any(pdf.stem not in doc_ids for pdf in pdfs):
            raise ValueError("input PDF missing from manifest")
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".parse-", dir=output) as tmp:
        staged = Path(tmp)
        with (staged / "ocr_log.csv").open("w", newline="") as log:
            writer = csv.DictWriter(log, fieldnames=LOG_FIELDS)
            writer.writeheader()
            for pdf in pdfs:
                doc_id = doc_ids.get(pdf.stem)
                with (staged / f"{pdf.stem}.words.jsonl").open("w") as words_file:
                    for page in extract_page_text(pdf, params):
                        (staged / f"{pdf.stem}_p{page['page']:04d}.txt").write_text(page["text"] + "\n")
                        for word in page["words"]:
                            record = {"doc_id": doc_id, "page": page["page"], **word, "ocr": page["ocr"]}
                            words_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                        writer.writerow({"doc_id": doc_id, "stem": pdf.stem,
                                         **{key: page[key] for key in LOG_FIELDS if key in page}})
                        print(f"{pdf.stem} page {page['page']}: {page['engine']} ({page['reason']}), {page['text_chars']} chars")
        for pdf in pdfs:
            for stale in output.glob(f"{pdf.stem}_p[0-9][0-9][0-9][0-9].txt"):
                stale.unlink()
        for artifact in staged.iterdir():
            artifact.replace(output / artifact.name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--params", default="params.yaml")
    parser.add_argument("--input", default="data/rendered")
    parser.add_argument("--output", default="data/parsed")
    args = parser.parse_args()
    main(args.params, args.input, args.output)
