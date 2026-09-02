"""
Ekran yakalama backend'i: mss.grab() → JPEG bytes.

CaptureBackend Protocol + MssCaptureBackend. ScreenStreamServer'ın
_current_frame / _frame_lock seam'ine doğrudan yazar.

ECC: Protocol duck typing, frozen-safe, tip anotasyonları, <50 satır funcs,
kapsamlı hata yönetimi, adlandırılmış sabitler.
"""

from __future__ import annotations

import io
import logging
import threading
import time
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Adlandırılmış sabitler (ECC: sihirli sayı yok)
_DEFAULT_QUALITY = 70
_DEFAULT_FPS = 25
_DEFAULT_MONITOR = 1  # mss kuralı: 0 = tüm monitörler, 1 = birincil


@runtime_checkable
class CaptureBackend(Protocol):
    """Ekran yakalama sözleşmesi (ECC: Protocol duck typing)."""

    name: str

    def grab_jpeg(self, quality: int = _DEFAULT_QUALITY) -> Optional[bytes]:
        """Tek kare yakala → JPEG bytes. Hata → None."""
        ...

    def close(self) -> None:
        """Kaynakları serbest bırak."""
        ...


class MssCaptureBackend:
    """mss + Pillow ekran yakalama backend'i (Windows/Linux/macOS).

    ECC: tembel import (mss/PIL yalnız grab_jpeg'de), kapsamlı hata
    yönetimi (yakalama hatası → None, çökmez).
    """

    name: str = "mss"

    def __init__(self, monitor: int = _DEFAULT_MONITOR) -> None:
        self._monitor = monitor
        self._sct = None  # Tembel mss.mss() örneği

    def _ensure_sct(self) -> None:
        """Tembel mss başlatma."""
        if self._sct is None:
            import mss

            self._sct = mss.mss()

    def grab_jpeg(self, quality: int = _DEFAULT_QUALITY) -> Optional[bytes]:
        """Ekran yakala → JPEG bytes. Hata → None (dürüst, çökmez).

        ECC: kapsamlı hata yönetimi, başarısızlıkta erken dönüş.
        """
        try:
            self._ensure_sct()
            from PIL import Image

            shot = self._sct.grab(self._sct.monitors[self._monitor])
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            return buf.getvalue()
        except Exception as exc:
            logger.debug("mss yakalama hatası: %s", exc)
            return None

    def close(self) -> None:
        """mss kaynağını serbest bırak."""
        if self._sct is not None:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None


class AgentCaptureLoop:
    """Agent yakalama döngüsü: mss backend → server._current_frame slot'u.

    ScreenStreamServer'ın _frame_capture_loop'u GStreamer/scrot kullanır;
    bu döngü agent'ın mss backend'ini kullanarak aynı slot'a yazar →
    mevcut HTTP handler kare servis eder.

    ECC: tip anotasyonları, adlandırılmış sabitler, kapsamlı hata yönetimi.
    """

    def __init__(
        self,
        backend: CaptureBackend,
        server: object,  # ScreenStreamServer (duck-typed: _frame_lock, _current_frame)
        fps: int = _DEFAULT_FPS,
        quality: int = _DEFAULT_QUALITY,
    ) -> None:
        self._backend = backend
        self._server = server
        self._fps = fps
        self._quality = quality
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Yakalama thread'ini başlat."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="agent-capture",
        )
        self._thread.start()

    def _loop(self) -> None:
        """Kare yakalama döngüsü. ECC: <50 satır, adlandırılmış sabitler."""
        interval = 1.0 / self._fps
        while not self._stop_event.is_set():
            frame = self._backend.grab_jpeg(self._quality)
            if frame is not None:
                with self._server._frame_lock:
                    self._server._current_frame = frame
            time.sleep(interval)

    def stop(self) -> None:
        """Yakalama thread'ini durdur ve backend'i kapat."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None
        self._backend.close()
