# Pardus Paylaşım Mevcut Durumu

**Durum**: `NOT_RELEASE_READY`
**Versiyon**: 1.0.0
**Tarih**: 2026-08-02

## Kod Durumu
- Branch local olarak mevcut: `feat/fail-closed-implementation`
- Upstream/PR: Yok (Henüz merge edilmedi).
- Yerel test: `393 passed, 7 skipped`
- Docker: `397 passed, 3 skipped`
- Ruff sonucu: `0 error`
- Güvenlik: WSS TLS-Pinning ve `CERT_REQUIRED` tamamen aktif; `CERT_NONE` zafiyetleri kapatıldı. MITM koruması devrede. Hatalı TLS sertifikasında "fail-closed" çalışmaktadır.
- EXE build durumu: Gerçek `pardus_paylasim_agent` üzerinden üretilmiştir fakat imzasızdır (Authenticode: NotSigned, Unsigned Test Build) ve fiziksel testleri eksiktir. Güncel EXE SHA-256: `6134B2FA0CDCBEBA7A19DB8381DA108418A666B79C06E9326C199F26F8947A5F` (PyInstaller 6.21.0 / Python 3.14.0; yeniden derlemede değişir).
- SBOM durumu: Mevcut dosya `dist/sbom.json`'dır. Format: CycloneDX, Spec: 1.6, Strict schema validation: PASS (cyclonedx-python-lib 11.11.0 `JsonStrictValidator(SchemaVersion.V1_6)`, hatasız). Bağımlılıklar + EXE için göreli yollu `dist/manifest.sha256` SHA-256 listesi doğrulandı: `Missing: 0 / Mismatch: 0 / Unlisted: 0`.

## Durum
Ürün kodu ve testleri (Docker, TLS fail-closed) başarılı şekilde tamamlanmış olsa da, **CycloneDX/SPDX SBOM, installer, Authenticode imzası, güncel Pardus paketi ve fiziksel E2E testleri henüz tamamlanmadığı için** ürün şu anda **NOT_RELEASE_READY** durumundadır.

## Bekleyen Adımlar
- Gerçek fiziksel ortamda Windows - Pardus E2E iletişimi testleri.
- `pardus_paylasim_agent` entrypoint'i ile gerçek Windows exe'sinin oluşturulması ve Authenticode ile imzalanması.
- Geçerli standartta (CycloneDX/SPDX) SBOM ve checksum manifestlerinin yayınlanması.
- Kurulum aracı (MSI/installer) ve publish süreçleri.
