"""
0.6 — Ekran yakalama backend seçimi + hata yönetimi testleri.

Kapsam:
- `_gstreamer_backend_order`: oturum tipine göre deneme sırası (Wayland yalnız
  pipewire; X11 x11-önce; bilinmeyen pipewire-önce). Wayland'da doomed ximagesrc
  spawn edilmediği doğrulanır.
- `_drain_stderr`: stderr'i arka planda okur, pipe deadlock önler.
- `_spawn_gstreamer`: kare üretmeyen backend stderr'i `capture_error`'a yazar,
  başarılı yol `capture_backend` set eder.

Gerçek GStreamer/soket açılmaz; `session_type` ve `Popen` monkeypatch'lenir.
"""

import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from pardus_paylasim.screen import stream_server as ss_mod
from pardus_paylasim.screen.stream_server import ScreenStreamServer


def _make_server() -> ScreenStreamServer:
    """Sunucu örneği (config yok → DTO varsayılanları). Sunucu başlatılmaz."""
    return ScreenStreamServer(device_name="Test", port=52399)


class TestBackendOrder(unittest.TestCase):
    """Oturum tipine göre GStreamer backend sırası."""

    def _order_for(self, session_value: str):
        server = _make_server()
        with mock.patch.object(ss_mod, "session_type", return_value=session_value):
            return server._gstreamer_backend_order()

    def test_wayland_only_pipewire(self):
        # Wayland'da ximagesrc kesin çöker → yalnız pipewire denenmeli.
        self.assertEqual(self._order_for(ss_mod.SESSION_WAYLAND), ["pipewire"])

    def test_wayland_never_spawns_x11(self):
        # Regresyon kilidi: Wayland sırasında 'x11' backend'i asla olmamalı.
        self.assertNotIn("x11", self._order_for(ss_mod.SESSION_WAYLAND))

    def test_x11_prefers_ximagesrc_first(self):
        self.assertEqual(self._order_for(ss_mod.SESSION_X11), ["x11", "pipewire"])

    def test_unknown_tries_both_pipewire_first(self):
        self.assertEqual(self._order_for("unknown"), ["pipewire", "x11"])


class TestCaptureLoopSelection(unittest.TestCase):
    """`_frame_capture_loop` seçilen sıraya göre backend dener."""

    def test_wayland_skips_x11_attempt(self):
        # Wayland'da yalnız pipewire denenmeli; x11 yolu hiç çağrılmamalı.
        server = _make_server()
        server.has_gstreamer = True
        with (
            mock.patch.object(ss_mod, "session_type", return_value=ss_mod.SESSION_WAYLAND),
            mock.patch.object(server, "_try_gstreamer_pipewire", return_value=True) as pw,
            mock.patch.object(server, "_try_gstreamer_x11", return_value=True) as x11,
        ):
            server._frame_capture_loop()
        pw.assert_called_once()
        x11.assert_not_called()

    def test_x11_falls_through_to_pipewire(self):
        # X11 denemesi başarısızsa pipewire'a düşülmeli.
        server = _make_server()
        server.has_gstreamer = True
        with (
            mock.patch.object(ss_mod, "session_type", return_value=ss_mod.SESSION_X11),
            mock.patch.object(server, "_try_gstreamer_x11", return_value=False) as x11,
            mock.patch.object(server, "_try_gstreamer_pipewire", return_value=True) as pw,
        ):
            server._frame_capture_loop()
        x11.assert_called_once()
        pw.assert_called_once()

    def test_all_gstreamer_fail_uses_fallback(self):
        server = _make_server()
        server.has_gstreamer = True
        with (
            mock.patch.object(ss_mod, "session_type", return_value="unknown"),
            mock.patch.object(server, "_try_gstreamer_pipewire", return_value=False),
            mock.patch.object(server, "_try_gstreamer_x11", return_value=False),
            mock.patch.object(server, "_fallback_screenshot_loop") as fb,
        ):
            server._frame_capture_loop()
        fb.assert_called_once()


class _FakeStderr:
    """read(n) ile parça parça veri döndüren, sonra b'' veren sahte stderr."""

    def __init__(self, data: bytes):
        self._buf = io.BytesIO(data)

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)


class TestDrainStderr(unittest.TestCase):
    """stderr drenaj thread'i tüm veriyi toplar (pipe deadlock önler)."""

    def test_collects_all_stderr(self):
        payload = b"line1\nline2\nERROR fatal\n"
        proc = mock.Mock()
        proc.stderr = _FakeStderr(payload)
        sink: list = []

        thread = ScreenStreamServer._drain_stderr(proc, sink)
        self.assertIsNotNone(thread)
        thread.join(timeout=2)

        self.assertEqual(b"".join(sink), payload)

    def test_none_stderr_returns_none(self):
        proc = mock.Mock()
        proc.stderr = None
        self.assertIsNone(ScreenStreamServer._drain_stderr(proc, []))


class TestSpawnGstreamer(unittest.TestCase):
    """`_spawn_gstreamer` başarı/başarısızlık yollarını doğrula."""

    def test_failed_backend_records_stderr_in_capture_error(self):
        # Popen açılır ama kare gelmez (_read_gst... False) → stderr'in son
        # satırı capture_error'a düşmeli.
        server = _make_server()
        fake_proc = mock.Mock()
        fake_proc.stderr = _FakeStderr(b"WARNING setup\nERROR: no such element\n")
        with (
            mock.patch.object(ss_mod.subprocess, "Popen", return_value=fake_proc),
            mock.patch.object(server, "_read_gst_frames", return_value=False),
        ):
            ok = server._spawn_gstreamer("pipewire", "fake ! pipeline")

        self.assertFalse(ok)
        self.assertIsNotNone(server.capture_error)
        self.assertIn("pipewire", server.capture_error)
        self.assertIn("no such element", server.capture_error)

    def test_popen_raises_records_error(self):
        server = _make_server()
        with mock.patch.object(ss_mod.subprocess, "Popen", side_effect=OSError("gst yok")):
            ok = server._spawn_gstreamer("x11", "fake ! pipeline")
        self.assertFalse(ok)
        self.assertIsNotNone(server.capture_error)
        self.assertIn("x11", server.capture_error)

    def test_successful_backend_sets_capture_backend(self):
        # _read_gst_frames sahte: ilk kare işlenmiş gibi capture_backend set eder.
        server = _make_server()
        fake_proc = mock.Mock()
        fake_proc.stderr = _FakeStderr(b"")

        def fake_read():
            # Gerçek döngünün ilk-kare davranışını taklit et.
            server.capture_backend = server._pending_backend
            server._pending_backend = None
            server.capture_error = None
            return True

        with (
            mock.patch.object(ss_mod.subprocess, "Popen", return_value=fake_proc),
            mock.patch.object(server, "_read_gst_frames", side_effect=fake_read),
        ):
            ok = server._spawn_gstreamer("pipewire", "fake ! pipeline")

        self.assertTrue(ok)
        self.assertEqual(server.capture_backend, "pipewire")
        self.assertIsNone(server.capture_error)


if __name__ == "__main__":
    unittest.main()
