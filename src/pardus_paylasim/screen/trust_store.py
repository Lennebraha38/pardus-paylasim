import json
import os
import re
import shutil
import tempfile
import time
from typing import Optional

from filelock import FileLock

from pardus_paylasim.platform_info import is_windows

if is_windows():
    _config_dir = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")), "pardus-paylasim"
    )
else:
    _config_dir = os.path.expanduser("~/.config/pardus-paylasim")

TRUST_STORE_FILE = os.path.join(_config_dir, "trusted_devices.json")
LOCK_FILE = os.path.join(_config_dir, "trusted_devices.json.lock")

# Sadece hex karakterler (aralarda ':' olabilir), sha256 -> 64 hex karakter (eğer DER okunduysa 64, vb.)
# fingerprint_from_der çıktısı genelde "XX:XX:XX..." veya düz hex'dir.
_FP_PATTERN = re.compile(r"^(?:[A-Fa-f0-9]{2}:){31}[A-Fa-f0-9]{2}$|^[A-Fa-f0-9]{64}$")


class TrustStoreError(Exception):
    pass


def _load_store() -> dict:
    if not os.path.exists(TRUST_STORE_FILE):
        return {}
    try:
        with open(TRUST_STORE_FILE, "r") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise TrustStoreError("Trust store formatı geçersiz (kök eleman dict değil).")
            return data
    except json.JSONDecodeError as e:
        raise TrustStoreError(f"Trust store JSON parse hatası (bozuk dosya): {e}")
    except OSError as e:
        raise TrustStoreError(f"Trust store okunamadı: {e}")


def _save_store(store: dict) -> None:
    os.makedirs(_config_dir, exist_ok=True)
    if not is_windows():
        os.chmod(_config_dir, 0o700)

    fd, temp_path = tempfile.mkstemp(dir=_config_dir, prefix="trust_store_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(store, f)
            f.flush()
            os.fsync(f.fileno())
        if not is_windows():
            os.chmod(temp_path, 0o600)
        shutil.move(temp_path, TRUST_STORE_FILE)
    except Exception as e:
        os.remove(temp_path)
        raise TrustStoreError(f"Trust store yazılamadı: {e}")


def get_trusted_fingerprint(device_id: str) -> Optional[str]:
    os.makedirs(_config_dir, exist_ok=True)
    with FileLock(LOCK_FILE, timeout=5):
        store = _load_store()
        record = store.get(device_id)
        if record and isinstance(record, dict):
            fp = record.get("fingerprint")
            if fp and _FP_PATTERN.match(fp):
                return fp
        return None


def add_trusted_fingerprint(device_id: str, fingerprint: str) -> None:
    if not _FP_PATTERN.match(fingerprint):
        raise ValueError(f"Geçersiz fingerprint formatı: {fingerprint}")

    os.makedirs(_config_dir, exist_ok=True)
    with FileLock(LOCK_FILE, timeout=5):
        store = _load_store()
        store[device_id] = {"fingerprint": fingerprint, "timestamp": time.time()}
        _save_store(store)
