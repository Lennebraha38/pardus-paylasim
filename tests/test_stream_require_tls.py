"""
0.9 — require_tls: TLS-strip (downgrade) saldırısına karşı istemci kilidi.

İki açık kapatılır: (1) `_open`'ın sessiz https→http fallback'i, (2)
`_verify_pinned_fingerprint`'in düz HTTP'de doğrulamayı atlaması. require_tls
açıkken istemci ne düz HTTP'ye düşer ne de şifresiz akışı kabul eder — aktif
MITM https'i bloklayıp downgrade zorlayamaz.
"""

import os
import sys
import unittest
import unittest.mock
import urllib.error
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from pardus_paylasim.screen import tls_util
from pardus_paylasim.screen.stream_client import ScreenStreamClient


class TestRequireTlsDefault(unittest.TestCase):
    """require_tls varsayılanı HAS_TLS'i izler; açık parametre geçersiz kılar."""

    def test_default_follows_has_tls(self):
        # Cryptography kurulu (test ortamı) → varsayılan zorunlu TLS.
        client = ScreenStreamClient()
        self.assertEqual(client.require_tls, tls_util.HAS_TLS)

    def test_explicit_true_overrides(self):
        self.assertTrue(ScreenStreamClient(require_tls=True).require_tls)

    def test_explicit_false_overrides(self):
        # Asgari geliştirme kurulumu: düz HTTP'ye bilinçli izin.
        self.assertFalse(ScreenStreamClient(require_tls=False).require_tls)


class TestVerifyUnderRequireTls(unittest.TestCase):
    """Şifresiz/pinlenmemiş akış require_tls altında reddedilir."""

    def test_plain_http_rejected_when_required(self):
        # use_tls False + require_tls True → doğrulama başarısız (akış iptal).
        client = ScreenStreamClient(require_tls=True)
        client.use_tls = False
        self.assertFalse(client._verify_pinned_fingerprint())

    def test_unresolved_scheme_rejected_when_required(self):
        # Raw-socket ping şema çözemeden (use_tls None) require_tls altında
        # verify düşer — hayalet düz-HTTP yolu kapanır.
        client = ScreenStreamClient(require_tls=True)
        client.use_tls = None
        self.assertFalse(client._verify_pinned_fingerprint())

    def test_plain_http_allowed_when_not_required(self):
        # require_tls kapalı: düz HTTP doğrulamayı atlar (eski davranış).
        client = ScreenStreamClient(require_tls=False)
        client.use_tls = False
        self.assertTrue(client._verify_pinned_fingerprint())


class TestOpenNoDowngrade(unittest.TestCase):
    """`_open`: require_tls iken https başarısızsa http'ye ASLA düşülmez."""

    def _tracking_client(self, require_tls):
        client = ScreenStreamClient(require_tls=require_tls)
        attempts = []

        def fake_open_scheme(host_ip, port, path, timeout, tls):
            attempts.append(tls)
            if tls:
                raise urllib.error.URLError("https bloklandı (sahte MITM)")
            return "PLAIN_HTTP_RESPONSE"

        client._open_scheme = fake_open_scheme
        return client, attempts

    def test_no_http_fallback_when_required(self):
        # https denenir (tls=True), patlar; http (tls=False) DENENMEZ, hata yükselir.
        client, attempts = self._tracking_client(require_tls=True)
        with self.assertRaises(urllib.error.URLError):
            client._open("10.0.0.5", 52345, "/info", 5)
        self.assertEqual(attempts, [True])
        self.assertIsNone(client.use_tls)  # şema düz HTTP'ye kilitlenmedi

    def test_http_fallback_when_not_required(self):
        # require_tls kapalı: https patlayınca http'ye düşülür, use_tls False olur.
        client, attempts = self._tracking_client(require_tls=False)
        resp = client._open("10.0.0.5", 52345, "/info", 5)
        self.assertEqual(resp, "PLAIN_HTTP_RESPONSE")
        self.assertEqual(attempts, [True, False])
        self.assertFalse(client.use_tls)


class TestTrustStoreVerification(unittest.TestCase):
    """Trust store içindeki fingerprint uyuşmazlığında reddedilir."""

    def test_trust_store_mismatch_rejected(self):
        client = ScreenStreamClient(require_tls=True)
        client.use_tls = True
        client.target_ip = "10.0.0.1"
        client.target_port = 52345

        import unittest.mock

        with (
            unittest.mock.patch(
                "pardus_paylasim.screen.tls_util.get_peer_fingerprint",
                return_value="fake_fingerprint",
            ),
            unittest.mock.patch(
                "pardus_paylasim.screen.trust_store.get_trusted_fingerprint",
                return_value="real_fingerprint",
            ),
        ):
            self.assertFalse(client._verify_pinned_fingerprint())


class TestExplicitTrustBootstrap(unittest.TestCase):
    """TOFU (İlk Bağlantı) güvenlik döngüsü: Onay (callback) olmadan kayıt yapılamaz."""

    def setUp(self):
        self.client = ScreenStreamClient(require_tls=True)
        self.client.use_tls = True
        self.client.target_ip = "10.0.0.1"
        self.client.target_port = 52345
        self.client.target_device_id = "test-dev-id"

    @unittest.mock.patch(
        "pardus_paylasim.screen.tls_util.get_peer_fingerprint", return_value="live_fp_123"
    )
    @unittest.mock.patch(
        "pardus_paylasim.screen.trust_store.get_trusted_fingerprint", return_value=None
    )
    def test_new_device_no_callback_rejected(self, mock_get_trust, mock_get_peer):
        """Yeni cihaz + kullanıcı onayı yok → reddedilir"""
        self.client.pinned_fingerprint = "live_fp_123"
        self.client.trust_callback = None
        self.assertFalse(self.client._verify_pinned_fingerprint())

    @unittest.mock.patch(
        "pardus_paylasim.screen.tls_util.get_peer_fingerprint", return_value="live_fp_123"
    )
    @unittest.mock.patch(
        "pardus_paylasim.screen.trust_store.get_trusted_fingerprint", return_value=None
    )
    @unittest.mock.patch("pardus_paylasim.screen.trust_store.add_trusted_fingerprint")
    def test_new_device_approved_saved(self, mock_add_trust, mock_get_trust, mock_get_peer):
        """Yeni cihaz + onaylı fingerprint → kaydedilir"""
        self.client.pinned_fingerprint = "live_fp_123"
        self.client.trust_callback = lambda fp: True
        self.assertTrue(self.client._verify_pinned_fingerprint())
        mock_add_trust.assert_called_once_with("test-dev-id", "live_fp_123")

    @unittest.mock.patch(
        "pardus_paylasim.screen.tls_util.get_peer_fingerprint", return_value="live_fp_123"
    )
    @unittest.mock.patch(
        "pardus_paylasim.screen.trust_store.get_trusted_fingerprint", return_value=None
    )
    @unittest.mock.patch("pardus_paylasim.screen.trust_store.add_trusted_fingerprint")
    def test_new_device_rejected_callback(self, mock_add_trust, mock_get_trust, mock_get_peer):
        """Yeni cihaz + callback'ten false dönüşü → reddedilir"""
        self.client.pinned_fingerprint = "live_fp_123"
        self.client.trust_callback = lambda fp: False
        self.assertFalse(self.client._verify_pinned_fingerprint())
        mock_add_trust.assert_not_called()

    @unittest.mock.patch(
        "pardus_paylasim.screen.tls_util.get_peer_fingerprint", return_value="live_fp_123"
    )
    @unittest.mock.patch(
        "pardus_paylasim.screen.trust_store.get_trusted_fingerprint", return_value="live_fp_123"
    )
    def test_known_device_correct_fingerprint_accepted(self, mock_get_trust, mock_get_peer):
        """Kayıtlı cihaz + doğru fingerprint → kabul"""
        # Pinned değerine gerek yok, trust_store'da var.
        self.assertTrue(self.client._verify_pinned_fingerprint())

    @unittest.mock.patch(
        "pardus_paylasim.screen.tls_util.get_peer_fingerprint", return_value="fake_fp_999"
    )
    @unittest.mock.patch(
        "pardus_paylasim.screen.trust_store.get_trusted_fingerprint", return_value="live_fp_123"
    )
    def test_known_device_wrong_fingerprint_rejected(self, mock_get_trust, mock_get_peer):
        """Kayıtlı cihaz + değişmiş fingerprint → red"""
        self.assertFalse(self.client._verify_pinned_fingerprint())

    @unittest.mock.patch(
        "pardus_paylasim.screen.tls_util.get_peer_fingerprint",
        side_effect=Exception("Corrupted store"),
    )
    def test_broken_trust_store_fail_closed(self, mock_get_peer):
        """Bozuk trust store / hata → fail-closed"""
        self.assertFalse(self.client._verify_pinned_fingerprint())


if __name__ == "__main__":
    unittest.main()
