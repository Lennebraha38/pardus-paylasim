# Tehdit Modeli (Threat Model)

Pardus Paylaşım uygulaması için güven sınırları, yetenekler ve bilinen saldırı vektörleri analiz edilmiştir. Bu analiz, Faz 2 (Kimlik, Pairing ve Session Yetki Modeli) gereksinimlerine göre hazırlanmıştır.

## 1. Varlıklar ve Güven Sınırları

### Varlıklar (Assets)
- **Host Ekran Görüntüsü**: Hassas veri içerebilir.
- **Klavye/Fare Kontrolü**: Tam sistem erişimi sağlayabilir (C4 düzeyinde kritik).
- **Dosya Sistemi (Okuma/Yazma)**: Host üzerindeki dosyalara erişim ve zararlı dosya yükleme riski.
- **Pano (Clipboard)**: Parola, token gibi hassas veriler içerebilir.

### Güven Sınırları (Trust Boundaries)
1. **Local System (Güvenli)**: Pardus Paylaşım arkaplan servisi ve host UI.
2. **Yerel Ağ (Yarı Güvenli/Güvensiz)**: Aynı LAN üzerinde bulunan diğer cihazlar (Web istemciler, diğer Pardus/Windows masaüstü uygulamaları). Aynı ağda kötü niyetli aktörler veya zararlı yazılım bulaşmış cihazlar olabilir.
3. **İnternet (Güvensiz)**: WebRTC sinyalleşme sunucuları (STUN/TURN).

## 2. Capability (Yetenek) Kapsamı
- **Stream**: Yalnızca ekran görüntüsünü izleme.
- **Control**: Klavye/fare etkinlikleri gönderme (her oturum açık host onayı gerektirir).
- **FS_Read / FS_Write**: İzin verilen dizinlerle sınırlı dosya okuma/yazma (Path Traversal korumalı).

## 3. Bilinen Tehditler ve Alınan Önlemler

### 3.1 Aynı LAN'daki Saldırgan
- **Tehdit**: Saldırgan ağdaki keşif (mDNS) yayınlarını dinleyerek aktif paylaşımları bulur ve izinsiz bağlanmaya çalışır.
- **Önlem**: Auto-trust tamamen kaldırıldı (Faz 1). Her oturum için (cryptography kütüphanesi olmadığı için) host ekranında gösterilen, kısa ömürlü PIN (Short Authentication String) girmesi zorunludur.

### 3.2 Kötü Niyetli Web Origin
- **Tehdit**: Kullanıcının tarayıcısında çalışan zararlı bir web sitesi (CSRF veya fetch aracılığıyla) yerel `pardus-paylasim` servisine istek gönderir.
- **Önlem**: Katı CORS kuralları (`*` engellendi) uygulanır. Tarayıcı websocket bağlantıları `Origin` kontrolünden geçer. `SameSite=Strict` çerezleri ile CSRF engellenir.

### 3.3 MITM (Ortadaki Adam)
- **Tehdit**: Saldırgan, istemci ile host arasındaki trafiği dinler veya değiştirir.
- **Önlem**: HTTPS/WSS için Ephemeral Self-Signed TLS sertifikası kullanılır (TLS başarısız olduğunda sistem Fail-Closed olur, düz HTTP reddedilir). WebRTC trafiği DTLS-SRTP ile varsayılan olarak şifrelenir.

### 3.4 PIN Brute Force / Replay
- **Tehdit**: Saldırgan doğru PIN'i bulana kadar art arda deneme yapar veya eski bir oturum token'ını tekrar kullanır (Replay).
- **Önlem**: 
  - Kaba kuvvet koruması: 3 başarısız denemede IP geçici olarak kilitlenir. Sabit zamanlı (constant-time) karşılaştırma (`hmac.compare_digest`) ile timing attack önlenir.
  - Replay Koruması: PIN tek kullanımlıktır, doğrulandığı an listeden silinir. Yerine kriptografik olarak güvenli rastgele bir `Session Token` üretilir. Oturum token'ı 1 saat süreyle geçerlidir.

### 3.5 Çalınmış Cihaz
- **Tehdit**: Daha önce güvenilmiş bir cihaz çalınır ve host'a izinsiz erişim sağlar.
- **Önlem**: Kütüphane kısıtlamaları (Inkscape Python ortamında `cryptography` eksikliği) sebebiyle kalıcı cihaz güveni (Unattended Access) **kapalı** tutulur. Her yeni bağlantı için host tarafında anlık PIN (veya dosya aktarımında onay dialogu) gereklidir. Cihaz çalınsa bile yeniden PIN gerekmeden bağlanamaz.

### 3.6 NAT Arkasında Aynı IP'yi Paylaşan Peer'ler
- **Tehdit**: Önceki IP tabanlı güven modeli, NAT veya VPN arkasında IP paylaşan kötü niyetli bir cihaza yanlışlıkla yetki verebilirdi.
- **Önlem**: IP tabanlı kimlik doğrulama kaldırıldı (Faz 2). Tüm istekler, kimlik doğrulaması sırasında oluşturulan `Session Token` ile kriptografik olarak doğrulanır. IP adresi yalnızca loglama ve rate-limiting için kullanılır.

### 3.7 Kötü Niyetli Dosya Adı / İçeriği
- **Tehdit**: Path traversal (dizin dışına çıkma) veya aşırı büyük dosya göndererek sistemi doldurma.
- **Önlem**: Dosya yüklemelerinde `os.path.basename` kullanılarak dizin dışına çıkış engellendi (Faz 1). 1GB limit uygulandı.

### 3.8 Resource Exhaustion (Kaynak Tüketimi)
- **Tehdit**: Çok sayıda sahte PIN isteği, dosya transferi veya WebSocket bağlantısı açılarak sistem çökertilir.
- **Önlem**: PIN havuzu kapasitesi ve TTL süreleri sınırlıdır. Kötü niyetli aktör hızla banlanır (Brute Force kısıtlaması).

### 3.9 Kötü Niyetli Rendezvous / TURN
- **Tehdit**: İnternet tabanlı WebRTC bağlantılarında aracı sunucuların trafiği değiştirmesi.
- **Önlem**: WebRTC tasarımı gereği E2E (Uçtan Uca) şifrelidir. TURN sunucusu yalnızca şifreli veriyi (DTLS) iletebilir, içeriğe erişemez. Deneysel mod yalnızca `PARDUS_ENABLE_EXPERIMENTAL=1` ile açılır.

### 3.10 Log ve Local Storage Sızıntısı
- **Tehdit**: PIN'lerin veya Session Token'ların log dosyalarına veya tarayıcı konsoluna yazılması.
- **Önlem**: Loglarda hiçbir PIN veya Token düz metin olarak kaydedilmez (Faz 1 PIN disclosure engellemesi). Web istemcisinde token, XSS riskini azaltmak için `HttpOnly` cookie'de taşınır.

### 3.11 Symlink / TOCTOU
- **Tehdit**: Dosya okuma/yazma işlemleri sırasında dosyanın symlink ile başka bir konuma yönlendirilmesi.
- **Önlem**: Dosya operasyonlarında izinler katı tutulur (Fail-Closed).
