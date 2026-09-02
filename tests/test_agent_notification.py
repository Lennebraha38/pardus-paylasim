"""Faz 3.3: Bildirim şimi testleri."""

from __future__ import annotations

from pardus_paylasim_agent.notification import (
    NoOpNotificationSink,
    NotificationSink,
    PlyerNotificationSink,
    create_notification_sink,
)


class TestNotificationSink:
    """Bildirim backend testleri."""

    def test_plyer_protocol_uyumu(self) -> None:
        sink = PlyerNotificationSink()
        assert isinstance(sink, NotificationSink)

    def test_noop_protocol_uyumu(self) -> None:
        sink = NoOpNotificationSink()
        assert isinstance(sink, NotificationSink)

    def test_noop_hata_firlatmaz(self) -> None:
        sink = NoOpNotificationSink()
        sink.notify("Başlık", "Mesaj")  # Hata fırlatmamalı

    def test_create_sink_gecerli_tip_doner(self) -> None:
        sink = create_notification_sink()
        assert isinstance(sink, NotificationSink)
