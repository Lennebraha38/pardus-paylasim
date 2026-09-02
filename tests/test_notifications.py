"""
Masaüstü bildirimi (notifications.send_notification) testleri.

GTK ortamdan bağımsız koşulabilmesi için sahte (fake) bir uygulama nesnesi
kullanılır; GTK varsa gerçek `Gio.Notification` yolu, yoksa zarif-düşüş yolu
sınanır.
"""

import unittest

from pardus_paylasim import notifications


class _FakeApp:
    """send_notification/withdraw_notification çağrılarını kaydeden sahte app."""

    def __init__(self):
        self.sent = []
        self.withdrawn = []

    def send_notification(self, notification_id, notification):
        self.sent.append((notification_id, notification))

    def withdraw_notification(self, notification_id):
        self.withdrawn.append(notification_id)


class TestSendNotification(unittest.TestCase):
    def test_returns_false_without_app(self):
        # app None ise bildirim gönderilemez ama istisna atmaz.
        ok = notifications.send_notification(None, "Başlık", "Gövde")
        self.assertFalse(ok)

    @unittest.skipUnless(notifications.HAS_GTK, "GTK kurulu değil")
    def test_sends_with_real_gtk(self):
        # GTK varsa gerçek Gio.Notification üretilip app'e iletilmeli.
        app = _FakeApp()
        ok = notifications.send_notification(
            app, "Yeni dosya", "belge.pdf", notification_id="file-received"
        )
        self.assertTrue(ok)
        self.assertEqual(len(app.sent), 1)
        self.assertEqual(app.sent[0][0], "file-received")

    @unittest.skipUnless(notifications.HAS_GTK, "GTK kurulu değil")
    def test_high_priority_accepted(self):
        # "high" öncelik hata atmadan işlenmeli.
        app = _FakeApp()
        ok = notifications.send_notification(app, "Acil", "mesaj", priority="high")
        self.assertTrue(ok)

    def test_falls_back_when_gtk_absent(self):
        # GTK yoksa app verilse bile False dönmeli (gönderim mümkün değil).
        if notifications.HAS_GTK:
            self.skipTest("GTK kurulu; fallback yolu test edilemez")
        app = _FakeApp()
        ok = notifications.send_notification(app, "X", "Y")
        self.assertFalse(ok)
        self.assertEqual(app.sent, [])


class TestWithdrawNotification(unittest.TestCase):
    def test_noop_without_app(self):
        # app None ise sessizce döner (istisna yok).
        notifications.withdraw_notification(None, "id")

    @unittest.skipUnless(notifications.HAS_GTK, "GTK kurulu değil")
    def test_withdraw_delegates(self):
        app = _FakeApp()
        notifications.withdraw_notification(app, "file-received")
        self.assertEqual(app.withdrawn, ["file-received"])


if __name__ == "__main__":
    unittest.main()
