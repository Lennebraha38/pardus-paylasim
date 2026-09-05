"""
Statik UI entegrasyon testleri - pytest fixture gerektirmez, doğrudan çalışır.
4 yeni modülün window.py ve app.py'ye entegre olduğunu doğrular.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOW_FILE = os.path.join(REPO_ROOT, "src", "pardus_paylasim", "window.py")
APP_FILE = os.path.join(REPO_ROOT, "src", "pardus_paylasim", "app.py")


def _read(path):
    with open(path) as f:
        return f.read()


def test_window_has_innovations_tab():
    """_build_innovations_tab metodu window.py'de var mı?"""
    content = _read(WINDOW_FILE)
    assert "def _build_innovations_tab" in content


def test_window_added_innovations_to_stack():
    """'innovations' view_stack'e eklenmiş mi?"""
    content = _read(WINDOW_FILE)
    assert 'add_titled' in content
    assert '"innovations"' in content


def test_window_mesh_handler():
    """_on_mesh_toggle handler'ı MeshNode import ediyor mu?"""
    content = _read(WINDOW_FILE)
    assert "def _on_mesh_toggle" in content
    assert "MeshNode" in content


def test_window_ai_handler():
    """_on_ai_scan_demo handler'ı LocalSensitiveDetector import ediyor mu?"""
    content = _read(WINDOW_FILE)
    assert "def _on_ai_scan_demo" in content
    assert "LocalSensitiveDetector" in content


def test_window_async_handler():
    """_on_async_refresh handler'ı AsyncTransferStore import ediyor mu?"""
    content = _read(WINDOW_FILE)
    assert "def _on_async_refresh" in content
    assert "AsyncTransferStore" in content


def test_window_tab_names_6_entries():
    """TAB_NAMES 6 sekme içermeli."""
    content = _read(WINDOW_FILE)
    assert "TAB_NAMES" in content
    for name in ("privacy", "discovery", "screenshare", "clipboard", "settings", "innovations"):
        assert f'"{name}"' in content, f"Missing tab: {name}"


def test_window_a11y_labels_on_buttons():
    """Yenilik sekmesi butonlarında _set_a11y_label var mı?"""
    content = _read(WINDOW_FILE)
    assert "btn_mesh_toggle" in content
    assert "btn_ai_scan" in content
    assert "btn_async_refresh" in content
    # A11y label çağrıları
    assert "self._set_a11y_label(btn_mesh_toggle" in content
    assert "self._set_a11y_label(btn_ai_scan" in content
    assert "self._set_a11y_label(btn_async_refresh" in content


def test_app_has_ai_scan_arg():
    content = _read(APP_FILE)
    assert "--ai-scan" in content


def test_app_has_mesh_status_arg():
    content = _read(APP_FILE)
    assert "--mesh-status" in content


def test_app_has_async_list_arg():
    content = _read(APP_FILE)
    assert "--async-list" in content


def test_app_imports_local_detector():
    content = _read(APP_FILE)
    assert "from pardus_paylasim.clipboard.ai.local_detector import LocalSensitiveDetector" in content


def test_app_help_lists_new_commands():
    content = _read(APP_FILE)
    assert "--ai-scan" in content
    assert "--mesh-status" in content
    assert "--async-list" in content


def test_window_uses_adw_preferences_group_in_innovations():
    """_build_innovations_tab Adw bileşenlerini kullanıyor mu?"""
    content = _read(WINDOW_FILE)
    # _build_innovations_tab içinde Adw.PreferencesGroup kullanılmalı
    in_innovations = content.split("def _build_innovations_tab")[1].split("def _on_mesh_toggle")[0]
    assert "Adw.PreferencesGroup" in in_innovations
    assert "Adw.ActionRow" in in_innovations


if __name__ == "__main__":
    tests = [
        ("window_has_innovations_tab", test_window_has_innovations_tab),
        ("window_added_innovations_to_stack", test_window_added_innovations_to_stack),
        ("window_mesh_handler", test_window_mesh_handler),
        ("window_ai_handler", test_window_ai_handler),
        ("window_async_handler", test_window_async_handler),
        ("window_tab_names_6_entries", test_window_tab_names_6_entries),
        ("window_a11y_labels_on_buttons", test_window_a11y_labels_on_buttons),
        ("app_has_ai_scan_arg", test_app_has_ai_scan_arg),
        ("app_has_mesh_status_arg", test_app_has_mesh_status_arg),
        ("app_has_async_list_arg", test_app_has_async_list_arg),
        ("app_imports_local_detector", test_app_imports_local_detector),
        ("app_help_lists_new_commands", test_app_help_lists_new_commands),
        ("window_uses_adw_preferences_group_in_innovations",
         test_window_uses_adw_preferences_group_in_innovations),
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
