"""
GTK4 Clipboard & Sensitive Text Redactor View.
"""

from collections import deque
from dataclasses import dataclass
from typing import Any

from pardus_paylasim.clipboard.sensitive_masker import SensitiveMasker, SensitiveMatch


@dataclass(frozen=True)
class ClipboardHistoryItem:
    text: str
    direction: str  # "in" veya "out"
    timestamp: float
    matches_count: int


class ClipboardHistoryManager:
    """Bellek-içi FIFO pano geçmişi ve duyarlı veri istatistik yöneticisi."""

    def __init__(self, maxlen: int = 20):
        self.history: deque[ClipboardHistoryItem] = deque(maxlen=maxlen)

    def record(self, text: str, direction: str, timestamp: float) -> ClipboardHistoryItem:
        matches = SensitiveMasker.scan_text(text)
        item = ClipboardHistoryItem(
            text=text,
            direction=direction,
            timestamp=timestamp,
            matches_count=len(matches),
        )
        self.history.appendleft(item)
        return item

    def clear(self) -> None:
        self.history.clear()

    def get_items(self) -> list[ClipboardHistoryItem]:
        return list(self.history)


class ClipboardViewHandler:
    """Controller for clipboard inspection and sensitive text redactor UI."""

    def __init__(self, max_history: int = 20):
        self.history_mgr = ClipboardHistoryManager(maxlen=max_history)

    @staticmethod
    def analyze_text(text: str) -> list[SensitiveMatch]:
        return SensitiveMasker.scan_text(text)

    @staticmethod
    def sanitize_text(text: str) -> str:
        return SensitiveMasker.mask_text(text)

    def record_history(self, text: str, direction: str, timestamp: float) -> ClipboardHistoryItem:
        return self.history_mgr.record(text, direction, timestamp)

    def clear_history(self) -> None:
        self.history_mgr.clear()

    def get_history(self) -> list[ClipboardHistoryItem]:
        return self.history_mgr.get_items()


class ClipboardViewComponent:
    """GTK4 / Libadwaita Pano Görünüm Bileşeni."""

    def __init__(self, handler: ClipboardViewHandler | None = None):
        self.handler = handler or ClipboardViewHandler()
        self.container: Any = None

    def redact_and_record(self, raw_text: str, direction: str, timestamp: float) -> tuple[str, int]:
        """Metni maskeler, geçmişe ekler ve maskelenen öge sayısını döner."""
        matches = self.handler.analyze_text(raw_text)
        masked = self.handler.sanitize_text(raw_text)
        self.handler.record_history(raw_text, direction, timestamp)
        return masked, len(matches)
