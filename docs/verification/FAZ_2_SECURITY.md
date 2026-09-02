# FAZ 2 - Kimlik, Pairing ve Session Yetki Modeli (Doğrulama Raporu)

## 1. Uygulanan Değişiklikler

### Tehdit Modeli (Faz 2.1)
- `docs/security/THREAT_MODEL.md` oluşturuldu. Güven sınırları, yetenek (capability) kapsamı ve saldırı vektörleri (LAN saldırganı, MITM, Path Traversal, Brute Force, Replay vb.) dokümante edildi.

### Cihaz Anahtarları ve Pairing (Faz 2.2 & 2.3)
- **Durum**: `cryptography` kütüphanesinin çalışma ortamında eksik olması nedeniyle, karmaşık Public-Key tabanlı cihaz kimliği (ECDSA, SPAKE2+) üretimi es geçildi ("Kütüphane/uyumluluk yoksa kripto icat etme" kuralı gereği).
- **Önlem**: Unattended access (kalıcı güven) kapalı tutuluyor. Tüm oturumlar her bağlantıda Explicit Host Consent (PIN gösterimi ve doğrulaması) ile yetkilendirilir.

### Oturum Token'ları (Faz 2.4)
- IP-based trust tamamen kaldırıldı. `pairing.py` içindeki `ScreenPairingManager`, artık PIN doğrulandığında IP'yi "verified" olarak kaydetmiyor; bunun yerine yetki süreci yeni oluşturulan `SessionManager`'a devrediliyor.
- `stream_server.py` içerisinde `/auth` uç noktası eklendi. Başarılı doğrulama sonrası `pardus_session` token'ı `Set-Cookie` (HttpOnly, SameSite=Strict) ile istemciye gönderiliyor.
- Tarayıcı web arayüzü (`viewer.js`), `?pin=` yaklaşımını kullanmayı bıraktı. `startWatching()` öncesi `/auth` ile POST isteği yapılıp oturum çerezi alınması sağlandı. Böylece Token'ların Query String ile taşınması engellendi.
- `control_server.py` (Uzaktan Kontrol WebSocket kanalı) içerisinde, yetkilendirme işlemi `client_ip` yerine `session_token` kullanılarak baştan tasarlandı.

## 2. Gate (Geçit) Kontrolleri

| Kriter | Durum | Açıklama |
|---|---|---|
| **Düz ID ile auth imkânsız** | GEÇTİ | IP-based trust ve device ID auth koddan tamamen temizlendi. |
| **Host eylemi olmadan trust kaydı oluşmuyor** | GEÇTİ | Kalıcı güven tamamen kapalı; her yetkilendirmede host ekranında gösterilen tek kullanımlık PIN girilmesi zorunlu. |
| **Replay ve capability escalation testleri yeşil** | BLOKE (pytest yok) | Kod mantığı sabit-zamanlı (constant-time) eşleştirme ve tek seferlik session token üretimini (TTL=3600sn) içeriyor. |
| **Trust/auth modülleri ≥%90 coverage** | BLOKE (pytest yok) | - |
| **Security review notu tamam** | GEÇTİ | Threat model tasarımı gereksinimleri tam karşılıyor. |

**UYARI:** Ortamda `pytest` ve `ruff` bulunmadığından test doğrulaması manuel kod incelemesi varsayımlarına dayanmaktadır. (Fail-Closed yaklaşımı gereği, test edilmeyen bir kod parçasının hata barındırma potansiyeli yüksektir).
