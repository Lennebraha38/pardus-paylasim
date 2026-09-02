"""
`control_server` consent / oturum-token testleri (headless).

Kapsam (1.10 — C7 consent yarısı):
  - Token YALNIZ grant sonrası verilir; host toggle kapalıyken grant None.
  - Per-mesaj token doğrulama: doğru IP+token geçer; yanlış-IP token, eksik
    veya yanlış token reddedilir.
  - `revoke`: tek istemcinin token'ını düşürür; başka IP etkilenmez.
  - Kill-switch (`set_allowed(False)`): TÜM aktif token'ları anında iptal eder
    → mevcut oturumlar bir sonraki mesajda yetkisiz kalır.
  - Tehlikeli tuş (VT-geçiş Ctrl+Alt+F*) filtresi + opt-in toggle.
  - Kontrol oturumu denetim (audit) kaydı: start/stop `history`'ye yazılır.

Hiçbir test soket/GTK gerektirmez: `ControlConsent`, saf `is_dangerous_key`
ve `ControlChannelServer._audit` doğrudan sürülür. Test stili: unittest,
TR docstring, AAA (Arrange/Act/Assert).
"""

from __future__ import annotations

import os
import tempfile
import unittest

from pardus_paylasim import platform_info
from pardus_paylasim.discovery.history import (
    DIRECTION_CONTROL,
    STATUS_CONTROL_START,
    STATUS_CONTROL_STOP,
    TransferHistory,
)
from pardus_paylasim.screen import control_protocol as cp
from pardus_paylasim.screen import input_inject
from pardus_paylasim.screen.control_server import (
    ControlChannelServer,
    ControlConsent,
    is_dangerous_key,
)

_IP_A = "192.168.1.50"
_IP_B = "192.168.1.51"


class TestGrantIssuesToken(unittest.TestCase):
    """Token yalnız host toggle açıkken ve grant çağrısıyla üretilir."""

    def test_grant_before_allow_returns_none(self):
        """Toggle kapalıyken grant token vermez (default KAPALI kapısı)."""
        # Arrange
        consent = ControlConsent()

        # Act
        token = consent.grant(_IP_A)

        # Assert
        self.assertIsNone(token)

    def test_grant_after_allow_returns_token(self):
        """Toggle açıkken grant kriptografik token döndürür."""
        # Arrange
        consent = ControlConsent()
        consent.set_allowed(True)

        # Act
        token = consent.grant(_IP_A)

        # Assert
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 16)

    def test_two_clients_get_distinct_tokens(self):
        """Ayrı IP'ler ayrı token alır (biri diğerinin yerine geçemez)."""
        # Arrange
        consent = ControlConsent()
        consent.set_allowed(True)

        # Act
        token_a = consent.grant(_IP_A)
        token_b = consent.grant(_IP_B)

        # Assert
        self.assertNotEqual(token_a, token_b)

    def test_default_not_allowed(self):
        """Yeni consent defteri default KAPALI olmalı."""
        # Arrange / Act
        consent = ControlConsent()

        # Assert
        self.assertFalse(consent.is_allowed())


class TestValidatePerMessage(unittest.TestCase):
    """Per-mesaj token doğrulama: yalnız doğru IP+token geçer."""

    def setUp(self):
        self.consent = ControlConsent()
        self.consent.set_allowed(True)
        self.token = self.consent.grant(_IP_A)

    def test_correct_ip_and_token_passes(self):
        """Grant edilen IP + doğru token → geçerli."""
        # Act / Assert
        self.assertTrue(self.consent.validate(_IP_A, self.token))

    def test_wrong_ip_token_rejected(self):
        """Doğru token yanlış IP'den gelirse reddedilir (IP'ye bağlı)."""
        # Act / Assert — _IP_B için hiç token yok
        self.assertFalse(self.consent.validate(_IP_B, self.token))

    def test_missing_token_rejected(self):
        """Eksik/boş sid reddedilir (mesaj düşer)."""
        # Act / Assert
        self.assertFalse(self.consent.validate(_IP_A, None))
        self.assertFalse(self.consent.validate(_IP_A, ""))

    def test_wrong_token_rejected(self):
        """Yanlış token değeri reddedilir (tahmin/eski token)."""
        # Act / Assert
        self.assertFalse(self.consent.validate(_IP_A, "yanlis-token"))

    def test_validate_false_when_not_allowed(self):
        """Toggle kapandıysa geçerli token bile reddedilir."""
        # Arrange
        self.consent.set_allowed(False)

        # Act / Assert
        self.assertFalse(self.consent.validate(_IP_A, self.token))


class TestRevoke(unittest.TestCase):
    """`revoke` tek istemcinin token'ını düşürür; başka IP etkilenmez."""

    def test_revoke_drops_only_target(self):
        """Bir IP revoke edilince yalnız o token ölür; diğeri yaşar."""
        # Arrange
        consent = ControlConsent()
        consent.set_allowed(True)
        token_a = consent.grant(_IP_A)
        token_b = consent.grant(_IP_B)

        # Act
        consent.revoke(_IP_A)

        # Assert
        self.assertFalse(consent.validate(_IP_A, token_a))
        self.assertTrue(consent.validate(_IP_B, token_b))

    def test_revoke_unknown_ip_noop(self):
        """Kayıtlı olmayan IP'yi revoke etmek hata vermez (idempotent)."""
        # Arrange
        consent = ControlConsent()
        consent.set_allowed(True)

        # Act / Assert — istisna fırlatmamalı
        consent.revoke("10.0.0.99")


class TestKillSwitch(unittest.TestCase):
    """Kill-switch: `set_allowed(False)` tüm token'ları anında iptal eder."""

    def test_disable_clears_all_tokens(self):
        """Toggle kapatınca aktif her oturum yetkisiz kalır."""
        # Arrange
        consent = ControlConsent()
        consent.set_allowed(True)
        token_a = consent.grant(_IP_A)
        token_b = consent.grant(_IP_B)

        # Act — kill-switch
        consent.set_allowed(False)

        # Assert — ikisi de düştü
        self.assertFalse(consent.validate(_IP_A, token_a))
        self.assertFalse(consent.validate(_IP_B, token_b))

    def test_reenable_issues_fresh_token(self):
        """Yeniden açınca ESKI token geçersiz; yeni token üretilir."""
        # Arrange
        consent = ControlConsent()
        consent.set_allowed(True)
        old_token = consent.grant(_IP_A)
        consent.set_allowed(False)

        # Act
        consent.set_allowed(True)
        new_token = consent.grant(_IP_A)

        # Assert
        self.assertNotEqual(old_token, new_token)
        self.assertFalse(consent.validate(_IP_A, old_token))
        self.assertTrue(consent.validate(_IP_A, new_token))


class TestServerConsentDelegation(unittest.TestCase):
    """`ControlChannelServer` consent kapısını doğru devreder."""

    def _server(self):
        # Stream server audit/consent yolunda kullanılmaz → sentinel yeterli.
        return ControlChannelServer(stream_server=object())

    def test_set_control_allowed_toggles(self):
        """`set_control_allowed` consent defterini açar/kapatır."""
        # Arrange
        server = self._server()
        self.assertFalse(server.is_control_allowed())

        # Act
        server.set_control_allowed(True)

        # Assert
        self.assertTrue(server.is_control_allowed())

    def test_dangerous_keys_default_off(self):
        """VT-geçiş tuşları default bloklu (opt-in)."""
        # Arrange / Act
        server = self._server()

        # Assert
        self.assertFalse(server.is_dangerous_keys_allowed())

    def test_dangerous_keys_toggle(self):
        """`set_allow_dangerous_keys` opt-in bayrağını çevirir."""
        # Arrange
        server = self._server()

        # Act
        server.set_allow_dangerous_keys(True)

        # Assert
        self.assertTrue(server.is_dangerous_keys_allowed())


class TestDangerousKeyFilter(unittest.TestCase):
    """Saf `is_dangerous_key`: VT-geçiş (Ctrl+Alt+F*) tespiti."""

    def test_ctrl_alt_f1_is_dangerous(self):
        """Ctrl+Alt+F1 VT geçişidir → tehlikeli."""
        # Arrange
        event = cp.KeyEvent(code="KEY_F1", down=True, mods=("alt", "ctrl"))

        # Act / Assert
        self.assertTrue(is_dangerous_key(event))

    def test_all_f_keys_dangerous_with_ctrl_alt(self):
        """F1..F12 tümü Ctrl+Alt ile tehlikeli sayılır."""
        # Arrange / Act / Assert
        for n in range(1, 13):
            event = cp.KeyEvent(code=f"KEY_F{n}", down=True, mods=("alt", "ctrl"))
            self.assertTrue(is_dangerous_key(event), f"KEY_F{n} tehlikeli olmalı")

    def test_f1_without_both_mods_safe(self):
        """Yalnız Ctrl (Alt yok) ile F1 tehlikeli değil."""
        # Arrange
        event = cp.KeyEvent(code="KEY_F1", down=True, mods=("ctrl",))

        # Act / Assert
        self.assertFalse(is_dangerous_key(event))

    def test_ordinary_key_safe(self):
        """Sıradan tuş (Ctrl+Alt+A) VT geçişi değil → güvenli."""
        # Arrange
        event = cp.KeyEvent(code="KEY_A", down=True, mods=("alt", "ctrl"))

        # Act / Assert
        self.assertFalse(is_dangerous_key(event))

    def test_non_key_event_safe(self):
        """KeyEvent olmayan olay (Move) asla tehlikeli değil."""
        # Arrange
        event = cp.MoveEvent(x=0.5, y=0.5)

        # Act / Assert
        self.assertFalse(is_dangerous_key(event))


class TestControlAudit(unittest.TestCase):
    """Kontrol oturumu denetim (audit) kaydı `history`'ye yazılır (C4)."""

    def setUp(self):
        # Geçici JSONL: gerçek ~/.config'e dokunma.
        fd, self._path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        self.history = TransferHistory(path=self._path)
        self.server = ControlChannelServer(stream_server=object(), history=self.history)

    def tearDown(self):
        if os.path.exists(self._path):
            os.remove(self._path)

    def test_audit_start_recorded(self):
        """Kontrol başlangıcı DIRECTION_CONTROL + start olarak kaydedilir."""
        # Act
        self.server._audit(_IP_A, STATUS_CONTROL_START, "xtest")

        # Assert
        rows = self.history.read_all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["direction"], DIRECTION_CONTROL)
        self.assertEqual(rows[0]["status"], STATUS_CONTROL_START)
        self.assertEqual(rows[0]["peer"], _IP_A)

    def test_audit_start_and_stop_recorded(self):
        """Başlangıç + bitiş iki ayrı denetim satırı üretir."""
        # Act
        self.server._audit(_IP_A, STATUS_CONTROL_START, "xtest")
        self.server._audit(_IP_A, STATUS_CONTROL_STOP, "ended")

        # Assert
        rows = self.history.read_all()
        statuses = {r["status"] for r in rows}
        self.assertEqual(len(rows), 2)
        self.assertIn(STATUS_CONTROL_START, statuses)
        self.assertIn(STATUS_CONTROL_STOP, statuses)


class TestAvailableBackendProbe(unittest.TestCase):
    """`available_backend_name` probe: enjekte etmeden backend adı bildirir.

    `/info` bunu yayar → istemci kontrol İSTEMEDEN kontrolün mümkün olup
    olmadığını bilir. Yan etki yok (grant yok, backend kurulmaz).
    """

    def _server(self):
        return ControlChannelServer(stream_server=object())

    def test_none_when_no_backend(self):
        """Hiçbir backend mevcut değilse None (kontrol reddedilecek)."""
        # Arrange
        server = self._server()
        original = input_inject.detect_availability
        input_inject.detect_availability = lambda: {
            "portal": False,
            "ydotool": False,
            "xtest": False,
            "pynput": False,
        }
        try:
            # Act
            name = server.available_backend_name()
        finally:
            input_inject.detect_availability = original

        # Assert
        self.assertIsNone(name)

    def test_picks_xtest_on_x11(self):
        """X11 oturumda XTEST mevcutsa 'xtest' seçilir (öncelik)."""
        # Arrange
        server = self._server()
        orig_avail = input_inject.detect_availability
        orig_sess = platform_info.session_type
        input_inject.detect_availability = lambda: {
            "portal": False,
            "ydotool": False,
            "xtest": True,
            "pynput": True,
        }
        platform_info.session_type = lambda: platform_info.SESSION_X11
        try:
            # Act
            name = server.available_backend_name()
        finally:
            input_inject.detect_availability = orig_avail
            platform_info.session_type = orig_sess

        # Assert
        self.assertEqual(name, "xtest")

    def test_probe_does_not_grant(self):
        """Probe consent defterini değiştirmez (token üretmez, izin vermez)."""
        # Arrange
        server = self._server()

        # Act
        server.available_backend_name()

        # Assert — probe salt-okunur
        self.assertFalse(server.is_control_allowed())


if __name__ == "__main__":
    unittest.main()
