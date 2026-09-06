import json
import os
import threading
from dataclasses import dataclass
from typing import Dict, List

from pardus_paylasim.platform_info import app_data_dir


@dataclass
class TrustedDevice:
    device_name: str
    public_key: str
    added_at: float


class TrustStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._file_path = os.path.join(app_data_dir(), "trusted_devices.json")
        self._devices: Dict[str, TrustedDevice] = {}
        self._load()

    def _load(self):
        if not os.path.exists(self._file_path):
            return
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.items():
                    self._devices[k] = TrustedDevice(**v)
        except Exception as e:
            pass

    def _save(self):
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        try:
            with open(self._file_path, "w", encoding="utf-8") as f:
                data = {
                    k: {
                        "device_name": v.device_name,
                        "public_key": v.public_key,
                        "added_at": v.added_at,
                    }
                    for k, v in self._devices.items()
                }
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            pass

    def add_trusted_device(self, public_key: str, device_name: str) -> None:
        import time

        with self._lock:
            self._devices[public_key] = TrustedDevice(device_name, public_key, time.time())
            self._save()

    def remove_trusted_device(self, public_key: str) -> None:
        with self._lock:
            if public_key in self._devices:
                del self._devices[public_key]
                self._save()

    def is_trusted(self, public_key: str) -> bool:
        with self._lock:
            return public_key in self._devices

    def get_all(self) -> List[TrustedDevice]:
        with self._lock:
            return list(self._devices.values())
