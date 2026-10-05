"""Build small offline CI fixtures from pinned source PDF pages."""
import argparse
import hashlib
import subprocess
import tempfile
from pathlib import Path

import img2pdf
import yaml
from pypdf import PdfReader, PdfWriter


def extract_page(source, number, output):
    reader = PdfReader(source)
    writer = PdfWriter()
    writer.add_page(reader.pages[number - 1])
    writer.write(output)


def main(params_path, input_dir, external_pdf, output_dir):
    params = yaml.safe_load(Path(params_path).read_text())["fixtures"]
    apple = Path(input_dir) / params["apple_pdf"]
    external = Path(external_pdf)
    for path, expected in [(apple, params["apple_sha256"]),
                           (external, params["multicolumn_sha256"])]:
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"source hash mismatch: {path}; review page selections before updating pins")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(apple)
    with tempfile.TemporaryDirectory(prefix="lantern-fixtures-") as tmp:
        images = []
        for number in params["scanned_pages"]:
            prefix = str(Path(tmp) / f"page-{number}")
            subprocess.run(["pdftoppm", "-f", str(number), "-l", str(number),
                            "-r", str(params["dpi"]), "-gray", "-png", "-singlefile",
                            str(apple), prefix], check=True)
            images.append(prefix + ".png")
        sizes = {(float(reader.pages[n - 1].mediabox.width),
                  float(reader.pages[n - 1].mediabox.height)) for n in params["scanned_pages"]}
        if len(sizes) != 1:
            raise ValueError("scanned source pages must share a page size")
        layout = img2pdf.get_layout_fun(pagesize=sizes.pop())
        (output / "scanned.pdf").write_bytes(img2pdf.convert(images, layout_fun=layout, nodate=True, engine=img2pdf.Engine.internal))
    extract_page(apple, params["statement_page"], output / "statement.pdf")
    extract_page(external, params["multicolumn_page"], output / "multicolumn.pdf")
    for name in ["scanned.pdf", "statement.pdf", "multicolumn.pdf"]:
        path = output / name
        print(f"{name}: {len(PdfReader(path).pages)} pages, {path.stat().st_size} bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--params", default="params.yaml")
    parser.add_argument("--input", default="data/rendered")
    parser.add_argument("--external", required=True, help="local SEC-filed Amdocs annual report PDF")
    parser.add_argument("--output", default="tests/fixtures")
    args = parser.parse_args()
    main(args.params, args.input, args.external, args.output)
