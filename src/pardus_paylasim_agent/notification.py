"""BildirimSink şimi: plyer veya no-op.

ECC: Protocol duck typing, tip anotasyonları, KISS.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class NotificationSink(Protocol):
    """Bildirim sözleşmesi."""

    def notify(self, title: str, message: str) -> None: ...


class PlyerNotificationSink:
    """plyer backend (Windows toast bildirimleri)."""

    def notify(self, title: str, message: str) -> None:
        try:
            from plyer import notification

            notification.notify(title=title, message=message, timeout=5)
        except Exception as exc:
            logger.debug("plyer bildirim hatası: %s", exc)


class NoOpNotificationSink:
    """No-op fallback (plyer yoksa). ECC: sessiz yutma yok → logla."""

    def notify(self, title: str, message: str) -> None:
        logger.info("[Bildirim] %s: %s", title, message)


def create_notification_sink() -> NotificationSink:
    """Mevcut en iyi bildirim backend'ini döndür."""
    try:
        import plyer  # noqa: F401

        return PlyerNotificationSink()
    except ImportError:
        return NoOpNotificationSink()
