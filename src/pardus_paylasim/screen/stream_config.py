"""
Ekran akışı yapılandırması (`StreamConfig`).

Çözünürlük/kalite/fps/port artık hardcoded değil — bu değerler `config.py`
(GSettings veya JSON fallback) üzerinden gelir ve GStreamer pipeline'ları ile
kare döngü hızını (`stream_server.py`) besler.

Immutable DTO (frozen): çalışma-zamanı adaptif değişimler yeni kopya üretir
(`with_quality`/`with_framerate`), var olan örneği mutasyona uğratmaz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Optional, Tuple

# Değer sınırları. GSettings şeması zaten kısıtlar; JSON fallback / bozuk veri
# için kod tarafında da güvenle kırpılır (fail-safe, çökme değil).
QUALITY_MIN, QUALITY_MAX = 1, 100
FRAMERATE_MIN, FRAMERATE_MAX = 1, 60
PORT_MIN, PORT_MAX = 1, 65535

DEFAULT_JPEG_QUALITY = 70
DEFAULT_FRAMERATE = 25
DEFAULT_PORT = 52345

# "native"/"auto"/boş → ölçekleme yok (kaynak çözünürlüğü).
_NATIVE_TOKENS = frozenset({"", "native", "auto"})
_RESOLUTION_RE = re.compile(r"^\s*(\d+)\s*[xX]\s*(\d+)\s*$")


def parse_jpeg_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    """JPEG baytlarından `(width, height)` çıkar (SOF marker). Bulunamazsa None.

    Native (ölçeksiz) modda `capture_resolution`/`/info` dürüst olsun diye ilk
    kareden gerçek boyut okunur — hardcoded '1920x1080' yalanı yerine. Saf
    stdlib; Pillow/GStreamer gerektirmez.
    """
    if len(data) < 4 or data[0] != 0xFF or data[1] != 0xD8:
        return None
    i, n = 2, len(data)
    while i + 1 < n:
        # Marker 0xFF ile başlar; dolgu 0xFF baytları atlanır.
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        i += 2
        # Uzunluksuz (standalone) marker'lar: SOI/EOI/RSTn/TEM.
        if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
            continue
        if i + 1 >= n:
            return None
        seg_len = (data[i] << 8) | data[i + 1]
        # SOF0..SOF15 (0xC0-0xCF) hariç DHT(0xC4)/JPG(0xC8)/DAC(0xCC).
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if i + 6 >= n:
                return None
            height = (data[i + 3] << 8) | data[i + 4]
            width = (data[i + 5] << 8) | data[i + 6]
            return (width, height) if width > 0 and height > 0 else None
        i += seg_len
    return None


def _clamp(value: int, low: int, high: int) -> int:
    """Değeri [low, high] aralığına kırp."""
    return max(low, min(high, value))


def _coerce_int(value: object, default: int) -> int:
    """Herhangi bir değeri int'e çevir; olmuyorsa varsayılan (exception atma)."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class StreamConfig:
    """Ekran akışı parametreleri (immutable).

    - `width`/`height`: None → kaynak (native) çözünürlük, ölçekleme yok.
    - `jpeg_quality`: JPEG kodlama kalitesi 1..100.
    - `framerate`: hedef kare hızı 1..60 (fps).
    - `port`: HTTP(S) dinleme portu.
    - `adaptive`: backpressure altında kalite/fps otomatik düşürme (B1 stretch).
    """

    width: Optional[int] = None
    height: Optional[int] = None
    jpeg_quality: int = DEFAULT_JPEG_QUALITY
    framerate: int = DEFAULT_FRAMERATE
    port: int = DEFAULT_PORT
    adaptive: bool = True

    def __post_init__(self) -> None:
        # frozen → normalize etmek için object.__setattr__ ile kırp.
        object.__setattr__(
            self,
            "jpeg_quality",
            _clamp(int(self.jpeg_quality), QUALITY_MIN, QUALITY_MAX),
        )
        object.__setattr__(
            self,
            "framerate",
            _clamp(int(self.framerate), FRAMERATE_MIN, FRAMERATE_MAX),
        )
        object.__setattr__(
            self,
            "port",
            _clamp(int(self.port), PORT_MIN, PORT_MAX),
        )
        # Geçersiz/0/negatif boyut → native (None). Anlamsız ölçek engellenir.
        object.__setattr__(self, "width", self._sanitize_dim(self.width))
        object.__setattr__(self, "height", self._sanitize_dim(self.height))

    @staticmethod
    def _sanitize_dim(value: Optional[int]) -> Optional[int]:
        if value is None:
            return None
        try:
            ivalue = int(value)
        except (TypeError, ValueError):
            return None
        return ivalue if ivalue > 0 else None

    @property
    def is_native_resolution(self) -> bool:
        """Ölçekleme yok mu? (width/height ikisi de yoksa native)."""
        return self.width is None or self.height is None

    @property
    def resolution_label(self) -> str:
        """`/info` ve GSettings için okunur çözünürlük etiketi."""
        if self.is_native_resolution:
            return "native"
        return f"{self.width}x{self.height}"

    @property
    def frame_interval(self) -> float:
        """Kare döngü uyku aralığı (saniye) = 1/framerate."""
        return 1.0 / self.framerate

    def with_quality(self, quality: int) -> "StreamConfig":
        """Yeni kaliteyle kopya (adaptif düşürme için)."""
        return replace(self, jpeg_quality=quality)

    def with_framerate(self, framerate: int) -> "StreamConfig":
        """Yeni fps'le kopya (adaptif düşürme için)."""
        return replace(self, framerate=framerate)

    # --- GStreamer pipeline parçaları (config → pipeline; hardcoded değil) ---

    def gst_scale_fragment(self) -> str:
        """videoscale caps parçası. native → boş (ölçekleme yok)."""
        if self.is_native_resolution:
            return ""
        return f"videoscale ! video/x-raw,width={self.width},height={self.height} ! "

    def gst_framerate_caps(self) -> str:
        """videorate sonrası kare hızı caps'i."""
        return f"video/x-raw,framerate={self.framerate}/1"

    def gst_jpegenc(self) -> str:
        """JPEG kodlayıcı parçası (kalite config'den)."""
        return f"jpegenc quality={self.jpeg_quality}"

    @staticmethod
    def parse_resolution(text: object) -> Tuple[Optional[int], Optional[int]]:
        """`"native"`/`"1920x1080"` → `(w, h)`. Tanınmayan → `(None, None)`."""
        if text is None:
            return (None, None)
        raw = str(text).strip()
        if raw.lower() in _NATIVE_TOKENS:
            return (None, None)
        match = _RESOLUTION_RE.match(raw)
        if not match:
            return (None, None)
        width, height = int(match.group(1)), int(match.group(2))
        if width <= 0 or height <= 0:
            return (None, None)
        return (width, height)

    @classmethod
    def from_app_config(cls, config: object) -> "StreamConfig":
        """`AppConfig` benzeri `get(key, default)` sağlayan nesneden üret.

        Python anahtarları (GSettings kebab-case karşılığı): `resolution` (str),
        `screen_quality` (`screen-quality`), `framerate`, `port`. Eksik/bozuk
        değerler varsayılana düşer.
        """
        get = getattr(config, "get", None)
        if not callable(get):
            return cls()
        width, height = cls.parse_resolution(get("resolution", "native"))
        return cls(
            width=width,
            height=height,
            jpeg_quality=_coerce_int(
                get("screen_quality", DEFAULT_JPEG_QUALITY), DEFAULT_JPEG_QUALITY
            ),
            framerate=_coerce_int(get("framerate", DEFAULT_FRAMERATE), DEFAULT_FRAMERATE),
            port=_coerce_int(get("port", DEFAULT_PORT), DEFAULT_PORT),
        )
