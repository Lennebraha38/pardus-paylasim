# Kullanıcı Geri Bildirim Sonuçları

> Bu dosya GERÇEK kullanıcı oturumlarından doldurulur. Tahmini/uydurma
> kayıt YASAKTIR — boş satır, dolu yalandan iyidir.
> Form: `docs/KULLANICI_ANKETI.md`.

## Oturumlar

| # | Tarih | Ortam (Pardus sürümü) | Seviye (1-5) | Notlar |
|---|-------|----------------------|--------------|--------|
| 1 | – | – | – | – |
| 2 | – | – | – | – |
| 3 | – | – | – | – |
| 4 | – | – | – | – |
| 5 | – | – | – | – |

## Senaryo sonuçları (tamamlandı mı? + 1-5 puan)

| Senaryo | O1 | O2 | O3 | O4 | O5 |
|---------|----|----|----|----|----|
| 1. Dosya gönderme | – | – | – | – | – |
| 2. Maskeleme | – | – | – | – | – |
| 3. Metadata temizleme | – | – | – | – | – |
| 4. Çevrimdışı kuyruk | – | – | – | – | – |
| 5. Ekran paylaşımı | – | – | – | – | – |

## Açık uçlu yanıtlar (özet, katılımcı izniyle)

- En beğenilen:
- En çok eksik hissedilen:
- Günlük kullanıma alır mıydı (Evet/Hayır + neden):

## TLS regresyonu (Debian proot, cryptography kurulu ortamda)

```bash
proot-distro login debian -- bash -c "
cd ~/pardus-paylasim
python3 -m pytest tests/test_transfer_multi.py tests/test_transfer_accept.py \
  tests/test_transfer_history.py tests/test_transfer_crypto.py -v"
```

> Beklenen: hepsi PASS. Bu ortamda `cryptography` yok; yukarıdaki
> komut gerçek Pardus/Debian iş istasyonunda koşulmalıdır.
