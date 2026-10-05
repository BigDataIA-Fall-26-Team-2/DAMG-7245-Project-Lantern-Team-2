"""Part 2: hybrid table extraction and number normalization (issues #29, #30).

Per page: a lattice gate (visible vertical rulings >= min_rulings) decides whether Camelot
lattice is tried; Camelot stream, Camelot network and pdfplumber 'text' are always tried.
Each candidate table is scored as label_ratio x coverage and the best one is kept when its
score >= accept_score. The winner is written in the long format of docs/CONTRACTS.md
(row_label, col_label, raw, value, scale) and every decision is logged.
Rules are justified by the bake-off in prototyping/dhruvi/bakeoff/ (README.md).
"""
import argparse
import re
import warnings
from collections import Counter
from pathlib import Path

import camelot
import pandas as pd
import pdfplumber
import yaml

COLUMNS = ["row_label", "col_label", "raw", "value", "scale"]
LOG_FIELDS = ["stem", "page", "table", "accepted", "method", "score", "label_ratio", "coverage",
              "numeric_rows", "skipped_rows", "v_rulings", "lattice_tried", "candidates",
              "runner_up", "runner_up_score", "errors"]
PRIORITY = {"camelot-lattice": 0, "camelot-stream": 1, "pdfplumber-text": 2, "camelot-network": 3}
NUMBER = re.compile(r"^\(?-?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?\)?$")
DASHES = {"-", "\u2014", "\u2013", "\u2212"}
FOOTNOTE = re.compile(r"(\(\d\)|\*+|\u2020|\u2021)$")
YEAR = re.compile(r"^(19|20)\d{2}$")
YEAR_IN_TEXT = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
MONTH_DAY = re.compile(r"(" + "|".join(MONTHS) + r")(\d{1,2})")


# ---------- normalization (#30) ----------
def norm(text):
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def clean_token(cell):
    """Drop '$' and spaces; strip a trailing footnote marker such as (1), * or a dagger after a number."""
    token = str(cell).replace("$", "").replace(" ", "").strip()
    stripped = FOOTNOTE.sub("", token)
    if stripped and stripped != token and NUMBER.match(stripped):
        token = stripped
    return token


def is_number_cell(cell):
    token = clean_token(cell)
    return token in DASHES or bool(NUMBER.match(token))


def normalize(raw, scale=1.0):
    """Raw cell -> float in full units. (x) and an unmatched '(' or ')' mean negative; a dash means 0."""
    token = clean_token(raw)
    if token in DASHES:
        return 0.0
    if not NUMBER.match(token):
        return None
    negative = "(" in token or ")" in token or token.startswith("-")
    number = float(token.strip("()").lstrip("-").replace(",", ""))
    return round((-number if negative else number) * scale, 6)


# ---------- scoring and method choice (#29) ----------
def parse_rows(df):
    """Each row -> (label fragments, number cells); lone '$' cells are dropped."""
    rows = []
    for raw_row in df.fillna("").astype(str).values.tolist():
        cells = [c.strip() for c in raw_row if c.strip() and c.strip() != "$"]
        rows.append(([c for c in cells if not is_number_cell(c)], [c for c in cells if is_number_cell(c)]))
    return rows


def is_year_row(label, numbers):
    return not label and all(YEAR.match(clean_token(n)) for n in numbers)


def table_stats(df):
    """(label_ratio, numeric_rows): data rows have >= 2 numbers and are not year headers."""
    data = [(l, n) for l, n in parse_rows(df) if len(n) >= 2 and not is_year_row(l, n)]
    if not data:
        return 0.0, 0
    return sum(1 for l, _ in data if l) / len(data), len(data)


def gray_level(color):
    """0 = black, 1 = white; None means the PDF default fill (black)."""
    if color is None:
        return 0.0
    values = [float(v) for v in (color if isinstance(color, (list, tuple)) else [color]) if isinstance(v, (int, float))]
    if not values:
        return 0.0
    if len(values) == 4:  # CMYK
        return max(0.0, 1.0 - values[3] - sum(values[:3]) / 3)
    return sum(values) / len(values)


def visible_vertical_rulings(page, max_gray):
    """Vertical lines/thin rects that are actually visible (white cell borders are ignored)."""
    rects = sum(1 for r in page.rects if r["width"] < 2 and r["height"] > 10
                and gray_level(r.get("non_stroking_color")) < max_gray)
    lines = sum(1 for l in page.lines if abs(l["x0"] - l["x1"]) < 1 and l["height"] > 10
                and gray_level(l.get("stroking_color")) < max_gray)
    return rects + lines


def candidate_tables(pdf_path, page_no, page_height, bbox, use_lattice):
    tables, errors = [], []
    area = None
    if bbox:  # Camelot table_areas use a bottom-left origin: "x1,y1,x2,y2" = top-left, bottom-right
        x0, top, x1, bottom = bbox
        area = [f"{x0},{page_height - top},{x1},{page_height - bottom}"]
    for flavor in (["lattice"] if use_lattice else []) + ["stream", "network"]:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                kwargs = {"table_areas": area} if area else {}
                found = camelot.read_pdf(str(pdf_path), pages=str(page_no), flavor=flavor, **kwargs)
            tables += [(f"camelot-{flavor}", t.df) for t in found]
        except Exception as e:
            errors.append(f"camelot-{flavor}: {type(e).__name__}")
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[page_no - 1]
            if bbox:
                page = page.crop(bbox)
            settings = {"vertical_strategy": "text", "horizontal_strategy": "text"}
            tables += [("pdfplumber-text", pd.DataFrame(rows)) for rows in page.extract_tables(settings)]
    except Exception as e:
        errors.append(f"pdfplumber-text: {type(e).__name__}")
    return tables, errors


def choose_table(pdf_path, page_no, tp, bbox=None):
    """Score every candidate; return (best candidate or None, log dict)."""
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_no - 1]
        height = float(page.height)
        v_rulings = visible_vertical_rulings(page.crop(bbox) if bbox else page, tp["visible_max_gray"])
    use_lattice = v_rulings >= tp["min_rulings"]
    tables, errors = candidate_tables(pdf_path, page_no, height, bbox, use_lattice)
    cands = []
    for method, df in tables:
        ratio, n = table_stats(df)
        cands.append({"method": method, "df": df, "label_ratio": ratio, "numeric_rows": n})
    most = max((c["numeric_rows"] for c in cands), default=0)
    for c in cands:
        c["coverage"] = c["numeric_rows"] / most if most else 0.0
        c["score"] = round(c["label_ratio"] * c["coverage"], 3)
    ranked = sorted(cands, key=lambda c: (-c["score"], PRIORITY[c["method"]]))
    best = ranked[0] if ranked else None
    accepted = bool(best) and best["score"] >= tp["accept_score"] and best["numeric_rows"] >= tp["min_numeric_rows"]
    log = {"accepted": accepted, "method": best["method"] if best else "",
           "score": best["score"] if best else 0.0,
           "label_ratio": round(best["label_ratio"], 3) if best else 0.0,
           "coverage": round(best["coverage"], 3) if best else 0.0,
           "numeric_rows": best["numeric_rows"] if best else 0, "v_rulings": v_rulings,
           "lattice_tried": use_lattice, "candidates": len(cands),
           "runner_up": ranked[1]["method"] if len(ranked) > 1 else "",
           "runner_up_score": ranked[1]["score"] if len(ranked) > 1 else "",
           "errors": ";".join(errors)}
    return (best if accepted else None), log


def load_params(path="params.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)


def extract_best_df(pdf_path, page, bbox=None, params_path="params.yaml"):
    """Shared function (docs/CONTRACTS.md): best-scoring table DataFrame for a page, or None.

    bbox: optional [x0, top, x1, bottom] in points, top-left origin (Part 3 table routing)."""
    best, _ = choose_table(Path(pdf_path), page, load_params(params_path)["tables"], bbox)
    return None if best is None else best["df"]


# ---------- long-format output ----------
def page_lines(page_text):
    """Each page text line -> (label text, tuple of trailing values). The page text spells labels
    correctly even when a table extractor cuts a label into fragments or drops the first one."""
    lines = []
    for line in page_text.splitlines():
        tokens, values = line.split(), []
        while tokens and (tokens[-1] == "$" or is_number_cell(tokens[-1])):
            token = tokens.pop()
            if token != "$":
                values.append(normalize(token))
        lines.append((" ".join(tokens), tuple(reversed(values))))
    return lines


def column_labels(header_cells, n_cols):
    """ISO period labels from the header, e.g. 'FY ended 2025-09-27', '3M ended 2026-06-27', '2025-09-27'."""
    joined = re.sub(r"\s+", "|", "|".join(header_cells))
    no_sep = joined.replace("|", "")
    days = MONTH_DAY.findall(no_sep)
    years = YEAR_IN_TEXT.findall(joined)
    if len(days) == n_cols and len(years) == n_cols:
        dates = [f"{y}-{MONTHS.index(m) + 1:02d}-{int(d):02d}" for (m, d), y in zip(days, years)]
        low = no_sep.lower()
        if "threemonthsended" in low and "ninemonthsended" in low and n_cols % 2 == 0:
            half = n_cols // 2
            return [f"{p} ended {d}" for p, d in zip(["3M"] * half + ["9M"] * half, dates)]
        if "yearsended" in low or "yearended" in low:
            return [f"FY ended {d}" for d in dates]
        return dates
    return [f"col{k + 1}" for k in range(n_cols)]


def header_lines(page_text):
    """Page text lines above the first line that holds a label plus a non-year number."""
    lines = []
    for line in page_text.splitlines():
        tokens = line.split()
        numbers = [t for t in tokens if is_number_cell(t) and not YEAR.match(clean_token(t))]
        if numbers and len(tokens) > len(numbers):
            break
        lines.append(line)
    return lines


def to_long(df, page_text):
    """Winning table -> contract rows [row_label, col_label, raw, value, scale]; returns (rows, skipped).

    Numbers and columns come from the table; labels and section headers come from the page's own
    text lines, matched to each table row by its values (scanning forward, so repeated totals keep order)."""
    rows = parse_rows(df)
    data_idx = [i for i, (l, n) in enumerate(rows) if len(n) >= 2 and not is_year_row(l, n)]
    if not data_idx:
        return [], 0
    first = data_idx[0]
    n_cols = Counter(len(rows[i][1]) for i in data_idx).most_common(1)[0][0]
    header_cells = [c for r in df.fillna("").astype(str).values.tolist()[:first] for c in r if c.strip()]
    col_labels = column_labels(header_lines(page_text), n_cols)
    if col_labels[0].startswith("col"):
        col_labels = column_labels(header_cells, n_cols)
    page_n = norm(page_text)
    table_scale = 1e6 if "inmillions" in page_n else 1e3 if "inthousands" in page_n else 1.0
    share_scale = 1e3 if "reflectedinthousands" in page_n else table_scale
    lines = page_lines(page_text)
    out, skipped, section, pending, cursor = [], 0, "", "", 0
    for fragments, numbers in rows:
        if not numbers or is_year_row(fragments, numbers):
            continue
        if len(numbers) > n_cols:  # number-like text inside a label; values are the rightmost columns
            numbers = numbers[-n_cols:]
        if len(numbers) != n_cols:
            skipped += 1
            continue
        key = tuple(normalize(n) for n in numbers)
        match = next((j for j in range(cursor, len(lines)) if lines[j][1] == key), None)
        if match is None:  # no page line carries these values (page footer, stray numbers)
            skipped += 1
            continue
        for text, values in lines[cursor:match]:  # lines between the previous match and this one
            if values:
                pending = ""
            elif text.endswith(":"):
                section, pending = text[:-1].strip(), ""
            elif text and cursor > 0:
                pending = text  # first line of a two-line label
        label, cursor = lines[match][0], match + 1
        full = f"{pending} {label}".strip() if pending else label
        pending = ""
        row_label = f"{section}: {full}" if section and full else full
        sec = norm(section)
        if "sharesused" in sec:
            scale = share_scale
        elif "pershare" in sec or "pershare" in norm(full):
            scale = 1.0
        else:
            scale = table_scale
        out += [[row_label, col_labels[k], raw, normalize(raw, scale), scale] for k, raw in enumerate(numbers)]
        if norm(full).startswith("total"):
            section = ""
    return out, skipped


def clear_page_csvs(out, stem, page_no=None):
    """Delete table CSVs left by an earlier run: one page, or every page of `stem` if page_no is None.

    Without this, a page that no longer yields a table (or a re-rendered, shorter PDF) keeps its
    old _tK.csv in the output folder, and downstream stages (XBRL comparison, evaluation) read it
    as current output.
    """
    pattern = f"{stem}_p{page_no:04d}_t*.csv" if page_no is not None else f"{stem}_p*_t*.csv"
    for old in Path(out).glob(pattern):
        old.unlink()


def write_table_csv(rows, path):
    """Write one normalized table CSV; if the write fails part-way, remove the partial file."""
    try:
        pd.DataFrame(rows, columns=COLUMNS).to_csv(path, index=False)
    except Exception:
        Path(path).unlink(missing_ok=True)
        raise


def main():
    ap = argparse.ArgumentParser(description="Part 2 hybrid table extraction + normalization")
    ap.add_argument("--params", default="params.yaml")
    ap.add_argument("--input", default="data/rendered", help="folder of PDFs")
    ap.add_argument("--output", default="data/tables")
    ap.add_argument("--pages", default="", help="optional comma list stem:page (default: every page)")
    args = ap.parse_args()

    tp = load_params(args.params)["tables"]
    out = Path(args.output)
    (out / "log").mkdir(parents=True, exist_ok=True)
    wanted = {}
    for spec in filter(None, args.pages.split(",")):
        stem, page = spec.split(":")
        wanted.setdefault(stem, set()).add(int(page))

    logs = []
    for pdf_path in sorted(Path(args.input).glob("*.pdf")):
        if wanted and pdf_path.stem not in wanted:
            continue
        if not wanted:  # full run: remove every table CSV this filing produced before
            clear_page_csvs(out, pdf_path.stem)
        with pdfplumber.open(pdf_path) as pdf:
            texts = [p.extract_text() or "" for p in pdf.pages]
        for page_no in sorted(wanted.get(pdf_path.stem, [])) or range(1, len(texts) + 1):
            clear_page_csvs(out, pdf_path.stem, page_no)  # never keep this page's CSV from an earlier run
            best, log = choose_table(pdf_path, page_no, tp)
            log.update(stem=pdf_path.stem, page=page_no, table="", skipped_rows=0)
            if best is not None:
                rows, skipped = to_long(best["df"], texts[page_no - 1])
                if rows:
                    write_table_csv(rows, out / f"{pdf_path.stem}_p{page_no:04d}_t1.csv")
                    log.update(table=1, skipped_rows=skipped)
                else:
                    log["accepted"] = False
            logs.append(log)

    pd.DataFrame(logs, columns=LOG_FIELDS).to_csv(out / "log" / "tables_log.csv", index=False)
    written = [l for l in logs if l["table"] == 1]
    print(f"pages scanned: {len(logs)}, tables written: {len(written)}, "
          f"winners: {dict(Counter(l['method'] for l in written))}")


if __name__ == "__main__":
    main()
