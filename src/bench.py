"""Stage: bench (Part 10). Per-page runtime, peak memory and failures for the parsing stages.

Each stage runs in its own subprocess, so peak RSS is not inflated by models another stage loaded.
Writes data/bench/{stage}.csv (one row per page), data/bench/{stage}.meta.json (setup/cold time, device),
data/bench/summary.csv (p50/p95 s/page, peak RSS, failures) and data/bench/machine.json.
"""
import argparse
import csv
import importlib.util
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import psutil
import yaml

SRC = Path(__file__).resolve().parent
FIELDS = ["stage", "stem", "page", "seconds", "rss_mb", "n_out", "status"]


def load_params(path):
    return yaml.safe_load(Path(path).read_text())


def stages_for(params):
    return ["parse_pdfplumber", "tables", "layout"] + [f"parse_docling_{d}" for d in params["bench"]["docling_devices"]]


def page_jobs(input_dir, extra_pdfs, limit=None):
    """[(pdf_path, n_pages)] for every rendered filing plus the extra PDFs (e.g. the scanned fixture)."""
    import pdfplumber
    jobs = []
    for pdf in sorted(Path(input_dir).glob("*.pdf")) + [Path(f) for f in extra_pdfs]:
        with pdfplumber.open(pdf) as p:
            n = len(p.pages)
        jobs.append((str(pdf), min(n, limit) if limit else n))
    return jobs


def load_docling_parse():
    # src/docling_parse.py shares its name with Docling's own package, so load it under another name.
    spec = importlib.util.spec_from_file_location("lantern_docling_parse", SRC / "docling_parse.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_runner(stage, params, params_path):
    """Set up a stage once (cold start) and return open_pdf(pdf_path) -> run(page_no) -> output count."""
    if stage == "parse_pdfplumber":
        import parse_text
        def open_pdf(pdf):
            gen = parse_text.extract_page_text(pdf, params["ocr"])   # yields one page at a time, in order
            return lambda n: len(next(gen)["text"].strip())
        return open_pdf, "cpu"

    if stage == "tables":
        import tables
        def open_pdf(pdf):
            def run(n):
                df, _info = tables.extract_best_df(pdf, n, params_path=params_path)
                return 0 if df is None else len(df)
            return run
        return open_pdf, "cpu"

    if stage == "layout":
        import pdfplumber
        import layout
        model, lp, ocr_dpi = layout.load_model(), params["layout"], params["ocr"]["dpi"]
        def open_pdf(pdf):
            doc = pdfplumber.open(pdf)
            def run(n):   # same work per page as layout.main()
                page = doc.pages[n - 1]
                _img, _kept, recs = layout.detect_page(model, page, lp)
                for r in layout.reading_order(recs, lp["column_gap_pt"]):
                    if r["block_type"] in layout.TEXT_TYPES:
                        layout.block_text(page, r["bbox"], ocr_dpi, lp["text_pad_pt"])
                    if r["block_type"] == "Table":
                        layout.route_table(pdf, page, r["bbox"], lp["pad_pt"], params_path)
                return len(recs)
            return run
        return open_pdf, "cpu"

    if stage.startswith("parse_docling_"):
        device = stage.rsplit("_", 1)[1]
        dp = load_docling_parse()
        conv = dp.make_converter({**params["docling"], "device": device})
        def open_pdf(pdf):
            def run(n):
                doc = conv.convert(pdf, page_range=(n, n)).document
                return sum(1 for _ in doc.iterate_items())
            return run
        return open_pdf, device

    raise ValueError(f"unknown stage {stage}")


def run_stage(stage, params_path, input_dir, out_dir, limit):
    """Child process: run one stage over every page, one CSV row per page."""
    params = load_params(params_path)
    proc = psutil.Process(os.getpid())
    t0 = time.perf_counter()
    open_pdf, device = make_runner(stage, params, params_path)
    setup_s = time.perf_counter() - t0                     # model loading etc. (cold start)
    rows = []
    for pdf, n_pages in page_jobs(input_dir, params["bench"]["extra_pdfs"], limit):
        run = open_pdf(pdf)
        for n in range(1, n_pages + 1):
            t = time.perf_counter()
            try:
                n_out = run(n)
                status = "ok" if n_out else "empty"
            except Exception:
                n_out, status = 0, "error: " + traceback.format_exc(limit=1).strip().splitlines()[-1][:120]
            rows.append({"stage": stage, "stem": Path(pdf).stem, "page": n,
                         "seconds": round(time.perf_counter() - t, 4),
                         "rss_mb": round(proc.memory_info().rss / 2**20, 1), "n_out": n_out, "status": status})
            print(f"{stage} {Path(pdf).stem} p{n}: {rows[-1]['seconds']:.2f}s {status}", flush=True)
    with open(out_dir / f"{stage}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    (out_dir / f"{stage}.meta.json").write_text(json.dumps({"stage": stage, "device": device,
                                                            "setup_s": round(setup_s, 2)}, indent=2))


def machine_info():
    info = {"platform": platform.platform(), "python": platform.python_version(),
            "logical_cpus": psutil.cpu_count(), "ram_gb": round(psutil.virtual_memory().total / 2**30, 1)}
    if sys.platform == "darwin":
        info["cpu"] = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                     capture_output=True, text=True).stdout.strip()
    try:
        import torch
        info["torch"] = torch.__version__
        info["mps_available"] = torch.backends.mps.is_available()
        info["cuda_available"] = torch.cuda.is_available()
    except ImportError:
        pass
    return info


def summarize(out_dir, stages):
    rows = []
    for stage in stages:
        path = out_dir / f"{stage}.csv"
        if not path.exists():
            continue
        recs = list(csv.DictReader(open(path)))
        secs = np.array([float(r["seconds"]) for r in recs])
        meta = json.loads((out_dir / f"{stage}.meta.json").read_text())
        rows.append({"stage": stage, "device": meta["device"], "pages": len(recs),
                     "s_per_page_p50": round(float(np.percentile(secs, 50)), 3),
                     "s_per_page_p95": round(float(np.percentile(secs, 95)), 3),
                     "s_per_page_mean": round(float(secs.mean()), 3),
                     "total_s": round(float(secs.sum()), 1), "setup_s": meta["setup_s"],
                     "peak_rss_mb": max(float(r["rss_mb"]) for r in recs),
                     "errors": sum(r["status"].startswith("error") for r in recs),
                     "empty": sum(r["status"] == "empty" for r in recs)})
    with open(out_dir / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r)


def cost_table(out_dir, params):
    """Cost per 1,000 pages and per year for each option, from measured s/page (summary.csv) and cited prices.

    VM hours = s/page x pages / 3600 / workers. The GPU row uses the Mac GPU (MPS) timing as a stand-in for the
    cloud GPU, and workers_per_vm is an assumption; both are stated in benchmarks.md."""
    b = params["bench"]
    mean = {r["stage"]: float(r["s_per_page_mean"]) for r in csv.DictReader(open(out_dir / "summary.csv"))}
    trad = mean["parse_pdfplumber"] + mean["tables"] + mean["layout"]
    opts = [("traditional (P1+P2+P3)", "laptop M3 Pro", trad, 1, 0.0),
            ("docling", "laptop M3 Pro (MPS)", mean["parse_docling_mps"], 1, 0.0),
            ("traditional (P1+P2+P3)", b["vm_cpu"]["name"], trad, b["workers_per_vm"], b["vm_cpu"]["usd_per_hour"]),
            ("docling", b["vm_cpu"]["name"], mean["parse_docling_cpu"], b["workers_per_vm"], b["vm_cpu"]["usd_per_hour"]),
            ("docling", b["vm_gpu"]["name"] + " (MPS timing as proxy)", mean["parse_docling_mps"], 1,
             b["vm_gpu"]["usd_per_hour"])]
    rows = []
    for path, hw, s, workers, usd_h in opts:
        hours_1k = s * 1000 / 3600 / workers
        rows.append({"option": path, "hardware": hw, "s_per_page": round(s, 3), "workers": workers,
                     "hours_per_1000_pages": round(hours_1k, 3),
                     "usd_per_1000_pages": round(hours_1k * usd_h, 4),
                     "hours_per_year": round(hours_1k * b["pages_per_year"] / 1000, 1),
                     "usd_per_year": round(hours_1k * usd_h * b["pages_per_year"] / 1000, 2)})
    for kind in ("ocr", "tables"):
        usd_page = b["textract_usd_per_page"][kind]
        rows.append({"option": f"textract {kind}", "hardware": "managed API", "s_per_page": "", "workers": "",
                     "hours_per_1000_pages": "", "usd_per_1000_pages": round(usd_page * 1000, 2),
                     "hours_per_year": "", "usd_per_year": round(usd_page * b["pages_per_year"], 2)})
    with open(out_dir / "cost.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r)


def main(params_path, input_dir, output, stages, limit):
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)
    params = load_params(params_path)
    stages = stages or stages_for(params)
    (out_dir / "machine.json").write_text(json.dumps(machine_info(), indent=2))
    for stage in stages:                                   # one fresh process per stage (clean peak RSS)
        cmd = [sys.executable, __file__, "--child", stage, "--params", params_path,
               "--input", input_dir, "--output", output] + (["--limit", str(limit)] if limit else [])
        subprocess.run(cmd, check=True)
    summarize(out_dir, stages)
    cost_table(out_dir, params)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default="params.yaml")
    ap.add_argument("--input", default="data/rendered")
    ap.add_argument("--output", default="data/bench")
    ap.add_argument("--stages", nargs="*", help="subset of stages (default: all)")
    ap.add_argument("--limit", type=int, help="only the first N pages of each PDF (quick test)")
    ap.add_argument("--child", help=argparse.SUPPRESS)
    ap.add_argument("--cost-only", action="store_true", help="recompute cost.csv from summary.csv")
    a = ap.parse_args()
    if a.cost_only:
        cost_table(Path(a.output), load_params(a.params))
    elif a.child:
        run_stage(a.child, a.params, a.input, Path(a.output), a.limit)
    else:
        main(a.params, a.input, a.output, a.stages, a.limit)
