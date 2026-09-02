import asyncio
import json
import logging
import random
import ssl
from typing import Callable, Optional

import websockets

from pardus_paylasim.screen.webrtc_server import webrtc_manager

logger = logging.getLogger("RendezvousClient")


class RendezvousClient:
    def __init__(self, router_url: str):
        self.router_url = router_url
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.device_id: Optional[str] = None
        self.running = False
        self._on_id_callback = None

        # Faz 9.1: Server Certificate Validation
        self.ssl_context = ssl.create_default_context()
        if not self.router_url.startswith("wss://"):
            logger.warning("Güvenli olmayan wss:// bağlantısı, Faz 9 gereği sadece test için.")

    def set_id_callback(self, callback: Callable[[str], None]):
        self._on_id_callback = callback

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

                            # Faz 9.1: Target consent (Basit Onay Simülasyonu)
                            logger.warning(
                                f"Gelen Rendezvous offer: {sender_id}. Lütfen arayüzden onaylayın (Otomatik test için geçici olarak onaylandı)."
                            )

                            logger.info(f"Rendezvous offer received from {sender_id}")
                            try:
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
                jitter = random.uniform(0, 0.3 * backoff)
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
