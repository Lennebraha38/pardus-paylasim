"""PanoAdaptörü Protocol + Win32/No-op uygulamaları.

ECC: Protocol duck typing, tip anotasyonları, kapsamlı hata yönetimi,
KISS (Win32 için ctypes — harici bağımlılık yok).
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class ClipboardAdapter(Protocol):
    """Pano erişim sözleşmesi."""

    def get_text(self) -> Optional[str]: ...

    def set_text(self, text: str) -> None: ...


class Win32ClipboardAdapter:
    """Windows panosu ctypes ile (harici bağımlılık yok).

    ECC: kapsamlı hata yönetimi, erken dönüşler.
    """

    def get_text(self) -> Optional[str]:
        """Panodan metin oku. Hata → None."""
        try:
            import ctypes

            CF_UNICODETEXT = 13
            u32 = ctypes.windll.user32  # type: ignore[attr-defined]
            k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            if not u32.OpenClipboard(0):
                return None
            try:
                handle = u32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return None
                ptr = k32.GlobalLock(handle)
                if not ptr:
                    return None
                try:
                    return ctypes.wstring_at(ptr)
                finally:
                    k32.GlobalUnlock(handle)
            finally:
                u32.CloseClipboard()
        except Exception as exc:
            logger.debug("Win32 pano okuma hatası: %s", exc)
            return None

    def set_text(self, text: str) -> None:
        """Panoya metin yaz. Hata → sessiz log."""
        try:
            import ctypes

            CF_UNICODETEXT = 13
            GMEM_MOVEABLE = 0x0002
            u32 = ctypes.windll.user32  # type: ignore[attr-defined]
            k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            if not u32.OpenClipboard(0):
                return
            try:
                u32.EmptyClipboard()
                data = text.encode("utf-16-le") + b"\x00\x00"
                h = k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
                ptr = k32.GlobalLock(h)
                ctypes.memmove(ptr, data, len(data))
                k32.GlobalUnlock(h)
                u32.SetClipboardData(CF_UNICODETEXT, h)
            finally:
                u32.CloseClipboard()
        except Exception as exc:
            logger.debug("Win32 pano yazma hatası: %s", exc)


class NoOpClipboardAdapter:
    """No-op fallback (Windows dışı veya ctypes sorunlu)."""

    def get_text(self) -> Optional[str]:
        return None

    def set_text(self, text: str) -> None:
        pass


def create_clipboard_adapter() -> ClipboardAdapter:
    """Platform-uygun pano adaptörü döndür."""
    if os.name == "nt":
        return Win32ClipboardAdapter()
    return NoOpClipboardAdapter()
