"""
Bluetooth / BLE Device Discovery Engine for Pardus Ecosystem.
Uses BlueZ D-Bus API for continuous BLE scanning and device discovery.
Supports both LE and Classic Bluetooth device detection.
"""

import re
import shutil
import subprocess
import threading
import time
from typing import Callable, Dict


class BLEDiscovery:
    """Continuous Bluetooth LE and Classic device scanner."""

    def __init__(self, device_name: str):
        self.device_name = device_name
        self.running = False
        self.has_bluetoothctl = shutil.which("bluetoothctl") is not None
        self.has_hcitool = shutil.which("hcitool") is not None
        self._seen_devices: Dict[str, dict] = {}
        self._scan_proc = None  # Track scan subprocess for cleanup

    def start_scanning(self, on_device_found: Callable[[str, str, int, dict], None]):
        """Start continuous BLE and Bluetooth device scanning."""
        self.running = True
        self._seen_devices.clear()

        # Start the main scanning thread
        threading.Thread(target=self._scan_loop, args=(on_device_found,), daemon=True).start()

    def _scan_loop(self, on_device_found: Callable[[str, str, int, dict], None]):
        """Main scanning loop using bluetoothctl or hcitool."""
        if self.has_bluetoothctl:
            self._scan_with_bluetoothctl(on_device_found)
        elif self.has_hcitool:
            self._scan_with_hcitool(on_device_found)
        else:
            # Fallback: periodic device listing
            self._scan_fallback(on_device_found)

    def _scan_with_bluetoothctl(self, on_device_found: Callable[[str, str, int, dict], None]):
        """Continuous scan using bluetoothctl command."""
        try:
            # Ensure adapter is powered on
            subprocess.run(
                ["bluetoothctl", "power", "on"],
                capture_output=True,
                timeout=5,
            )

            # Start scan process
            self._scan_proc = subprocess.Popen(
                ["bluetoothctl", "scan", "on"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            # Read scan output line by line
            while self.running and self._scan_proc.poll() is None:
                try:
                    line = self._scan_proc.stdout.readline()
                    if not line:
                        continue

                    line = line.strip()
                    # Parse discovery events
                    # "[NEW] Device AA:BB:CC:DD:EE:FF Device Name"
                    if "Device" in line:
                        # bluetoothctl discovery format: "[NEW] Device MAC Name"
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
                            # Simpler format: "Device MAC Name"
                            parts = line.split(" ", 2)
                            if len(parts) >= 3 and parts[0] == "Device":
                                mac = parts[1]
                                name = parts[2] if len(parts) > 2 else "Bilinmeyen"
                                self._report_device(on_device_found, mac, name)

                    # Also parse RSSI lines if available
                    if "RSSI" in line:
                        rssi_match = re.search(r"RSSI:\s*(-?\d+)", line)
                        if rssi_match:
                            rssi_val = rssi_match.group(1)
                            # Try to associate RSSI with the correct device by MAC in line
                            associated = False
                            for mac in self._seen_devices:
                                if mac.lower() in line.lower():
                                    self._seen_devices[mac]["rssi"] = f"{rssi_val} dBm"
                                    associated = True
                                    break
                            if not associated and self._seen_devices:
                                # If no MAC matches, update the most recently seen device
                                last_mac = max(
                                    self._seen_devices,
                                    key=lambda m: self._seen_devices[m].get("last_seen", 0),
                                )
                                self._seen_devices[last_mac]["rssi"] = f"{rssi_val} dBm"

                except Exception:
                    time.sleep(0.1)

            # If scan process ended, keep listing known devices
            while self.running:
                self._list_known_devices(on_device_found)
                time.sleep(5)

        except Exception:
            # Fallback to periodic listing
            while self.running:
                self._list_known_devices(on_device_found)
                time.sleep(3)

    def _scan_with_hcitool(self, on_device_found: Callable[[str, str, int, dict], None]):
        """Scan using hcitool for LE and classic devices."""
        while self.running:
            try:
                # Scan for LE devices
                le_result = subprocess.run(
                    ["hcitool", "lescan", "--duration=2"],
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

                # Scan for classic devices
                classic_result = subprocess.run(
                    ["hcitool", "scan"],
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
                pass

            time.sleep(3)

    def _list_known_devices(self, on_device_found: Callable[[str, str, int, dict], None]):
        """List already-known/paired Bluetooth devices."""
        try:
            result = subprocess.run(
                ["bluetoothctl", "devices"],
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
            pass

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
            name = f"Pardus Cihaz ({mac[-5:]})"

        mac = mac.upper().strip()

        # Get last known RSSI (only real values parsed from scan output; no fake default).
        rssi = "Bilinmiyor"
        if mac in self._seen_devices:
            rssi = self._seen_devices[mac].get("rssi", rssi)

        # Guess device type from MAC OUI lookup (simplified)
        device_type = "Bluetooth LE" if "BLE" in name else "Bluetooth"

        props = {
            "os": "Pardus 25 GNU/Linux",
            "rssi": rssi,
            "screen_share": "1",
            "file_share": "1",
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
        # Terminate the bluetoothctl scan process if active
        if self._scan_proc is not None:
            try:
                self._scan_proc.terminate()
                self._scan_proc.wait(timeout=2)
            except Exception:
                try:
                    self._scan_proc.kill()
                except Exception:
                    pass
            self._scan_proc = None
        try:
            subprocess.run(
                ["bluetoothctl", "scan", "off"],
                capture_output=True,
                timeout=3,
            )
        except Exception:
            pass
