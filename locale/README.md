# Çeviri katalogları

Gerçek `.po`/`.mo` dosyaları paket içinde tutulur:

```
src/pardus_paylasim/locale/en/LC_MESSAGES/pardus-paylasim.{po,mo}
```

Bu üst düzey `locale/` dizini, eski `Containerfile`/paketleme beklentileriyle
uyumluluk ve sistem kurulumlarında `/usr/share/locale` hedefi için ayrılmıştır.
Katalog üretmek:

```bash
python3 scripts/i18n_build.py
```
