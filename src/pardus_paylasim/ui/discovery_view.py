"""
GTK4 Device Discovery View: Displays nearby Wi-Fi & Bluetooth Pardus devices.
"""

from typing import Callable, List

from pardus_paylasim.discovery.device_manager import DeviceManager, PardusDevice


class DiscoveryViewHandler:
    """Controller for Wi-Fi and Bluetooth device discovery UI."""

    def __init__(self, local_name: str = "Pardus Masaüstü"):
        self.device_mgr = DeviceManager(local_device_name=local_name)

    def start_scanning(self, update_ui_cb: Callable[[List[PardusDevice]], None]):
        self.device_mgr.register_listener(update_ui_cb)
        self.device_mgr.start_discovery()

    def stop_scanning(self):
        self.device_mgr.stop_discovery()

    def get_current_devices(self) -> List[PardusDevice]:
        return self.device_mgr.get_devices()
