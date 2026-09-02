"""
Unit tests for MetadataCleaner & ReportBuilder.
"""

import os
import tempfile
import unittest

from pardus_paylasim.cleaner.metadata_cleaner import MetadataCleaner
from pardus_paylasim.cleaner.report_builder import ReportBuilder


class TestMetadataCleaner(unittest.TestCase):
    def test_scan_and_clean_temp_file(self):
        cleaner = MetadataCleaner()
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp.write(b"GPS Latitude: 39.9207 N, Author: Test User\n")
            tmp_path = tmp.name

        try:
            res = cleaner.clean_file(tmp_path)
            self.assertTrue(res.success)
            if os.path.exists(res.cleaned_path):
                os.remove(res.cleaned_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_report_builder_json_md(self):
        cleaner = MetadataCleaner()
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(b"PK\x03\x04")
            tmp_path = tmp.name

        try:
            res = cleaner.clean_file(tmp_path)
            json_rep = ReportBuilder.to_json([res])
            self.assertIn("Pardus Güvenli Paylaşım", json_rep)
            md_rep = ReportBuilder.to_markdown([res])
            self.assertIn("# 🛡️ Pardus Güvenli Paylaşım", md_rep)
            if os.path.exists(res.cleaned_path):
                os.remove(res.cleaned_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
