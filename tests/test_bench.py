"""Regression tests for src/bench.py cost generation (review on #107): partial stage sets must not crash."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import bench  # noqa: E402

PARAMS = {"bench": {"pages_per_year": 1000, "workers_per_vm": 4,
                    "vm_cpu": {"name": "cpu-vm", "usd_per_hour": 1.0},
                    "vm_gpu": {"name": "gpu-vm", "usd_per_hour": 2.0},
                    "textract_usd_per_page": {"ocr": 0.0015, "tables": 0.015}}}


def write_summary(out, stages):
    with open(out / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["stage", "s_per_page_mean"])
        w.writeheader()
        for s in stages:
            w.writerow({"stage": s, "s_per_page_mean": 1.0})


def cost_options(out):
    return [f'{r["option"]} | {r["hardware"]}' for r in csv.DictReader(open(out / "cost.csv"))]


def test_single_stage_run_writes_cost_without_crashing(tmp_path):
    write_summary(tmp_path, ["parse_pdfplumber"])          # Lokesh's repro: --stages parse_pdfplumber
    bench.cost_table(tmp_path, PARAMS)
    assert cost_options(tmp_path) == ["textract ocr | managed API", "textract tables | managed API"]


def test_cpu_only_docling_has_no_gpu_rows(tmp_path):
    write_summary(tmp_path, ["parse_pdfplumber", "tables", "layout", "parse_docling_cpu"])
    bench.cost_table(tmp_path, PARAMS)
    opts = cost_options(tmp_path)
    assert "docling | cpu-vm" in opts
    assert any(o.startswith("traditional") for o in opts)
    assert not any("gpu-vm" in o or "MPS" in o for o in opts)
