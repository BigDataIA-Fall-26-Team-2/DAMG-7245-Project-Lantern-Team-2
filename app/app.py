"""LANTERN explorer (Streamlit, issues #59 / #68).

Pick a filing and page; see the page image with boxes, the records and tables extracted
from it, the XBRL check for its numbers, and the key metrics.

Run from the repo root:
    streamlit run app/app.py -- --data data --reports reports

Every panel reads pipeline outputs only (no imports from src/). A panel whose input has not
been produced yet says which stage writes it instead of failing.
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import pdfplumber
import streamlit as st

BLOCK_COLOURS = {"Text": (31, 119, 180), "Title": (214, 39, 40), "List": (44, 160, 44),
                 "Table": (255, 127, 14), "Figure": (148, 103, 189), "Footnote": (140, 86, 75)}
RECORD_COLOUR = (0, 150, 136)
CELL_COLOUR = (230, 0, 126)
NO_FILL = (255, 255, 255, 0)


# --------------------------------------------------------------------- inputs
def parse_args():
    ap = argparse.ArgumentParser(description="LANTERN explorer")
    ap.add_argument("--data", default="data", help="pipeline data folder")
    ap.add_argument("--reports", default="reports", help="reports folder (metrics.json)")
    ap.add_argument("--dpi", type=int, default=110, help="page image resolution")
    args, _ = ap.parse_known_args(sys.argv[1:])
    return args


@st.cache_data
def read_csv(path):
    return pd.read_csv(path)


@st.cache_data
def read_jsonl(path):
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


@st.cache_data
def page_count(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)


def load_comparisons(xbrl_dir):
    """{path name: comparison DataFrame} for every data/xbrl/comparison_{path}.csv."""
    return {f.stem.split("_", 1)[1]: read_csv(str(f))
            for f in sorted(Path(xbrl_dir).glob("comparison_*.csv"))}


def missing(what, stage):
    st.info(f"{what} not produced yet: run the `{stage}` stage.")


# ------------------------------------------------------------------- the page
def line_part(label):
    """'Net sales: Total net sales' -> 'Total net sales'."""
    return str(label).rsplit(": ", 1)[-1]


def cell_key(row):
    return f"{row.pdf_label}  |  {row.period_label}  |  {row.status}"


@st.cache_data
def locate_cell(pdf_path, page_no, label, raw):
    """Box of a table value on the page: its text on the same line as its row label."""
    text = str(raw).replace("$", "").strip()
    if not text or text.lower() == "nan":
        return None
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_no - 1]
        values = page.search(text, regex=False)
        labels = page.search(line_part(label), regex=False)
    if not values:
        return None
    if not labels:
        hit = values[0] if len(values) == 1 else None
    else:
        gap, hit = min(((abs(v["top"] - lab["top"]), v) for v in values for lab in labels),
                       key=lambda t: t[0])
        if gap > 6:
            hit = None
    if hit is None:
        return None
    return (hit["x0"] - 2, hit["top"] - 2, hit["x1"] + 2, hit["bottom"] + 2)


@st.cache_data
def page_image(pdf_path, page_no, dpi, boxes):
    """Page picture with boxes drawn; boxes = ((x0, top, x1, bottom), colour, width), PDF points."""
    with pdfplumber.open(pdf_path) as pdf:
        im = pdf.pages[page_no - 1].to_image(resolution=dpi)
        for bbox, colour, width in boxes:
            im.draw_rect(bbox, fill=NO_FILL, stroke=colour, stroke_width=width)
        return im.annotated


# -------------------------------------------------------------------- presets
def net_income_preset(manifest, comparisons):
    """Jump to net income for the latest fiscal year on the 10-K income statement."""
    trad = comparisons.get("traditional")
    if trad is None:
        return
    forms = dict(zip(manifest.stem, manifest.form.astype(str)))
    rows = trad[(trad.statement == "income") & (trad.pdf_label.str.lower() == "net income")
                & trad.period_label.str.startswith("FY")
                & trad.stem.map(lambda s: forms.get(s, "").upper() == "10-K")]
    if rows.empty:
        return
    row = rows.loc[rows.period_label.str[-10:].idxmax()]
    st.session_state["stem"] = row.stem
    st.session_state["page"] = int(row.page)
    st.session_state["path"] = "traditional"
    st.session_state["cell"] = cell_key(row)


# ----------------------------------------------------------------------- app
def main():
    args = parse_args()
    data, reports = Path(args.data), Path(args.reports)
    st.set_page_config(page_title="LANTERN explorer", layout="wide")
    st.title("LANTERN explorer")

    manifest_path = data / "rendered" / "manifest.csv"
    if not manifest_path.exists():
        missing("data/rendered/manifest.csv", "render")
        st.stop()
    manifest = read_csv(str(manifest_path))
    comparisons = load_comparisons(data / "xbrl")
    facts_path = data / "xbrl" / "facts.csv"
    facts = read_csv(str(facts_path)) if facts_path.exists() else None

    with st.sidebar:
        st.header("Filing and page")
        st.button("Net income, end to end", on_click=net_income_preset,
                  args=(manifest, comparisons), disabled="traditional" not in comparisons,
                  help="10-K income statement, net income for the latest fiscal year")
        stem = st.selectbox("Filing", manifest.stem.tolist(), key="stem")
        info = manifest.set_index("stem").loc[stem]
        pdf_path = str(info.pdf_path)
        n_pages = page_count(pdf_path)
        if st.session_state.get("page", 1) > n_pages:
            st.session_state["page"] = n_pages
        page_no = int(st.number_input("Page", min_value=1, max_value=n_pages, step=1, key="page"))
        st.caption(f"{info.form} · period {info.period} · accession {info.accession} · {n_pages} pages")
        show_blocks = st.checkbox("Show layout blocks", value=True)

    boxes, notes = [], []
    left, right = st.columns([3, 2])

    with right:
        tab_xbrl, tab_records, tab_table, tab_text = st.tabs(
            ["XBRL check", "Records", "Table CSV", "Page text"])

        with tab_xbrl:
            if not comparisons:
                missing("XBRL comparison (data/xbrl/comparison_*.csv)", "xbrl")
            else:
                path = st.radio("Extraction path", list(comparisons), horizontal=True, key="path")
                cmp = comparisons[path]
                here = cmp[(cmp.stem == stem) & (cmp.page == page_no)]
                if here.empty:
                    st.caption("No statement table checked on this page. Statement pages: "
                               + ", ".join(f"p{p}" for p in sorted(cmp[cmp.stem == stem].page.unique())))
                else:
                    counts = here.status.value_counts()
                    st.caption(f"{here.statement.iloc[0]} · {len(here)} cells · "
                               + " · ".join(f"{k} {v}" for k, v in counts.items()))
                    options = [cell_key(r) for r in here.itertuples()]
                    if st.session_state.get("cell") not in options:
                        st.session_state["cell"] = options[0]
                    choice = st.selectbox("Cell", options, key="cell")
                    row = here.iloc[options.index(choice)]
                    st.dataframe(pd.DataFrame({
                        "field": ["PDF raw", "PDF value", "XBRL concept", "XBRL value", "XBRL period",
                                  "decimals", "tolerance", "status", "mapping", "cause"],
                        "value": [row.pdf_raw, row.pdf_value, f"{row.prefix}:{row.concept}",
                                  row.xbrl_value, row.xbrl_period, row.decimals, row.tolerance,
                                  row.status, row.mapping, row.get("cause", "")]}).astype(str),
                        hide_index=True, width="stretch")
                    if facts is not None and isinstance(row.concept, str) and row.concept:
                        fact = facts[(facts.stem == stem) & (facts.prefix == row.prefix)
                                     & (facts.concept == row.concept)
                                     & (facts.period_label == row.xbrl_period)]
                        if not pd.isna(row.dims) and str(row.dims):
                            fact = fact[fact.dims.astype(str) == str(row.dims)]
                        else:
                            fact = fact[fact.n_dims == 0]
                        if not fact.empty:
                            f = fact.iloc[0]
                            value = f"{f.value:,.0f}" if abs(f.value) >= 1000 else f"{f.value:g}"
                            st.caption(f"Arelle fact: {f.prefix}:{f.concept} = {value} {f.unit}, "
                                       f"{f.period_type} {f.start if f.period_type == 'duration' else ''}"
                                       f"→{f.end}, decimals {f.decimals}")
                    bbox = locate_cell(pdf_path, page_no, row.pdf_label, row.pdf_raw)
                    if bbox:
                        boxes.append((bbox, CELL_COLOUR, 3))
                        notes.append("Pink box: the selected cell, found by its text on the same "
                                     "line as its row label.")
                    else:
                        notes.append("The selected cell could not be located on the page by text.")
                    with st.expander("All cells on this page"):
                        st.dataframe(here[["pdf_label", "period_label", "pdf_value", "xbrl_value",
                                           "status", "mapping"]], hide_index=True,
                                     width="stretch")

        with tab_records:
            export = data / "export" / f"{stem}.jsonl"
            if not export.exists():
                missing(f"Provenance records ({export})", "export")
            else:
                recs = [r for r in read_jsonl(str(export)) if r.get("page") == page_no]
                if not recs:
                    st.caption("No records on this page.")
                else:
                    ids = [r.get("block_id", str(i)) for i, r in enumerate(recs)]
                    pick = st.selectbox("Record", ids, key="record")
                    rec = recs[ids.index(pick)]
                    if rec.get("bbox"):
                        boxes.append((tuple(rec["bbox"]), RECORD_COLOUR, 3))
                        notes.append("Teal box: the selected record's bbox.")
                    st.json(rec, expanded=False)

        with tab_table:
            tables = sorted((data / "tables").glob(f"{stem}_p{page_no:04d}_t*.csv"))
            if not tables:
                st.caption("No table CSV for this page (data/tables).")
            for t in tables:
                st.caption(t.name)
                st.dataframe(read_csv(str(t)), hide_index=True, width="stretch")

        with tab_text:
            txt = data / "parsed" / f"{stem}_p{page_no:04d}.txt"
            if txt.exists():
                st.text(txt.read_text())
            else:
                missing(f"Page text ({txt})", "parse_pdfplumber")

    with left:
        blocks_path = data / "layout" / f"{stem}.blocks.jsonl"
        if show_blocks:
            if blocks_path.exists():
                for b in read_jsonl(str(blocks_path)):
                    if b.get("page") == page_no and b.get("bbox"):
                        colour = BLOCK_COLOURS.get(b.get("block_type"), (127, 127, 127))
                        boxes.insert(0, (tuple(b["bbox"]), colour, 1))
                notes.insert(0, "Thin boxes: layout blocks, coloured by type.")
            else:
                notes.insert(0, f"Layout blocks not produced yet ({blocks_path}): run the `layout` stage.")
        st.image(page_image(pdf_path, page_no, args.dpi, tuple(boxes)),
                 caption=f"{stem} · page {page_no}", width="stretch")
        for note in notes:
            st.caption(note)

    st.divider()
    st.subheader("Key metrics")
    cols = st.columns(max(len(comparisons), 1) + 1)
    for col, (path, cmp) in zip(cols, comparisons.items()):
        agree = cmp.status.isin(["match", "sign"]).mean()
        col.metric(f"XBRL match rate · {path}", f"{cmp.status.eq('match').mean():.1%}",
                   help="strict: sign counted separately")
        col.caption(f"value agreement (match + sign): {agree:.1%} of {len(cmp)} cells")
        rates = data / "xbrl" / f"match_rates_{path}.csv"
        if rates.exists():
            col.dataframe(read_csv(str(rates)), hide_index=True, width="stretch")
    metrics = reports / "metrics.json"
    with cols[-1]:
        if metrics.exists():
            st.caption("reports/metrics.json")
            st.json(json.loads(metrics.read_text()), expanded=False)
        else:
            missing("reports/metrics.json", "evaluate")


main()
