"""
0.12 — Ekran yakalama birim testleri (headless, GStreamer/soket gerektirmez).

Üç eksen:
  1. `extract_jpeg_frames` — saf JPEG sınır ayrıştırıcı: chunk'a bölünmüş
     kareler, tek chunk'ta çoklu kare, SOI öncesi çöp, yarım kalan (remainder).
  2. Backend seçimi — `shutil.which` (yakalama aracı var/yok) ve `session_type`
     (Wayland/X11/bilinmeyen) monkeypatch'lenerek algılama + deneme sırası.
  3. StreamConfig → GStreamer pipeline-string render: config değerleri (kalite,
     fps, ölçek) pipeline parçalarına doğru yansıyor mu.

`_read_gst_frames`'in eski gömülü ayrıştırma döngüsü saf `extract_jpeg_frames`'e
çıkarıldı; bu testler o davranışı sabitler (regresyon kalkanı).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from pardus_paylasim import platform_info
from pardus_paylasim.screen import stream_server
from pardus_paylasim.screen.stream_config import StreamConfig
from pardus_paylasim.screen.stream_server import (
    ScreenStreamServer,
    extract_jpeg_frames,
)

SOI = b"\xff\xd8"
EOI = b"\xff\xd9"


def _jpeg(payload: bytes = b"body") -> bytes:
    """Sahte ama sınır-geçerli tek JPEG karesi (SOI + gövde + EOI)."""
    return SOI + payload + EOI


class TestExtractJpegFrames(unittest.TestCase):
    """Saf JPEG sınır ayrıştırıcı: chunk birleştirme + remainder davranışı."""

    def test_single_complete_frame(self):
        frame = _jpeg(b"hello")
        frames, remainder = extract_jpeg_frames(frame)
        self.assertEqual(frames, [frame])
        self.assertEqual(remainder, b"")

    def test_multiple_frames_in_one_buffer(self):
        # Tek okumada iki tam kare gelebilir → ikisi de ayıklanmalı.
        f1, f2 = _jpeg(b"one"), _jpeg(b"two")
        frames, remainder = extract_jpeg_frames(f1 + f2)
        self.assertEqual(frames, [f1, f2])
        self.assertEqual(remainder, b"")

    def test_partial_frame_returned_as_remainder(self):
        # EOI henüz gelmemiş → kare yok, tümü remainder (sonraki chunk bekler).
        partial = SOI + b"incomplete-no-eoi-yet"
        frames, remainder = extract_jpeg_frames(partial)
        self.assertEqual(frames, [])
        self.assertEqual(remainder, partial)

    def test_chunk_split_reassembly(self):
        # Bir kare iki chunk'a bölünmüş: ilk chunk yarım → remainder; ikinci
        # chunk remainder'a eklenince tam kare çıkmalı (gerçek akış senaryosu).
        frame = _jpeg(b"split-across-reads")
        mid = len(frame) // 2
        chunk_a, chunk_b = frame[:mid], frame[mid:]

        frames1, remainder1 = extract_jpeg_frames(chunk_a)
        self.assertEqual(frames1, [])
        self.assertEqual(remainder1, chunk_a)

        frames2, remainder2 = extract_jpeg_frames(remainder1 + chunk_b)
        self.assertEqual(frames2, [frame])
        self.assertEqual(remainder2, b"")

    def test_leading_garbage_before_soi_discarded(self):
        # SOI öncesi çöp bayt (senkron kaybı) atılır; kare temiz çıkar.
        frame = _jpeg(b"clean")
        frames, remainder = extract_jpeg_frames(b"\x00\x11garbage" + frame)
        self.assertEqual(frames, [frame])
        self.assertEqual(remainder, b"")

    def test_trailing_partial_after_complete_frame(self):
        # Tam kare + ardından yeni kare başlangıcı: kare ayıklanır, yeni SOI
        # remainder'da tutulur (bir sonraki EOI'yi bekler).
        f1 = _jpeg(b"done")
        tail = SOI + b"next-frame-start"
        frames, remainder = extract_jpeg_frames(f1 + tail)
        self.assertEqual(frames, [f1])
        self.assertEqual(remainder, tail)

    def test_empty_buffer(self):
        frames, remainder = extract_jpeg_frames(b"")
        self.assertEqual(frames, [])
        self.assertEqual(remainder, b"")

    def test_no_soi_at_all(self):
        # Hiç SOI yok → kare yok, tüm tampon remainder.
        frames, remainder = extract_jpeg_frames(b"just random bytes")
        self.assertEqual(frames, [])
        self.assertEqual(remainder, b"just random bytes")


class TestCaptureBackendDetection(unittest.TestCase):
    """`shutil.which` monkeypatch → yakalama aracı algılama bayrakları."""

    def test_gstreamer_detected_when_present(self):
        # Yalnız gst-launch-1.0 varmış gibi → has_gstreamer True, diğer False.
        original_which = stream_server.shutil.which

        def fake_which(cmd):
            return "/usr/bin/gst-launch-1.0" if cmd == "gst-launch-1.0" else None

        stream_server.shutil.which = fake_which
        try:
            server = ScreenStreamServer()
        finally:
            stream_server.shutil.which = original_which

        self.assertTrue(server.has_gstreamer)
        self.assertFalse(server.has_scrot)
        self.assertFalse(server.has_gnome_screenshot)
        self.assertFalse(server.has_import)

    def test_scrot_only_detected(self):
        original_which = stream_server.shutil.which

        def fake_which(cmd):
            return "/usr/bin/scrot" if cmd == "scrot" else None

        stream_server.shutil.which = fake_which
        try:
            server = ScreenStreamServer()
        finally:
            stream_server.shutil.which = original_which

        self.assertFalse(server.has_gstreamer)
        self.assertTrue(server.has_scrot)

    def test_no_capture_tools(self):
        # Hiçbir araç yok → tüm bayraklar False (dürüst yetenek raporu).
        original_which = stream_server.shutil.which
        stream_server.shutil.which = lambda cmd: None
        try:
            server = ScreenStreamServer()
        finally:
            stream_server.shutil.which = original_which

        self.assertFalse(server.has_gstreamer)
        self.assertFalse(server.has_scrot)
        self.assertFalse(server.has_gnome_screenshot)
        self.assertFalse(server.has_import)


class TestBackendOrder(unittest.TestCase):
    """`session_type` → GStreamer backend deneme sırası (oturuma göre)."""

    def _order_for(self, session: str) -> list:
        # stream_server modülü session_type'ı doğrudan import etti → orada patch.
        original = stream_server.session_type
        stream_server.session_type = lambda: session
        try:
            server = ScreenStreamServer()
            return server._gstreamer_backend_order()
        finally:
            stream_server.session_type = original

    def test_wayland_pipewire_only(self):
        # Wayland → yalnız pipewire (ximagesrc Wayland'da kesin çöker).
        self.assertEqual(self._order_for(platform_info.SESSION_WAYLAND), ["pipewire"])

    def test_x11_prefers_ximagesrc(self):
        # X11 → yerel ximagesrc önce, pipewire yedek.
        self.assertEqual(self._order_for(platform_info.SESSION_X11), ["x11", "pipewire"])

    def test_unknown_tries_both(self):
        # Bilinmeyen oturum → en genel (pipewire) önce, sonra x11.
        self.assertEqual(self._order_for("unknown"), ["pipewire", "x11"])


class TestPipelineRender(unittest.TestCase):
    """StreamConfig değerleri GStreamer pipeline string'ine doğru yansır."""

    def test_quality_in_jpegenc(self):
        cfg = StreamConfig(jpeg_quality=42)
        self.assertEqual(cfg.gst_jpegenc(), "jpegenc quality=42")

    def test_framerate_in_caps(self):
        cfg = StreamConfig(framerate=30)
        self.assertEqual(cfg.gst_framerate_caps(), "video/x-raw,framerate=30/1")

    def test_native_resolution_no_scale_fragment(self):
        # width/height verilmezse ölçekleme yok → boş scale parçası.
        cfg = StreamConfig()
        self.assertTrue(cfg.is_native_resolution)
        self.assertEqual(cfg.gst_scale_fragment(), "")

    def test_scaled_resolution_fragment(self):
        cfg = StreamConfig(width=1280, height=720)
        self.assertEqual(
            cfg.gst_scale_fragment(),
            "videoscale ! video/x-raw,width=1280,height=720 ! ",
        )

    def test_pipewire_pipeline_uses_config_values(self):
        # Sunucunun kurduğu pipewire pipeline'ı config parçalarını içermeli.
        cfg = StreamConfig(jpeg_quality=55, framerate=20, width=800, height=600)
        server = ScreenStreamServer(config=cfg)
        captured = {}

        def fake_spawn(backend, pipeline):
            captured["backend"] = backend
            captured["pipeline"] = pipeline
            return True

        server._spawn_gstreamer = fake_spawn
        result = server._try_gstreamer_pipewire()

        self.assertTrue(result)
        self.assertEqual(captured["backend"], "pipewire")
        pipeline = captured["pipeline"]
        self.assertIn("pipewiresrc", pipeline)
        self.assertIn("jpegenc quality=55", pipeline)
        self.assertIn("framerate=20/1", pipeline)
        self.assertIn("width=800,height=600", pipeline)
        self.assertIn("fdsink fd=1", pipeline)

    def test_x11_pipeline_uses_config_values(self):
        cfg = StreamConfig(jpeg_quality=63, framerate=15)
        server = ScreenStreamServer(config=cfg)
        captured = {}

        def fake_spawn(backend, pipeline):
            captured["backend"] = backend
            captured["pipeline"] = pipeline
            return True

        server._spawn_gstreamer = fake_spawn
        result = server._try_gstreamer_x11()

        self.assertTrue(result)
        self.assertEqual(captured["backend"], "x11")
        pipeline = captured["pipeline"]
        self.assertIn("ximagesrc", pipeline)
        self.assertIn("jpegenc quality=63", pipeline)
        self.assertIn("framerate=15/1", pipeline)
        # Native (ölçeksiz) → videoscale parçası olmamalı.
        self.assertNotIn("videoscale", pipeline)
        self.assertIn("fdsink fd=1", pipeline)


if __name__ == "__main__":
    unittest.main()
