"""
GTK4 Device Discovery View: Displays nearby Wi-Fi & Bluetooth Pardus devices.
"""

from collections.abc import Callable
from typing import Any

from pardus_paylasim.discovery.device_manager import DeviceManager, PardusDevice


class DiscoveryViewHandler:
    """Controller for Wi-Fi and Bluetooth device discovery UI."""

    def __init__(self, local_name: str = "Pardus Masaüstü"):
        self.device_mgr = DeviceManager(local_device_name=local_name)

    def start_scanning(self, update_ui_cb: Callable[[list[PardusDevice]], None]):
        self.device_mgr.register_listener(update_ui_cb)
        self.device_mgr.start_discovery()

    def stop_scanning(self):
        self.device_mgr.stop_discovery()

    def get_current_devices(self) -> list[PardusDevice]:
        return self.device_mgr.get_devices()

    def get_trusted_devices(self) -> list[PardusDevice]:
        return self.device_mgr.get_trusted_devices()

    def add_manual_device(self, ip: str, port: int, name: str | None = None) -> PardusDevice:
        return self.device_mgr.upsert_manual_device(name or ip, ip, port)

    def get_ble_status(self) -> dict[str, bool | str]:
        return self.device_mgr.get_ble_status()


class DiscoveryViewComponent:
    """GTK4 Cihaz Keşif ve Listeleme Bileşeni."""

    def __init__(self, handler: DiscoveryViewHandler | None = None):
        self.handler = handler or DiscoveryViewHandler()
        self.selected_ids: set[str] = set()
        self.container: Any = None

    def update_selection(self, selected_ids: set[str]) -> None:
        self.selected_ids = set(selected_ids)

    def filter_devices(self, query: str = "", only_trusted: bool = False) -> list[PardusDevice]:
        devices = self.handler.get_current_devices()
        filtered = []
        q = query.strip().lower()
        for d in devices:
            if only_trusted and not d.is_trusted:
                continue
            if q and (q not in d.name.lower() and q not in d.address.lower()):
                continue
            filtered.append(d)
        return filtered
