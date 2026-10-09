"""Part 9: metric edge cases from review on #111."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import evaluate  # noqa: E402


def test_repeated_numbers_are_each_counted():
    """Reference prints 100 three times, hypothesis once: two are missing."""
    n = evaluate.text_metrics("100 100 100", "100")["numeric"]
    assert n["precision"] == 1.0
    assert n["recall"] == round(1 / 3, 4)
    assert n["f1"] == 0.5


def test_extra_repeats_lower_precision():
    n = evaluate.text_metrics("100", "100 100")["numeric"]
    assert n["recall"] == 1.0 and n["precision"] == 0.5


def test_html_entities_are_decoded_before_scoring():
    m = evaluate.text_metrics("Research & Development",
                              "Research &amp; Development")
    assert m["wer"] == 0.0 and m["cer"] == 0.0


def test_html_entities_are_decoded_before_numeric_tokens():
    assert evaluate.numeric_tokens("&#36;1,234") == evaluate.numeric_tokens("$1,234")