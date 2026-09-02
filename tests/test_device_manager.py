"""
`DeviceManager` mDNS tüketim testleri (0.3).

Odak: keşif callback'i (`_on_mdns_found`) yeni TXT alanlarını okur —
`control_share` yeteneği ve servis portları (`screen_port`/`file_port`/
`clip_port`/`control_port`). Port parse bozuk/eksik veriye dayanıklı olmalı
(exception değil, varsayılan).

Diske/persistence'a bağımlı değil: `_load_trusted_devices` monkeypatch ile
boş küme döndürülür; keşif thread'i başlatılmaz (yalnız saf callback çağrılır).
"""

import unittest
from unittest import mock

from pardus_paylasim.discovery import device_manager as dm
from pardus_paylasim.discovery.device_manager import DeviceManager


def _make_manager() -> DeviceManager:
    """Persistence okumadan (diske dokunmadan) yönetici üret."""
    with (
        mock.patch.object(DeviceManager, "_load_trusted_devices", return_value=set()),
        mock.patch.object(dm, "MDNSDiscovery"),
        mock.patch.object(dm, "BLEDiscovery"),
    ):
        return DeviceManager(local_device_name="Bu Cihaz")


class TestParseServicePorts(unittest.TestCase):
    def test_reads_all_ports(self):
        props = {
            "screen_port": "52345",
            "file_port": "8900",
            "clip_port": "8901",
            "control_port": "52346",
        }
        ports = DeviceManager._parse_service_ports(props, screen_default=52345)
        self.assertEqual(ports["screen_port"], 52345)
        self.assertEqual(ports["file_port"], 8900)
        self.assertEqual(ports["clip_port"], 8901)
        self.assertEqual(ports["control_port"], 52346)

    def test_missing_fields_use_defaults(self):
        # Eski (port yayınlamayan) peer → varsayılanlar, çökme yok.
        ports = DeviceManager._parse_service_ports({}, screen_default=52345)
        self.assertEqual(ports["screen_port"], 52345)
        self.assertEqual(ports["file_port"], 8900)
        self.assertEqual(ports["clip_port"], 8901)
        self.assertEqual(ports["control_port"], 0)

    def test_garbage_port_falls_back(self):
        # Bozuk değer int'e çevrilemez → varsayılan (exception atma).
        props = {"screen_port": "abc", "file_port": None}
        ports = DeviceManager._parse_service_ports(props, screen_default=9999)
        self.assertEqual(ports["screen_port"], 9999)
        self.assertEqual(ports["file_port"], 8900)


class TestOnMdnsFoundCapabilities(unittest.TestCase):
    def test_control_share_adds_capability(self):
        mgr = _make_manager()
        props = {
            "screen_share": "1",
            "file_share": "1",
            "control_share": "1",
            "type": "Wi-Fi (mDNS)",
        }
        mgr._on_mdns_found("Uzak Cihaz", "10.0.0.7", 52345, props)

        dev = mgr.devices["10.0.0.7"]
        self.assertIn("Uzaktan Kontrol", dev.capabilities)
        self.assertIn("Ekran Paylaşımı", dev.capabilities)

    def test_no_control_share_omits_capability(self):
        mgr = _make_manager()
        props = {"screen_share": "1", "file_share": "1"}
        mgr._on_mdns_found("Uzak Cihaz", "10.0.0.8", 52345, props)

        dev = mgr.devices["10.0.0.8"]
        self.assertNotIn("Uzaktan Kontrol", dev.capabilities)

    def test_service_ports_attached_to_device(self):
        mgr = _make_manager()
        props = {
            "screen_share": "1",
            "screen_port": "52345",
            "file_port": "8900",
            "clip_port": "8901",
            "control_port": "52346",
        }
        mgr._on_mdns_found("Uzak Cihaz", "10.0.0.9", 52345, props)

        dev = mgr.devices["10.0.0.9"]
        self.assertEqual(dev.service_ports["control_port"], 52346)
        self.assertEqual(dev.service_ports["file_port"], 8900)

    def test_missing_ports_default_zero_control(self):
        # control_port yayınlanmamış peer → 0 (kanal yok).
        mgr = _make_manager()
        props = {"screen_share": "1"}
        mgr._on_mdns_found("Eski Cihaz", "10.0.0.10", 52345, props)

        dev = mgr.devices["10.0.0.10"]
        self.assertEqual(dev.service_ports["control_port"], 0)


if __name__ == "__main__":
    unittest.main()
