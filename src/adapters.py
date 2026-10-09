import csv
import hashlib
import html
import json
import re
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

from schema import Block, Table, SCHEMA_VERSION

FORBIDDEN = {"inverted", "footer", "table_info", "score", "docling_label",
             "ocr", "extractor", "extractor_version", "model"}

PACKAGE = {"camelot": "camelot-py", "pdfplumber": "pdfplumber"}


def table_methods(log_path="data/tables/log/tables_log.csv"):
    try:
        with open(log_path, newline="", encoding="utf-8") as f:
            return {
                (r["stem"], int(r["page"])): r["method"]
                for r in csv.DictReader(f)
                if r.get("accepted") == "True"
            }
    except FileNotFoundError:
        return {}


def extractor_version(method):
    pkg = PACKAGE.get(method.split("-")[0])
    if not pkg:
        return "unknown"
    try:
        return f"{pkg} {version(pkg)}"
    except PackageNotFoundError:
        return pkg
    
PACKAGE.setdefault("docling", "docling")

def posix_path(p):
    """Manifest paths can be written on Windows; records always use '/'."""
    return str(p).replace("\\", "/")


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _dei_value(doc, name):
    m = re.search(r"<ix:nonNumeric\b[^>]*\bname=\"dei:" + name + r"\"[^>]*>(.*?)</ix:nonNumeric>",
                  doc, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    text = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
    return text or None


def dei_fiscal(ixbrl_path):
    """(fiscal_year, fiscal_period) from the filing's own dei facts.

    Part 5 asks for dei:DocumentFiscalYearFocus and
    dei:DocumentFiscalPeriodFocus, the filer's own statement of the period,
    rather than a value guessed from the period end date (a 10-Q is then Q3,
    not just Q). Returns (None, None) when the file or a fact is missing.
    """
    path = Path(posix_path(ixbrl_path))
    if not path.exists():
        return None, None
    doc = path.read_text(encoding="utf-8", errors="replace")
    year = _dei_value(doc, "DocumentFiscalYearFocus")
    period = _dei_value(doc, "DocumentFiscalPeriodFocus")
    try:
        year = int(year) if year else None
    except ValueError:
        year = None
    return year, period


def _base_meta(manifest_row):
    return {
        "schema": SCHEMA_VERSION,
        "doc_id": manifest_row["accession"],
        "company": manifest_row["company"],
        "cik": manifest_row["cik"],
        "ticker": manifest_row["ticker"],
        "form": manifest_row["form"],
        "fiscal_year": int(manifest_row["fiscal_year"]),
        "fiscal_period": manifest_row["fiscal_period"],
        "source_path": manifest_row["source_path"],
        "sha256": manifest_row["sha256"],
    }


def _clean_text(v):
    if v is None:
        return None
    v = " ".join(str(v).split())
    return v or None


def block_from_layout_record(manifest_row, rec, section):
    text = _clean_text(rec.get("text"))
    if text is None:
        return None
    out = _base_meta(manifest_row)
    out.update(
        page=rec["page"],
        section=section,
        block_id=rec["block_id"],
        block_type=rec["block_type"],
        bbox=[round(float(c), 2) for c in rec["bbox"]],
        units="pt",
        origin="top-left",
        text=text,
        table=None,
        extractor="pdfplumber",
        extractor_version=rec.get("extractor_version") or extractor_version("pdfplumber"),
        ocr=bool(rec.get("ocr", False)),
        ocr_conf=None,
    )
    if out["ocr"]:
        out["ocr_conf"] = 0.0
    return Block.model_validate(out)


def table_from_csv_rows(manifest_row, page, block_id, bbox, csv_rows, method=None):
    col_labels, row_labels = [], []
    for r in csv_rows:
        if r["col_label"] not in col_labels:
            col_labels.append(r["col_label"])
        if r["row_label"] not in row_labels:
            row_labels.append(r["row_label"])

    grid_raw = {(r["row_label"], r["col_label"]): r["raw"] for r in csv_rows}
    grid_val = {(r["row_label"], r["col_label"]): r["value"] for r in csv_rows}

    def cell(grid, rl, cl):
        v = grid.get((rl, cl))
        if v is None or str(v).strip() == "":
            return None
        return str(v)

    columns = [""] + col_labels
    rows, raw_cells = [], []
    for rl in row_labels:
        rows.append([rl] + [cell(grid_val, rl, c) for c in col_labels])
        raw_cells.append([rl] + [cell(grid_raw, rl, c) for c in col_labels])

    scales = {str(r.get("scale", "")).strip() for r in csv_rows}
    scales.discard("")
    scale = scales.pop() if len(scales) == 1 else None

    table = Table(columns=columns, rows=rows, raw_cells=raw_cells, scale=scale)
    out = _base_meta(manifest_row)
    out.update(
        page=page, section=None, block_id=block_id, block_type="Table",
        bbox=[round(float(c), 2) for c in bbox], units="pt", origin="top-left",
        text=None, table=table,
        extractor=method or "unknown",
        extractor_version=extractor_version(method) if method else "unknown",
        ocr=False, ocr_conf=None,
    )
    return Block.model_validate(out)


def block_from_docling_record(manifest_row, rec, section):
    text = _clean_text(rec.get("text"))
    if text is None:
        return None
    out = _base_meta(manifest_row)
    out.update(
        page=rec["page"], section=section, block_id=rec["block_id"],
        block_type=rec["block_type"],
        bbox=[round(float(c), 2) for c in rec["bbox"]],
        units="pt", origin="top-left", text=text, table=None,
        extractor="docling", extractor_version=str(rec.get("model") or "docling"),
        ocr=False, ocr_conf=None,
    )
    return Block.model_validate(out)