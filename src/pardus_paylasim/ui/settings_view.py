"""
GTK4 Settings & Security Trust View Controller and Component.
Manages TrustStore, device fingerprint, auto-accept toggles, and configuration.
"""

from typing import Any

from pardus_paylasim.auth.trust_store import TrustStore
from pardus_paylasim.config import AppConfig


class SettingsViewHandler:
    """Controller for application settings and trusted devices list."""

    def __init__(self, config: AppConfig | None = None, trust_store: TrustStore | None = None):
        self.config = config or AppConfig()
        self.trust_store = trust_store or TrustStore.get_instance()

    def get_trusted_devices(self) -> dict[str, dict]:
        return self.trust_store.list_trusted()

    def add_trusted_device(self, fingerprint: str, name: str, ip: str = "") -> None:
        self.trust_store.add_trusted(fingerprint, name, ip)

    def remove_trusted_device(self, fingerprint: str) -> bool:
        return self.trust_store.remove_trusted(fingerprint)

    def is_trusted(self, fingerprint: str) -> bool:
        return self.trust_store.is_trusted(fingerprint)

    def get_auto_accept(self) -> bool:
        return bool(self.config.get("auto_accept_trusted", False))

    def set_auto_accept(self, value: bool) -> None:
        self.config.set("auto_accept_trusted", bool(value))

    def get_device_name(self) -> str:
        return str(self.config.get("device_name", "Pardus Cihazı"))

    def set_device_name(self, name: str) -> None:
        self.config.set("device_name", str(name))


class SettingsViewComponent:
    """GTK4 Ayarlar ve Güven Deposu Görünüm Bileşeni."""

    def __init__(self, handler: SettingsViewHandler | None = None):
        self.handler = handler or SettingsViewHandler()
        self.container: Any = None
