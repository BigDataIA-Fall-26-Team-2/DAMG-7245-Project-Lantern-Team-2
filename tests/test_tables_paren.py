"""Guna's Part 9 finding 7: a ')' cut off past the right edge of the last column."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tables import close_paren, normalize  # noqa: E402

PAGE = "Retained earnings/(Accumulated deficit) 11,326 (14,264)\nAccumulated other comprehensive loss (4,508) (5,571)"


def test_cut_bracket_is_restored_when_the_page_prints_it():
    assert close_paren("(14,264", PAGE) == "(14,264)"
    assert close_paren("(5,571", PAGE) == "(5,571)"


def test_value_is_the_same_before_and_after():
    assert normalize("(14,264", 1e6) == normalize(close_paren("(14,264", PAGE), 1e6) == -14264000000


def test_nothing_is_invented_when_the_page_does_not_print_it():
    assert close_paren("(9,999", PAGE) == "(9,999"


def test_ordinary_cells_are_unchanged():
    for raw in ("11,326", "(4,508)", "-", "$ 39,544"):
        assert close_paren(raw, PAGE) == raw
