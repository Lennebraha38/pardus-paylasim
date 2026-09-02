"""
Unified Device Registry & Manager for Pardus Continuity / Ekosistem Tanıma.
Combines Wi-Fi (mDNS) and Bluetooth (BLE) discovered devices into a single list.
Supports device persistence, pairing state, and trust management.

macOS-style ecosystem awareness:
- Automatically discovers nearby Pardus devices via mDNS + BLE
- Persists paired/trusted devices across sessions
- Tracks device capabilities (screen share, file share, clipboard)
- Monitors device proximity via RSSI
"""

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from pardus_paylasim.discovery.ble_discovery import BLEDiscovery
from pardus_paylasim.discovery.mdns_discovery import MDNSDiscovery

# Persistence file path
PERSISTENCE_DIR = os.path.expanduser("~/.local/share/pardus-paylasim")
PERSISTENCE_FILE = os.path.join(PERSISTENCE_DIR, "trusted_devices.json")


@dataclass
class PardusDevice:
    """Represents a discovered Pardus device in the ecosystem."""

    id: str  # Unique identifier (IP or MAC)
    name: str  # e.g., "Ahmet'in Pardus Laptop'ı"
    address: str  # IP address or MAC address
    port: int  # Port number for services
    connection_type: str  # "Wi-Fi (mDNS)", "Bluetooth LE", "Ethernet"
    os_info: str  # "Pardus 25 GNU/Linux"
    capabilities: List[str] = field(default_factory=list)
    rssi: str = "-60 dBm"  # Signal strength
    last_seen: float = field(default_factory=time.time)
    status: str = "Açık (Hazır)"  # "Açık (Hazır)", "Eşleşti", "Ekran Paylaşılıyor", "Güvenilir"
    is_trusted: bool = False
    is_paired: bool = False
    # Servis portları (mDNS TXT'den): screen_port/file_port/clip_port/control_port
    service_ports: Dict[str, int] = field(default_factory=dict)


class DeviceManager:
    """Manages discovery and state of nearby Pardus devices with persistence.

    Thread-safe: all public methods use internal locks to protect shared state.
    """

    def __init__(self, local_device_name: str = "Pardus Masaüstü"):
        self.local_device_name = local_device_name
        self._lock = threading.Lock()
        self.devices: Dict[str, PardusDevice] = {}
        self.mdns = MDNSDiscovery(device_name=local_device_name)
        self.ble = BLEDiscovery(device_name=local_device_name)
        self._listeners: List[Callable[[List[PardusDevice]], None]] = []

        # Load trusted devices from persistence
        self._trusted_ids: set = self._load_trusted_devices()

    # ── Persistence ──────────────────────────────

    def _load_trusted_devices(self) -> set:
        """Load previously trusted/paired device IDs from disk."""
        try:
            if os.path.exists(PERSISTENCE_FILE):
                with open(PERSISTENCE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    trusted = set()
                    for entry in data.get("trusted", []):
                        trusted.add(entry.get("id", ""))
                    return trusted
        except Exception:
            pass
        return set()

    def _save_trusted_devices(self):
        """Save trusted device IDs to disk atomically."""
        try:
            os.makedirs(PERSISTENCE_DIR, exist_ok=True)
            with self._lock:
                trusted = []
                for dev_id in self._trusted_ids:
                    if dev_id in self.devices:
                        dev = self.devices[dev_id]
                        trusted.append(
                            {
                                "id": dev.id,
                                "name": dev.name,
                                "address": dev.address,
                                "connection_type": dev.connection_type,
                                "os_info": dev.os_info,
                                "last_seen": dev.last_seen,
                            }
                        )
                    else:
                        trusted.append({"id": dev_id})

            # Atomic write: write to temp file then rename
            tmp_file = PERSISTENCE_FILE + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump({"trusted": trusted}, f, indent=2, ensure_ascii=False)
            os.replace(tmp_file, PERSISTENCE_FILE)
        except Exception:
            pass

    def trust_device(self, device_id: str):
        """Mark a device as trusted and persist."""
        with self._lock:
            self._trusted_ids.add(device_id)
            if device_id in self.devices:
                self.devices[device_id].is_trusted = True
                self.devices[device_id].status = "Güvenilir Cihaz"
        self._save_trusted_devices()
        self.notify_listeners()

    def untrust_device(self, device_id: str):
        """Remove trust from a device."""
        with self._lock:
            self._trusted_ids.discard(device_id)
            if device_id in self.devices:
                self.devices[device_id].is_trusted = False
                self.devices[device_id].status = "Açık (Hazır)"
        self._save_trusted_devices()
        self.notify_listeners()

    # ── Discovery ────────────────────────────────

    def register_listener(self, callback: Callable[[List[PardusDevice]], None]):
        """Register a callback for device list updates. Deduplicates by identity."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def _parse_rssi_int(self, rssi_str: str) -> int:
        """Safely parse RSSI string to integer for sorting."""
        try:
            if "dBm" in rssi_str:
                return int(rssi_str.replace("dBm", "").strip())
            return int(rssi_str.strip())
        except (ValueError, TypeError):
            return 0

    def notify_listeners(self):
        """Notify all registered listeners of device list changes."""
        with self._lock:
            device_list = list(self.devices.values())
            # Sort by: trusted first, then by signal strength, then by last seen
            device_list.sort(
                key=lambda d: (
                    not d.is_trusted,
                    -self._parse_rssi_int(d.rssi),
                    -d.last_seen,
                )
            )
            # Copy listener list to avoid mutation during iteration
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(device_list)
            except Exception:
                pass

    def start_discovery(self):
        """Starts real-time background scanning on Wi-Fi and Bluetooth."""
        self.mdns.start_broadcasting_and_scanning(self._on_mdns_found)
        self.ble.start_scanning(self._on_ble_found)

    @staticmethod
    def _parse_service_ports(props: dict, screen_default: int) -> dict:
        """TXT'deki servis portlarını güvenle int'e çevir (bozuksa varsayılan)."""

        def _port(key: str, default: int) -> int:
            try:
                return int(props.get(key, default))
            except (TypeError, ValueError):
                return default

        return {
            "screen_port": _port("screen_port", screen_default),
            "file_port": _port("file_port", 8900),
            "clip_port": _port("clip_port", 8901),
            "control_port": _port("control_port", 0),
        }

    def _on_mdns_found(self, name: str, ip: str, port: int, props: dict):
        """Handle mDNS discovery event. Called from background thread."""
        caps = []
        if props.get("screen_share") == "1":
            caps.append("Ekran Paylaşımı")
        if props.get("file_share") == "1":
            caps.append("Dosya Gönderimi")
        if props.get("clipboard_share") == "1":
            caps.append("Hassas Pano")
        if props.get("control_share") == "1":
            caps.append("Uzaktan Kontrol")

        ports = self._parse_service_ports(props, port)

        with self._lock:
            is_trusted = ip in self._trusted_ids or name in self._trusted_ids

            dev = PardusDevice(
                id=ip,
                name=name.split(".")[0] if "." in name else name,
                address=ip,
                port=port,
                connection_type=props.get("type", "Wi-Fi (mDNS)"),
                os_info=props.get("os", "Pardus 25 GNU/Linux"),
                capabilities=caps if caps else ["Ekran Paylaşımı", "Dosya Gönderimi"],
                rssi=props.get("rssi", "-45 dBm"),
                status="Güvenilir Cihaz" if is_trusted else "Açık (Wi-Fi)",
                is_trusted=is_trusted,
                service_ports=ports,
            )
            self.devices[ip] = dev
        self.notify_listeners()

    def _on_ble_found(self, name: str, mac: str, port: int, props: dict):
        """Handle BLE discovery event. Called from background thread."""
        caps = []
        if props.get("screen_share") == "1":
            caps.append("Ekran Paylaşımı")
        if props.get("file_share") == "1":
            caps.append("Dosya Gönderimi")

        with self._lock:
            is_trusted = mac in self._trusted_ids or name in self._trusted_ids

            dev = PardusDevice(
                id=mac,
                name=name,
                address=mac,
                port=port,
                connection_type=props.get("type", "Bluetooth LE"),
                os_info=props.get("os", "Pardus Bluetooth"),
                capabilities=caps if caps else ["Ekran Paylaşımı", "Cihaz Bilgisi"],
                rssi=props.get("rssi", "-62 dBm"),
                status="Güvenilir Cihaz" if is_trusted else "Açık (Bluetooth)",
                is_trusted=is_trusted,
            )
            self.devices[mac] = dev
        self.notify_listeners()

    def get_devices(self) -> List[PardusDevice]:
        """Get current device list sorted by trust and proximity."""
        with self._lock:
            return list(self.devices.values())

    def get_device_by_id(self, device_id: str) -> Optional[PardusDevice]:
        """Get a specific device by its ID."""
        with self._lock:
            return self.devices.get(device_id)

    def get_trusted_devices(self) -> List[PardusDevice]:
        """Get only trusted devices."""
        with self._lock:
            return [d for d in self.devices.values() if d.is_trusted]

    def stop_discovery(self):
        """Stop all discovery activities."""
        self.mdns.stop()
        self.ble.stop()
