import asyncio
import json
import logging
import random
import ssl
from collections.abc import Callable

import websockets

logger = logging.getLogger("RendezvousClient")


class RendezvousClient:
    def __init__(self, router_url: str):
        self.router_url = router_url
        self.ws: websockets.WebSocketClientProtocol | None = None
        self.device_id: str | None = None
        self.running = False
        self._on_id_callback = None
        # Onay callback'i: (sender_id, offer_type) -> bool. Tanımsızsa RED.
        self._consent_callback = None

        # Faz 9.1: Server Certificate Validation
        self.ssl_context = ssl.create_default_context()
        if not self.router_url.startswith("wss://"):
            logger.warning("Güvenli olmayan wss:// bağlantısı, Faz 9 gereği sadece test için.")

    def set_id_callback(self, callback: Callable[[str], None]):
        self._on_id_callback = callback

    def set_consent_callback(self, callback: Callable[[str, str], bool]) -> None:
        """Gelen WebRTC teklifleri için kullanıcı onayı sağlayıcısı."""
        self._consent_callback = callback

    async def connect(self):
        self.running = True
        backoff = 1.0
        max_backoff = 60.0

        while self.running:
            try:
                ssl_arg = self.ssl_context if self.router_url.startswith("wss://") else None
                async with websockets.connect(self.router_url, ssl=ssl_arg) as ws:
                    self.ws = ws
                    backoff = 1.0  # Başarılı bağlantıda backoff sıfırlanır
                    await ws.send(json.dumps({"type": "register"}))

                    async for message in ws:
                        data = json.loads(message)
                        msg_type = data.get("type")

                        if msg_type == "registered":
                            self.device_id = data.get("id")
                            logger.info(f"Rendezvous ID alındı: {self.device_id}")
                            if self._on_id_callback:
                                self._on_id_callback(self.device_id)

                        elif msg_type == "offer":
                            sender_id = data.get("sender_id")
                            sdp = data.get("sdp")
                            offer_type = data.get("offer_type")
                            monitor_index = data.get("monitor_index", 0)

                            # Fail-closed: onay callback'i yoksa veya False dönerse
                            # teklif reddedilir; otomatik kabul yoktur.
                            approved = False
                            if self._consent_callback is not None:
                                try:
                                    approved = bool(
                                        self._consent_callback(sender_id, offer_type or "")
                                    )
                                except Exception as e:
                                    logger.warning("Onay callback hatası: %s", e)
                            if not approved:
                                logger.warning(
                                    "Rendezvous teklifi reddedildi (onay yok): %s",
                                    sender_id,
                                )
                                await ws.send(
                                    json.dumps(
                                        {"type": "reject", "target_id": sender_id}
                                    )
                                )
                                continue
                            logger.info("Rendezvous offer onaylandı: %s", sender_id)
                            try:
                                # aiortc ağır bir bağımlılık; yalnız gerçek
                                # teklif işlenirken yüklenir (headless testler
                                # ve CLI bu modülü hafifçe import edebilsin).
                                from pardus_paylasim.screen.webrtc_server import (
                                    webrtc_manager,
                                )

                                # Webrtc manager process
                                desc = await webrtc_manager.handle_offer(
                                    sdp, offer_type, monitor_index
                                )
                                await ws.send(
                                    json.dumps(
                                        {
                                            "type": "answer",
                                            "target_id": sender_id,
                                            "sdp": desc.sdp,
                                            "answer_type": desc.type,
                                        }
                                    )
                                )
                            except Exception as e:
                                logger.error(f"Rendezvous WebRTC hatası: {e}")

            except Exception as e:
                # Faz 9.1: Exponential Backoff + Jitter
                jitter = random.SystemRandom().uniform(0, 0.3 * backoff)
                sleep_time = backoff + jitter
                logger.warning(
                    f"Rendezvous bağlantı hatası: {e}. {sleep_time:.2f} saniye sonra tekrar denenecek."
                )
                await asyncio.sleep(sleep_time)
                backoff = min(max_backoff, backoff * 2)

    def stop(self):
        self.running = False
        if self.ws:
            asyncio.create_task(self.ws.close())
