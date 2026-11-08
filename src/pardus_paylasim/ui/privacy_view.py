"""
GTK4 Privacy View: Drag-and-Drop file metadata scanning and anonymization.
"""

from typing import Any

from pardus_paylasim.cleaner.metadata_cleaner import CleaningResult, MetadataCleaner
from pardus_paylasim.cleaner.report_builder import ReportBuilder

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    HAS_GTK = True
except Exception:
    HAS_GTK = False


class PrivacyViewHandler:
    """Core logic controller for Privacy & Metadata Cleaning UI View."""

    def __init__(self):
        self.cleaner = MetadataCleaner()
        self.last_results: list[CleaningResult] = []

    def process_files(self, file_paths: list[str]) -> list[CleaningResult]:
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


class PrivacyViewComponent:
    """GTK4 Gizlilik ve Üstveri Temizleme Sekmesi Bileşeni."""

    def __init__(self, handler: PrivacyViewHandler | None = None):
        self.handler = handler or PrivacyViewHandler()
        self.container: Any = None

    def clean_dropped_paths(self, paths: list[str]) -> tuple[list[CleaningResult], dict[str, int]]:
        """Dosyaları işler ve özet istatistikleri döner (toplam, başarılı, riskli)."""
        results = self.handler.process_files(paths)
        stats = {
            "total": len(results),
            "success": sum(1 for r in results if r.success),
            "with_risk": sum(1 for r in results if bool(r.risks_found) or r.risks_removed_count > 0),
        }
        return results, stats
