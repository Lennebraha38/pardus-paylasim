"""
Pardus Paylaşım — BLE Keşfi ve Adaptör Testleri.
"""

from unittest import mock

from pardus_paylasim.discovery.ble_discovery import BLEDiscovery


def test_ble_adapter_detection_sys_class():
    with mock.patch("glob.glob", return_value=["/sys/class/bluetooth/hci0"]):
        ble = BLEDiscovery("TestDevice")
        assert ble.is_adapter_available()
        status = ble.get_adapter_status()
        assert status["available"] is True
        assert status["adapter_name"] == "hci0"


def test_ble_adapter_detection_absent():
    with mock.patch("glob.glob", return_value=[]), mock.patch(
        "shutil.which", return_value=None
    ):
        ble = BLEDiscovery("TestDevice")
        ble._mock_mode = False
        assert not ble.is_adapter_available()
        status = ble.get_adapter_status()
        assert status["available"] is False
        assert status["adapter_name"] == "Yok"


def test_ble_report_device_pardus_vs_generic():
    ble = BLEDiscovery("TestDevice")
    reported = []

    def callback(name, mac, port, props):
        reported.append((name, mac, port, props))

    # 1. Pardus cihazı
    ble._report_device(callback, "11:22:33:44:55:66", "Pardus Masaüstü")
    assert len(reported) == 1
    assert reported[0][3]["os"] == "Pardus GNU/Linux"
    assert reported[0][3]["screen_share"] == "1"

    # 2. Genel Bluetooth cihazı (kulaklık/telefon)
    ble._report_device(callback, "AA:BB:CC:DD:EE:FF", "Sony WH-1000XM4")
    assert len(reported) == 2
    assert reported[1][3]["os"] == "Bluetooth Cihazı"
    assert reported[1][3]["screen_share"] == "0"


def test_ble_mock_mode(monkeypatch):
    monkeypatch.setenv("PARDUS_BLE_MOCK", "1")
    ble = BLEDiscovery("MockDevice")
    assert ble.is_adapter_available()
    status = ble.get_adapter_status()
    assert status["mock_mode"] is True

    reported = []

    def callback(name, mac, port, props):
        reported.append((name, mac, port, props))

    ble.running = True
    # Tek adım mock döngüsü
    with mock.patch("time.sleep", side_effect=lambda s: setattr(ble, "running", False)):
        ble._scan_mock(callback)

    assert len(reported) >= 1
    assert "Pardus BLE Beacon" in reported[0][0]
    assert reported[0][3]["os"] == "Pardus GNU/Linux"


def test_ble_stop_cleanup():
    ble = BLEDiscovery("TestDevice")
    fake_proc = mock.MagicMock()
    fake_proc.poll.return_value = None
    ble._scan_proc = fake_proc
    ble.running = True

    with mock.patch("subprocess.run"):
        ble.stop()

    assert not ble.running
    fake_proc.terminate.assert_called_once()
    assert ble._scan_proc is None
