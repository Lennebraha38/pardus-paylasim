"""Güvenilir cihaz deposu (parmak izi tabanlı TOFU).

Cihaz kimliği = kalıcı cihaz sertifikasının SHA-256 parmak izi
(`tls_util.get_or_create_device_cert`). Eşleştirme (QR/mDNS onayı)
sırasında karşı tarafın parmak izi buraya kaydolur; sonraki
bağlantılarda `is_ip_trusted` ile otomatik kabul kararı verilebilir.

Depo: `~/.local/share/pardus-paylasim/trusted_devices.json` (0600 dizin).
"""

import json
import logging
import os
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_STORE_DIR = os.path.expanduser("~/.local/share/pardus-paylasim")
_STORE_FILE = os.path.join(_STORE_DIR, "trusted_devices.json")


@dataclass
class TrustedDevice:
    device_name: str
    public_key: str  # SHA-256 parmak izi (hex)
    added_at: float
    last_ip: Optional[str] = None


class TrustStore:
    def __init__(self, file_path: Optional[str] = None):
        self._lock = threading.Lock()
        self._file_path = file_path or _STORE_FILE
        self._devices: Dict[str, TrustedDevice] = {}
        self._load()

    def _load(self):
        if not os.path.exists(self._file_path):
            return
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.items():
                    if not isinstance(v, dict):
                        continue
                    self._devices[k] = TrustedDevice(
                        device_name=v.get("device_name", "?"),
                        public_key=k,
                        added_at=float(v.get("added_at", 0)),
                        last_ip=v.get("last_ip"),
                    )
        except Exception as e:
            logger.debug("Güven deposu okunamadı, boş başlanıyor: %s", e)

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
            tmp_path = self._file_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                data = {
                    k: {
                        "device_name": v.device_name,
                        "added_at": v.added_at,
                        "last_ip": v.last_ip,
                    }
                    for k, v in self._devices.items()
                }
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._file_path)
        except Exception as e:
            logger.debug("Güven deposu yazılamadı: %s", e)

    def add_trusted_device(self, public_key: str, device_name: str) -> None:
        import time

        with self._lock:
            old = self._devices.get(public_key)
            self._devices[public_key] = TrustedDevice(
                device_name, public_key, time.time(),
                last_ip=old.last_ip if old else None,
            )
            self._save()

    def record_pairing(self, fingerprint: str, device_name: str,
                       ip: Optional[str] = None) -> bool:
        """Eşleştirmede güven kaydı (QR/mDNS onayı sonrası çağrılır)."""
        if not fingerprint or len(fingerprint) != 64 or any(
            c not in "0123456789abcdef" for c in fingerprint.lower()
        ):
            return False
        import time

        fp = fingerprint.lower()
        with self._lock:
            old = self._devices.get(fp)
            self._devices[fp] = TrustedDevice(
                device_name or "?", fp, time.time(),
                last_ip=ip or (old.last_ip if old else None),
            )
            self._save()
        return True

    def remove_trusted_device(self, public_key: str) -> None:
        with self._lock:
            if public_key in self._devices:
                del self._devices[public_key]
                self._save()

    def is_trusted(self, public_key: str) -> bool:
        with self._lock:
            return (public_key or "").lower() in self._devices

    def find_by_ip(self, ip: Optional[str]) -> Optional[TrustedDevice]:
        """Son görülen IP'ye göre güvenilir cihaz bulur."""
        if not ip:
            return None
        with self._lock:
            for dev in self._devices.values():
                if dev.last_ip == ip:
                    return dev
        return None

    def is_ip_trusted(self, ip: Optional[str]) -> bool:
        return self.find_by_ip(ip) is not None

    def get_all(self) -> List[TrustedDevice]:
        with self._lock:
            return list(self._devices.values())


def should_auto_accept(sender_ip: Optional[str], store: TrustStore,
                       auto_accept_enabled: bool) -> bool:
    """Otomatik kabul kararı (saf fonksiyon; test edilebilir).

    Yalnızca kullanıcı ayarı açık VE gönderen IP güvenilir kayıtta ise.
    NOT: IP tek başına zayıf kimliktir (yerel ağda taklit edilebilir);
    bu yüzden varsayılan kapalıdır ve ayar metninde uyarılır.
    """
    if not auto_accept_enabled:
        return False
    return store.is_ip_trusted(sender_ip)


def group_fingerprint(fp: str) -> str:
    """Parmak izini okunabilir gruplar: 'A1:B2:...' (16 grup)."""
    fp = (fp or "").upper().replace(":", "").replace(" ", "")
    return ":".join(fp[i:i + 2] for i in range(0, len(fp), 2))


def valid_fingerprint(fp) -> str:
    """64-hex parmak izini normalize eder; bozuksa '' döner."""
    if not isinstance(fp, str):
        return ""
    fp = fp.strip().lower()
    if len(fp) != 64 or any(c not in "0123456789abcdef" for c in fp):
        return ""
    return fp


def own_fingerprint() -> str:
    """Bu cihazın kalıcı parmak izi (yoksa/üretilemezse "")."""
    try:
        from pardus_paylasim.screen import tls_util

        _, _, fp = tls_util.get_or_create_device_cert()
        return fp
    except Exception as e:
        logger.debug("cihaz parmak izi alınamadı: %s", e)
        return ""
