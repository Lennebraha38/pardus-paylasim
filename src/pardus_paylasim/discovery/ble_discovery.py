"""
Bluetooth / BLE Device Discovery Engine for Pardus Ecosystem.
Uses BlueZ D-Bus / bluetoothctl API for continuous BLE scanning and device discovery.
Supports hardware adapter presence checking, graceful fallback, and mock testing.
"""

import glob
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


class BLEDiscovery:
    """Continuous Bluetooth LE and Classic device scanner with hardware auto-detection."""

    def __init__(self, device_name: str):
        self.device_name = device_name
        self.running = False
        self.bluetoothctl_path = shutil.which("bluetoothctl")
        self.hcitool_path = shutil.which("hcitool")
        self.has_bluetoothctl = self.bluetoothctl_path is not None
        self.has_hcitool = self.hcitool_path is not None
        self._seen_devices: dict[str, dict] = {}
        self._scan_proc: subprocess.Popen | None = None
        self._mock_mode = os.getenv("PARDUS_BLE_MOCK", "0").lower() in ("1", "true", "yes")
        self.backend_type: str = "mock" if self._mock_mode else "auto"

    def is_adapter_available(self) -> bool:
        """Sistemde fiziksel bir Bluetooth adaptörü (hci0, hci1 vb.) olup olmadığını doğrular."""
        if self._mock_mode:
            return True

        # 1. /sys/class/bluetooth/ kontrolü
        hci_nodes = glob.glob("/sys/class/bluetooth/hci*")
        if hci_nodes:
            return True

        # 2. bluetoothctl list komutu ile kontrol
        if self.has_bluetoothctl and self.bluetoothctl_path:
            try:
                res = subprocess.run(  # noqa: S603
                    [self.bluetoothctl_path, "list"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if res.returncode == 0 and "Controller" in res.stdout:
                    return True
            except Exception:
                logger.debug("bluetoothctl list sorgusu başarısız", exc_info=True)

        return False

    def get_adapter_status(self) -> dict[str, bool | str]:
        """Adaptörün varlık, güç ve çalışma durumunu döndürür."""
        available = self.is_adapter_available()
        return {
            "available": available,
            "powered": available,
            "scanning": self.running,
            "mock_mode": self._mock_mode,
            "adapter_name": "hci0" if available else "Yok",
            "backend": self.backend_type,
        }

    def start_scanning(self, on_device_found: Callable[[str, str, int, dict], None]):
        """Start continuous BLE and Bluetooth device scanning."""
        self.running = True
        self._seen_devices.clear()

        # Start the main scanning thread
        threading.Thread(target=self._scan_loop, args=(on_device_found,), daemon=True).start()

    def _try_scan_with_dbus(self, on_device_found: Callable[[str, str, int, dict], None]) -> bool:
        """BlueZ sistem D-Bus (org.bluez ObjectManager) üzerinden cihazları yerel API ile sorgular."""
        try:
            import gi
            gi.require_version("Gio", "2.0")
            from gi.repository import Gio

            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            if bus is None:
                return False

            msg = Gio.DBusMessage.new_method_call(
                "org.bluez",
                "/",
                "org.freedesktop.DBus.ObjectManager",
                "GetManagedObjects",
            )
            reply = bus.send_message_with_reply_sync(msg, Gio.DBusSendMessageFlags.NONE, 2000)
            if reply and reply.get_message_type() == Gio.DBusMessageType.METHOD_RETURN:
                body = reply.get_body()
                if body:
                    objects = body.unpack()[0]
                    for _, ifaces in objects.items():
                        if "org.bluez.Device1" in ifaces:
                            dev_props = ifaces["org.bluez.Device1"]
                            mac = str(dev_props.get("Address", ""))
                            name = str(dev_props.get("Name", dev_props.get("Alias", "Bluetooth Cihazı")))
                            rssi = dev_props.get("RSSI", None)
                            if rssi is not None:
                                self._seen_devices.setdefault(mac.upper(), {})["rssi"] = f"{rssi} dBm"
                            if self._is_valid_mac(mac):
                                self._report_device(on_device_found, mac, name)
                    return True
        except Exception:
            logger.debug("BlueZ D-Bus sorgusu başarısız veya D-Bus erişilemez", exc_info=True)
        return False

    def _scan_loop(self, on_device_found: Callable[[str, str, int, dict], None]):
        """Main scanning loop with adapter check, native D-Bus first, and fallback."""
        if self._mock_mode:
            self.backend_type = "mock"
            self._scan_mock(on_device_found)
            return

        if not self.is_adapter_available():
            self.backend_type = "none"
            logger.info("Bluetooth donanımı (adaptör) bulunamadı; BLE tarama pasif bekliyor.")
            while self.running:
                time.sleep(2)
            return

        # 1. Öncelikli olarak doğrudan BlueZ D-Bus API'sini dene (sıfır alt süreç, yerli Linux API)
        if self._try_scan_with_dbus(on_device_found):
            self.backend_type = "dbus"
            while self.running:
                self._try_scan_with_dbus(on_device_found)
                time.sleep(4)
            return

        # 2. D-Bus erişimi kısıtlıysa bluetoothctl alt süreç yedeğine geç
        self.backend_type = "bluetoothctl"
        if self.has_bluetoothctl:
            self._scan_with_bluetoothctl(on_device_found)
        elif self.has_hcitool:
            self._scan_with_hcitool(on_device_found)
        else:
            self._scan_fallback(on_device_found)

    def _scan_mock(self, on_device_found: Callable[[str, str, int, dict], None]):
        """Sanal test ortamları için yapay BLE cihaz simülasyonu."""
        mock_mac = "AA:BB:CC:11:22:33"
        mock_name = f"Pardus BLE Beacon ({self.device_name})"
        props = {
            "os": "Pardus GNU/Linux",
            "rssi": "-55 dBm",
            "screen_share": "1",
            "file_share": "1",
            "type": "Bluetooth LE (Simüle)",
        }
        while self.running:
            on_device_found(mock_name, mock_mac, 0, props)
            time.sleep(3)

    def _scan_with_bluetoothctl(self, on_device_found: Callable[[str, str, int, dict], None]):
        """Continuous scan using bluetoothctl command."""
        try:
            # Ensure adapter is powered on
            subprocess.run(  # noqa: S603
                [self.bluetoothctl_path or "bluetoothctl", "power", "on"],
                capture_output=True,
                timeout=5,
            )

            # Start scan process
            self._scan_proc = subprocess.Popen(  # noqa: S603
                [self.bluetoothctl_path or "bluetoothctl", "scan", "on"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            # Read scan output line by line
            while self.running and self._scan_proc and self._scan_proc.poll() is None:
                try:
                    if not self._scan_proc or not self._scan_proc.stdout:
                        break
                    line = self._scan_proc.stdout.readline()
                    if not line:
                        continue

                    line = line.strip()
                    if "Device" in line:
                        match = re.match(
                            r"\[?(NEW|DEL|CHG)?\]?\s*Device\s+"
                            r"([0-9A-Fa-f:]{17})\s+(.+)",
                            line,
                        )
                        if match:
                            event_type, mac, name = match.groups()
                            if event_type == "DEL":
                                continue
                            self._report_device(on_device_found, mac, name)
                        else:
                            parts = line.split(" ", 2)
                            if len(parts) >= 3 and parts[0] == "Device":
                                mac = parts[1]
                                name = parts[2] if len(parts) > 2 else "Bilinmeyen"
                                self._report_device(on_device_found, mac, name)

                    if "RSSI" in line:
                        rssi_match = re.search(r"RSSI:\s*(-?\d+)", line)
                        if rssi_match:
                            rssi_val = rssi_match.group(1)
                            associated = False
                            for mac in self._seen_devices:
                                if mac.lower() in line.lower():
                                    self._seen_devices[mac]["rssi"] = f"{rssi_val} dBm"
                                    associated = True
                                    break
                            if not associated and self._seen_devices:
                                last_mac = list(self._seen_devices.keys())[-1]
                                self._seen_devices[last_mac]["rssi"] = f"{rssi_val} dBm"

                except Exception:
                    logger.debug("bluetoothctl satır okuma hatası", exc_info=True)

        except Exception:
            logger.debug("bluetoothctl tarama başlatma hatası", exc_info=True)
            self._scan_fallback(on_device_found)

    def _scan_with_hcitool(self, on_device_found: Callable[[str, str, int, dict], None]):
        """Scan using hcitool command for older systems."""
        while self.running:
            try:
                le_result = subprocess.run(  # noqa: S603
                    [self.hcitool_path or "hcitool", "lescan", "--duplicates"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if le_result.returncode == 0:
                    for line in le_result.stdout.strip().split("\n"):
                        if line and "LE Scan" not in line:
                            parts = line.split()
                            if len(parts) >= 2:
                                mac = parts[0]
                                name = " ".join(parts[1:]) if len(parts) > 1 else "BLE Cihaz"
                                if self._is_valid_mac(mac):
                                    self._report_device(on_device_found, mac, name)

                classic_result = subprocess.run(  # noqa: S603
                    [self.hcitool_path or "hcitool", "scan"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if classic_result.returncode == 0:
                    for line in classic_result.stdout.strip().split("\n"):
                        if line and "Scanning" not in line:
                            parts = line.split("\t", 1)
                            if len(parts) >= 2:
                                mac, name = parts[0].strip(), parts[1].strip()
                                if self._is_valid_mac(mac):
                                    self._report_device(on_device_found, mac, name)

            except Exception:
                logger.debug("hcitool tarama hatası", exc_info=True)

            time.sleep(3)

    def _list_known_devices(self, on_device_found: Callable[[str, str, int, dict], None]):
        """List already-known/paired Bluetooth devices."""
        try:
            result = subprocess.run(  # noqa: S603
                [self.bluetoothctl_path or "bluetoothctl", "devices"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line.startswith("Device"):
                        parts = line.split(" ", 2)
                        if len(parts) >= 3:
                            mac, name = parts[1], parts[2]
                            self._report_device(on_device_found, mac, name)
        except Exception:
            logger.debug("bilinen cihazları listeleme hatası", exc_info=True)

    def _scan_fallback(self, on_device_found: Callable[[str, str, int, dict], None]):
        """Fallback: periodic device listing without continuous scan."""
        while self.running:
            self._list_known_devices(on_device_found)
            time.sleep(5)

    def _report_device(
        self,
        on_device_found: Callable[[str, str, int, dict], None],
        mac: str,
        name: str,
    ):
        """Report a discovered device, deduplicating by MAC."""
        if not name or name == "Bilinmeyen":
            name = f"Bluetooth Cihazı ({mac[-5:]})"

        mac = mac.upper().strip()

        rssi = "Bilinmiyor"
        if mac in self._seen_devices:
            rssi = self._seen_devices[mac].get("rssi", rssi)

        device_type = "Bluetooth LE" if "BLE" in name else "Bluetooth"
        is_pardus = "pardus" in name.lower() or "pardus" in str(mac).lower()
        device_os = "Pardus GNU/Linux" if is_pardus else "Bluetooth Cihazı"

        props = {
            "os": device_os,
            "rssi": rssi,
            "screen_share": "1" if is_pardus else "0",
            "file_share": "1" if is_pardus else "0",
            "type": device_type,
        }

        self._seen_devices[mac] = {
            "name": name,
            "rssi": rssi,
            "last_seen": time.time(),
        }

        on_device_found(f"{name}", mac, 0, props)

    @staticmethod
    def _is_valid_mac(mac: str) -> bool:
        """Check if string is a valid MAC address."""
        return bool(re.match(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$", mac))

    def stop(self):
        """Stop BLE scanning."""
        self.running = False
        if self._scan_proc is not None:
            try:
                self._scan_proc.terminate()
                self._scan_proc.wait(timeout=2)
            except Exception:
                try:
                    self._scan_proc.kill()
                except Exception:
                    logger.debug("scan_proc durdurma hatası", exc_info=True)
            self._scan_proc = None
        try:
            subprocess.run(  # noqa: S603
                [self.bluetoothctl_path or "bluetoothctl", "scan", "off"],
                capture_output=True,
                timeout=3,
            )
        except Exception:
            logger.debug("bluetoothctl scan off hatası", exc_info=True)
