"""Offline regression checks for pinned corpus selection and reruns."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import download
import render


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.raw = self.root / "raw"
        self.params = self.root / "params.yaml"
        self.config = yaml.safe_load((Path(__file__).resolve().parents[1] / "params.yaml").read_text())
        self.params.write_text(yaml.safe_dump(self.config))
        self.calls = []

    def fetch(self, form, ticker, **kwargs):
        self.calls.append((form, kwargs))
        pinned = self.config["download"]["filings"][form]
        folder = self.raw / "sec-edgar-filings" / ticker / form / pinned["accession"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "primary-document.html").write_text("<html>fixture</html>")
        (folder / "full-submission.txt").write_text(
            f'ACCESSION NUMBER: {pinned["accession"]}\n'
            f'CONFORMED PERIOD OF REPORT: {pinned["period"]}\n'
            'FILED AS OF DATE: 20260731\n\tCENTRAL INDEX KEY: 320193\n'
            '<DOCUMENT>\n<FILENAME>filing.htm\n<TEXT><html>fixture</html></TEXT>\n</DOCUMENT>\n'
            '<DOCUMENT>\n<FILENAME>filing.xsd\n<TEXT><schema/></TEXT>\n</DOCUMENT>\n'
        )
        return 1

    def run_download(self):
        with patch.object(download, "Downloader") as cls:
            cls.return_value.get.side_effect = self.fetch
            download.main(str(self.params), str(self.raw))

    def test_exact_pair_and_rerun_after_submission_cleanup(self):
        self.run_download()
        self.run_download()
        folders = list(self.raw.glob("sec-edgar-filings/*/*/*/"))
        self.assertEqual(len(folders), 2)
        self.assertEqual(len(self.calls), 4)
        self.assertTrue(all(kwargs["limit"] == 1 for _, kwargs in self.calls))
        for folder in folders:
            meta = json.loads((folder / "unpacked/meta.json").read_text())
            self.assertEqual(meta["cik"], "0000320193")
            self.assertTrue((folder / "unpacked" / meta["source_file"]).exists())
            self.assertFalse((folder / "full-submission.txt").exists())

    def test_stale_corpus_rejected_before_network(self):
        (self.raw / "sec-edgar-filings/AAPL/10-K/unexpected").mkdir(parents=True)
        with patch.object(download, "Downloader") as cls:
            with self.assertRaisesRegex(ValueError, "outside params.yaml"):
                download.main(str(self.params), str(self.raw))
            cls.assert_not_called()

    def test_render_rejects_unexpected_input_before_browser(self):
        (self.raw / "sec-edgar-filings/AAPL/10-K/unexpected").mkdir(parents=True)
        with patch.object(render, "sync_playwright") as browser:
            with self.assertRaisesRegex(ValueError, "input does not match"):
                render.main(str(self.params), str(self.raw), str(self.root / "rendered"))
            browser.assert_not_called()

    def test_render_rejects_stale_pdf_before_overwriting_manifest(self):
        self.run_download()
        output = self.root / "rendered"
        output.mkdir()
        (output / "old.pdf").write_bytes(b"stale")
        (output / "manifest.csv").write_text("previous manifest")
        with patch.object(render, "sync_playwright") as browser:
            with self.assertRaisesRegex(ValueError, "stale PDFs"):
                render.main(str(self.params), str(self.raw), str(output))
            browser.assert_not_called()
        self.assertEqual((output / "manifest.csv").read_text(), "previous manifest")

    def test_wrong_period_rejected_without_deleting_submission(self):
        original = self.fetch
        def wrong_period(form, ticker, **kwargs):
            count = original(form, ticker, **kwargs)
            pinned = self.config["download"]["filings"][form]
            p = self.raw / "sec-edgar-filings" / ticker / form / pinned["accession"] / "full-submission.txt"
            p.write_text(p.read_text().replace(pinned["period"], "20200101"))
            return count
        self.fetch = wrong_period
        with self.assertRaisesRegex(ValueError, "does not match pinned"):
            self.run_download()
        self.assertTrue(list(self.raw.rglob("full-submission.txt")))

    def test_wrong_accession_rejected(self):
        original = self.fetch
        def wrong_accession(form, ticker, **kwargs):
            count = original(form, ticker, **kwargs)
            pinned = self.config["download"]["filings"][form]
            folder = self.raw / "sec-edgar-filings" / ticker / form / pinned["accession"]
            folder.rename(folder.with_name("unexpected"))
            return count
        self.fetch = wrong_accession
        with self.assertRaisesRegex(ValueError, "accessions do not match"):
            self.run_download()


if __name__ == "__main__":
    unittest.main()
