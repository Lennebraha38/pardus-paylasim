# Kanıt İndeksi (Evidence Index)

Bu dosya, **Git'te izlenir** ve gitignore altındaki (`dist/`, `artifacts/`) doğrulama
kanıtlarının kalıcı, değişmez işaretçisidir. Kanıt dosyalarının kendileri repoya
girmez; bunun yerine SHA-256 parmak izleri ve zaman damgalı release-evidence ZIP'i
burada kayıt altına alınır. Böylece kanıt kaybolsa bile içerik bütünlüğü ispatlanabilir.

**Nihai durum:** `NOT_RELEASE_READY` (Installer, Authenticode imzası, güncel Pardus
paketi ve fiziksel E2E tamamlanmadan değişmez.)

---

## 1. Release-Evidence Artefaktı (zaman damgalı ZIP + SHA-256)

| Alan | Değer |
|---|---|
| ZIP adı | `artifacts/release-evidence/20260802_104756_release-evidence.zip` |
| ZIP SHA-256 | `C45E006B3234560A249020155DA77353EA7399D54D4978CDA962AF899F6ABE16` |
| SHA yan dosyası | `artifacts/release-evidence/20260802_104756_release-evidence.zip.sha256` |
| İçerik (12 dosya) | build/manifest-regen/sbom-strict/run_verify/image-inspect/ruff/local-unit-tests/smoke×3 logları + `manifest.sha256` + `sbom.json` |

Doğrulama:
```bash
sha256sum -c artifacts/release-evidence/20260802_104756_release-evidence.zip.sha256
```

---

## 2. Test Edilen Commit'ler (dürüst kayıt)

| Aşama | Commit | Not |
|---|---|---|
| Betik+checklist temizliği (Commit A) | `58d38b8dc45f07fd5afb047dd239ec7302631213` | Tam kanıt loglama betikleri |
| EXE build HEAD | `58d38b8dc45f07fd5afb047dd239ec7302631213` | PyInstaller bu commit üzerinde koştu |
| Betik sertleştirme + manifest yeniden üretici (Commit A2) | `09d2752bd6b4686a339361530897f975bf2f51e6` | `src/` ve `.spec` DEĞİŞMEDİ |
| Docker doğrulama HEAD | `09d2752bd6b4686a339361530897f975bf2f51e6` | Temiz ağaç; imaj `git_commit` label = bu |
| Unit test + ruff commit | `68c81533…` / `09d2752…` | Rapordaki ilgili bölümlerde belirtildi |

**Şeffaflık notu:** Build (`58d38b8`) ile Docker doğrulama (`09d2752`) farklı commit'lerde
koştu. Aradaki delta yalnız betik sertleştirme + manifest yeniden üreticidir; ürün kaynağı
(`src/`) ve PyInstaller `.spec` dosyası değişmediğinden EXE girdileri aynıdır.

---

## 3. Artefakt SHA-256 Parmak İzleri

| Artefakt | SHA-256 |
|---|---|
| `dist/pardus-paylasim-agent/pardus-paylasim-agent.exe` | `6134B2FA0CDCBEBA7A19DB8381DA108418A666B79C06E9326C199F26F8947A5F` |
| `pardus-paylasim-agent.spec` | `135FFBEE1B0917F2F4058AE3998F5BE38DAF758378931CCA0E45F0E00EEEF830` |
| `dist/sbom.json` | `7BB6F3B8965119317668DF44EB3A3A4239E7788D8A4B8FA3479C391B0631C9DD` |
| `dist/manifest.sha256` | `AEF5D72A039E93DEDC99FAD2D1AC6C6C6BEB0E9DD38D7AAD38DD4663D2ACF9D7` |
| `dist/pardus-paylasim-agent.zip` | `56934724D7B317ABAB0774A28017A2EDBBCB29EB56E1839D5229C6509031D75D` |

> Not: EXE SHA-256 yeniden derlemede değişir (PyInstaller deterministik değildir). Bu tablo,
> mevcut imzasız test derlemesinin (`NotSigned`) parmak izini sabitler.

---

## 4. Kanıt → Gereksinim Eşlemesi

| # | Gereksinim | Kanıt |
|---|---|---|
| 1 | Build tamamlandı | `.../20260802_021600/build_agent_windows.log` (exit 0) |
| 2 | SBOM geçerli CycloneDX 1.6 strict PASS | `.../20260802_021600/sbom_strict_validation.log` |
| 3 | Manifest yeniden üretim: `Missing: 0 / Mismatch: 0 / Unlisted: 0` | `.../20260802_021600/manifest_regen_verify.log` |
| 4 | Build log: HEAD/branch/tam-cmd/stdout-stderr/exit/spec-SHA/EXE-yol-boyut-SHA/Authenticode/zamanlar (Antigravity YOK) | `.../20260802_021600/build_agent_windows.log` |
| 5 | `run_verify.log`: HEAD + image ID + git_commit label + `397 passed, 3 skipped` + compose exit 0 | `.../20260802_022619/run_verify.log`, `image_inspect_supplement.log` |
| 6 | Gitignore kanıtları → zaman damgalı ZIP + SHA-256; kaybolan dahili task-log yolları raporlardan çıkarıldı, gerçek `artifacts/` yolları kondu | Bu dosya §1 + `FINAL_STABILIZATION_REPORT.md` |
| 7 | Smoke checklist yalnız gerçek ölçümle; uygulanmayan `[ ] UNVERIFIED` | `tests/e2e/WINDOWS_SMOKE_TEST_CHECKLIST.md` + smoke logları |
| 8 | `CURRENT_STATE.md` + `FINAL_STABILIZATION_REPORT.md` commit'lendi; `git status --porcelain=v1` boş | Commit B |
| 9 | Nihai durum `NOT_RELEASE_READY` | `CURRENT_STATE.md`, `FINAL_STABILIZATION_REPORT.md` |
