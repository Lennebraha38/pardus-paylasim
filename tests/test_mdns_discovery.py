"""
mDNS keşif (`mdns_discovery`) gating testleri.

Odak: sahte peer sızıntısının kapatıldığını kanıtla. Zeroconf yoksa VEYA
başlatma çökerse — simülasyon env kapalıyken — hayalet cihaz ENJEKTE EDİLMEZ;
bunun yerine hata durumu (`.error` + `on_error`) kurulur. Simülasyon yalnız
`PARDUS_MDNS_SIMULATE=1` ile açılır ve o modda bile eski `192.168.1.101`
peer'ini raporlamaz.

Gerçek zeroconf ağına bağımlı değildir: modül-seviyesi `HAS_ZEROCONF` ve env
monkeypatch edilir; simülasyon thread'i `join` ile deterministik beklenir.
"""

import os
import unittest
from unittest import mock

from pardus_paylasim.discovery import mdns_discovery as md
from pardus_paylasim.discovery.mdns_discovery import MDNSDiscovery


class TestSimulationGate(unittest.TestCase):
    def test_disabled_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(md._simulation_enabled())

    def test_enabled_only_with_exact_1(self):
        with mock.patch.dict(os.environ, {md.SIMULATE_ENV: "1"}, clear=True):
            self.assertTrue(md._simulation_enabled())
        with mock.patch.dict(os.environ, {md.SIMULATE_ENV: "0"}, clear=True):
            self.assertFalse(md._simulation_enabled())
        with mock.patch.dict(os.environ, {md.SIMULATE_ENV: "true"}, clear=True):
            self.assertFalse(md._simulation_enabled())


class TestNoZeroconfNoSimulation(unittest.TestCase):
    """Zeroconf kurulu değil + simülasyon kapalı → hata, sahte peer YOK."""

    def test_error_state_and_no_devices(self):
        found = []
        errors = []
        disco = MDNSDiscovery("Bu Cihaz")
        with (
            mock.patch.object(md, "HAS_ZEROCONF", False),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            disco.start_broadcasting_and_scanning(
                on_device_found=lambda *a: found.append(a),
                on_error=errors.append,
            )
        self.assertEqual(found, [])  # hayalet cihaz enjekte edilmedi
        self.assertIsNotNone(disco.error)  # hata durumu kuruldu
        self.assertEqual(len(errors), 1)  # on_error tetiklendi

    def test_start_failure_helper_sets_error_without_callback(self):
        # on_error verilmese de çökmeden .error dolar.
        disco = MDNSDiscovery("Bu Cihaz")
        with mock.patch.dict(os.environ, {}, clear=True):
            disco._handle_start_failure("boom", lambda *a: None)
        self.assertEqual(disco.error, "boom")


class TestSimulationModeNoFakePeer(unittest.TestCase):
    """Simülasyon açıkken bile eski uydurma XFCE peer raporlanmaz."""

    def test_simulate_reports_only_self(self):
        found = []
        disco = MDNSDiscovery("Bu Cihaz", port=52345)
        disco.running = True
        with (
            mock.patch.object(disco, "_get_local_ip", return_value="10.0.0.5"),
            mock.patch.object(md.time, "sleep", return_value=None),
        ):
            disco._simulate_local_scan(lambda *a: found.append(a))

        # Yalnız bu cihaz raporlanır.
        self.assertEqual(len(found), 1)
        name, ip, port, props = found[0]
        self.assertEqual(name, "Bu Cihaz")
        self.assertEqual(ip, "10.0.0.5")
        # Kaldırılan sahte peer hiçbir raporun IP'sinde olmamalı.
        self.assertNotIn("192.168.1.101", [entry[1] for entry in found])

    def test_start_uses_simulation_when_env_set_and_no_zeroconf(self):
        found = []
        disco = MDNSDiscovery("Bu Cihaz")
        with (
            mock.patch.object(md, "HAS_ZEROCONF", False),
            mock.patch.dict(os.environ, {md.SIMULATE_ENV: "1"}, clear=True),
            mock.patch.object(disco, "_start_simulation") as sim,
        ):
            disco.start_broadcasting_and_scanning(on_device_found=lambda *a: found.append(a))
        sim.assert_called_once()
        self.assertIsNone(disco.error)  # sim modunda hata durumu yok


class TestSourceHasNoFakePeer(unittest.TestCase):
    """Regresyon kilidi: kaynak dosyada literal sahte IP kalmadı."""

    def test_fake_ip_literal_removed(self):
        source = md.__file__
        with open(source, "r", encoding="utf-8") as fh:
            text = fh.read()
        # Yorumda "kaldırıldı" geçebilir ama kod literali olmamalı:
        # tırnak içinde IP yok.
        self.assertNotIn('"192.168.1.101"', text)
        self.assertNotIn("'192.168.1.101'", text)


class TestBuildTxtProps(unittest.TestCase):
    """TXT kayıt üretimi: gerçek OS + yetenek bayrakları + servis portları."""

    def test_os_and_session_from_platform_info(self):
        # OS hardcoded değil → platform_info'dan gelir.
        disco = MDNSDiscovery("Bu Cihaz")
        with (
            mock.patch.object(
                md.platform_info, "current_os_label", return_value="Pardus 25 GNU/Linux"
            ),
            mock.patch.object(md.platform_info, "session_type", return_value="x11"),
        ):
            props = disco._build_txt_props()
        self.assertEqual(props["os"], "Pardus 25 GNU/Linux")
        self.assertEqual(props["session"], "x11")
        self.assertEqual(props["version"], md.SERVICE_VERSION)
        self.assertEqual(props["device"], "Bu Cihaz")

    def test_default_capabilities_screen_file_clip_on_control_off(self):
        # Varsayılan yetenek seti: ekran+dosya+pano açık, kontrol kapalı.
        disco = MDNSDiscovery("Bu Cihaz")
        props = disco._build_txt_props()
        self.assertEqual(props["screen_share"], "1")
        self.assertEqual(props["file_share"], "1")
        self.assertEqual(props["clipboard_share"], "1")
        self.assertEqual(props["control_share"], "0")

    def test_control_capability_sets_flag(self):
        # Kontrol yeteneği verilirse control_share=1.
        disco = MDNSDiscovery(
            "Bu Cihaz",
            capabilities={md.CAP_SCREEN, md.CAP_CONTROL},
        )
        props = disco._build_txt_props()
        self.assertEqual(props["control_share"], "1")
        self.assertEqual(props["screen_share"], "1")
        self.assertEqual(props["file_share"], "0")

    def test_service_ports_published(self):
        # Her servis portu ayrı TXT alanı olarak yazılır.
        disco = MDNSDiscovery(
            "Bu Cihaz",
            port=52345,
            file_port=8900,
            clip_port=8901,
        )
        props = disco._build_txt_props()
        self.assertEqual(props["screen_port"], "52345")
        self.assertEqual(props["file_port"], "8900")
        self.assertEqual(props["clip_port"], "8901")

    def test_control_port_omitted_when_zero(self):
        # control_port=0 → yayınlanmaz (kanal yok).
        disco = MDNSDiscovery("Bu Cihaz", control_port=0)
        props = disco._build_txt_props()
        self.assertNotIn("control_port", props)

    def test_control_port_published_when_set(self):
        disco = MDNSDiscovery("Bu Cihaz", control_port=52346)
        props = disco._build_txt_props()
        self.assertEqual(props["control_port"], "52346")


if __name__ == "__main__":
    unittest.main()
