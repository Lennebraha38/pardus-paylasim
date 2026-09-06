"""
Masaüstü bildirimleri.

Dosya/pano alımı gibi olayları kullanıcıya işletim sistemi bildirim
merkezinden duyurur. GNOME/Pardus'ta `Gio.Notification` +
`Gtk.Application.send_notification` kullanılır; pencere odakta değilken bile
görünür (uygulama-içi toast'ları tamamlar, yerini almaz).

GTK yoksa (headless sunucu / asgari kurulum) sessizce log'a düşer — proje
genelindeki zarif-düşüş (graceful degradation) kalıbıyla tutarlı.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gio  # type: ignore

    HAS_GTK = True
except (ImportError, ValueError):
    HAS_GTK = False


# Bildirim önemi -> Gio.NotificationPriority eşlemesi.
# Sabit anahtarlar; çağıran taraf GTK türlerini import etmek zorunda kalmaz.
_PRIORITY_NORMAL = "normal"
_PRIORITY_HIGH = "high"


def send_notification(
    app: Optional[object],
    title: str,
    body: str,
    notification_id: str = "pardus-paylasim",
    priority: str = _PRIORITY_NORMAL,
    icon_name: str = "tr.org.pardus.paylasim",
) -> bool:
    """Masaüstü bildirimi gönderir.

    Args:
        app: Etkin `Gtk.Application`/`Adw.Application` örneği (veya None).
        title: Bildirim başlığı.
        body: Bildirim gövdesi.
        notification_id: Aynı kimlikli bildirim öncekini günceller (üst üste
            yığılmayı önler); her olay türü için ayrı kimlik verilebilir.
        priority: "normal" veya "high".
        icon_name: Tema ikon adı (uygulama app-id'si tema ikonuna eşlenir).

    Returns:
        True: bildirim gönderildi. False: GTK yok / app yok / hata (yalnız
        log'a düşüldü — istisna atmaz).
    """
    if not HAS_GTK or app is None:
        # Bildirim altyapısı yok; olay yine de kayda geçsin.
        logger.info("Bildirim (masaüstü yok): %s — %s", title, body)
        return False

    try:
        notification = Gio.Notification.new(title)
        notification.set_body(body)

        # Uygulama ikonunu ekle (tema ikonu bulunamazsa GTK yok sayar).
        try:
            notification.set_icon(Gio.ThemedIcon.new(icon_name))
        except Exception as e:
            # İkon kritik değil; başarısızsa bildirim ikonsuz gönderilir.
            pass

        if priority == _PRIORITY_HIGH:
            notification.set_priority(Gio.NotificationPriority.HIGH)
        else:
            notification.set_priority(Gio.NotificationPriority.NORMAL)

        app.send_notification(notification_id, notification)
        return True
    except Exception as e:
        # Bildirim ikincil bir kanaldır; hata uygulamayı durdurmamalı.
        logger.warning("Masaüstü bildirimi gönderilemedi: %s", e)
        return False


def withdraw_notification(app: Optional[object], notification_id: str) -> None:
    """Gösterilen bir bildirimi geri çeker (varsa). Hata durumunda sessizdir."""
    if not HAS_GTK or app is None:
        return
    try:
        app.withdraw_notification(notification_id)
    except Exception as e:
        logger.debug("Bildirim geri çekilemedi (%s): %s", notification_id, e)
