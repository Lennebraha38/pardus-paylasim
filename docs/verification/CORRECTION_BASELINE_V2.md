# CORRECTION_BASELINE_V2 - Repo Gerçeği (Faz 0)

Tarih: 2026-07-31T16:03:00Z
Denetim Öncesi HEAD: `a851ca749e934438568624c3230a5a6014a83073`

## 1. Git ve Çalışma Ağacı Durumu
- **Branch:** `feat/fail-closed-implementation` (yerelde var, upstream yapılandırılmamış).
- **Temizlik:** DIRTY. `.gitignore` dosyasındaki `work/` klasörü yanlış UTF-16 encoding ile eklendiğinden dolayı `work/` değişiklikleri takip ediliyor.
- **Merge Durumu:** `master` branchi ile birleşmemiş.
- **Python / uv Sürümü:** Python 3.14 (sanal ortam), uv kullanılıyor.

## 2. Test ve Ruff Durumu (İlk Koşu)
- **Ruff:** 12 error tespit edildi (Kullanılmayan importlar, marker sıralaması vb.).
- **Pytest (Docker/E2E Dışı Koşu):** 374 passed, 6 skipped, 4 deselected.
- **Pytest (Tam Koşu):** 377 passed, 6 skipped, 1 failed (`test_rendezvous_router`).
- **Hata Sebebi:** `socket.gaierror: [Errno 11001] getaddrinfo failed`. Yerel ortamda "router" adresi DNS tarafından çözülemiyor.

## 3. Docker Durumu ve Tutarsızlıklar
- **Çalışan Container'lar:** `pardus-host-1`, `pardus-host-2`, `linux-protocol-mock`, `router` up.
- **Dosya Eşleşmezliği (Hash Kontrolü):**
  - Host `tests/e2e/test_protocols.py` Hash: `F286C64E7A...`
  - Container `tests/e2e/test_protocols.py` Hash: `5bd795c371...`
  *Sonuç:* Container'lar güncel repodan üretilmiş DEĞİL, eski cache kullanılmış.

## 4. Paketleme ve Artefakt Durumu
- `.deb` dosyalarının son değişiklik tarihi: `31.07.2026 13:00:43`.
- Mevcut HEAD ise 16:00 sonrasına ait.
- SBOM ve Provenance bilgileri mevcut değil.
- Paketler güncel committen üretilmedi.

## 5. Güvenlik Denetimi İhlalleri (Tespitler)
- **TLS:** Dosya gönderiminde `context.check_hostname = False` ve `context.verify_mode = ssl.CERT_NONE` kalmış. Fingerprint pining kontrolü eksik ve aktif MITM engellenmiyor.
- **Rendezvous:** WSS kullanılmıyor (sadece ws://), payload schema doğrulaması yapılmıyor.
- **Token Scope:** Her token geniş yetki ile çalışıyor (scope yetki izolasyonu uygulanmamış).
- **E2E Hatalı Beyanı:** Testlerin çoğu gerçek bir network üzerinden tam bir protocol E2E testini kanıtlamıyor.

## 6. Dokümantasyon Çelişkileri
- `docs/CURRENT_STATE.md` "RELEASE_READY" derken, aslında `RELEASE_MATRIX.md` "NOT_RELEASE_READY" diyor.
- "8/8 E2E test geçti" beyanı yanlış (esasen backend testleri).

## 7. Sonuç
Proje an itibarıyla **NOT_RELEASE_READY** durumundadır. Paketleme ve TLS pining işlemleri tamamlanmamıştır. Faz 1 kapsamında önce doküman beyanları geri çekilecek ve sonrasında güvenlik, Docker yenileme ve paketleme adımlarına geçilecektir.
