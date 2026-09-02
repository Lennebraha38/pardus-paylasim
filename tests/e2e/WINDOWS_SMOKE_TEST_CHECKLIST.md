# Windows Smoke Test Checklist

Bu belge, derlenen Windows agent (EXE) paketinin doğrulanması için **ölçüm-slotlu**
smoke test adımlarını içerir. Her kutu YALNIZCA gerçek ölçümle doldurulur.

## Kutu Durumu Sözleşmesi

- `[ ] UNVERIFIED` — henüz gerçek ölçüm yapılmadı (dürüst baz durum).
- `[x]` + ölçüm bloğu — gerçek, kaydedilmiş ölçüm mevcut.
- **Port sabitleme YOK.** Beklenen portlar (Screen/Control ~52345, File Receiver
  ~8900, Clipboard ~8901) yalnızca yön göstericidir. File receiver portu otomatik
  seçilebilir; gerçekte hangi portlar dinleniyorsa **çalışan PID'den keşfedilip**
  yazılır (`Get-NetTCPConnection -OwningProcess <PID> -State Listen`).
- **Yerel** (tek makine) ölçülebilenler otomatikleştirilir. **Çapraz-cihaz**
  gerektirenler (uzak mDNS keşfi, cihazdan-cihaza TLS, tray görsel) fiziksel
  ortam olmadan `UNVERIFIED` kalır.

---

## 1. Process Stability (30 Saniye Çalışma) — YEREL

- [x] `dist\pardus-paylasim-agent\pardus-paylasim-agent.exe` çalıştırıldı; crash
  olmadan ≥30 sn arka planda aktif kaldığı doğrulandı.

  ```powershell
  # Ölçüm komutu:
  $p = Start-Process ".\dist\pardus-paylasim-agent\pardus-paylasim-agent.exe" -PassThru
  Start-Sleep -Seconds 30
  Get-Process -Id $p.Id
  ```

  **Ölçüm (gerçek):**
  - PID: `101008`
  - 30 sn sonrası durum: `ALIVE` (Responding=True, WorkingSet=84.3 MB)
  - Başlangıç (UTC): `2026-08-02T02:28:27.6869514Z`
  - 30 sn kontrol (UTC): `2026-08-02T02:28:57.9080115Z`
  - Kanıt: `artifacts/verification/20260802_022619/smoke_process_start.log`

## 2. Dinlenen Portlar (Gerçek PID'den Keşif) — YEREL

- [x] Çalışan agent PID'inin dinlediği portlar gerçek PID'den keşfedildi
  (sabit port varsayımı YOK).

  ```powershell
  # Ölçüm komutu:
  Get-NetTCPConnection -OwningProcess <PID> -State Listen |
      Select-Object LocalAddress, LocalPort, State
  ```

  **Ölçüm (gerçek):**
  - PID: `101008`
  - Dinlenen portlar: `52345` (Screen/Control), `49267` (File Receiver — OTOMATİK
    seçilmiş; beklenen ~8900 DEĞİL → port sabitleme yapılmadığı bu ölçümle kanıtlı)
  - Adres: `0.0.0.0` (her iki port)
  - Zaman (UTC): `2026-08-02T02:28:57Z`
  - Kanıt: `artifacts/verification/20260802_022619/smoke_process_start.log`

## 3. mDNS (Zeroconf) Yayın Doğrulaması — ÇAPRAZ-CİHAZ

- [ ] UNVERIFIED — Ağdaki başka bir cihaz (veya `zeroconf` istemcisi) üzerinden
  `_pardus-paylasim._tcp.local.` servisinin yayınlandığı ve discovery paketiyle
  bulunabildiği doğrulanır. Uzak cihaz gerektirir → fiziksel ortam olmadan
  UNVERIFIED.

## 4. TLS Handshake ve Fail-Closed Doğrulaması

### 4a. Yerel TLS Handshake (otomatik) — YEREL

- [x] Agent'ın TLS dinleyen portlarına yerelden bir TLS istemcisi bağlandı; el
  sıkışmasının tamamlandığı doğrulandı. Ayrı bir CERT_REQUIRED (default CA)
  istemcisiyle self-signed sertifikanın REDDEDİLDİĞİ (fail-closed) kanıtlandı.

  ```python
  # Ölçüm: python ssl+socket ile yerel handshake + hatalı-cert reddi testi
  # 1) ssl._create_unverified_context() -> handshake tamamlanır mı
  # 2) ssl.create_default_context()     -> self-signed REDDEDİLMELİ (fail-closed)
  ```

  **Ölçüm (gerçek):**
  - Handshake (unverified): `OK` — proto `TLSv1.3`, her iki portta (52345, 49267)
    aynı sunucu sertifikası, cert-SHA256 `155ACCA69F8EE522D53C251E904532A87DB6B1F0C116119336C6353308612ADA`
  - Fail-closed (default-CA doğrulaması): `OK` — `SSLCertVerificationError:
    self-signed certificate` (sertifika pinning öncesi güven zinciri reddi)
  - Zaman (UTC): `2026-08-02T02:29:32Z`
  - Kanıt: `artifacts/verification/20260802_022619/smoke_tls_handshake.log`

### 4b. Cihazdan-Cihaza TLS (Pardus ↔ Windows) — ÇAPRAZ-CİHAZ

- [ ] UNVERIFIED — Gerçek Pardus istemcisi Windows agent'a bağlanır; uçtan uca
  TLS pinning ve fail-closed davranışı doğrulanır. Uzak cihaz gerektirir →
  fiziksel ortam olmadan UNVERIFIED.

## 5. Tray (Sistem Tepsisi) Simgesi ve Menü — ÇAPRAZ-CİHAZ / MANUEL

- [ ] UNVERIFIED — System Tray'de Pardus Paylaşım simgesinin belirdiği ve menü
  ögelerinin (Ayarlar, Çıkış, Bağlantı durumu) çalıştığı görsel olarak doğrulanır.
  Görsel/manuel kanıt gerektirir → otomatik ortamda UNVERIFIED.

## 6. Kapatma Sonrası Temizlik — YEREL

- [x] Agent kapatıldı; process'in tamamen düştüğü ve dinlenen portların serbest
  bırakıldığı (zombi process / asılı port yok) doğrulandı.

  ```powershell
  # Ölçüm komutu:
  Stop-Process -Id <PID>
  Start-Sleep -Seconds 3
  Get-Process -Id <PID> -ErrorAction SilentlyContinue   # boş olmalı
  Get-NetTCPConnection -OwningProcess <PID> -State Listen -ErrorAction SilentlyContinue  # boş olmalı
  # Ek doğrulama: port numaralarının artık HİÇBİR PID tarafından dinlenmediği
  Get-NetTCPConnection -LocalPort 52345,49267 -State Listen -ErrorAction SilentlyContinue
  ```

  **Ölçüm (gerçek):**
  - PID: `101008`
  - Kapatma öncesi dinlenen portlar: `49267, 52345`
  - Process düştü mü: `EVET` (Stop-Process sonrası Get-Process boş → GONE)
  - Portlar serbest mi: `EVET` — PID 101008'de dinleyici yok; port 49267 ve 52345
    hiçbir PID tarafından artık dinlenmiyor (freed)
  - Başlangıç (UTC): `2026-08-02T02:32:07.3900911Z`
  - Bitiş (UTC): `2026-08-02T02:32:12.1190960Z`
  - Kanıt: `artifacts/verification/20260802_022619/smoke_shutdown.log`
