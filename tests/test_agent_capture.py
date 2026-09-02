"""Faz 3.2: Ekran yakalama testleri."""

from __future__ import annotations

import time
from typing import Optional

from pardus_paylasim_agent.capture import (
    AgentCaptureLoop,
    CaptureBackend,
    MssCaptureBackend,
)


class DummyServer:
    """AgentCaptureLoop için duck-typed mock sunucu."""

    def __init__(self) -> None:
        import threading

        self._frame_lock = threading.Lock()
        self._current_frame: Optional[bytes] = None
        self.capture_backend: Optional[str] = None
        self.capture_error: Optional[str] = "başlangıç hatası"


class DummyBackend:
    """CaptureBackend Protocol mock."""

    name = "dummy"

    def __init__(self) -> None:
        self.closed = False

    def grab_jpeg(self, quality: int = 70) -> Optional[bytes]:
        return b"fake_jpeg_data"

    def close(self) -> None:
        self.closed = True


class TestMssCaptureBackend:
    """mss backend testleri (mocksuz, yalnız protocol ve state)."""

    def test_protocol_uyumu(self) -> None:
        backend = MssCaptureBackend()
        assert isinstance(backend, CaptureBackend)
        assert backend.name == "mss"

    def test_close_idempotent(self) -> None:
        backend = MssCaptureBackend()
        backend.close()
        backend.close()  # Hata fırlatmamalı


class TestAgentCaptureLoop:
    """AgentCaptureLoop entegrasyon testleri."""

    def test_start_stop_yasam_dongusu(self) -> None:
        backend = DummyBackend()
        server = DummyServer()
        loop = AgentCaptureLoop(backend=backend, server=server, fps=10)

        loop.start()
        # Thread'in bir kare yazması için kısa bekleme
        time.sleep(0.2)
        loop.stop()

        # Doğrulamalar
        assert backend.closed is True
        assert server._current_frame == b"fake_jpeg_data"
