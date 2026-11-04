# Pardus Paylaşım Mevcut Durumu

**Durum**: `RELEASE_READY` (v1.1.0 TEKNOFEST Pardus Geliştirme Kategorisi)
**Versiyon**: 1.1.0
**Tarih**: 2026-11-04
**Maintainer / Geliştirici**: Lennebraha38 <farukhilmi12345@gmail.com>
**Açık Kaynak Kod Deposu**: https://github.com/Lennebraha38/pardus-paylasim

## Kod ve Test Durumu
- Branch: `main`
- Yerel test: `599 passed, 9 skipped, 0 failed`
- Ruff sonucu: `0 error` (tüm `src/` ve `tests/` temiz)
- Benchmarks: `tests/benchmarks.py` tüm senaryolar (webrtc 200kb parçalı akış dahil) başarıyla tamamlandı
- Güvenlik: WSS TLS-Pinning ve `CERT_REQUIRED` tamamen aktif; birleşik parmak izi güven deposu (`auth/trust_store.py` + `screen/trust_store.py`), dosya kabul diyaloğu fail-closed, path traversal sanitizasyonu, sensitive masker Luhn/TCKN koruması, RFC 5987 UTF-8 dosya adı koruması devrede.
- Paketleme: `build_deb.py` ve standart `debian/` dizini ile tek parça Pardus/Debian `.deb` paketi üretimi doğrulanmıştır.
