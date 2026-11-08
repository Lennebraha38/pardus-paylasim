# Pardus Paylaşım — P2P Ağ, Mesh & Veri Çerçeveleme Protokol Spesifikasyonu (v1.1)

Bu belge, **Pardus Paylaşım** sisteminde yerel ağda (LAN/WLAN) bulut bağımsız çalışan eşler arası (P2P), çoklu sekme (multi-hop mesh relay), dosya ve ekran aktarım protokollerinin teknik kablo biçimini (wire format), durum makinelerini ve güvenlik garantilerini tanımlar.

---

## 1. Genel Mimari ve Tasarım İlkeleri

1. **Sıfır Bulut Bağımlılığı (LAN Privacy First):** Tüm sinyalizasyon, eş keşfi ve veri transferi yerel alt ağda gerçekleşir. STUN/TURN veya harici sunucu zorunluluğu yoktur.
2. **Fail-Closed Güvenlik:** Kriptografik doğrulama veya üstveri temizliği başarısız olduğunda sistem aktarımı engeller (fail-closed).
3. **Akustik / Katmanlı İletim:**
   - **Keşif Katmanı:** mDNS (RFC 6762 / RFC 6763) + Bluetooth LE Beacon.
   - **Doğrudan Veri Katmanı:** TLS v1.3 (RFC 8446) / AES-256-GCM soket akışı (Port `8900`).
   - **Mesh Relay Katmanı:** UDP/TCP parçalı çerçeveleme (Port `8920`).
   - **Ekran / Kontrol Katmanı:** WebSockets / WebRTC DataChannel + HTTP/1.1 TLS (Port `52345` / `8921`).

---

## 2. İkili Çerçeveleme Başlığı (Binary Wire Format)

Mesh ve parça aktarımında kullanılan her paket sabit 16 baytlık ikili başlık ile başlar:

```text
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          Magic (0x5050)       |    Version    |     OpCode    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|       Hop Count       | Flags |           Reserved            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                         Payload Length                        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                         CRC-32 Checksum                       |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       Payload Data (...)                      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

### Alan Tanımları:
- **Magic (2 Bayt):** `0x50 0x50` (`"PP"` — Pardus Paylaşım).
- **Version (1 Bayt):** Protokol sürümü (Mevcut: `0x01`).
- **OpCode (1 Bayt):**
  - `0x01`: `PING` / Kalp Atışı.
  - `0x02`: `FRAG_OFFER` (Aktarım Teklifi & Üstveri).
  - `0x03`: `FRAG_ACK` (Kabul / Onay Bildirimi).
  - `0x04`: `FRAG_DATA` (Parçalı Veri Yükü, azami 64 KB).
  - `0x05`: `FRAG_COMPLETE` (Aktarım Tamamlandı).
  - `0x06`: `CANCEL` (Aktarım İptali).
- **Hop Count (1 Bayt):** Geçilen sekme sayısı. Her aktarıcı düğümde 1 artırılır; `MAX_RELAY_HOPS` (3) aşılırsa paket imha edilir (TTL koruması).
- **Flags (1 Bayt):**
  - Bit 0 (`0x01`): Sıkıştırılmış veri (zlib).
  - Bit 1 (`0x02`): Şifrelenmiş yük (AES-GCM).
  - Bit 2 (`0x04`): Öncelikli kontrol paketi.
- **Payload Length (4 Bayt, Big-Endian):** Takip eden yükün bayt cinsinden uzunluğu.
- **CRC-32 Checksum (4 Bayt, Big-Endian):** Yük verisinin IEEE 802.3 CRC32 doğrulaması.

---

## 3. Çoklu Sekme (Multi-Hop Mesh) İletim Akışı

Doğrudan Wi-Fi menzili dışında kalan veya aralarında güvenlik duvarı bulunan düğümlere komşu Pardus düğümleri üzerinden otomatik yönlendirme yapılır:

```text
+----------+             +----------+             +----------+
|  Kaynak  |             |  Röle    |             |  Hedef   |
| Düğüm A  |             | Düğüm B  |             | Düğüm C  |
+----+-----+             +----+-----+             +----+-----+
     |                        |                        |
     | 1. FRAG_OFFER (hop=0)  |                        |
     |----------------------->|                        |
     |                        | 2. FRAG_OFFER (hop=1)  |
     |                        |----------------------->|
     |                        |                        |
     |                        | 3. FRAG_ACK (hop=1)    |
     |                        |<-----------------------|
     | 4. FRAG_ACK (hop=2)    |                        |
     |<-----------------------|                        |
     |                        |                        |
     | 5. FRAG_DATA [1..N]    |                        |
     |=======================>| 6. FRAG_DATA [1..N]    |
     |                        |=======================>|
     |                        |                        |
     |                        | 7. COMPLETE            |
     |                        |<-----------------------|
     | 8. COMPLETE            |                        |
     |<-----------------------|                        |
```

### Döngü Engelleme (Loop Prevention):
Her düğüm son 5 dakika içinde gördüğü `(source_peer_id, transfer_id, chunk_index)` üçlüsünü LRU önbelleğinde saklar. Tekrar eden paketler anında düşürülerek ağ fırtınaları (broadcast storms) engellenir.

---

## 4. WebRTC ve Ekran Akışı Uyumu

- **Kanal:** WebRTC DataChannel (SCTP) veya TLS üzerinden WebSocket (RFC 6455).
- **Video Kodlayıcı:** Donanım profiline göre seçilen VA-API / NVENC / V4L2 M2M veya yazılımsal H.264 (Baseline Profile, Level 3.1, zerolatency).
- **Oturum Güvenliği:** 6 haneli zaman kısıtlı PIN (Host-PIN) + TOFU (Trust-On-First-Use) SHA-256 sertifika parmak izi denetimi.
- **Dosya İndirme Başlıkları:** RFC 5987 / RFC 6266 uyumlu `Content-Disposition: attachment; filename="<ascii>"; filename*=UTF-8''<url-encoded>` yapısı ile Türkçe karakter desteği.

---

## 5. Güvenlik ve Tehdit Modeli

| Tehdit | Karşı Önlem |
| :--- | :--- |
| **Ağ Dinleme (Sniffing)** | Tüm veri transferlerinde TLS 1.3 zorunluluğu, SHA-256 parmak izi pini |
| **Ortadaki Adam (MITM)** | `TrustStore` stdlib kilitli güven deposu, ilk eşleşmede parmak izi doğrulama |
| **Kötücül Dosya Adı / Traversal** | `os.path.realpath` ile sınırlandırılmış kök dizin denetimi, sürücü harfi ve `..` engeli |
| **Üstveri / EXIF Sızıntısı** | `MetadataCleaner` fail-closed denetimi (mat2 eksikse transfer kesin bloke) |
| **Pano Veri İfşası** | `SensitiveMasker` Luhn (Kredi Kartı) ve Mod-97 (IBAN) doğrulamalı otomatik maskeleme |
