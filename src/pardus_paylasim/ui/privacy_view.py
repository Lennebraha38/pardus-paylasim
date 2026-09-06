"""
GTK4 Privacy View: Drag-and-Drop file metadata scanning and anonymization.
"""

from typing import List

from pardus_paylasim.cleaner.metadata_cleaner import CleaningResult, MetadataCleaner
from pardus_paylasim.cleaner.report_builder import ReportBuilder

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    HAS_GTK = True
except Exception as e:
    HAS_GTK = False


class PrivacyViewHandler:
    """Core logic controller for Privacy & Metadata Cleaning UI View."""

    def __init__(self):
        self.cleaner = MetadataCleaner()
        self.last_results: List[CleaningResult] = []

    def process_files(self, file_paths: List[str]) -> List[CleaningResult]:
        results = []
        for path in file_paths:
            res = self.cleaner.clean_file(path)
            results.append(res)
        self.last_results = results
        return results

    def generate_report_markdown(self) -> str:
        return ReportBuilder.to_markdown(self.last_results)

    def generate_report_json(self) -> str:
        return ReportBuilder.to_json(self.last_results)

    def generate_report_txt(self) -> str:
        return ReportBuilder.to_txt(self.last_results)
