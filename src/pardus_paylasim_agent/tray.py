import logging

import pyperclip
import pystray
from PIL import Image, ImageDraw

logger = logging.getLogger("PardusAgentTray")


def create_image(width, height, color1, color2):
    image = Image.new("RGB", (width, height), color1)
    dc = ImageDraw.Draw(image)
    dc.rectangle((width // 2, 0, width, height // 2), fill=color2)
    dc.rectangle((0, height // 2, width // 2, height), fill=color2)
    return image


class AgentTray:
    def __init__(self, agent, shutdown_event):
        self.agent = agent
        self.shutdown_event = shutdown_event
        self.icon = None

    def _copy_pin(self, icon, item):
        if self.agent._pin:
            try:
                pyperclip.copy(self.agent._pin)
                logger.info("PIN panoya kopyalandı.")
            except Exception as e:
                logger.error(f"Pano kopyalama hatası: {e}")

    def _quit(self, icon, item):
        logger.info("Tray üzerinden çıkış istendi.")
        self.shutdown_event.set()
        icon.stop()

    def run(self):
        try:
            menu = pystray.Menu(
                pystray.MenuItem("Pardus Paylaşım Agent", action=None, enabled=False),
                pystray.MenuItem(
                    lambda item: f"PIN: {self.agent._pin or 'Yok'}", action=None, enabled=False
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("PIN'i Kopyala", action=self._copy_pin),
                pystray.MenuItem("Çıkış", action=self._quit),
            )
            self.icon = pystray.Icon(
                "pardus_agent",
                create_image(64, 64, "#1b2a47", "#3498db"),
                "Pardus Paylaşım Agent",
                menu=menu,
            )
            logger.info("System Tray başlatılıyor...")
            self.icon.run()
        except Exception as e:
            logger.error(f"Tray başlatma hatası: {e}")
