"""
Merkezi logging yapılandırması.

Tüm modüller ``logging.getLogger(__name__)`` ile logger alır; bu modül tek
noktadan handler/format/seviye kurar. Seviye ``PARDUS_LOG_LEVEL`` ortam
değişkeni ile ayarlanır (varsayılan INFO) — kod içinde sabit seviye yok.

Kullanıcıya gösterilen CLI stdout çıktısı (rapor metni, maskeleme sonucu,
kullanım bilgisi) logger'a taşınmaz; ``print`` olarak kalır. Logger yalnızca
hata/durum/teşhis mesajları için kullanılır ve ``stderr``'e yazar.
"""

import logging
import os
import sys

_DEFAULT_LEVEL = "INFO"
_LOG_FORMAT = "[%(name)s] %(levelname)s: %(message)s"

_configured = False


def _resolve_level(level: str | int | None) -> int:
    """Verilen seviyeyi ya da ``PARDUS_LOG_LEVEL`` ortam değerini çöz."""
    if level is None:
        level = os.environ.get("PARDUS_LOG_LEVEL", _DEFAULT_LEVEL)
    if isinstance(level, int):
        return level
    resolved = logging.getLevelName(str(level).upper())
    # Geçersiz isim -> getLevelName str döndürür; INFO'ya düş.
    return resolved if isinstance(resolved, int) else logging.INFO


def setup_logging(level: str | int | None = None) -> None:
    """Kök logger'ı bir kez yapılandır (idempotent).

    ``app.py`` giriş noktasında GUI ve CLI yollarının ikisinde de çağrılır.
    Tekrar çağrılması güvenlidir; handler tekrar eklenmez.
    """
    global _configured
    resolved = _resolve_level(level)
    root = logging.getLogger()
    root.setLevel(resolved)

    if _configured:
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(handler)
    _configured = True
