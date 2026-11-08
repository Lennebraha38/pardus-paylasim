"""
Pardus Paylaşım — Modüler UI Görünüm ve Kontrolör Birim Testleri.
Her bir görünüm ve bileşeni GTK bağımsız test edilebilir kılan mimariyi doğrular.
"""

from unittest import mock

from pardus_paylasim.ui import (
    ClassroomViewComponent,
    ClassroomViewHandler,
    ClipboardViewComponent,
    ClipboardViewHandler,
    DiscoveryViewComponent,
    DiscoveryViewHandler,
    MeshViewComponent,
    MeshViewHandler,
    PrivacyViewComponent,
    PrivacyViewHandler,
    ScreenShareViewComponent,
    ScreenShareViewHandler,
    SettingsViewComponent,
    SettingsViewHandler,
)


def test_clipboard_view_modular():
    handler = ClipboardViewHandler(max_history=5)
    component = ClipboardViewComponent(handler)

    raw = "İletişim: 5551234567, gizli: 1234-5678-9012-3456"
    masked, count = component.redact_and_record(raw, direction="out", timestamp=1000.0)

    assert "5551234567" not in masked
    assert count >= 1
    assert len(handler.get_history()) == 1

    handler.clear_history()
    assert len(handler.get_history()) == 0


def test_privacy_view_modular(tmp_path):
    handler = PrivacyViewHandler()
    component = PrivacyViewComponent(handler)

    p = tmp_path / "sample.txt"
    p.write_text("temiz dosya metni")

    results, stats = component.clean_dropped_paths([str(p)])
    assert stats["total"] == 1
    assert stats["success"] == 1
    assert stats["with_risk"] == 0

    md = handler.generate_report_markdown()
    assert "Metadata" in md or "sample.txt" in md


def test_discovery_view_modular():
    handler = DiscoveryViewHandler(local_name="TestDevice")
    component = DiscoveryViewComponent(handler)

    dev = handler.add_manual_device("192.168.1.50", 8900, "Pardus Node")
    assert dev.address == "192.168.1.50"

    filtered = component.filter_devices(query="Pardus")
    assert len(filtered) >= 1

    component.update_selection({"192.168.1.50:8900"})
    assert "192.168.1.50:8900" in component.selected_ids


def test_screen_share_view_modular():
    handler = ScreenShareViewHandler(device_name="TestScreenHost")
    component = ScreenShareViewComponent(handler)

    with mock.patch.object(handler, "start_host_stream", return_value="123456"):
        pin = component.start_host(on_pin=lambda p: None)
        assert pin == "123456"
        assert component.is_hosting is True

    with mock.patch.object(handler, "stop_host_stream"):
        component.stop_host()
        assert component.is_hosting is False


def test_mesh_view_modular():
    handler = MeshViewHandler()
    component = MeshViewComponent(handler)

    node = handler.ensure_node(port=18925)
    assert node is not None

    with mock.patch.object(node, "start"), mock.patch.object(node, "stop"):
        active = component.toggle_mesh(True)
        assert active is True
        assert component.is_active is True

        active = component.toggle_mesh(False)
        assert active is False
        assert component.is_active is False


def test_classroom_view_modular():
    handler = ClassroomViewHandler(role="ogretmen")
    component = ClassroomViewComponent(handler)

    perms = handler.get_role_permissions()
    assert perms["can_broadcast"] is True
    assert perms["can_create_quiz"] is True
    assert perms["can_answer_quiz"] is False

    raw_quiz = "Pardus hangi tabanlıdır? | RedHat | Debian | Arch | doğru:2"
    quiz = handler.create_quiz(raw_quiz, title="Pardus Bilgi")
    assert quiz.question_count == 1
    assert quiz.title == "Pardus Bilgi"

    component.update_targets({"192.168.1.10", "192.168.1.11"})
    assert component.is_target_selected() is True


def test_settings_view_modular():
    cfg_mock = mock.MagicMock()
    cfg_mock.get.return_value = True
    trust_mock = mock.MagicMock()
    trust_mock.list_trusted.return_value = {"FP1": {"name": "Tahta"}}

    handler = SettingsViewHandler(config=cfg_mock, trust_store=trust_mock)
    component = SettingsViewComponent(handler)
    assert component.handler is handler

    assert handler.get_auto_accept() is True
    assert len(handler.get_trusted_devices()) == 1
