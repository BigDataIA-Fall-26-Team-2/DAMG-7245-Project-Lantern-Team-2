"""Part 11 (#38): extract numeric XBRL facts from each filing with Arelle.

Reads data/rendered/manifest.csv (one row per filing; `source_file` is the unpacked iXBRL .htm),
loads each filing with Arelle and writes one row per numeric fact to data/xbrl/facts.csv:
concept, label, value, unit, decimals, period (instant or duration, start/end/months) and
dimensions, de-duplicated. `period_label` uses the same format as the table CSVs' col_label
("FY ended 2025-09-27", "3M ended 2026-06-27", or the date for an instant) so facts join to cells.

Two quirks are handled here:
* SEC's full-submission.txt wraps every XBRL document in <XBRL>...</XBRL> (side files in
  <XML>...</XML>) and the unpacked files keep that envelope. Arelle then rejects the .xsd, never
  loads the US-GAAP taxonomy, and every us-gaap fact has no definition. We load an unwrapped
  temporary copy instead; data/raw is never modified.
* Arelle stores date-only period ends and instants as midnight of the next day, so one day is
  subtracted to get the filing's own dates (fiscal year end 2025-09-27, not 2025-09-28).
"""
import argparse
import difflib
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import timedelta
from pathlib import Path

import pandas as pd
import yaml

FACT_COLUMNS = ["stem", "accession", "form", "concept", "prefix", "label", "value", "unit",
                "decimals", "period_type", "start", "end", "months", "period_label",
                "n_dims", "dims", "n_copies"]
DEDUP_KEY = ["stem", "prefix", "concept", "period_type", "start", "end", "unit", "dims"]
XBRL_SUFFIXES = {".htm", ".xsd", ".xml"}


def unwrap(data: bytes) -> bytes:
    """Strip SEC's <XBRL>...</XBRL> or <XML>...</XML> envelope from both ends, if present."""
    s = data.strip()
    for tag in (b"XBRL", b"XML"):
        open_, close = b"<" + tag + b">", b"</" + tag + b">"
        if s.startswith(open_) and s.endswith(close):
            return s[len(open_):-len(close)].strip() + b"\n"
    return data


def unwrapped_copy(src_dir, dest_dir):
    """Copy a filing's unpacked folder to dest_dir with envelopes stripped; return files changed."""
    shutil.copytree(src_dir, dest_dir)
    changed = 0
    for p in Path(dest_dir).iterdir():
        if p.suffix.lower() in XBRL_SUFFIXES:
            data = p.read_bytes()
            new = unwrap(data)
            if new != data:
                p.write_bytes(new)
                changed += 1
    return changed


def period_fields(context):
    """Return (period_type, start, end, months, period_label) in the filing's own dates."""
    if context.isInstantPeriod:
        end = (context.instantDatetime - timedelta(days=1)).date().isoformat()
        return "instant", None, end, None, end
    if not context.isStartEndPeriod:
        return "forever", None, None, None, None
    start = context.startDatetime.date()
    end = (context.endDatetime - timedelta(days=1)).date()
    months = round((end - start).days / 30.44)
    label = f"FY ended {end}" if months == 12 else f"{months}M ended {end}"
    return "duration", start.isoformat(), end.isoformat(), months, label


def dims_string(context):
    """Dimensions as a sorted 'axis=member;...' string ('' for face-of-statement totals)."""
    parts = []
    for dim, mem in context.qnameDims.items():
        member = mem.memberQname if mem.isExplicit else mem.stringValue
        parts.append(f"{dim}={member}")
    return ";".join(sorted(parts))


def fact_rows(model, stem, accession, form):
    """One dict per numeric, non-nil fact that has a concept definition."""
    rows = []
    for f in model.facts:
        if f.concept is None or not f.isNumeric or f.isNil or f.xValue is None:
            continue
        ptype, start, end, months, plabel = period_fields(f.context)
        rows.append({"stem": stem, "accession": accession, "form": form,
                     "concept": f.concept.qname.localName, "prefix": f.concept.qname.prefix,
                     "label": f.concept.label(lang="en"), "value": float(f.xValue),
                     "unit": f.unitID, "decimals": f.decimals,
                     "period_type": ptype, "start": start, "end": end, "months": months,
                     "period_label": plabel, "n_dims": len(f.context.qnameDims),
                     "dims": dims_string(f.context)})
    return rows


def precision(decimals):
    """Sort key for XBRL decimals: INF is exact, missing is least precise, else higher = finer."""
    if decimals == "INF":
        return float("inf")
    try:
        return int(decimals)
    except (TypeError, ValueError):
        return float("-inf")


def dedupe(df):
    """Keep the most precise copy per (concept, period, unit, dims); count copies and value disagreements.

    The same fact can be tagged twice at different rounding (10-K: UnrecognizedTaxBenefits as
    "$22.0 billion", decimals -8, in the text and 22,038 million, decimals -6, in the table).
    """
    filled = df.fillna({c: "" for c in DEDUP_KEY})
    filled = filled.assign(_prec=filled["decimals"].map(precision)).sort_values(
        "_prec", ascending=False, kind="stable")
    groups = filled.groupby(DEDUP_KEY, sort=False)
    out = groups.head(1).drop(columns="_prec").sort_index()
    out["n_copies"] = groups["value"].transform("size").loc[out.index]
    conflicts = int((groups["value"].nunique() > 1).sum())
    return out, conflicts


def main():
    ap = argparse.ArgumentParser(description="Part 11: extract numeric XBRL facts with Arelle")
    ap.add_argument("--input", default="data/rendered/manifest.csv",
                    help="manifest with stem, accession, form, source_file (unpacked iXBRL .htm)")
    ap.add_argument("--output", default="data/xbrl", help="folder for facts.csv and log/arelle.log")
    args = ap.parse_args()

    from arelle import Cntlr  # imported here so the helpers can be unit-tested without Arelle

    out = Path(args.output)
    (out / "log").mkdir(parents=True, exist_ok=True)
    log_path = out / "log" / "arelle.log"
    log_path.unlink(missing_ok=True)
    cntlr = Cntlr.Cntlr(logFileName=str(log_path))

    frames = []
    for m in pd.read_csv(args.input, dtype=str).itertuples():
        src = Path(m.source_file)
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "unpacked"
            n_unwrapped = unwrapped_copy(src.parent, work)
            model = cntlr.modelManager.load(str(work / src.name))
            if model is None:
                raise SystemExit(f"{m.stem}: Arelle could not load {src}; see {log_path}")
            try:
                undefined = sum(f.concept is None for f in model.facts)
                rows = fact_rows(model, m.stem, m.accession, m.form)
            finally:
                model.close()
        if not rows:
            raise SystemExit(f"{m.stem}: no numeric facts with a definition; see {log_path}")
        df, conflicts = dedupe(pd.DataFrame(rows))
        print(f"{m.stem}: unwrapped {n_unwrapped} files; {len(rows)} numeric facts -> "
              f"{len(df)} after de-duplication ({int((df.n_dims == 0).sum())} non-dimensional); "
              f"{undefined} facts without a definition; {conflicts} duplicate groups with differing values")
        frames.append(df)

    facts = pd.concat(frames, ignore_index=True)[FACT_COLUMNS]
    tmp_out = out / "facts.csv.tmp"
    facts.to_csv(tmp_out, index=False)
    tmp_out.replace(out / "facts.csv")
    cntlr.close()
    print(f"wrote {out / 'facts.csv'}: {len(facts)} facts from {len(frames)} filings")


# ---------------------------------------------------------------------------
# #39  Compare PDF statement tables with XBRL facts
# Mapping layers: manual (config/label_map.yaml) -> label linkbase -> fuzzy.
# Run: python src/xbrl.py compare --path traditional --tables data/tables
# ---------------------------------------------------------------------------

COMPARE_COLUMNS = ["path", "stem", "statement", "page", "pdf_label", "period_label",
                   "xbrl_period", "prefix", "concept", "dims", "mapping", "pdf_raw",
                   "pdf_value", "xbrl_value", "decimals", "tolerance", "status", "cause"]
NEGATED_CAUSE = "presentation: negated label in _pre.xml"
SCALE_EXPONENTS = (3, 6, 9)


def norm(text):
    """Normalize a label for matching: straight quotes, lowercase, single spaces."""
    text = str(text).replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def line_part(label):
    """'Net sales: Total net sales' -> 'Total net sales' (text after the last prefix)."""
    return str(label).rsplit(": ", 1)[-1]


def tolerance(decimals):
    """Half a unit of the last reported digit: decimals -6 -> 500,000; INF/blank -> 0.5."""
    try:
        d = float(decimals)
    except (TypeError, ValueError):
        return 0.5
    if d != d or d in (float("inf"), float("-inf")):
        return 0.5
    return 0.5 * 10 ** (-d)


def classify(pdf, xbrl, tol):
    """Status for one cell: match, sign, scale_x1e{N}, mismatch, pdf_missing, xbrl_missing."""
    if pdf is None or pd.isna(pdf):
        return "pdf_missing"
    if xbrl is None or pd.isna(xbrl):
        return "xbrl_missing"
    if abs(pdf - xbrl) <= tol:
        return "match"
    if abs(abs(pdf) - abs(xbrl)) <= tol:
        return "sign"
    if pdf != 0 and xbrl != 0:
        for e in SCALE_EXPONENTS:
            k = 10 ** e
            if abs(abs(pdf) * k - abs(xbrl)) <= max(tol, 0.5 * k):
                return f"scale_x1e{e}"
            if abs(abs(pdf) - abs(xbrl) * k) <= max(tol * k, 0.5 * k):
                return f"scale_x1e-{e}"
    return "mismatch"


def load_label_map(path):
    """config/label_map.yaml -> {statement: [entry, ...]}, each entry with a normalized key."""
    raw = yaml.safe_load(Path(path).read_text())
    return {st: [dict(e, key=norm(e["pdf"])) for e in entries]
            for st, entries in raw["lines"].items()}


def manual_candidates(entries, label):
    """Layer 1: exact match on the normalized label, or prefix match if the entry says so."""
    key = norm(label)
    for e in entries:
        if key == e["key"] or (e.get("match") == "prefix" and key.startswith(e["key"])):
            return [("manual", {"prefix": e.get("prefix", "us-gaap"), "concept": e["concept"],
                                "dims": e.get("dims") or ""})]
    return []


def linkbase_labels(source_file):
    """Layer 2 source: {normalized label text: [(prefix, concept), ...]} from the _lab.xml."""
    found = sorted(Path(source_file).parent.glob("*_lab.xml"))
    if not found:
        return {}
    root = ET.fromstring(unwrap(found[0].read_bytes()))
    xl = "{http://www.w3.org/1999/xlink}"
    loc_concept, label_text, arcs = {}, {}, []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "loc":
            frag = el.get(xl + "href", "").rsplit("#", 1)[-1]
            prefix, _, local = frag.partition("_")
            loc_concept[el.get(xl + "label")] = (prefix, local)
        elif tag == "label":
            label_text.setdefault(el.get(xl + "label"), []).append(el.text or "")
        elif tag == "labelArc":
            arcs.append((el.get(xl + "from"), el.get(xl + "to")))
    out = {}
    for frm, to in arcs:
        if frm not in loc_concept:
            continue
        for text in label_text.get(to, []):
            key = norm(text)
            if key and loc_concept[frm] not in out.setdefault(key, []):
                out[key].append(loc_concept[frm])
    return out


def fact_index(facts):
    """{(stem, prefix, concept, dims or '', period_label): (value, decimals)}."""
    idx = {}
    for r in facts.itertuples(index=False):
        dims = "" if r.n_dims == 0 else str(r.dims)
        idx[(r.stem, r.prefix, r.concept, dims, r.period_label)] = (r.value, r.decimals)
    return idx


def candidates(label, entries, labels, choices, cutoff):
    """Try the three mapping layers in order; return [(method, candidate), ...]."""
    found = manual_candidates(entries, label)
    if found:
        return found
    for text in (norm(label), norm(line_part(label))):
        if text in labels:
            return [("label", {"prefix": p, "concept": c, "dims": ""}) for p, c in labels[text]]
    hit = difflib.get_close_matches(norm(line_part(label)), choices, n=1, cutoff=cutoff)
    if hit:
        return [("fuzzy", {"prefix": p, "concept": c, "dims": ""}) for p, c in labels[hit[0]]]
    return []


def period_bounds(facts):
    """{duration period_label: (start, end)} so a duration column can find its instants."""
    d = facts[facts.period_type == "duration"].drop_duplicates("period_label")
    return dict(zip(d.period_label, zip(d.start, d.end)))


def period_options(period, bounds):
    """The column's own period, then (duration columns only) its end and opening instants.
    Beginning/ending balance rows are instants printed inside a duration column."""
    options = [period]
    if period in bounds:
        start, end = bounds[period]
        opening = (pd.Timestamp(start) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        options += [str(end), opening]
    return options


def instant_options(entry, options):
    """Keep only the instant a balance line refers to: `instant: end` or `instant: opening`."""
    which = entry.get("instant")
    if which == "end":
        return options[1:2]
    if which == "opening":
        return options[2:3]
    return options


def missing_cells(entries, periods, stem, idx, bounds, seen):
    """Curated lines that have an XBRL fact for a table period but no PDF cell.
    Returns (entry, column period, fact period, value, decimals); seen holds
    (concept, dims, fact period, table column) of every extracted cell and is updated.
    The column matters: last year's ending balance is the same fact as this year's opening."""
    found = []
    for e in entries:
        dims = e.get("dims") or ""
        prefix = e.get("prefix", "us-gaap")
        for period in periods:
            for p in instant_options(e, period_options(period, bounds)):
                key = (stem, prefix, e["concept"], dims, p)
                if key in idx and (e["concept"], dims, p, period) not in seen:
                    seen.add((e["concept"], dims, p, period))
                    found.append((e, period, p) + tuple(idx[key]))
                    break
    return found


def negated_concepts(source_file):
    """{(prefix, concept)} the filing presents with a negated label, from its _pre.xml."""
    found = sorted(Path(source_file).parent.glob("*_pre.xml"))
    if not found:
        return set()
    root = ET.fromstring(unwrap(found[0].read_bytes()))
    xl = "{http://www.w3.org/1999/xlink}"
    loc_concept, negated = {}, set()
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] == "loc":
            frag = el.get(xl + "href", "").rsplit("#", 1)[-1]
            prefix, _, local = frag.partition("_")
            loc_concept[el.get(xl + "label")] = (prefix, local)
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] == "presentationArc" and "negated" in (el.get("preferredLabel") or ""):
            target = loc_concept.get(el.get(xl + "to"))
            if target:
                negated.add(target)
    return negated


def resolve(cands, stem, period, pdf_value, idx, bounds):
    """Pick the candidate and period the PDF number agrees with.
    Rank: match > sign > the only candidate with a fact. Several candidate concepts and
    no agreement -> 'ambiguous' (never guess silently)."""
    empty = {"prefix": "", "concept": "", "dims": ""}
    found = []
    for method, c in cands:
        for p in period_options(period, bounds):
            fact = idx.get((stem, c["prefix"], c["concept"], c["dims"], p))
            if fact is not None:
                status = classify(pdf_value, fact[0], tolerance(fact[1]))
                found.append((status, method, c, p, fact[0], fact[1]))
    for wanted in ("match", "sign"):
        for status, method, c, p, val, dec in found:
            if status == wanted:
                return method, c, p, val, dec
    concepts = {(c["prefix"], c["concept"], c["dims"]) for _, c in cands}
    if len(concepts) > 1:
        return "ambiguous", empty, period, None, None
    if found:
        _, method, c, p, val, dec = found[0]
        return method, c, p, val, dec
    if cands:
        return cands[0][0], cands[0][1], period, None, None
    return "none", empty, period, None, None


def compare_main(argv=None):
    ap = argparse.ArgumentParser(description="Compare PDF statement tables with XBRL facts (#39)")
    ap.add_argument("--path", default="traditional", help="extraction path: traditional or docling")
    ap.add_argument("--tables", default="data/tables", help="folder with {stem}_p{NNNN}_t1.csv")
    ap.add_argument("--facts", default="data/xbrl/facts.csv")
    ap.add_argument("--manifest", default="data/rendered/manifest.csv")
    ap.add_argument("--label-map", default="config/label_map.yaml")
    ap.add_argument("--params", default="params.yaml")
    ap.add_argument("--output", default="data/xbrl", help="folder for comparison_{path}.csv")
    a = ap.parse_args(argv)

    cfg = yaml.safe_load(Path(a.params).read_text())["xbrl"]
    pages, cutoff = cfg["statement_pages"], float(cfg["fuzzy_cutoff"])
    facts = pd.read_csv(a.facts)
    idx = fact_index(facts)
    bounds = period_bounds(facts)
    face = facts[facts.n_dims == 0]
    manifest = pd.read_csv(a.manifest).set_index("stem")
    label_map = load_label_map(a.label_map)

    rows = []
    for stem, statements in pages.items():
        source = manifest.loc[stem, "source_file"]
        labels = linkbase_labels(source)
        negated = negated_concepts(source)
        have = set(zip(face[face.stem == stem].prefix, face[face.stem == stem].concept))
        choices = [k for k, v in labels.items() if any(pc in have for pc in v)]
        for statement, page in statements.items():
            table = Path(a.tables) / f"{stem}_p{int(page):04d}_t1.csv"
            if not table.exists():
                print(f"WARNING: no table for {stem} {statement} p{page}: {table}")
                continue
            df = pd.read_csv(table)
            entries = label_map.get(statement, [])
            seen = set()
            for r in df.itertuples(index=False):
                cands = candidates(r.row_label, entries, labels, choices, cutoff)
                method, c, xper, xval, dec = resolve(cands, stem, r.col_label, r.value, idx, bounds)
                tol = tolerance(dec)
                status = "xbrl_missing" if xval is None else classify(r.value, xval, tol)
                cause = NEGATED_CAUSE if status == "sign" and (c["prefix"], c["concept"]) in negated else ""
                rows.append({"path": a.path, "stem": stem, "statement": statement,
                             "page": page, "pdf_label": r.row_label,
                             "period_label": r.col_label, "xbrl_period": xper,
                             "prefix": c["prefix"], "concept": c["concept"], "dims": c["dims"],
                             "mapping": method, "pdf_raw": r.raw, "pdf_value": r.value,
                             "xbrl_value": xval, "decimals": dec, "tolerance": tol,
                             "status": status, "cause": cause})
                seen.add((c["concept"], c["dims"], xper, r.col_label))
            # pdf_missing: a curated line has an XBRL fact for this table's periods, no PDF row
            for e, period, p, xval, dec in missing_cells(entries, df.col_label.unique(), stem,
                                                         idx, bounds, seen):
                rows.append({"path": a.path, "stem": stem, "statement": statement,
                             "page": page, "pdf_label": e["pdf"], "period_label": period,
                             "xbrl_period": p, "prefix": e.get("prefix", "us-gaap"),
                             "concept": e["concept"], "dims": e.get("dims") or "",
                             "mapping": "manual", "pdf_raw": None, "pdf_value": None,
                             "xbrl_value": xval, "decimals": dec, "tolerance": tolerance(dec),
                             "status": "pdf_missing", "cause": ""})

    out = pd.DataFrame(rows, columns=COMPARE_COLUMNS)
    out_dir = Path(a.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"comparison_{a.path}.csv"
    tmp = target.with_suffix(".csv.tmp")
    out.to_csv(tmp, index=False)
    tmp.replace(target)

    rates = (out.assign(is_match=out.status.eq("match"))
                .groupby("statement").is_match.agg(lines="size", matches="sum"))
    rates.loc["ALL"] = [len(out), int(out.status.eq("match").sum())]
    rates = rates.astype(int)
    rates["match_rate"] = (rates.matches / rates.lines).round(4)
    rates.to_csv(out_dir / f"match_rates_{a.path}.csv")
    print(f"wrote {target} ({len(out)} rows)")
    print(out.status.value_counts().to_string())
    print(out.mapping.value_counts().to_string())
    print(out[out.cause != ""].cause.value_counts().to_string())
    print(rates.to_string())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "compare":
        compare_main(sys.argv[2:])
    else:
        main()
