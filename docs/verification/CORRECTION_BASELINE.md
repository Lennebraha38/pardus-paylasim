# CORRECTION BASELINE

Bu rapor `Faz 0` kapsamında, proje değiştirilmeden önceki gerçek durumun ölçülmesine dair kanıtları içermektedir.

## 1. Branch ve HEAD
- **Mevcut Branch:** `feat/fail-closed-implementation`
- **HEAD Commit:** `1ecc6c3a17e5284df45a85f460f92a59298214ed`

## 2. Çalışma Ağacı ve Upstream
- **Upstream Durumu:** Yok (`fatal: no upstream configured for branch 'feat/fail-closed-implementation'`). Remote/origin'de mevcut commit'ler veya bu dal bulunmamakta.
- **Çalışma Ağacı:** Temiz (Herhangi bir modified/untracked dosya yok, 1ecc6c3 commit'ine sabit).
- **Master Durumu:** `master` branch `feat/fail-closed-implementation` dalından 3 commit geride.

## 3. Test Ortamı ve Sürüm
- **Python Sürümü:** Sistemde Python 3.12, 3.11 ve 3.14 (Inkscape) mevcuttur. Test ortamı `uv` ile Python 3.12 üzerinden `work/venvs/py312` oluşturularak izole edilmiştir.
- **Mevcut Paket Tarihleri:** `pardus-paylasim.deb` ve `pardus-paylasim_1.0.0_all.deb` paketleri 26 Temmuz 2026 tarihinde oluşturulmuş olup güncel (31 Temmuz fail-closed) commit'lerinden eskidir. 
- **SBOM ve Provenance:** Yeni bir SBOM dosyası (örn: `sbom.json` veya CycloneDX JSON'u) üretilmemiş, provenance bulunmamaktadır.
- **Windows EXE:** Eski veya yeni herhangi bir Windows `.exe` installer veya dağıtımı mevcut değildir (`dist/` dizini bulunamadı).

## 4. Analiz ve Test (Baseline Sonucu)
- **İlk Ruff Sonucu:** 145 Hata tespit edildi.
- **İlk Pytest Sonucu:** `e2e` bağımlılıkları (`requests`) eksik olduğu için Collection aşamasında fail oldu. Bu durum düzeltilip testler baştan çalıştırılacaktır.

## 5. Dokümantasyon Çelişkileri
- `CURRENT_STATE.md` belgesinde "Bütün testler geçmektedir" ve "Paketleme süreçleri doğrulandı" iddiaları yer almasına rağmen, fiziksel Windows doğrulamaları (E2E) yapılmamış, SBOM tam oluşturulmamış ve eski debian paketleri korunmuştur. (Durum geri çekilecektir).
