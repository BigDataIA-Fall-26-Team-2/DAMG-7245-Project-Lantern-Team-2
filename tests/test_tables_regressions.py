import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import tables  # noqa: E402


# --- PR #93 review: per-table headers, ambiguous matches, mixed units ---
def test_column_labels_one_period_phrase_applies_to_every_column():
    assert tables.column_labels(["Nine Months Ended", "June 27, June 28,", "2026 2025"], 2) == [
        "9M ended 2026-06-27", "9M ended 2025-06-28"]


def test_to_long_uses_each_tables_own_header_block():
    # 10-Q p14 shape: an instant table, then a nine-month cash-flow table, extracted as one table
    page_text = "\n".join([
        "Intangible Assets, Net", "June 27, September 27,", "2026 2025",
        "Total intangible assets, net 25,417 13,301",
        "Commercial Paper",
        "The following table provides a summary of cash flows (in millions):",
        "Nine Months Ended", "June 27, June 28,", "2026 2025",
        "Total repayments of commercial paper, net $ (5,911) $ (65)"])
    df = pd.DataFrame([["Total intangible assets, net", "25,417", "13,301"],
                       ["Total repayments of commercial paper, net", "$", "(5,911)", "$", "(65)"]])

    rows, skipped = tables.to_long(df, page_text)

    assert skipped == 0
    assert [r[1] for r in rows] == ["2026-06-27", "2025-09-27", "9M ended 2026-06-27", "9M ended 2025-06-28"]


def test_to_long_uses_label_text_when_values_repeat_and_rejects_ambiguous_rows():
    page_text = "Total assets 100 90\nTotal liabilities and equity 100 90"
    labelled = pd.DataFrame([["Total liabilities and equity", "100", "90"]])  # extractor dropped Total assets
    unlabelled = pd.DataFrame([["", "100", "90"]])

    rows, skipped = tables.to_long(labelled, page_text)
    assert skipped == 0 and {r[0] for r in rows} == {"Total liabilities and equity"}

    rows, skipped = tables.to_long(unlabelled, page_text)
    assert rows == [] and skipped == 1  # two lines fit and nothing tells them apart: reject


def _words(line_specs):
    """[(top, [(text, x0), ...]), ...] -> pdfplumber-like word boxes and the matching page text."""
    words, lines = [], []
    for top, items in line_specs:
        lines.append(" ".join(t for t, _ in items))
        words += [{"text": t, "x0": x0, "x1": x0 + 5 * len(t), "top": top, "bottom": top + 8}
                  for t, x0 in items]
    return words, "\n".join(lines)


def test_to_long_scales_each_column_from_its_own_header():
    # 10-Q p28 shape: caption says millions, but shares are in thousands and the price is per share
    caption = "Share repurchases were (in millions, except number of shares, which are reflected in thousands, and per-share amounts):"
    x, caption_items = 20, []
    for t in caption.split():
        caption_items.append((t, x))
        x += 5 * len(t) + 2
    words, page_text = _words([
        (100, caption_items),
        (112, [("Total", 300), ("Number", 330), ("Average", 420), ("Price", 460)]),
        (124, [("of", 300), ("Shares", 315), ("Purchased", 350), ("Paid", 420), ("Per", 445), ("Share", 465)]),
        (136, [("May", 50), ("3,", 70), ("2026", 85), ("to", 110), ("May", 125), ("30,", 145), ("2026:", 165)]),
        (148, [("Open", 50), ("market", 80), ("purchases", 120), ("26,920", 330), ("$", 410), ("297.18", 430)]),
    ])
    df = pd.DataFrame([["Open market purchases", "26,920", "$", "297.18"]])

    rows, _ = tables.to_long(df, page_text, words)

    assert {r[0] for r in rows} == {"May 3, 2026 to May 30, 2026: Open market purchases"}
    assert [(r[2], r[3], r[4]) for r in rows] == [("26,920", 26_920_000.0, 1e3), ("297.18", 297.18, 1.0)]
    rows_without_boxes, _ = tables.to_long(df, page_text)  # old behaviour: one caption scale for all
    assert [r[4] for r in rows_without_boxes] == [1e6, 1e6]


def test_extract_best_df_returns_contract_rows_and_method_info(monkeypatch):
    df = pd.DataFrame([["Net income", "112,010", "93,736"]])
    monkeypatch.setattr(tables, "load_params", lambda path="params.yaml": {"tables": {}})
    monkeypatch.setattr(tables, "choose_table", lambda pdf, page, tp, bbox=None: (
        {"method": "camelot-stream", "df": df}, {"method": "camelot-stream", "score": 0.95}))
    monkeypatch.setattr(tables, "page_text_and_words", lambda pdf, page, bbox=None: (
        "(In millions)\nYears ended September 27, 2025 September 28, 2024\nNet income $ 112,010 $ 93,736", []))

    out, info = tables.extract_best_df("x.pdf", 32, bbox=[0, 0, 612, 792])

    assert list(out.columns) == tables.COLUMNS
    assert out.iloc[0].tolist() == ["Net income", "FY ended 2025-09-27", "112,010", 112_010_000_000.0, 1e6]
    assert info["method"] == "camelot-stream" and info["score"] == 0.95 and info["accepted"]
    assert info["extractor_version"].startswith("camelot-py")


# Real word boxes from the 10-Q page 28 share-repurchase table (top, [(text, x0, x1), ...]):
# column headers are wrapped over six lines, and the caption gives the units only as exceptions.
P28_LINES = [
    (99, [('Share', 6, 30), ('repurchase', 33, 78), ('activity', 81, 109), ('during', 112, 137), ('the', 140, 152), ('three', 155, 176), ('months', 179, 208), ('ended', 211, 236), ('June', 239, 259), ('27,', 262, 274), ('2026,', 277, 300), ('was', 303, 319), ('as', 322, 331), ('follows', 334, 362), ('(in', 365, 375), ('millions,', 378, 410), ('except', 413, 440), ('number', 443, 473), ('of', 476, 484), ('shares,', 487, 516), ('which', 519, 542), ('are', 545, 558), ('reflected', 561, 596), ('in', 599, 606)]),
    (109, [('thousands,', 6, 50), ('and', 53, 68), ('per-share', 70, 109), ('amounts):', 111, 151)]),
    (127, [('Total', 429, 447), ('Number', 449, 479), ('of', 482, 489), ('Approximate', 525, 574), ('Dollar', 576, 598)]),
    (136, [('Shares', 446, 472), ('Value', 546, 567), ('of', 569, 577)]),
    (145, [('Average', 358, 390), ('Purchased', 424, 465), ('as', 467, 476), ('Part', 478, 494), ('Shares', 523, 549), ('That', 552, 568), ('May', 571, 586), ('Yet', 588, 600)]),
    (153, [('Total', 264, 282), ('Number', 284, 315), ('Price', 364, 384), ('of', 439, 446), ('Publicly', 448, 479), ('Be', 535, 545), ('Purchased', 547, 588)]),
    (162, [('of', 271, 278), ('Shares', 281, 307), ('Paid', 358, 375), ('Per', 377, 390), ('Announced', 425, 469), ('Plans', 471, 493), ('Under', 526, 549), ('the', 551, 563), ('Plans', 566, 587), ('or', 589, 597)]),
    (171, [('Periods', 7, 36), ('Purchased', 269, 309), ('Share', 363, 385), ('or', 435, 443), ('Programs', 445, 483), ('Programs', 539, 576), ('(1)', 578, 584)]),
    (184, [('March', 7, 29), ('29,', 31, 43), ('2026', 45, 63), ('to', 65, 71), ('May', 74, 89), ('2,', 91, 98), ('2026:', 100, 120)]),
    (197, [('Open', 25, 45), ('market', 47, 71), ('and', 73, 87), ('privately', 89, 119), ('negotiated', 121, 158), ('purchases', 161, 197), ('—', 315, 323), ('$', 348, 353), ('—', 389, 397), ('—', 485, 493)]),
    (222, [('May', 7, 22), ('3,', 24, 31), ('2026', 33, 51), ('to', 53, 60), ('May', 62, 77), ('30,', 79, 91), ('2026:', 93, 113)]),
    (232, [('(2)', 328, 335), ('(2)', 393, 400), ('(2)', 498, 505)]),
    (235, [('May', 25, 40), ('2026', 42, 60), ('ASRs', 62, 82), ('26,468', 299, 323), ('26,468', 469, 493)]),
    (248, [('Open', 25, 45), ('market', 47, 71), ('and', 73, 87), ('privately', 89, 119), ('negotiated', 121, 158), ('purchases', 161, 197), ('26,920', 299, 323), ('$', 348, 353), ('297.18', 373, 397), ('26,920', 469, 493)]),
    (273, [('May', 7, 22), ('31,', 24, 35), ('2026', 38, 55), ('to', 58, 64), ('June', 67, 84), ('27,', 86, 97), ('2026:', 99, 119)]),
    (286, [('Open', 25, 45), ('market', 47, 71), ('and', 73, 87), ('privately', 89, 119), ('negotiated', 121, 158), ('purchases', 161, 197), ('26,223', 299, 323), ('$', 348, 353), ('296.18', 373, 397), ('26,223', 469, 493)]),
    (301, [('Total', 43, 60), ('79,611', 299, 323), ('$', 519, 523), ('138,004', 572, 601)]),
]


def test_to_long_scales_share_and_price_columns_on_the_real_p28_layout():
    words = [{"text": t, "x0": x0, "x1": x1, "top": top, "bottom": top + 8}
             for top, items in P28_LINES for t, x0, x1 in items]
    page_text = "\n".join(" ".join(t for t, _, _ in items) for _, items in P28_LINES)
    df = pd.DataFrame([  # the Camelot stream table as extracted: no header rows
        ["Open market and privately negotiated purchases", "—", "$", "—", "—"],
        ["May 3, 2026 to May 30, 2026:", "", "", "", ""],
        ["", "(2)", "", "(2)", "(2)"],
        ["May 2026 ASRs", "26,468", "", "", "26,468"],
        ["Open market and privately negotiated purchases", "26,920", "$", "297.18", "26,920"],
        ["May 31, 2026 to June 27, 2026:", "", "", "", ""],
        ["Open market and privately negotiated purchases", "26,223", "$", "296.18", "26,223"],
        ["Total", "79,611", "", "", ""]])

    rows, _ = tables.to_long(df, page_text, words)

    may = [r for r in rows if r[0].startswith("May 3, 2026") and r[2] != "—"]
    assert [(r[2], r[3], r[4]) for r in may] == [
        ("26,920", 26_920_000.0, 1e3), ("297.18", 297.18, 1.0), ("26,920", 26_920_000.0, 1e3)]
    assert all(r[0] for r in rows)  # the "(2) (2) (2)" footnote line is not emitted as a data row
