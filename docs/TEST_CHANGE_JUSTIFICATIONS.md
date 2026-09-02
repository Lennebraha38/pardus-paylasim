# Pardus Paylaşım Test ve Güvenlik Değişiklikleri Gerekçe Raporu

## 1. Testlerde Yapılan Değişiklikler ve Gerekçeleri

### `tests/e2e/test_protocols.py`
- **Değişiklik:** WSS bağlantı testinde `CERT_NONE` kaldırılarak tam sertifika doğrulaması (`CERT_REQUIRED`) ve CA pinning (Trust Store) zorunlu hale getirildi. 
- **Gerekçe:** Güvenlik gereği fail-closed prensibi uygulanmalıdır. Testler "sessiz güven" veya "güvensiz bağlantı" üzerinden başarı üretmemelidir.
- **Sonuç:** DNS çözünürlüğü ve sertifika doğrulama adımları test ortamına uyarlandı ve %100 geçer not aldı.

### `tests/docker/Dockerfile.verify`
- **Değişiklik:** `docker-compose.verify.yml` içerisindeki bind mount kaldırılarak `COPY . /app` ile immutable bir imaj yaratıldı. Eksik C derleme bağımlılıkları (`pkg-config`, `libcairo2-dev`, `libgirepository1.0-dev`) sisteme dahil edildi. `pycairo` ve `pygobject` gibi halihazırda apt ile gelen paketler pip kurulum listesinden hariç tutuldu.
- **Gerekçe:** Test ve release doğrulama ortamları yerel geliştirici makinesinin dirty state'inden bağımsız olmalıdır (Reproducible Builds). Pip'in sistem paketlerinin üzerine derleme yapmaya çalışması build hatalarına ve tutarsızlıklara yol açıyordu.

## 2. Mimari ve Güvenlik Değişiklikleri

### `trust_store.py` (Yeni Eklendi)
- **Değişiklik:** Sertifikaların TOFU (Trust On First Use) olmadan açıkça eşleşme anahtarıyla (pinning) doğrulanmasını sağlayan yapı eklendi.
- **Gerekçe:** Ortadaki adam (MITM) saldırılarına karşı `CERT_NONE` kullanımını engellemek için her bağlantının eşleşme aşamasında elde edilen sertifikaya zorunlu güvenmesi gerekir.

### `stream_client.py`
- **Değişiklik:** TLS bağlantısı sırasında sertifika doğrulaması için "Trust Store" altyapısına bağlandı. Hatalı sertifikada bağlantıyı sessizce kabul etmek yerine `fail-closed` prensibiyle anında kesmesi sağlandı.

## 3. Doğrulama Durumu

*   **Ruff Format & Lint:** `All checks passed!` (0 hata), `99 files already formatted` (exit 0).
*   **Yerel pytest:** `393 passed, 7 skipped` (exit 0) — `artifacts/verification/20260802_022619/local_unit_tests.log`.
*   **Docker E2E:** `397 passed, 3 skipped` (compose exit 0, failed=0) — `artifacts/verification/20260802_022619/run_verify.log`.
*   **Git State:** Temiz, dirty dosya barındırmayan commit üzerinden doğrulandı (HEAD `09d2752`).
*   **Paketleme:** İmzasız (`NotSigned`) Windows test derlemesi (`dist/pardus-paylasim-agent/pardus-paylasim-agent.exe`) üretildi; SBOM `dist/sbom.json` (CycloneDX 1.6, strict PASS). Kanıt indeksi: `docs/verification/EVIDENCE_INDEX.md`.

Pardus Paylaşım, ürün kodu ve testleri tamamlanmış olsa da installer, Authenticode imzası,
güncel Pardus paketi ve fiziksel E2E testleri tamamlanmadığından **NOT_RELEASE_READY** durumundadır.
