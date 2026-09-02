"""
GTK4 Clipboard & Sensitive Text Redactor View.
"""

from typing import List

from pardus_paylasim.clipboard.sensitive_masker import SensitiveMasker, SensitiveMatch


class ClipboardViewHandler:
    """Controller for clipboard inspection and sensitive text redactor UI."""

    @staticmethod
    def analyze_text(text: str) -> List[SensitiveMatch]:
        return SensitiveMasker.scan_text(text)

    @staticmethod
    def sanitize_text(text: str) -> str:
        return SensitiveMasker.mask_text(text)
