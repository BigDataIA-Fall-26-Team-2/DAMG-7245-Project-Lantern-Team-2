"""Download SEC filings and unpack each full-submission.txt into its documents.

Stage: download. Reads params.yaml:download. Writes to data/raw/.
"""
import argparse
import json
import re
from pathlib import Path

import yaml
from sec_edgar_downloader import Downloader

DOCUMENT_RE = re.compile(r"<DOCUMENT>(.*?)</DOCUMENT>", re.DOTALL)
FILENAME_RE = re.compile(r"<FILENAME>(.*?)[\r\n]")
HEADER_FIELD_RE = {
    "accession": re.compile(r"^ACCESSION NUMBER:\s*(\S+)", re.MULTILINE),
    "period": re.compile(r"^CONFORMED PERIOD OF REPORT:\s*(\S+)", re.MULTILINE),
    "filing_date": re.compile(r"^FILED AS OF DATE:\s*(\S+)", re.MULTILINE),
}


def unpack_submission(submission_path: Path) -> dict:
    """Split one EDGAR full-submission.txt into its embedded documents under unpacked/."""
    text = submission_path.read_text(errors="replace")
    header_end = text.index("<DOCUMENT>")
    header = text[:header_end]

    meta = {}
    for key, pattern in HEADER_FIELD_RE.items():
        match = pattern.search(header)
        if not match:
            raise ValueError(f"{submission_path}: missing header field for '{key}'")
        meta[key] = match.group(1)

    unpacked_dir = submission_path.parent / "unpacked"
    unpacked_dir.mkdir(exist_ok=True)

    seen_filenames = set()
    for i, doc_match in enumerate(DOCUMENT_RE.finditer(text)):
        doc = doc_match.group(1)
        filename_match = FILENAME_RE.search(doc)
        if not filename_match:
            continue
        if i == 0:
            continue  # SEQUENCE 1 is the primary document, already kept as primary-document.*
        filename = filename_match.group(1).strip()
        if filename in seen_filenames:
            raise ValueError(f"{submission_path}: duplicate document filename '{filename}'")
        seen_filenames.add(filename)
        text_start = doc.index("<TEXT>") + len("<TEXT>")
        text_end = doc.rindex("</TEXT>")  # rindex: content before the real closing tag may itself contain "</TEXT>"
        (unpacked_dir / filename).write_text(doc[text_start:text_end].strip() + "\n")

    if not any(p.suffix == ".xsd" for p in unpacked_dir.iterdir()):
        raise ValueError(f"{submission_path}: no .xsd schema found among unpacked documents")

    return meta


def main(params_path: str, output: str) -> None:
    params = yaml.safe_load(Path(params_path).read_text())["download"]
    raw_dir = Path(output)
    raw_dir.mkdir(parents=True, exist_ok=True)

    dl = Downloader(params["user_agent_name"], params["user_agent_email"], raw_dir)

    for form in params["forms"]:
        if "/" in form:
            raise ValueError(f"form '{form}' contains '/', which breaks this script's one-folder-per-form layout")
        count = dl.get(
            form,
            params["ticker"],
            after=params["after"],
            before=params["before"],
            download_details=True,
        )
        if count == 0:
            raise RuntimeError(f"no {form} filings found for {params['ticker']} in the configured date range")
        print(f"downloaded {count} {form} filing(s)")

    filing_dirs = sorted(raw_dir.glob(f"sec-edgar-filings/{params['ticker']}/*/*/"))
    for filing_dir in filing_dirs:
        if len(list(filing_dir.glob("primary-document.*"))) != 1:
            raise RuntimeError(f"{filing_dir}: expected one primary-document file from download_details")

        submission_path = filing_dir / "full-submission.txt"
        meta = unpack_submission(submission_path)
        submission_path.unlink()  # fully decomposed into unpacked_dir; avoid storing it twice
        meta["ticker"] = params["ticker"]
        meta["form"] = filing_dir.parent.name
        (filing_dir / "unpacked" / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
        print(f"unpacked {filing_dir.name} ({meta['form']}, period {meta['period']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--params", default="params.yaml")
    parser.add_argument("--output", default="data/raw")
    args = parser.parse_args()
    main(args.params, args.output)
