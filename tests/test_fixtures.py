"""Checks on committed fixture artifacts; no downloads or source corpus needed."""
from pathlib import Path

import pdfplumber
from pypdf import PdfReader

FIXTURES = Path(__file__).parent / "fixtures"


def test_scanned_fixture_has_three_image_only_pages():
    reader = PdfReader(FIXTURES / "scanned.pdf")
    assert len(reader.pages) == 3
    for page in reader.pages:
        assert not (page.extract_text() or "").strip()
        assert len(page.images) == 1
        assert tuple(float(v) for v in page.mediabox[2:]) == (612, 792)


def test_statement_retains_searchable_income_statement():
    reader = PdfReader(FIXTURES / "statement.pdf")
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    assert "CONSOLIDATED STATEMENTS OF OPERATIONS" in text
    assert "112,010" in text


def test_multicolumn_has_text_in_all_four_columns():
    with pdfplumber.open(FIXTURES / "multicolumn.pdf") as pdf:
        assert len(pdf.pages) == 1
        page = pdf.pages[0]
        words = page.extract_words()
        for column in range(4):
            body = [w for w in words if column / 4 <= w['x0'] / page.width < (column + 1) / 4
                    and 0.25 < w['top'] / page.height < 0.7]
            assert len(body) > 40
