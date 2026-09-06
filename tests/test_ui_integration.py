"""
Statik UI entegrasyon testleri - pytest fixture gerektirmez, doğrudan çalışır.
Mesh/WebRTC/Async modüllerinin window.py ve app.py'ye entegre olduğunu doğrular.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOW_FILE = os.path.join(REPO_ROOT, "src", "pardus_paylasim", "window.py")
APP_FILE = os.path.join(REPO_ROOT, "src", "pardus_paylasim", "app.py")


def _read(path):
    with open(path) as f:
        return f.read()


def test_window_has_mesh_tab():
    """_build_mesh_tab metodu window.py'de var mı?"""
    content = _read(WINDOW_FILE)
    assert "def _build_mesh_tab" in content


def test_window_added_mesh_to_stack():
    """'mesh' view_stack'e eklenmiş mi?"""
    content = _read(WINDOW_FILE)
    assert 'add_titled' in content
    assert '"mesh"' in content


def test_window_mesh_handler():
    """_on_mesh_toggle handler'ı MeshNode import ediyor mu?"""
    content = _read(WINDOW_FILE)
    assert "def _on_mesh_toggle" in content
    assert "MeshNode" in content


def test_window_async_handler():
    """_on_async_refresh handler'ı AsyncTransferStore import ediyor mu?"""
    content = _read(WINDOW_FILE)
    assert "def _on_async_refresh" in content
    assert "AsyncTransferStore" in content


def test_window_webrtc_section():
    """Mesh sekmesinde WebRTC bölümü var mı?"""
    content = _read(WINDOW_FILE)
    assert "WebRTC" in content
    assert "webrtc_status_row" in content


def test_window_no_hype_titles():
    """Abartılı başlıklar kullanılmamalı (Yenilikler/Devrim/AI)."""
    content = _read(WINDOW_FILE)
    assert "Yenilik" not in content
    assert "Devrim" not in content
    assert "devrim" not in content
    assert "Yapay Zeka" not in content
    assert "_on_ai_scan_demo" not in content
    assert "clipboard.ai" not in content


def test_window_tab_names_6_entries():
    """TAB_NAMES 6 sekme içermeli (son sekme: mesh)."""
    content = _read(WINDOW_FILE)
    assert "TAB_NAMES" in content
    for name in ("privacy", "discovery", "screenshare", "clipboard", "settings", "mesh"):
        assert f'"{name}"' in content, f"Missing tab: {name}"
    assert '"innovations"' not in content


def test_window_a11y_labels_on_buttons():
    """Mesh sekmesi butonlarında _set_a11y_label var mı?"""
    content = _read(WINDOW_FILE)
    assert "btn_mesh_toggle" in content
    assert "btn_async_refresh" in content
    assert "self._set_a11y_label(btn_mesh_toggle" in content
    assert "self._set_a11y_label(btn_async_refresh" in content


def test_window_mesh_peer_add():
    """Eş ekleme UI'ı (girdi + Ekle + handler) var mı?"""
    content = _read(WINDOW_FILE)
    assert "entry_mesh_peer" in content
    assert "def _on_mesh_peer_add" in content
    assert "add_peer" in content
    assert "self._set_a11y_label(btn_peer_add" in content


def test_window_clean_before_send():
    """Gönderim-öncesi temizlik seçeneği ve bağlantısı var mı?"""
    content = _read(WINDOW_FILE)
    assert "chk_clean_before_send" in content
    assert "prepare_send_file" in content
    assert "Göndermeden önce metadata temizle" in content


def test_window_mesh_discovery_wiring():
    """Keşif başlatma/durdurma ve eş sayaç tazeleme bağlı mı?"""
    content = _read(WINDOW_FILE)
    assert "start_discovery" in content
    assert "on_peer_discovered" in content
    assert "on_peer_lost" in content


def test_app_has_mesh_status_arg():
    content = _read(APP_FILE)
    assert "--mesh-status" in content


def test_app_has_async_list_arg():
    content = _read(APP_FILE)
    assert "--async-list" in content


def test_app_no_ai_scan_arg():
    """Kaldırılan AI komutu app.py'de olmamalı."""
    content = _read(APP_FILE)
    assert "--ai-scan" not in content
    assert "clipboard.ai" not in content
    assert "LocalSensitiveDetector" not in content


def test_app_help_lists_commands():
    content = _read(APP_FILE)
    assert "--mesh-status" in content
    assert "--async-list" in content


def test_window_uses_adw_preferences_group_in_mesh():
    """_build_mesh_tab Adw bileşenlerini kullanıyor mu?"""
    content = _read(WINDOW_FILE)
    in_mesh = content.split("def _build_mesh_tab")[1].split("def _on_mesh_toggle")[0]
    assert "Adw.PreferencesGroup" in in_mesh
    assert "Adw.ActionRow" in in_mesh


if __name__ == "__main__":
    tests = [
        ("window_has_mesh_tab", test_window_has_mesh_tab),
        ("window_added_mesh_to_stack", test_window_added_mesh_to_stack),
        ("window_mesh_handler", test_window_mesh_handler),
        ("window_async_handler", test_window_async_handler),
        ("window_webrtc_section", test_window_webrtc_section),
        ("window_no_hype_titles", test_window_no_hype_titles),
        ("window_tab_names_6_entries", test_window_tab_names_6_entries),
        ("window_a11y_labels_on_buttons", test_window_a11y_labels_on_buttons),
        ("window_mesh_peer_add", test_window_mesh_peer_add),
        ("window_clean_before_send", test_window_clean_before_send),
        ("window_mesh_discovery_wiring", test_window_mesh_discovery_wiring),
        ("app_has_mesh_status_arg", test_app_has_mesh_status_arg),
        ("app_has_async_list_arg", test_app_has_async_list_arg),
        ("app_no_ai_scan_arg", test_app_no_ai_scan_arg),
        ("app_help_lists_commands", test_app_help_lists_commands),
        ("window_uses_adw_preferences_group_in_mesh",
         test_window_uses_adw_preferences_group_in_mesh),
    ]
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            failed += 1
    print()
    print(f"Passed: {passed}, Failed: {failed}")
    sys.exit(0 if failed == 0 else 1)
