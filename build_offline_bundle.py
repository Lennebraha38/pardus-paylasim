"""
Offline Installation Package Builder for Pardus Güvenli Paylaşım.
Creates a self-contained offline installer tarball that requires ZERO internet connectivity.
"""

import hashlib
import os
import shutil
import tarfile


def generate_receipt(filepath):
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while True:
            data = f.read(65536)
            if not data:
                break
            sha256.update(data)
    receipt_path = f"{filepath}.sha256"
    with open(receipt_path, 'w', encoding='utf-8') as f:
        f.write(f"{sha256.hexdigest()}  {os.path.basename(filepath)}\n")
    print(f"[*] SHA256 Doğrulama Özeti (Receipt) Oluşturuldu: {receipt_path}")

APP_NAME = "pardus-paylasim"
VERSION = "1.0.0"
OFFLINE_DIR = f"build/{APP_NAME}-offline"
TARBALL_NAME = f"{APP_NAME}-offline.tar.gz"


def validate_path_for_packaging(full_path: str, base_dir: str):
    """Path validation, symlink rejection and dist boundary controls."""
    if os.path.islink(full_path):
        raise ValueError(f"Security Error: Symlinks are not allowed in distribution packages: {full_path}")

    abs_base = os.path.abspath(base_dir)
    abs_path = os.path.abspath(full_path)
    if not abs_path.startswith(abs_base):
        raise ValueError(f"Security Error: Path escapes distribution boundary: {abs_path}")


def validate_source_directories(dirs_to_check):
    for d in dirs_to_check:
        if not os.path.exists(d):
            continue
        for root, dirs, files in os.walk(d):
            for name in dirs + files:
                validate_path_for_packaging(os.path.join(root, name), d)


def create_offline_bundle():
    print("[*] İnternetsiz (Çevrim Dışı) Pardus Kurulum Paketi Oluşturuluyor...")

    if os.path.exists(OFFLINE_DIR):
        shutil.rmtree(OFFLINE_DIR)

    os.makedirs(f"{OFFLINE_DIR}/src", exist_ok=True)
    os.makedirs(f"{OFFLINE_DIR}/data", exist_ok=True)

    validate_source_directories(["src/pardus_paylasim", "data"])

    # 1. Copy source code & data
    shutil.copytree("src/pardus_paylasim", f"{OFFLINE_DIR}/src/pardus_paylasim", dirs_exist_ok=True)
    shutil.copytree("data", f"{OFFLINE_DIR}/data", dirs_exist_ok=True)
    shutil.copy("pyproject.toml", f"{OFFLINE_DIR}/pyproject.toml")
    shutil.copy("README.md", f"{OFFLINE_DIR}/README.md")
    if os.path.exists("pardus-paylasim_1.0.0_all.deb"):
        shutil.copy("pardus-paylasim_1.0.0_all.deb", f"{OFFLINE_DIR}/")

    # 2. Write offline standalone installation script
    offline_script = r"""#!/usr/bin/env bash
# Pardus Güvenli Paylaşım - Tamamen Çevrim Dışı (Offline) Kurulum Betiği
set -e

echo "=================================================================="
echo "  Pardus Güvenli Paylaşım - Çevrim Dışı (İnternetsiz) Kurulum"
echo "=================================================================="

INSTALL_PREFIX="/usr/local"
BIN_PATH="$INSTALL_PREFIX/bin/pardus-paylasim"
PYTHON_LIB="$INSTALL_PREFIX/lib/python3/dist-packages"

echo "[1/3] Dosyalar yerel sisteme kopyalanıyor..."
sudo mkdir -p "$PYTHON_LIB"
sudo mkdir -p "$INSTALL_PREFIX/bin"
sudo mkdir -p ~/.local/share/applications

sudo cp -r src/pardus_paylasim "$PYTHON_LIB/" 2>/dev/null || sudo cp -r src/pardus_paylasim /usr/lib/python3/dist-packages/

# Kurulum Yürütücüsü (Bağlantısız Çalışır)
echo "[2/3] Uygulama yürütücüsü oluşturuluyor..."
sudo bash -c "cat << EOF > $BIN_PATH
#!/bin/sh
export PYTHONPATH=$PYTHON_LIB:/usr/lib/python3/dist-packages:\$PYTHONPATH
exec python3 -m pardus_paylasim.app \"\$@\"
EOF"

sudo chmod +x "$BIN_PATH"

# Masaüstü Kısayolu ve Dosya Yöneticisi Entegrasyonları
echo "[3/3] Masaüstü ve dosya yöneticisi entegrasyonları kuruluyor..."
sudo mkdir -p /usr/local/share/applications
sudo cp data/tr.org.pardus.paylasim.desktop /usr/local/share/applications/ 2>/dev/null || true

if [ -d "data/nautilus" ]; then
    sudo mkdir -p /usr/local/share/nautilus-python/extensions
    sudo cp data/nautilus/pardus-paylasim-nautilus.py /usr/local/share/nautilus-python/extensions/ 2>/dev/null || true
fi

if [ -d "data/thunar" ]; then
    mkdir -p ~/.local/share/Thunar/sendto
    cp data/thunar/pardus-paylasim-thunar.desktop ~/.local/share/Thunar/sendto/ 2>/dev/null || true
fi

echo ""
echo "=================================================================="
echo " [BAŞARILI] İnternet bağlantısı olmadan kurulum tamamlandı!"
echo " Uygulamayı başlatmak için terminale: pardus-paylasim"
echo "=================================================================="
"""

    with open(f"{OFFLINE_DIR}/offline_install.sh", "w", encoding="utf-8", newline="\n") as f:
        f.write(offline_script)

    os.chmod(f"{OFFLINE_DIR}/offline_install.sh", 0o755)

    # 3. Create .tar.gz archive
    now = int(os.environ.get("SOURCE_DATE_EPOCH", 1700000000))
    with tarfile.open(TARBALL_NAME, "w:gz") as tar:
        # Add the root directory first
        ti_root = tarfile.TarInfo(f"{APP_NAME}-offline")
        ti_root.type = tarfile.DIRTYPE
        ti_root.mode = 0o755
        ti_root.mtime = now
        ti_root.uid = 0
        ti_root.gid = 0
        ti_root.uname = "root"
        ti_root.gname = "root"
        tar.addfile(ti_root)

        for root, dirs, files in os.walk(OFFLINE_DIR):
            dirs.sort()
            files.sort()
            for name in dirs + files:
                full_path = os.path.join(root, name)
                arcname = os.path.join(f"{APP_NAME}-offline", os.path.relpath(full_path, OFFLINE_DIR)).replace("\\", "/")

                if os.path.islink(full_path):
                    raise ValueError(f"Security Error: Symlinks not allowed in archive: {full_path}")
                if ".." in arcname or arcname.startswith("/"):
                    raise ValueError(f"Security Error: Path traversal attempt in archive: {arcname}")

                ti = tar.gettarinfo(full_path, arcname=arcname)
                ti.mtime = now
                ti.uid = 0
                ti.gid = 0
                ti.uname = "root"
                ti.gname = "root"
                if ti.isreg():
                    with open(full_path, "rb") as f:
                        tar.addfile(ti, f)
                else:
                    tar.addfile(ti)

    print(f"[SUCCESS] Çevrim dışı kurulum paketi üretildi: {os.path.abspath(TARBALL_NAME)}")
    generate_receipt(TARBALL_NAME)


if __name__ == "__main__":
    create_offline_bundle()
