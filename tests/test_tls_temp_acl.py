"""
0.10 — Özel anahtar geçici dosyası izin kilidi (POSIX chmod / Windows icacls).

`_write_secure_temp` diske yazdığı özel anahtarı yalnız geçerli kullanıcıya
erişilebilir kılmalı. Windows'ta `os.chmod` izin bitlerini yok saydığından
`icacls /inheritance:r /grant:r <user>:F` ile miras ACE'ler kaldırılıp yalnız
kullanıcıya tam yetki verilir. Testler platformdan bağımsız: alt süreç ve OS
dalları monkeypatch'lenir, gerçek `icacls` gerektirmez.
"""

import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from pardus_paylasim.screen import tls_util


class TestWriteSecureTemp(unittest.TestCase):
    """Yazılan dosya içerik + izin kilidi yolunu tetikler."""

    def test_writes_content_and_returns_path(self):
        # Arrange / Act
        path = tls_util._write_secure_temp(b"gizli-anahtar", suffix=".key")
        try:
            with open(path, "rb") as f:
                data = f.read()
            # Assert
            self.assertEqual(data, b"gizli-anahtar")
            self.assertTrue(path.endswith(".key"))
        finally:
            os.unlink(path)

    def test_invokes_permission_lock(self):
        # Arrange
        with mock.patch.object(tls_util, "_lock_temp_permissions", return_value=True) as lock:
            # Act
            path = tls_util._write_secure_temp(b"x", suffix=".crt")
            try:
                # Assert: yazılan yol tam olarak kilit fonksiyonuna geçer.
                lock.assert_called_once_with(path)
            finally:
                os.unlink(path)


class TestLockTempPermissions(unittest.TestCase):
    """OS dalı: nt → icacls, posix → chmod."""

    def test_posix_uses_chmod(self):
        # Arrange
        with mock.patch.object(os, "name", "posix"), mock.patch.object(os, "chmod") as chmod:
            # Act
            result = tls_util._lock_temp_permissions("/tmp/x.key")
            # Assert
            chmod.assert_called_once_with("/tmp/x.key", 0o600)
            self.assertTrue(result)

    def test_posix_chmod_failure_returns_false(self):
        # chmod patlarsa best-effort False, istisna sızmaz.
        with (
            mock.patch.object(os, "name", "posix"),
            mock.patch.object(os, "chmod", side_effect=OSError("izin yok")),
        ):
            self.assertFalse(tls_util._lock_temp_permissions("/tmp/x.key"))

    def test_nt_delegates_to_icacls(self):
        # Arrange
        with (
            mock.patch.object(os, "name", "nt"),
            mock.patch.object(tls_util, "_restrict_windows_acl", return_value=True) as acl,
        ):
            # Act
            result = tls_util._lock_temp_permissions(r"C:\Temp\x.key")
            # Assert
            acl.assert_called_once_with(r"C:\Temp\x.key")
            self.assertTrue(result)


class TestRestrictWindowsAcl(unittest.TestCase):
    """`icacls` çağrısının doğru argümanlarla kurulması + hata yutma."""

    def _run_mock(self, returncode=0, stderr=b""):
        completed = mock.Mock()
        completed.returncode = returncode
        completed.stderr = stderr
        return completed

    def test_builds_expected_icacls_command(self):
        # Arrange: getpass/subprocess fonksiyon içinde import edilir; global
        # modül isimleri üzerinden patch'lenir.
        with (
            mock.patch("getpass.getuser", return_value="tevfik"),
            mock.patch("subprocess.run", return_value=self._run_mock(0)) as run,
        ):
            # Act
            result = tls_util._restrict_windows_acl(r"C:\Temp\x.key")
        # Assert
        self.assertTrue(result)
        args = run.call_args.args[0]
        self.assertEqual(args[0], "icacls")
        self.assertEqual(args[1], r"C:\Temp\x.key")
        self.assertIn("/inheritance:r", args)
        self.assertIn("/grant:r", args)
        self.assertIn("tevfik:F", args)

    def test_nonzero_returncode_returns_false(self):
        # icacls hata → False (yutulur, çağıran patlamaz).
        with (
            mock.patch("getpass.getuser", return_value="tevfik"),
            mock.patch(
                "subprocess.run",
                return_value=self._run_mock(5, b"erisim reddedildi"),
            ),
        ):
            self.assertFalse(tls_util._restrict_windows_acl(r"C:\Temp\x.key"))

    def test_icacls_missing_returns_false(self):
        # icacls PATH'te yok (OSError) → False.
        with (
            mock.patch("getpass.getuser", return_value="tevfik"),
            mock.patch("subprocess.run", side_effect=FileNotFoundError()),
        ):
            self.assertFalse(tls_util._restrict_windows_acl(r"C:\Temp\x.key"))

    def test_timeout_returns_false(self):
        # icacls asılırsa timeout → False.
        with (
            mock.patch("getpass.getuser", return_value="tevfik"),
            mock.patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired("icacls", 10),
            ),
        ):
            self.assertFalse(tls_util._restrict_windows_acl(r"C:\Temp\x.key"))

    def test_empty_username_returns_false(self):
        # Kullanıcı adı çözülemezse ACL kurulamaz → False (grant hedefi yok).
        with mock.patch("getpass.getuser", return_value=""):
            self.assertFalse(tls_util._restrict_windows_acl(r"C:\Temp\x.key"))


if __name__ == "__main__":
    unittest.main()
