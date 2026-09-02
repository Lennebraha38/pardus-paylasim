"""
`StreamConfig` DTO testleri (0.4).

Odak: yapılandırılabilir akış parametreleri artık hardcoded değil. DTO
immutable (frozen) ve fail-safe — bozuk/sınır-dışı değerler exception atmaz,
varsayılana/kırpılmış değere düşer. `from_app_config` GSettings/JSON fallback
`AppConfig` benzeri `get()` arayüzünden değer okur.

Saf stdlib; GTK/GStreamer'a bağımlı değil (headless).
"""

import io
import struct
import unittest

from pardus_paylasim.screen.stream_config import (
    DEFAULT_FRAMERATE,
    DEFAULT_JPEG_QUALITY,
    DEFAULT_PORT,
    StreamConfig,
    parse_jpeg_dimensions,
)


def _make_jpeg(width: int, height: int) -> bytes:
    """Minimal geçerli JPEG üret (SOI + APP0 + SOF0 + EOI) — Pillow'suz.

    parse_jpeg_dimensions'ı gerçek marker düzeninde test etmek için: uzunluklu
    bir segment (APP0) atlanmalı, sonra SOF0'dan boyut okunmalı.
    """
    soi = b"\xff\xd8"
    # APP0 (JFIF): uzunluk 16, atlanması gereken segment.
    app0 = (
        b"\xff\xe0"
        + struct.pack(">H", 16)
        + b"JFIF\x00"
        + b"\x01\x01\x00"
        + struct.pack(">HH", 1, 1)
        + b"\x00\x00"
    )
    # SOF0: len(17), precision 8, height, width, 3 bileşen.
    sof0 = (
        b"\xff\xc0"
        + struct.pack(">H", 17)
        + b"\x08"
        + struct.pack(">HH", height, width)
        + b"\x03"
        + b"\x01\x11\x00" * 3
    )
    eoi = b"\xff\xd9"
    return soi + app0 + sof0 + eoi


class _FakeConfig:
    """`AppConfig.get(key, default)` arayüzünü taklit eder."""

    def __init__(self, values: dict) -> None:
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


class TestDefaults(unittest.TestCase):
    def test_defaults_are_native_70_25_52345(self):
        cfg = StreamConfig()
        self.assertIsNone(cfg.width)
        self.assertIsNone(cfg.height)
        self.assertEqual(cfg.jpeg_quality, DEFAULT_JPEG_QUALITY)
        self.assertEqual(cfg.framerate, DEFAULT_FRAMERATE)
        self.assertEqual(cfg.port, DEFAULT_PORT)
        self.assertTrue(cfg.adaptive)

    def test_native_resolution_when_no_dims(self):
        self.assertTrue(StreamConfig().is_native_resolution)
        self.assertEqual(StreamConfig().resolution_label, "native")

    def test_explicit_resolution_label(self):
        cfg = StreamConfig(width=1280, height=720)
        self.assertFalse(cfg.is_native_resolution)
        self.assertEqual(cfg.resolution_label, "1280x720")

    def test_frame_interval_is_reciprocal_of_framerate(self):
        self.assertAlmostEqual(StreamConfig(framerate=25).frame_interval, 0.04)
        self.assertAlmostEqual(StreamConfig(framerate=50).frame_interval, 0.02)


class TestClamping(unittest.TestCase):
    """Sınır-dışı değerler kırpılır (çökme yok)."""

    def test_quality_clamped_high_and_low(self):
        self.assertEqual(StreamConfig(jpeg_quality=999).jpeg_quality, 100)
        self.assertEqual(StreamConfig(jpeg_quality=0).jpeg_quality, 1)
        self.assertEqual(StreamConfig(jpeg_quality=-5).jpeg_quality, 1)

    def test_framerate_clamped(self):
        self.assertEqual(StreamConfig(framerate=1000).framerate, 60)
        self.assertEqual(StreamConfig(framerate=0).framerate, 1)

    def test_port_clamped(self):
        self.assertEqual(StreamConfig(port=999999).port, 65535)
        self.assertEqual(StreamConfig(port=0).port, 1)

    def test_nonpositive_dims_become_native(self):
        cfg = StreamConfig(width=0, height=-10)
        self.assertIsNone(cfg.width)
        self.assertIsNone(cfg.height)
        self.assertTrue(cfg.is_native_resolution)


class TestImmutability(unittest.TestCase):
    """frozen dataclass → alan atanamaz; with_* yeni kopya döndürür."""

    def test_frozen_no_field_assignment(self):
        cfg = StreamConfig()
        with self.assertRaises(Exception):
            cfg.jpeg_quality = 50  # type: ignore[misc]

    def test_with_quality_returns_new_copy(self):
        base = StreamConfig(jpeg_quality=70)
        lowered = base.with_quality(30)
        self.assertEqual(base.jpeg_quality, 70)  # orijinal değişmedi
        self.assertEqual(lowered.jpeg_quality, 30)
        self.assertIsNot(base, lowered)

    def test_with_framerate_returns_new_copy(self):
        base = StreamConfig(framerate=25)
        lowered = base.with_framerate(10)
        self.assertEqual(base.framerate, 25)
        self.assertEqual(lowered.framerate, 10)

    def test_with_quality_reclamps(self):
        # Adaptif düşürme sınır-dışı istese de kırpılır.
        self.assertEqual(StreamConfig().with_quality(500).jpeg_quality, 100)


class TestParseResolution(unittest.TestCase):
    def test_native_tokens(self):
        for token in ("native", "auto", "", "  ", "NATIVE"):
            self.assertEqual(StreamConfig.parse_resolution(token), (None, None))

    def test_valid_wxh(self):
        self.assertEqual(StreamConfig.parse_resolution("1920x1080"), (1920, 1080))

    def test_whitespace_and_case_x(self):
        self.assertEqual(StreamConfig.parse_resolution(" 1280 X 720 "), (1280, 720))

    def test_garbage_returns_native(self):
        for bad in ("abc", "1920", "x1080", "1920x", "0x0", None, "-1x5"):
            self.assertEqual(StreamConfig.parse_resolution(bad), (None, None))


class TestFromAppConfig(unittest.TestCase):
    def test_reads_all_keys(self):
        cfg = StreamConfig.from_app_config(
            _FakeConfig(
                {
                    "resolution": "1600x900",
                    "screen_quality": 85,
                    "framerate": 30,
                    "port": 40000,
                }
            )
        )
        self.assertEqual(cfg.width, 1600)
        self.assertEqual(cfg.height, 900)
        self.assertEqual(cfg.jpeg_quality, 85)
        self.assertEqual(cfg.framerate, 30)
        self.assertEqual(cfg.port, 40000)

    def test_missing_keys_use_defaults(self):
        cfg = StreamConfig.from_app_config(_FakeConfig({}))
        self.assertTrue(cfg.is_native_resolution)
        self.assertEqual(cfg.jpeg_quality, DEFAULT_JPEG_QUALITY)
        self.assertEqual(cfg.framerate, DEFAULT_FRAMERATE)
        self.assertEqual(cfg.port, DEFAULT_PORT)

    def test_garbage_values_fall_back(self):
        cfg = StreamConfig.from_app_config(
            _FakeConfig(
                {
                    "screen_quality": "abc",
                    "framerate": None,
                    "port": "xyz",
                    "resolution": "bozuk",
                }
            )
        )
        self.assertEqual(cfg.jpeg_quality, DEFAULT_JPEG_QUALITY)
        self.assertEqual(cfg.framerate, DEFAULT_FRAMERATE)
        self.assertEqual(cfg.port, DEFAULT_PORT)
        self.assertTrue(cfg.is_native_resolution)

    def test_object_without_get_returns_defaults(self):
        cfg = StreamConfig.from_app_config(object())
        self.assertEqual(cfg.jpeg_quality, DEFAULT_JPEG_QUALITY)
        self.assertEqual(cfg.port, DEFAULT_PORT)


class TestGstFragments(unittest.TestCase):
    """Pipeline parçaları config'den kurulur (hardcoded 25/1, quality=70 değil)."""

    def test_jpegenc_uses_config_quality(self):
        self.assertEqual(StreamConfig(jpeg_quality=85).gst_jpegenc(), "jpegenc quality=85")

    def test_framerate_caps_uses_config_fps(self):
        self.assertEqual(
            StreamConfig(framerate=30).gst_framerate_caps(),
            "video/x-raw,framerate=30/1",
        )

    def test_scale_fragment_empty_when_native(self):
        self.assertEqual(StreamConfig().gst_scale_fragment(), "")

    def test_scale_fragment_when_explicit_resolution(self):
        cfg = StreamConfig(width=1280, height=720)
        self.assertEqual(
            cfg.gst_scale_fragment(),
            "videoscale ! video/x-raw,width=1280,height=720 ! ",
        )

    def test_clamped_values_flow_into_fragments(self):
        # Sınır-dışı config kırpılır, parça kırpılmış değeri yansıtır.
        cfg = StreamConfig(jpeg_quality=999, framerate=0)
        self.assertEqual(cfg.gst_jpegenc(), "jpegenc quality=100")
        self.assertEqual(cfg.gst_framerate_caps(), "video/x-raw,framerate=1/1")


class TestParseJpegDimensions(unittest.TestCase):
    """İlk kareden gerçek çözünürlük okunur → dürüst /info (native mod)."""

    def test_reads_dimensions_from_valid_jpeg(self):
        self.assertEqual(parse_jpeg_dimensions(_make_jpeg(1920, 1080)), (1920, 1080))

    def test_reads_nonstandard_dimensions(self):
        self.assertEqual(parse_jpeg_dimensions(_make_jpeg(1366, 768)), (1366, 768))

    def test_returns_none_for_non_jpeg(self):
        self.assertIsNone(parse_jpeg_dimensions(b"not a jpeg at all"))

    def test_returns_none_for_empty(self):
        self.assertIsNone(parse_jpeg_dimensions(b""))

    def test_returns_none_for_truncated_before_sof(self):
        # SOI + kısmi APP0, SOF yok → boyut çıkarılamaz.
        self.assertIsNone(parse_jpeg_dimensions(b"\xff\xd8\xff\xe0\x00"))

    def test_skips_length_segments_before_sof(self):
        # Pillow varsa referansla doğrula (opsiyonel, kırılgan değil).
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow yok")
        buf = io.BytesIO()
        Image.new("RGB", (800, 600), (10, 20, 30)).save(buf, format="JPEG")
        self.assertEqual(parse_jpeg_dimensions(buf.getvalue()), (800, 600))


if __name__ == "__main__":
    unittest.main()
