# Flatpak derleme

Manifest, uygulamayı ve Python bağımlılıklarını PyPI'dan kurar. `flatpak-builder`
varsayılan olarak ağ erişimini kapatmadığı için `build-options.build-args`
altında `--share=network` verilmiştir.

Mağaza/CI için tekrarlanabilir derleme:

```bash
pip install flatpak-pip-generator
flatpak-pip-generator --requirements-file=../requirements-flatpak.txt \
  --output flatpak/python-deps
```

Ardından üretilen `python-deps.json` modülünü manifeste ekleyip
`build-options` bloğunu kaldırın. Sahte/placeholder sha256 kullanılmaz.
