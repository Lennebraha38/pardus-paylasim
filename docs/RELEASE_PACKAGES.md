# Yükleme Paketleri Envanteri

**Oluşturulma:** 2026-08-02 · **Branch:** `feat/fail-closed-implementation` · **HEAD:** `b4c42b0`
**Genel statü:** `NOT_RELEASE_READY` (bkz. `docs/CURRENT_STATE.md`, `docs/verification/FINAL_STABILIZATION_REPORT.md`)

Bu dosya, repoda **fiilen derlenmiş** kurulum çıktılarını ve bunları üreten kaynakları listeler.
Binary çıktılar `.gitignore` kapsamındadır (git'te tutulmaz); yalnızca yerel çalışma ağacında bulunur.

---

## 1. Windows paketleri

| # | Dosya | Boyut | SHA-256 | Durum |
|---|---|---|---|---|
| W1 | `dist/pardus-paylasim-agent/pardus-paylasim-agent.exe` | 4.532.490 B | `6134B2FA0CDCBEBA7A19DB8381DA108418A666B79C06E9326C199F26F8947A5F` | Derlenmiş (2026-08-02 05:16) |
| W2 | `dist/pardus-paylasim-agent.zip` | 24.697.372 B | `56934724D7B317ABAB0774A28017A2EDBBCB29EB56E1839D5229C6509031D75D` | Derlenmiş (2026-08-02 05:22) — **dağıtılan ana Windows paketi** |
| W3 | `PardusPaylasimAgent_Setup.exe` (Inno Setup) | — | — | **ÜRETİLMEDİ** — yalnızca `scripts/installer.iss` betiği var |

**W1 sürüm bilgisi:** FileVersion `1.0.0.0` · ProductVersion `1.0.0.0` · CompanyName `Tubitak ULAKBIM` · FileDescription `Pardus Paylasim Agent`
**Authenticode imzası:** `NotSigned` — imzalama kapısı açık.

**Paket tipi:** PyInstaller *onedir* (bir `.exe` + `_internal/` bağımlılık ağacı, toplam 105 girdi).
W2, W1 dizininin ZIP arşividir; kurulum = arşivi açıp `pardus-paylasim-agent.exe` çalıştırmak (installer yok).

**Yan çıktılar:**
- `dist/manifest.sha256` — 108 satır, dizin ağacının tam hash manifesti (`scripts/regen_manifest.py` ile yeniden üretilir)
- `dist/SHA256SUMS.txt` — ZIP'in tek satırlık hash kaydı
- `dist/sbom.json` — 44.099 B SBOM

**Üreten betikler:**
- `build_agent_windows.ps1` (kanıt loglamalı ana build hattı)
- `scripts/build_exe.ps1`
- `pardus-paylasim-agent.spec` (PyInstaller spec) · `version_info.txt` (VERSIONINFO kaynağı)
- `scripts/installer.iss` (Inno Setup; `..\dist\pardus-paylasim-agent\*` → `dist/PardusPaylasimAgent_Setup.exe`)

> Not: `build/pardus-paylasim/pardus-paylasim.exe` — GTK4 GUI'nin Windows derleme denemesi, `build/` ara
> dizininde kalmış; `dist/` altına alınmamış, dağıtım paketi **değildir**. Windows tarafında dağıtılan
> tek bileşen ajandır (agent).

---

## 2. Pardus / Debian paketleri

| # | Dosya | Boyut | SHA-256 | Durum |
|---|---|---|---|---|
| P1 | `pardus-paylasim_1.0.0_all.deb` | 121.530 B | `6d3c049a96ffca7154c3ff2b89b8746bce026d0d4bbeee2afe3f4ac78f4cf4c8` | Derlenmiş (2026-07-31 13:00) — **CI artifact adı** |
| P2 | `pardus-paylasim.deb` | 121.530 B | `6d3c049a96ffca7154c3ff2b89b8746bce026d0d4bbeee2afe3f4ac78f4cf4c8` | P1 ile **bit-bit aynı** — docker testlerinin beklediği ad |

İki dosya aynı içeriktir; ikisi de gereklidir:
`build_deb.py` → `pardus-paylasim.deb` üretir (`tests/docker/entrypoint.sh`, `tests/run_docker_test.sh` bu adı bağlar),
`.github/workflows/build.yml` ise `pardus-paylasim_1.0.0_all.deb` adını artifact olarak yükler.

**Paket meta (control):**
- Package `pardus-paylasim` · Version `1.0.0` · Architecture `all` · Section `utils` · Priority `optional`
- Depends: `python3, python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, mat2, libimage-exiftool-perl, avahi-daemon, avahi-utils, bluez, gstreamer1.0-tools, gstreamer1.0-plugins-base, gstreamer1.0-plugins-good, python3-zeroconf, python3-cryptography`
- Recommends: `gstreamer1.0-pipewire, nautilus-python, python3-qrcode`

**İçerik:** 84 girdi — `/usr/bin/pardus-paylasim` + `/usr/lib/python3/dist-packages/pardus_paylasim/**`
**Sağlama dosyaları:** `pardus-paylasim.deb.sha256`, `pardus-paylasim_1.0.0_all.deb.sha256` (ikisi de aynı hash'i taşır, doğrulandı)

**Üreten betikler:** `build_deb.py`, `scripts/build_deb.sh`, `debian/` (control, rules, install, changelog)

### ⚠ Güncellik uyarısı (açık kapı)

`.deb` **2026-07-31 13:00**'da üretildi; en yeni kaynak değişikliği **2026-08-02 00:02**
(`src/pardus_paylasim/screen/control_server.py`, `src/pardus_paylasim_agent/agent.py`).
Yani mevcut `.deb` **HEAD'i temsil etmiyor** — yeniden derlenip doğrulanması gereken açık kapılardan biri.

---

## 3. Yardımcı kurulum betikleri (paket değil)

| Dosya | Platform | İşlev |
|---|---|---|
| `install.sh` | Pardus/Debian | Kaynaktan kurulum |
| `kurulum.bat` | Windows | Geliştirici kurulumu |
| `baslat.bat` | Windows | Uygulamayı başlatır |
| `build_offline_bundle.py` | Çapraz | Çevrimdışı bağımlılık paketi |
| `create_final_dist_bundle.py` | Çapraz | Yarışma teslim paketi birleştirici |

---

## 4. Release öncesi açık kapılar

1. **Fiziksel Windows ↔ Pardus E2E** — çapraz-cihaz mDNS keşfi, çapraz-cihaz TLS, tray. Tümü `UNVERIFIED` (`docs/verification/RELEASE_MATRIX.md`, `tests/e2e/WINDOWS_SMOKE_TEST_CHECKLIST.md`)
2. **Installer** — `PardusPaylasimAgent_Setup.exe` üretilmedi (W3)
3. **Authenticode imzası** — `NotSigned` (W1/W2)
4. **Güncel `.deb`** — P1/P2 HEAD'den eski (bkz. §2 uyarı)

Dört kapı kapanmadan `master` merge / release kararı verilmez.
