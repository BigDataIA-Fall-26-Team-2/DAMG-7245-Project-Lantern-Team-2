"""Part 9: a lost page must count against the parser, never be skipped.

Reproduces the review finding on #111: two reference pages, export output for
only one. Before the fix the scorer skipped the second page and reported WER 0
and numeric F1 1. Now the lost page is scored as empty and listed as missing.
"""

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REF = "Net sales were 416,161 in fiscal 2025."


def run_evaluate(tmp_path, export_pages):
    gt = tmp_path / "gt"
    exp = tmp_path / "export"
    gt.mkdir()
    exp.mkdir()
    for page in (1, 2):
        (gt / f"DOC_p{page}.gt.txt").write_text(REF, encoding="utf-8")
    with open(exp / "DOC.jsonl", "w", encoding="utf-8") as f:
        for page in export_pages:
            f.write(json.dumps({
                "page": page, "block_id": f"p{page:04d}_b001",
                "block_type": "Text", "bbox": [10, 10, 200, 20],
                "text": REF, "table": None, "ocr": False,
            }) + "\n")
    params = {
        "evaluate": {
            "gt_dir": str(gt), "export_dir": str(exp),
            "xbrl_dir": str(tmp_path / "xbrl"),
            "metrics_out": str(tmp_path / "metrics.json"),
            "plot_out": str(tmp_path / "drift.png"),
            "stems": ["DOC"],
            "strata": {"DOC_p1": "prose", "DOC_p2": "prose"},
        },
        "managed": {"cache_dir": str(tmp_path / "managed")},
    }
    xbrl = tmp_path / "xbrl"
    xbrl.mkdir()
    row = "DOC,income,1,tr,rev,100,100,match,match,0,0\n"
    for path in ("traditional", "docling"):
        (xbrl / f"comparison_{path}.csv").write_text(
            "filing,statement,row,col,tag,xbrl_value,extracted,status,kind,abs_error,pct_error\n" + row,
            encoding="utf-8",
        )
    pfile = tmp_path / "params.yaml"
    pfile.write_text(yaml.safe_dump(params), encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "src" / "evaluate.py"),
                    "--params", str(pfile), "--no-plot"],
                   check=True, capture_output=True, cwd=ROOT)
    return json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))


def test_both_pages_present_scores_perfect(tmp_path):
    m = run_evaluate(tmp_path, export_pages=[1, 2])
    assert m["by_path"]["traditional"]["wer_mean"] == 0.0
    assert not m["missing"].get("traditional")


def test_lost_page_is_scored_and_listed(tmp_path):
    m = run_evaluate(tmp_path, export_pages=[1])
    assert m["missing"]["traditional"] == ["DOC_p2"]
    lost = m["pages"]["DOC_p2"]["traditional"]
    assert lost["wer"] == 1.0 and lost["numeric"]["f1"] == 0.0
    assert lost.get("missing") is True
    # the average now shows the loss instead of hiding it
    assert m["by_path"]["traditional"]["wer_mean"] == 0.5


def test_no_export_at_all_is_unmeasured_not_perfect(tmp_path):
    m = run_evaluate(tmp_path, export_pages=[])
    # an empty export file loads as no pages: nothing scored, both listed
    assert sorted(m["unmeasured"]["traditional"]) == ["DOC_p1", "DOC_p2"]
    assert "traditional" not in m["by_path"]