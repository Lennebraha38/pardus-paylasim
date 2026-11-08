import asyncio
import json
import logging
import threading

try:
    from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
    from aiortc.contrib.media import MediaRelay
    HAS_AIORTC = True
    relay = MediaRelay()
except ImportError:
    RTCConfiguration = None  # type: ignore[assignment,misc]
    RTCPeerConnection = None  # type: ignore[assignment,misc]
    RTCSessionDescription = None  # type: ignore[assignment,misc]
    MediaRelay = None  # type: ignore[assignment,misc]
    relay = None
    HAS_AIORTC = False

from .hardware_codec import HardwareCodecManager
from .webrtc_tracks import AudioCaptureTrack, ScreenCaptureTrack

logger = logging.getLogger("WebRTCServer")


class WebRTCManager:
    """WebRTC eşler arası oturum yöneticisi ve ekran/ses kanalları orkestratörü."""

    def __init__(self):
        self.pcs = set()
        self._loop = None
        self._thread = None
        self.hardware_profile = HardwareCodecManager.detect_capabilities()

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
    ):
        if not HAS_AIORTC or RTCPeerConnection is None:
            raise RuntimeError("aiortc kütüphanesi kurulu değil; WebRTC kullanılamaz.")

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

                        data = json.loads(message)
                        sender = data.get("sender", "Bilinmeyen")
                        text = data.get("text", "")
                        send_notification(
                            "Pardus Paylaşım — Sohbet",
                            f"{sender}: {text}",
                        )
                    except Exception:
                        logger.debug("Chat mesajı işleme hatası", exc_info=True)

        video_track = ScreenCaptureTrack(monitor_index=monitor_index, quality=quality)
        if relay:
            pc.addTrack(relay.subscribe(video_track))
        else:
            pc.addTrack(video_track)

        if with_audio:
            try:
                audio_track = AudioCaptureTrack()
                if relay:
                    pc.addTrack(relay.subscribe(audio_track))
                else:
                    pc.addTrack(audio_track)
            except Exception as e:
                logger.warning(f"Ses parçası eklenemedi, sadece görüntü iletilecek: {e}")

        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        return pc.localDescription

    async def close_all(self):
        """Tüm açık WebRTC eş bağlantılarını güvenle kapatır."""
        coros = [pc.close() for pc in self.pcs]
        await asyncio.gather(*coros, return_exceptions=True)
        self.pcs.clear()
