# Canlı Demo Kaydı (CLI)

> Ortam: başsız sunucu (GTK4 yok → uygulama otomatik CLI moduna geçer).
> Aşağıdaki çıktılar `PYTHONPATH=src python3 -m pardus_paylasim.app ...`
> komutlarıyla **gerçekten çalıştırılarak** alınmıştır (2026-09-06).
> GUI ekran görüntüleri GTK4 kurulu bir Pardus iş istasyonunda alınmalıdır.

## 1. Yapay zeka ile hassas veri taraması (`--ai-scan`)

```
$ pardus-paylasim --ai-scan "Toplanti: TCKN 10000000146, IBAN TR963456789012345678901234, mail a@b.com"
Tespit edilen hassas veriler:
  [tckn] KRİTİK: 10000000146... (100%)
  [iban_tr] KRİTİK: TR963456789012345678901234... (100%)
  [email] ORTA: a@b.com... (100%)
```

## 2. Klasik maskeleme (`--mask`)

```
$ pardus-paylasim --mask "Kartim 4532015112830366"
Maskelenmiş Metin:
Kartim 4532 **** **** 0366
```

## 3. Mesh ağı durumu (`--mesh-status`)

```
$ pardus-paylasim --mesh-status
Mesh ağı başlatıldı.
  Peer ID: 0c244d2c
  Port: 8920
  Bağlı eşler: 0
```

## 4. Asenkron kuyruk (`--async-list`)

```
$ pardus-paylasim --async-list
Bekleyen asenkron transferler:
  (Veritabanı: ~/.local/share/pardus-paylasim/async_transfers.db)
```

## 5. Uçtan uca mesh transferi (programatik, gerçek TCP)

```
$ python3 tests/test_mesh_e2e.py
E2E mesh: 204800 bayt, 4 parça — PASS
```

204.800 baytlık gerçek dosya, 4×64 KB parça hâlinde iki ayrı
`MeshNode` arasında loopback TCP üzerinden aktarıldı; alıcıda
birebir aynı baytlar birleştirildi.
