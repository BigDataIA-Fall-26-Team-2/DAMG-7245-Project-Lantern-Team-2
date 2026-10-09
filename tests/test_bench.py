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


def test_unavailable_device_archives_evidence_and_skips_subprocess(tmp_path, monkeypatch):
    """PR #128: preserve report evidence while excluding unavailable hardware."""
    import json
    previous = {
        "machine.json": json.dumps({"platform": "macOS", "mps_available": True}),
        "summary.csv": "stage,s_per_page_mean\nparse_docling_mps,1.092\n",
        "cost.csv": "option,hardware\ndocling,Mac\n",
        "parse_docling_mps.csv": "stage,seconds\nparse_docling_mps,1.092\n",
        "parse_docling_mps.meta.json": '{"device": "mps", "setup_s": 2.33}',
    }
    for name, content in previous.items():
        (tmp_path / name).write_text(content)
    monkeypatch.setattr(bench, "load_params", lambda _: PARAMS)
    monkeypatch.setattr(bench, "machine_info", lambda: {"mps_available": False, "cuda_available": False})

    def forbidden(*args, **kwargs):
        raise AssertionError("unavailable device launched a subprocess")

    monkeypatch.setattr(bench.subprocess, "run", forbidden)
    bench.main("unused", "unused", str(tmp_path), ["parse_docling_mps"], None)
    archives = list((tmp_path / "history").iterdir())
    assert len(archives) == 1
    for name, content in previous.items():
        assert (archives[0] / name).read_text() == content
    assert not (tmp_path / "parse_docling_mps.csv").exists()
    assert list(csv.DictReader((tmp_path / "summary.csv").open())) == []
    assert "parse_docling_mps" in json.loads((tmp_path / "skipped.json").read_text())
    assert cost_options(tmp_path) == ["textract ocr | managed API", "textract tables | managed API"]


def test_error_and_zero_page_measurements_are_excluded_from_cost(tmp_path):
    """PR #128: failure latency must never become a throughput estimate."""
    with (tmp_path / "summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["stage", "pages", "errors", "s_per_page_mean"])
        w.writeheader()
        w.writerows([
            {"stage": "parse_docling_mps", "pages": 94, "errors": 94, "s_per_page_mean": .079},
            {"stage": "parse_docling_cpu", "pages": 94, "errors": 0, "s_per_page_mean": 6.536},
            {"stage": "layout", "pages": 0, "errors": 0, "s_per_page_mean": 0},
        ])
    bench.cost_table(tmp_path, PARAMS)
    opts = cost_options(tmp_path)
    assert "docling | cpu-vm" in opts
    assert not any("MPS" in option or "gpu-vm" in option or "traditional" in option for option in opts)
