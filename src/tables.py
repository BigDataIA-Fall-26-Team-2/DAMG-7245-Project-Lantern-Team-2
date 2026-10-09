"""Part 2: hybrid table extraction and number normalization (issues #29, #30).

Per page: a lattice gate (visible vertical rulings >= min_rulings) decides whether Camelot
lattice is tried; Camelot stream, Camelot network and pdfplumber 'text' are always tried.
Each candidate table is scored as label_ratio x coverage and the best one is kept when its
score >= accept_score. The winner is written in the long format of docs/CONTRACTS.md
(row_label, col_label, raw, value, scale) and every decision is logged.

Values are scaled per cell: a column header that states its own unit (a price, a per-share
amount, a share count, "in thousands") overrides the page caption, so mixed-unit tables such as
the 10-Q share-repurchase table are not all multiplied by the caption's "in millions". Period
labels are taken from the header block directly above each group of rows, so two tables merged
into one extraction keep their own periods. Rows are matched to page lines by their values and,
when several lines carry the same values, by the extractor's own label text; a row that is still
ambiguous is skipped and counted instead of being given a confident wrong label.
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
              "runner_up", "runner_up_score", "errors", "fallback", "fallback_error"]
PRIORITY = {"camelot-lattice": 0, "camelot-stream": 1, "pdfplumber-text": 2, "camelot-network": 3}
NUMBER = re.compile(r"^\(?-?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?\)?$")
DASHES = {"-", "\u2014", "\u2013", "\u2212"}
FOOTNOTE = re.compile(r"(\(\d\)|\*+|\u2020|\u2021)$")
YEAR = re.compile(r"^(19|20)\d{2}$")
YEAR_IN_TEXT = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
MONTH_DAY = re.compile(r"(" + "|".join(MONTHS) + r")(\d{1,2})")
FOOTNOTE_REF = re.compile(r"^\(\d\)$")
PERIODS = [("threemonthsended", "3M"), ("sixmonthsended", "6M"), ("ninemonthsended", "9M"),
           ("twelvemonthsended", "FY"), ("yearsended", "FY"), ("yearended", "FY")]


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



def close_paren(raw, page_text):
    """Restore a ')' cut off past a table's right edge (pdfplumber-text, last column), only when the
    closed form is printed on the page: '(14,264' -> '(14,264)'. The value is unchanged."""
    core = clean_token(raw)
    if (core.startswith("(") and ")" not in core and NUMBER.match(core)
            and core + ")" in str(page_text).replace(" ", "")):
        return str(raw).rstrip() + ")"
    return raw

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


def extractor_version(method):
    if method.startswith("camelot"):
        return f"camelot-py {camelot.__version__}"
    if method.startswith("pdfplumber"):
        return f"pdfplumber {pdfplumber.__version__}"
    return ""


def page_text_and_words(pdf_path, page, bbox=None):
    """Page (or bbox crop) text and word boxes; crops keep the page's coordinates."""
    with pdfplumber.open(pdf_path) as pdf:
        p = pdf.pages[page - 1]
        if bbox:
            p = p.crop(bbox)
        return p.extract_text() or "", p.extract_words()


def extract_best_df(pdf_path, page, bbox=None, params_path="params.yaml"):
    """Shared function (docs/CONTRACTS.md): the best table on a page, in contract format.

    Returns (df, info). df has the contract columns row_label, col_label, raw, value, scale (or is
    None when no candidate is accepted); info = {"method", "score", "extractor_version",
    "accepted", "skipped_rows"} for the extractor fields of the Part 5 schema.
    bbox: optional [x0, top, x1, bottom] in points, top-left origin (Part 3 table routing); it is
    converted to Camelot's bottom-left origin inside candidate_tables()."""
    best, log = choose_table(Path(pdf_path), page, load_params(params_path)["tables"], bbox)
    info = {"method": log["method"], "score": log["score"],
            "extractor_version": extractor_version(log["method"]),
            "accepted": best is not None, "skipped_rows": 0}
    if best is None:
        return None, info
    # Full page on purpose: the scale note and period headers sit above the table bbox;
    # bbox only chooses the table (choose_table above), as in the full-filing path.
    text, words = page_text_and_words(pdf_path, page)
    rows, info["skipped_rows"] = to_long(best["df"], text, words)
    if not rows:
        info["accepted"] = False
        return None, info
    return pd.DataFrame(rows, columns=COLUMNS), info


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
    """ISO period labels from the header, e.g. 'FY ended 2025-09-27', '3M ended 2026-06-27', '2025-09-27'.

    One period phrase ("Nine Months Ended") applies to every column; two ("Three Months Ended",
    "Nine Months Ended") split the columns in half, in the order they appear; none means instants."""
    joined = re.sub(r"\s+", "|", "|".join(header_cells))
    no_sep = joined.replace("|", "")
    days = MONTH_DAY.findall(no_sep)
    years = YEAR_IN_TEXT.findall(joined)
    if len(days) == n_cols and len(years) == n_cols:
        dates = [f"{y}-{MONTHS.index(m) + 1:02d}-{int(d):02d}" for (m, d), y in zip(days, years)]
        low = no_sep.lower()
        tags = []
        for _, tag in sorted((low.find(p), t) for p, t in PERIODS if p in low):
            if tag not in tags:
                tags.append(tag)
        if len(tags) == 1:
            return [f"{tags[0]} ended {d}" for d in dates]
        if len(tags) == 2 and n_cols % 2 == 0:
            half = n_cols // 2
            return [f"{t} ended {d}" for t, d in zip([tags[0]] * half + [tags[1]] * half, dates)]
        return dates
    return [f"col{k + 1}" for k in range(n_cols)]


def is_data_line(line):
    """A page line with a label and at least one non-year number (footnote refs like (1) excluded)."""
    tokens = line.split()
    numbers = [t for t in tokens if is_number_cell(t) and not YEAR.match(clean_token(t))
               and not FOOTNOTE_REF.match(t)]
    return bool(numbers) and len(tokens) > len(numbers)


def _header_text(run):
    return [l for l in run if not l.rstrip().endswith(":")]  # section labels are not headers


def header_from_run(run, n_cols):
    """Period labels from a block of non-data lines, or None. Tries the whole block, then shorter
    suffixes, because the header sits just above the data (a caption sentence may precede it)."""
    lines = _header_text(run)
    for i in range(len(lines)):
        labels = column_labels(lines[i:], n_cols)
        if not labels[0].startswith("col"):
            return labels
    return None


def header_blocks(page_text, n_cols):
    """For each page line: (period labels or None, block number) of the nearest header above it.

    Every non-data run that parses as a period header starts a new block, so a second table on
    the page uses its own header. A run that has dates but does not parse ends the previous
    header (labels None) rather than letting the next rows inherit the wrong periods."""
    info, labels, block, run = [], None, 0, []
    for line in page_text.splitlines():
        if is_data_line(line):
            if run:
                parsed = header_from_run(run, n_cols)
                if parsed is not None:
                    labels, block = parsed, block + 1
                elif MONTH_DAY.search(re.sub(r"\s+", "", " ".join(_header_text(run)))):
                    labels = None
                run = []
        else:
            run.append(line)
        info.append((labels, block))
    return info


# ---------- per-column units from the header words above the data (P1) ----------
def word_lines(words, tol=3):
    """pdfplumber word boxes -> lines of words, top to bottom, each left to right."""
    lines = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(w["top"] - lines[-1][0]["top"]) <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(l, key=lambda w: w["x0"]) for l in lines]


def align_lines(text_lines, wlines):
    """Map each page-text line index to the index of the word line with the same text (in order)."""
    keys = [norm(" ".join(w["text"] for w in l)) for l in wlines]
    mapping, k = {}, 0
    for j, text in enumerate(text_lines):
        t = norm(text)
        if not t:
            continue
        for kk in range(k, len(keys)):
            if keys[kk] == t:
                mapping[j], k = kk, kk + 1
                break
    return mapping


def trailing_number_words(wline):
    nums = []
    for w in reversed(wline):
        if w["text"] == "$":
            continue
        if not is_number_cell(w["text"]):
            break
        nums.append(w)
    return nums[::-1]


def header_unit(header, share_scale):
    """Scale a column header states for its own values, or None when it says nothing about units."""
    h = norm(header)
    if "pershare" in h or "price" in h:
        return 1.0
    if "inthousands" in h:
        return 1e3
    if "inmillions" in h:
        return 1e6
    if "numberofshares" in h or "sharespurchased" in h:
        return share_scale
    return None


def column_units(wlines, idx, data_lines, n_cols, share_scale, max_dist=45, max_gap=30):
    """Per-column scales (None = no statement) from the header words directly above a table.

    Number columns are located from the data rows' trailing number words; header words are the
    lines above the first data row, up to a prose line (the caption sentence), another data row or
    a vertical gap. Each header word goes to the nearest number column within max_dist points;
    lines entirely in the label column (section labels) are skipped."""
    spans = [[] for _ in range(n_cols)]
    for j in data_lines:
        if j in idx:
            nums = trailing_number_words(wlines[idx[j]])
            if len(nums) >= n_cols:
                for k, w in enumerate(nums[-n_cols:]):
                    spans[k].append(w)
    if not all(spans):
        return [None] * n_cols
    cols = [(min(w["x0"] for w in s), max(w["x1"] for w in s)) for s in spans]
    edge = cols[0][0] - 20
    first = min(idx[j] for j in data_lines if j in idx)
    texts = [[] for _ in range(n_cols)]
    prev_top = wlines[first][0]["top"]
    for wl in reversed(wlines[:first]):
        top = wl[0]["top"]
        if prev_top - top > max_gap:
            break
        prev_top = top
        in_cols = [w for w in wl if (w["x0"] + w["x1"]) / 2 >= edge]
        if not in_cols:
            continue
        gaps = [b["x0"] - a["x1"] for a, b in zip(wl, wl[1:])]
        if len(wl) >= 4 and max(gaps) < 6:  # evenly spaced words = a caption or prose sentence
            break
        if is_data_line(" ".join(w["text"] for w in wl)):
            break
        for w in in_cols:
            c = (w["x0"] + w["x1"]) / 2
            k, dist = min(((k, max(lo - c, 0, c - hi)) for k, (lo, hi) in enumerate(cols)),
                          key=lambda t: t[1])
            if dist <= max_dist:
                texts[k].append((w["top"], w["x0"], w["text"]))
    # read each column's header top to bottom: "Number / of Shares / Purchased", not bottom-up
    return [header_unit(" ".join(t for _, _, t in sorted(col)), share_scale) for col in texts]


def match_line(lines, cursor, key, fragments):
    """Index of the page line (from cursor on) that carries these values, or None.

    Several lines can carry the same values (a balance sheet's Total assets and Total liabilities
    and equity). The extractor's own label fragments pick the line whose label fits; without label
    evidence a match must be unique, otherwise the row is rejected instead of mislabelled."""
    cands = [j for j in range(cursor, len(lines)) if lines[j][1] == key]
    if not cands:
        return None
    frag = norm("".join(fragments))
    if len(frag) >= 3:
        for j in cands:
            prev = lines[j - 1][0] if j > 0 and not lines[j - 1][1] else ""
            label = norm(lines[j][0])
            if frag in norm(prev) + label or (len(label) >= 6 and label in frag):
                return j
    return cands[0] if len(cands) == 1 else None


def to_long(df, page_text, words=None):
    """Winning table -> contract rows [row_label, col_label, raw, value, scale]; returns (rows, skipped).

    Numbers and columns come from the table; labels and section headers come from the page's own
    text lines, matched to each table row by its values (scanning forward, so repeated totals keep
    order, and using the extractor's label text when several lines carry the same values).
    Period labels come from the header block above each group of rows. With word boxes (`words`,
    from pdfplumber extract_words) each column's header can set its own unit."""
    rows = parse_rows(df)
    data_idx = [i for i, (l, n) in enumerate(rows) if len(n) >= 2 and not is_year_row(l, n)]
    if not data_idx:
        return [], 0
    first = data_idx[0]
    n_cols = Counter(len(rows[i][1]) for i in data_idx).most_common(1)[0][0]
    header_cells = [c for r in df.fillna("").astype(str).values.tolist()[:first] for c in r if c.strip()]
    fallback = column_labels(header_cells, n_cols)
    page_n = norm(page_text)
    table_scale = 1e6 if "inmillions" in page_n else 1e3 if "inthousands" in page_n else 1.0
    share_scale = 1e3 if "reflectedinthousands" in page_n else table_scale
    lines = page_lines(page_text)
    headers = header_blocks(page_text, n_cols)

    matches, skipped, cursor = [], 0, 0
    for fragments, numbers in rows:
        if not numbers or is_year_row(fragments, numbers):
            continue
        if len(numbers) > n_cols:  # number-like text inside a label; values are the rightmost columns
            numbers = numbers[-n_cols:]
        if len(numbers) != n_cols:
            skipped += 1
            continue
        match = match_line(lines, cursor, tuple(normalize(n) for n in numbers), fragments)
        if match is None:  # no page line carries these values, or the match is ambiguous
            skipped += 1
            continue
        matches.append((cursor, match, numbers))
        cursor = match + 1

    units = {}
    if words:
        wlines = word_lines(words)
        idx = align_lines(page_text.splitlines(), wlines)
        for block in {headers[j][1] for _, j, _ in matches}:
            js = [j for _, j, _ in matches if headers[j][1] == block]
            units[block] = column_units(wlines, idx, js, n_cols, share_scale)

    out, section, pending, block_seen = [], "", "", None
    for start, match, numbers in matches:
        labels, block = headers[match]
        if block != block_seen:  # first row under a new header: a new table, sections start fresh
            section, pending, block_seen = "", "", block
        for text, values in lines[start:match]:  # lines between the previous match and this one
            if values:
                pending = ""
            elif text.endswith(":"):
                section, pending = text[:-1].strip(), ""
            elif text and start > 0:
                pending = text  # first line of a two-line label
        label = lines[match][0]
        full = f"{pending} {label}".strip() if pending else label
        pending = ""
        if not full:  # a line of footnote markers such as "(2) (2) (2)", not a data row
            skipped += 1
            continue
        row_label = f"{section}: {full}" if section and full else full
        col_labels = labels or (fallback if block == 0 else [f"col{k + 1}" for k in range(n_cols)])
        sec = norm(section)
        if "sharesused" in sec:
            row_scale = share_scale
        elif "pershare" in sec or "pershare" in norm(full):
            row_scale = 1.0
        else:
            row_scale = table_scale
        col_units = units.get(block) or [None] * n_cols
        for k, raw in enumerate(numbers):
            scale = col_units[k] if col_units[k] is not None else row_scale
            out.append([row_label, col_labels[k], close_paren(raw, page_text), normalize(raw, scale), scale])
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

# ---------- Part 7: managed fallback ----------
def managed_fallback(pdf_path, page_no, log, out, params):
    """Ask the managed service (Part 7) about a page whose table was found but scored low.

    Returns "" when no check was needed, "used" when the managed answer was used,
    "miss" when nothing is cached and managed.enabled is false, and "error" when
    the check could not run. It never raises, so this stage never fails because of it,
    but on "error" the real exception is kept in log["fallback_error"] (and so in
    tables_log.csv), so a failure stays diagnosable.
    """
    cfg = params.get("managed", {}) or {}
    min_score = float((cfg.get("trigger", {}) or {}).get("min_table_score", 0.5))
    min_rows = int((params.get("tables", {}) or {}).get("min_numeric_rows", 3))
    dest = Path(out) / "managed" / f"{pdf_path.stem}_p{page_no:04d}.blocks.jsonl"
    if dest.exists():
        dest.unlink()  # never keep this page's managed answer from an earlier run
    if not log.get("method") or int(log.get("numeric_rows") or 0) < min_rows:
        return ""  # no real table on this page, nothing for a managed service to fix
    if float(log.get("score") or 0) >= min_score:
        return ""
    try:
        from managed import textract
        # the params this stage was run with (--params), never the root file
        row = textract.load_manifest(params).get(pdf_path.stem)
        if row is None:
            log["fallback_error"] = f"{pdf_path.stem} not in manifest"
            return "error"
        blocks = textract.fallback_blocks(row, pdf_path, page_no,
                                          reason="low table score", params=params)
    except Exception as e:
        log["fallback_error"] = f"{type(e).__name__}: {e}"
        return "error"
    if not blocks:
        return "miss"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("".join(b.to_jsonl() + "\n" for b in blocks), encoding="utf-8")
    return "used"


def main():
    ap = argparse.ArgumentParser(description="Part 2 hybrid table extraction + normalization")
    ap.add_argument("--params", default="params.yaml")
    ap.add_argument("--input", default="data/rendered", help="folder of PDFs")
    ap.add_argument("--output", default="data/tables")
    ap.add_argument("--pages", default="", help="optional comma list stem:page (default: every page)")
    args = ap.parse_args()

    params = load_params(args.params)
    tp = params["tables"]
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
            words = [p.extract_words() for p in pdf.pages]
        for page_no in sorted(wanted.get(pdf_path.stem, [])) or range(1, len(texts) + 1):
            clear_page_csvs(out, pdf_path.stem, page_no)  # never keep this page's CSV from an earlier run
            best, log = choose_table(pdf_path, page_no, tp)
            log.update(stem=pdf_path.stem, page=page_no, table="", skipped_rows=0)
            if best is not None:
                rows, skipped = to_long(best["df"], texts[page_no - 1], words[page_no - 1])
                if rows:
                    write_table_csv(rows, out / f"{pdf_path.stem}_p{page_no:04d}_t1.csv")
                    log.update(table=1, skipped_rows=skipped)
                else:
                    log["accepted"] = False
            log["fallback"] = managed_fallback(pdf_path, page_no, log, out, params)
            logs.append(log)

    pd.DataFrame(logs, columns=LOG_FIELDS).to_csv(out / "log" / "tables_log.csv", index=False)
    written = [l for l in logs if l["table"] == 1]
    print(f"pages scanned: {len(logs)}, tables written: {len(written)}, "
          f"winners: {dict(Counter(l['method'] for l in written))}")


if __name__ == "__main__":
    main()