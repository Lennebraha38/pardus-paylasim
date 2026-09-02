"""
Platform/oturum tespiti (`platform_info`) testleri.

Modül saf ve yan-etkisizdir → env değişkenleri ve `sys.platform`/`os.name`
monkeypatch ile kontrol edilir; gerçek OS'a bağımlı değildir, headless koşar.
"""

import os
import sys
import unittest
from unittest import mock

from pardus_paylasim import platform_info as pi


class TestOsDetection(unittest.TestCase):
    def test_is_windows_true_when_os_name_nt(self):
        # os.name == "nt" → Windows.
        with mock.patch.object(os, "name", "nt"):
            self.assertTrue(pi.is_windows())

    def test_is_windows_true_when_sys_platform_win(self):
        # sys.platform "win32" başlar → Windows (os.name farklı olsa bile).
        with mock.patch.object(os, "name", "posix"), mock.patch.object(sys, "platform", "win32"):
            self.assertTrue(pi.is_windows())

    def test_is_linux_true_on_linux_platform(self):
        with mock.patch.object(sys, "platform", "linux"):
            self.assertTrue(pi.is_linux())

    def test_windows_and_linux_mutually_exclusive(self):
        with mock.patch.object(os, "name", "nt"), mock.patch.object(sys, "platform", "win32"):
            self.assertTrue(pi.is_windows())
            self.assertFalse(pi.is_linux())


class TestSessionType(unittest.TestCase):
    def test_windows_session_is_windows(self):
        with mock.patch.object(os, "name", "nt"), mock.patch.object(sys, "platform", "win32"):
            self.assertEqual(pi.session_type(), pi.SESSION_WINDOWS)

    def test_xdg_wayland_wins(self):
        # XDG_SESSION_TYPE=wayland → wayland (DISPLAY set olsa bile).
        env = {"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0"}
        with (
            mock.patch.object(sys, "platform", "linux"),
            mock.patch.object(os, "name", "posix"),
            mock.patch.dict(os.environ, env, clear=True),
        ):
            self.assertEqual(pi.session_type(), pi.SESSION_WAYLAND)
            self.assertTrue(pi.is_wayland())
            self.assertFalse(pi.is_x11())

    def test_xdg_x11_gives_x11(self):
        env = {"XDG_SESSION_TYPE": "x11"}
        with (
            mock.patch.object(sys, "platform", "linux"),
            mock.patch.object(os, "name", "posix"),
            mock.patch.dict(os.environ, env, clear=True),
        ):
            self.assertEqual(pi.session_type(), pi.SESSION_X11)
            self.assertTrue(pi.is_x11())
            self.assertFalse(pi.is_wayland())

    def test_wayland_display_fallback_when_xdg_missing(self):
        # XDG yok ama WAYLAND_DISPLAY var → wayland.
        env = {"WAYLAND_DISPLAY": "wayland-0"}
        with (
            mock.patch.object(sys, "platform", "linux"),
            mock.patch.object(os, "name", "posix"),
            mock.patch.dict(os.environ, env, clear=True),
        ):
            self.assertEqual(pi.session_type(), pi.SESSION_WAYLAND)

    def test_display_fallback_when_xdg_missing(self):
        # XDG yok, WAYLAND_DISPLAY yok, DISPLAY var → x11.
        env = {"DISPLAY": ":0"}
        with (
            mock.patch.object(sys, "platform", "linux"),
            mock.patch.object(os, "name", "posix"),
            mock.patch.dict(os.environ, env, clear=True),
        ):
            self.assertEqual(pi.session_type(), pi.SESSION_X11)

    def test_no_signals_gives_unknown(self):
        # Linux, hiç sinyal yok (SSH/headless) → unknown, exception atmaz.
        with (
            mock.patch.object(sys, "platform", "linux"),
            mock.patch.object(os, "name", "posix"),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            self.assertEqual(pi.session_type(), pi.SESSION_UNKNOWN)
            self.assertFalse(pi.is_wayland())
            self.assertFalse(pi.is_x11())


class TestOsLabel(unittest.TestCase):
    def test_linux_reads_pretty_name(self):
        with (
            mock.patch.object(pi, "is_linux", return_value=True),
            mock.patch.object(
                pi, "_read_os_release_pretty_name", return_value="Pardus 25 GNU/Linux"
            ),
        ):
            self.assertEqual(pi.current_os_label(), "Pardus 25 GNU/Linux")

    def test_linux_falls_back_when_pretty_name_empty(self):
        # os-release okunamaz → platform.system()/release() fallback.
        with (
            mock.patch.object(pi, "is_linux", return_value=True),
            mock.patch.object(pi, "is_windows", return_value=False),
            mock.patch.object(pi, "_read_os_release_pretty_name", return_value=""),
            mock.patch.object(pi.platform, "system", return_value="Linux"),
            mock.patch.object(pi.platform, "release", return_value="6.1.0"),
        ):
            self.assertEqual(pi.current_os_label(), "Linux 6.1.0")

    def test_windows_label(self):
        with (
            mock.patch.object(pi, "is_linux", return_value=False),
            mock.patch.object(pi, "is_windows", return_value=True),
            mock.patch.object(pi.platform, "release", return_value="11"),
        ):
            self.assertEqual(pi.current_os_label(), "Windows 11")


class TestOsReleaseParse(unittest.TestCase):
    def test_strips_quotes(self):
        data = 'NAME="Pardus"\nPRETTY_NAME="Pardus 25 GNU/Linux"\nID=pardus\n'
        with mock.patch("builtins.open", mock.mock_open(read_data=data)):
            self.assertEqual(pi._read_os_release_pretty_name(), "Pardus 25 GNU/Linux")

    def test_missing_file_returns_empty(self):
        with mock.patch("builtins.open", side_effect=OSError("yok")):
            self.assertEqual(pi._read_os_release_pretty_name(), "")

    def test_no_pretty_name_returns_empty(self):
        data = "NAME=Pardus\nID=pardus\n"
        with mock.patch("builtins.open", mock.mock_open(read_data=data)):
            self.assertEqual(pi._read_os_release_pretty_name(), "")


class TestPaths(unittest.TestCase):
    def test_temp_dir_returns_string(self):
        result = pi.temp_dir()
        self.assertIsInstance(result, str)
        self.assertTrue(result)

    def test_downloads_windows(self):
        with (
            mock.patch.object(pi, "is_windows", return_value=True),
            mock.patch.object(os.path, "expanduser", return_value="C:\\Users\\Test"),
        ):
            result = pi.downloads_dir()
            self.assertTrue(result.endswith("Downloads"))
            self.assertIn("Test", result)

    def test_downloads_linux_prefers_pardus_indirilenler(self):
        # Pardus TR dizini varsa onu seç. (os.path.join → host ayracı.)
        with (
            mock.patch.object(pi, "is_windows", return_value=False),
            mock.patch.object(os.path, "expanduser", return_value="/home/u"),
            mock.patch.object(os.path, "isdir", return_value=True),
        ):
            self.assertEqual(pi.downloads_dir(), os.path.join("/home/u", "İndirilenler"))

    def test_downloads_linux_falls_back_to_downloads(self):
        # İndirilenler yoksa ~/Downloads.
        with (
            mock.patch.object(pi, "is_windows", return_value=False),
            mock.patch.object(os.path, "expanduser", return_value="/home/u"),
            mock.patch.object(os.path, "isdir", return_value=False),
        ):
            self.assertEqual(pi.downloads_dir(), os.path.join("/home/u", "Downloads"))


if __name__ == "__main__":
    unittest.main()
