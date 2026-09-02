import asyncio
import json
import logging
import threading

from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay

from .webrtc_tracks import AudioCaptureTrack, ScreenCaptureTrack

logger = logging.getLogger("WebRTCServer")
relay = MediaRelay()


class WebRTCManager:
    def __init__(self):
        self.pcs = set()
        self._loop = None
        self._thread = None

    def start_loop(self):
        if self._thread is not None:
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    async def handle_offer(
        self,
        sdp: str,
        type: str,
        monitor_index: int = 0,
        quality: str = "high",
        with_audio: bool = False,
    ) -> RTCSessionDescription:
        from aiortc import RTCConfiguration

        config = RTCConfiguration(iceServers=[])  # Faz 5.2 LAN Privacy Default

        offer = RTCSessionDescription(sdp=sdp, type=type)
        pc = RTCPeerConnection(configuration=config)
        self.pcs.add(pc)

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"WebRTC Connection state is {pc.connectionState}")
            if pc.connectionState == "failed" or pc.connectionState == "closed":
                await pc.close()
                self.pcs.discard(pc)

        @pc.on("datachannel")
        def on_datachannel(channel):
            if channel.label == "chat":

                @channel.on("message")
                def on_message(message):
                    logger.info(f"Chat message received: {message}")
                    try:
                        from pardus_paylasim.notifications import send_notification

                        send_notification(
                            title="Sohbet Mesajı (Web İstemcisi)",
                            message=message,
                            notification_id="chat-msg",
                        )
                    except Exception:
                        pass

        # Video (Ekran) Ekle
        try:
            video_track = ScreenCaptureTrack(monitor_index=monitor_index, quality=quality)
            pc.addTrack(video_track)
        except Exception as e:
            logger.error(f"WebRTC Video Track eklenemedi: {e}")

        # Ses Ekle (Faz 6 - Varsayılan Kapalı)
        if with_audio:
            try:
                audio_track = AudioCaptureTrack()
                pc.addTrack(audio_track)
            except Exception as e:
                logger.error(f"WebRTC Audio Track eklenemedi: {e}")

        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        # Faz 5.1 ICE gathering wait (Non-trickle ICE)
        async def wait_for_ice():
            while pc.iceGatheringState != "complete":
                await asyncio.sleep(0.1)

        try:
            await asyncio.wait_for(wait_for_ice(), timeout=5.0)
        except asyncio.TimeoutError:
            pass

        return pc.localDescription

    async def close_all(self):
        coros = [pc.close() for pc in self.pcs]
        if coros:
            await asyncio.gather(*coros)
        self.pcs.clear()
        if self._loop:
            self._loop.stop()


# Global nesne
webrtc_manager = WebRTCManager()


def process_offer_sync(
    sdp: str, type: str, monitor_index: int = 0, quality: str = "high", with_audio: bool = False
) -> str:
    """Faz 5.4 Tek Sahipli Uzun Ömürlü Asyncio Loop."""
    webrtc_manager.start_loop()
    future = asyncio.run_coroutine_threadsafe(
        webrtc_manager.handle_offer(sdp, type, monitor_index, quality, with_audio),
        webrtc_manager._loop,
    )
    desc = future.result(timeout=10.0)
    return json.dumps({"sdp": desc.sdp, "type": desc.type})
