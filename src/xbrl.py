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
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path

import pandas as pd

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


if __name__ == "__main__":
    main()
