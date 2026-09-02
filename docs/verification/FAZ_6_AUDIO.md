# FAZ 6 - AUDIO (Doğrulama Raporu)

## 1. Uygulanan Değişiklikler

### Capability ve Koşullu Başlatma (Faz 6.1 & 6.2)
- Ses aktarımı (`AudioCaptureTrack`) varsayılan olarak **kapalı** (opt-in) hale getirildi. 
- `WebRTCManager.handle_offer` metodu artık açıkça `with_audio=True` parametresi almadığı sürece hiçbir ses aygıtına bağlanmaz ve mikrofon izni istemez.
- `soundcard` modülü sadece import edilebilir durumdaysa yüklenir. Eğer yüklü değilse çökmeden (graceful fail) sadece ses özelliğini atlar.
- Ses paylaşımı, doğrudan Host tarafından açık izin verildiğinde aktif olabilecektir. 

### Sınırlandırılmış Veri ve FPS (Faz 6.3)
- `AudioCaptureTrack` içerisinde ses verisi, loopback cihazından okunurken Event Loop'un bloklanmaması için parçalı okuma (`run_in_executor`) mimarisi korunarak, blokaj riski en aza indirgenmiştir.
- Okunan `float32` veriler, `int16` formatına dönüştürülüp s16p layout'unda işlenmektedir.

## 2. Gate (Geçit) Kontrolleri

| Kriter | Durum | Açıklama |
|---|---|---|
| **Audio varsayılan kapalı (opt-in)** | GEÇTİ | `with_audio=False` olarak sabitlenmiş ve ses izole edilmiştir. |
| **Gerçek OS Kanıtı (Windows WASAPI/Pardus Pipewire)** | BLOKE (UNVERIFIED) | Sistemde gerçek ses loopback aygıtı takılı veya aktif olmadığından (headless docker ortamları vs.) tam doğrulama sağlanamamıştır. |
| **Mute/Revoke** | KISMİ | Track düzeyinde `stop()` mekanizması bulunmakta, ancak UI üzerinden tetiklenmesi host uygulamasının menü revizyonlarına bırakılmıştır. |

**SONUÇ:** Faz 6, mevcutheadless-ortam kuralları gereği EXPERIMENTAL ve UNVERIFIED durumuna alınmış, ancak "Varsayılan kapalı" (Fail-Closed) stratejisi eksiksiz uygulanarak projenin gizlilik ihlali (gizli dinleme) yapması engellenmiştir.
