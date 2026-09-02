"""
Saf yetenek/bağımlılık tespiti (GTK-free, Windows-safe).

Her opsiyonel bağımlılığı (mss, pynput, zeroconf, cryptography, PIL)
try-import ile probelar. Sonuç frozen AgentCapabilities dataclass'ı.
Yan etkisiz: modül yükler ama başlatmaz.

ECC uyumu:
  - @dataclass(frozen=True) → değiştirilemezlik (KRİTİK)
  - Tüm imzalarda tip anotasyonları
  - Genişletilebilirlik için Protocol deseni
  - KISS: tek sorumluluk, spekülatif soyutlama yok
  - Fonksiyonlar <50 satır
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from typing import Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentCapabilities:
    """Tespit edilen runtime yetenekleri (değiştirilemez DTO).

    ECC: frozen=True (değiştirilemezlik KRİTİK). Boolean is_ / has_ / can_
    önek kuralı (ECC adlandırma). Property'ler bileşik, asla mutasyon yok.
    """

    has_mss: bool  # Ekran yakalama (mss.grab → JPEG)
    has_pynput: bool  # Girdi enjeksiyonu (fare/klavye)
    has_pillow: bool  # JPEG kodlama (PIL.Image)
    has_zeroconf: bool  # mDNS keşif
    has_cryptography: bool  # TLS öz-imzalı sertifika
    has_gstreamer: bool  # GStreamer CLI (yalnız Linux, Windows'ta False)

    @property
    def can_capture(self) -> bool:
        """Ekran yakalama + JPEG kodlama mümkün mü?"""
        return self.has_mss and self.has_pillow

    @property
    def can_inject(self) -> bool:
        """Girdi enjeksiyonu mümkün mü?"""
        return self.has_pynput

    @property
    def can_serve(self) -> bool:
        """Host olarak çalışabilir mi (yakalama + enjeksiyon)?"""
        return self.can_capture and self.can_inject

    @property
    def can_discover(self) -> bool:
        """mDNS keşif mümkün mü?"""
        return self.has_zeroconf

    @property
    def can_tls(self) -> bool:
        """TLS sertifika üretimi mümkün mü?"""
        return self.has_cryptography

    def summary(self) -> str:
        """İnsan okunur yetenek özeti."""
        items: Tuple[str, ...] = tuple(
            label
            for flag, label in (
                (self.can_capture, "capture(mss+PIL)"),
                (self.can_inject, "inject(pynput)"),
                (self.can_discover, "mdns(zeroconf)"),
                (self.can_tls, "tls(cryptography)"),
            )
            if flag
        )
        return ", ".join(items) if items else "no_capabilities"


def _probe_import(module_name: str) -> bool:
    """Modülü import edebiliyor muyuz? Yan etkisiz probe.

    ECC: kapsamlı hata yönetimi — ImportError yakalanır,
    beklenmedik hata loglanır (sessiz yutulmaz).
    """
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False
    except Exception:  # pragma: no cover — beklenmedik (C uzantısı çökse)
        logger.debug("Beklenmedik hata probing %s", module_name, exc_info=True)
        return False


def detect_agent_capabilities() -> AgentCapabilities:
    """Runtime yeteneklerini tespit et. Yan etkisiz, headless-safe."""
    return AgentCapabilities(
        has_mss=_probe_import("mss"),
        has_pynput=_probe_import("pynput"),
        has_pillow=_probe_import("PIL"),
        has_zeroconf=_probe_import("zeroconf"),
        has_cryptography=_probe_import("cryptography"),
        has_gstreamer=shutil.which("gst-launch-1.0") is not None,
    )
