# FAZ 12 - SON E2E MATRİSİ (RELEASE MATRIX)

Aşağıdaki tablo, `Pardus Paylaşım` projesinin çeşitli çapraz-platform (cross-platform) bağlantılarında ve farklı tarayıcılarda doğrulanan çalışma yeteneklerini göstermektedir. Fiziksel donanım, gerçek işletim sistemi döngüsü (Wayland Portal API vb.) ve gerçek masaüstü ortamı gerektiren testler laboratuvar ortamı eksikliğinden dolayı zorla geçirilmemiş (**UNVERIFIED**) statüsündedir. Yalnızca Docker ortamında veya yerel sanal ekranda (Xvfb) doğrulanan kısımlar **PASS** olarak işaretlenmiştir.

## Sistem - Sistem Bağlantı Matrisi (Fiziksel / Native OS)

| Kaynak | Hedef | View | Control | File up | File down | Clipboard | WebRTC | Audio |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Pardus 23 X11** | **Pardus 23 X11** | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| **Pardus 23 Wayland** | **Pardus 25 Wayland** | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| **Pardus 25 X11** | **Pardus 23 Wayland** | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| **Windows 10/11** | **Pardus 23** | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| **Pardus 23** | **Windows 10/11** | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| **Windows 10/11** | **Pardus 25** | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| **Pardus 25** | **Windows 10/11** | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |

## Docker Protokol Test Matrisi

Docker üzerinde sanal ortamda (simülatör) yapılan konsept protokol testleri durumu:

| Kaynak | Hedef | Durum |
|---|---|:---:|
| **Docker Client** | **Docker Server** | PASS (Tüm TLS/Fail-Closed protokol testleri başariyla geçti) |

### Durum Açıklamaları
* **PASS**: Gerçek cihaz/Xvfb ekranında ilgili protokol güvenlik testlerini geçmiş, şifreli bir biçimde sorunsuz aktarılmış ve fail-closed kuralına uygun tepki vermiştir.
* **UNVERIFIED**: Kod altyapısı eksiksiz hazırlanmış olmasına rağmen ilgili özelliğin (örneğin donanımsal ses Loopback API'leri veya Wayland Portal XDG arayüzü) doğrulamasını yapmak için gerçek donanım (fiziksel test) kurulamamıştır. Kullanıcı güvenliğini tehlikeye atmamak için özellik release'de "Deneysel/Geliştirici modunda" veya varsayılan kapalı kalır.

## Zorunlu Güvenlik E2E Test Matrisi (Security E2E)

| Test Senaryosu | Durum | Yöntem |
|---|---|---|
| **Yanlış PIN girişi** | UNVERIFIED | Sunucu hata verir, disconnect olur. |
| **Süresi geçmiş PIN (Expired)** | UNVERIFIED | Oturum başlatılamaz. |
| **PIN Replay (Tekrar kullanım)** | UNVERIFIED | Aynı PIN ikinci kez yetki sağlamaz. |
| **MITM/Fingerprint uyuşmazlığı** | UNVERIFIED | TLS context fingerprint reddedilir. |
| **Untrusted Device ID spoof** | UNVERIFIED | Cihaz sadece ID ile güvenli listesine alınmaz. Explicit pairing (nonce) zorunlu. |
| **Revoked (İptal edilmiş) Cihaz** | UNVERIFIED | Trust store'dan silinmiş cihaz reddedilir. |
| **Unauthorized Capability** | UNVERIFIED | Yalnızca `view` yetkisi verilen oturum klavye basarsa (input inject) reddedilir. |
| **Malicious Origin (CORS)** | UNVERIFIED | Geçersiz Origin, WebSocket handshake sırasında fail eder. |
| **TLS Missing (Şifresiz HTTP)** | UNVERIFIED | Servis `require_tls=True` olduğundan başlatılmaz, bağlantı reddedilir. |
| **Upload Traversal (Dizin dışına çıkma)** | UNVERIFIED | Server side generated dosya isimleri kullanılarak `../../../` atlatılır. |
| **Symlink Escape** | UNVERIFIED | Symlink çözümlenip kök dizin kontrolü ile bloke edilir. |
| **Oversized Upload (Aşırı büyük veri)** | UNVERIFIED | Chunk/Stream limitlerine takılıp drop edilir. Tüm dosya RAM'e alınmaz. |
| **Interrupted Upload** | UNVERIFIED | Kopan bağlantıda Temp dosyalar silinir (Cleanup). |
| **Malicious WebSocket frame** | UNVERIFIED | Oversized/Fragmented limit dışı frame'ler WebSocket standardı gereği kapatılır. |
| **Rate flood** | UNVERIFIED | Endpoint başına saniyedeki istek kısıtı ile bağlantı engellenir. |
| **Kill-switch** | UNVERIFIED | Host uygulamayı kapattığında/revoke ettiğinde tüm WS, stream, aktarım soketleri kapanır. |

> Tüm özellikler **Fail-Closed** mimariye uygun bir şekilde revize edilmiştir.
