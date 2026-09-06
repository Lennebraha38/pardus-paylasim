#!/bin/bash
# Pardus Paylaşım — Nautilus sağ-tık betikleri kurulumu
#
# Kurulum (bir kez):
#   bash scripts/nautilus/install.sh
#
# Kaldırma:
#   rm -f ~/.local/share/nautilus/scripts/"Pardus ile Gönder" \
#         ~/.local/share/nautilus/scripts/"Pardus Gizlilik Temizle"
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR="$HOME/.local/share/nautilus/scripts"
mkdir -p "$TARGET_DIR"
install -m 0755 "$SCRIPT_DIR/Pardus ile Gönder" "$TARGET_DIR/Pardus ile Gönder"
install -m 0755 "$SCRIPT_DIR/Pardus Gizlilik Temizle" "$TARGET_DIR/Pardus Gizlilik Temizle"
echo "Kuruldu: $TARGET_DIR"
echo "Nautilus'u yeniden başlatın (nautilus -q) ve dosyaya sağ tıklayın."
