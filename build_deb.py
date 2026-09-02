"""
All-In-One Standalone Debian .deb Package Builder for Pardus.
Creates a 100% self-contained single .deb file (pardus-paylasim.deb).
"""

import hashlib
import io
import os
import shutil
import subprocess
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
BUILD_DIR = f"build/{APP_NAME}_standalone"
SINGLE_DEB_NAME = "pardus-paylasim.deb"


def create_ar_header(filename: str, filesize: int, mtime: int = 0) -> bytes:
    name_field = f"{filename:<16}".encode('ascii')[:16]
    mtime_field = f"{mtime:<12}".encode('ascii')[:12]
    owner_field = f"{'0':<6}".encode('ascii')[:6]
    group_field = f"{'0':<6}".encode('ascii')[:6]
    mode_field = f"{'100644':<8}".encode('ascii')[:8]
    size_field = f"{filesize:<10}".encode('ascii')[:10]
    fmag = b"`\n"
    return name_field + mtime_field + owner_field + group_field + mode_field + size_field + fmag


def validate_path_for_packaging(full_path: str, base_dir: str):
    """
    Path validation, symlink rejection and dist boundary controls.
    """
    if os.path.islink(full_path):
        raise ValueError(f"Security Error: Symlinks are not allowed in distribution packages: {full_path}")

    abs_base = os.path.abspath(base_dir)
    abs_path = os.path.abspath(full_path)
    if not abs_path.startswith(abs_base):
        raise ValueError(f"Security Error: Path escapes distribution boundary: {abs_path}")



def build_all_in_one_deb():
    print(f"[*] Pardus için Tek Parça Standalone .deb Paketi Derleniyor: {SINGLE_DEB_NAME}...")

    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)

    os.makedirs(f"{BUILD_DIR}/DEBIAN", exist_ok=True)
    os.makedirs(f"{BUILD_DIR}/usr/bin", exist_ok=True)
    os.makedirs(f"{BUILD_DIR}/usr/lib/python3/dist-packages/pardus_paylasim", exist_ok=True)
    os.makedirs(f"{BUILD_DIR}/usr/share/applications", exist_ok=True)
    os.makedirs(f"{BUILD_DIR}/usr/share/nautilus-python/extensions", exist_ok=True)
    os.makedirs(f"{BUILD_DIR}/usr/share/glib-2.0/schemas", exist_ok=True)

    # 1. DEBIAN/control (Sıfır Dış Bağımlılık - İnternet Aramaz - ama sistem paketlerine dayanır)
    control_content = f"""Package: {APP_NAME}
Version: {VERSION}
Architecture: all
Maintainer: Pardus Geliştirici Ekibi <iletisim@pardus.org.tr>
Depends: python3, python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, mat2, libimage-exiftool-perl, avahi-daemon, avahi-utils, bluez, gstreamer1.0-tools, gstreamer1.0-plugins-base, gstreamer1.0-plugins-good, python3-zeroconf, python3-cryptography
Recommends: gstreamer1.0-pipewire, nautilus-python, python3-qrcode
Section: utils
Priority: optional
Description: Pardus Güvenli Paylaşım, Cihaz Tanıma ve Ekran Paylaşımı Merkezi
 Dosya meta verilerini anonimleştirir, Wi-Fi ve Bluetooth üzerinden
 macOS tarzı cihaz tanıma ve ekran paylaşımı sağlar.
"""
    with open(f"{BUILD_DIR}/DEBIAN/control", "w", encoding="utf-8", newline="\n") as f:
        f.write(control_content)

    # 2. DEBIAN/postinst (Kurulum Sonrası: masaüstü + GSettings şema derleme)
    postinst_content = """#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v glib-compile-schemas >/dev/null 2>&1; then
    glib-compile-schemas /usr/share/glib-2.0/schemas || true
fi
exit 0
"""
    postinst_path = f"{BUILD_DIR}/DEBIAN/postinst"
    with open(postinst_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(postinst_content)
    os.chmod(postinst_path, 0o755)

    # 3. Yürütücü Çalıştırma Betiği
    launcher_content = """#!/bin/sh
export PYTHONPATH=/usr/lib/python3/dist-packages:$PYTHONPATH
exec python3 -m pardus_paylasim.app "$@"
"""
    launcher_path = f"{BUILD_DIR}/usr/bin/{APP_NAME}"
    with open(launcher_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(launcher_content)
    os.chmod(launcher_path, 0o755)

    # 4. Kod ve Masaüstü Entegrasyon Dosyalarını Kopyala
    shutil.copytree("src/pardus_paylasim", f"{BUILD_DIR}/usr/lib/python3/dist-packages/pardus_paylasim", dirs_exist_ok=True)

    # Exclude __pycache__
    for root, dirs, files in os.walk(f"{BUILD_DIR}/usr/lib/python3/dist-packages/pardus_paylasim", topdown=False):
        for name in dirs:
            if name == "__pycache__":
                shutil.rmtree(os.path.join(root, name))

    shutil.copy("data/tr.org.pardus.paylasim.desktop", f"{BUILD_DIR}/usr/share/applications/")

    # AppStream Metainfo
    os.makedirs(f"{BUILD_DIR}/usr/share/metainfo", exist_ok=True)
    if os.path.exists("data/tr.org.pardus.paylasim.metainfo.xml"):
        shutil.copy("data/tr.org.pardus.paylasim.metainfo.xml", f"{BUILD_DIR}/usr/share/metainfo/")

    # App Icon
    os.makedirs(f"{BUILD_DIR}/usr/share/icons/hicolor/scalable/apps", exist_ok=True)
    if os.path.exists("data/tr.org.pardus.paylasim.svg"):
        shutil.copy("data/tr.org.pardus.paylasim.svg", f"{BUILD_DIR}/usr/share/icons/hicolor/scalable/apps/")

    # GSettings şeması (postinst içinde glib-compile-schemas ile derlenir)
    if os.path.exists("data/tr.org.pardus.paylasim.gschema.xml"):
        shutil.copy("data/tr.org.pardus.paylasim.gschema.xml", f"{BUILD_DIR}/usr/share/glib-2.0/schemas/")

    if os.path.exists("data/nautilus/pardus-paylasim-nautilus.py"):
        shutil.copy("data/nautilus/pardus-paylasim-nautilus.py", f"{BUILD_DIR}/usr/share/nautilus-python/extensions/")
    if os.path.exists("data/thunar/pardus-paylasim-thunar.desktop"):
        os.makedirs(f"{BUILD_DIR}/usr/share/Thunar/sendto", exist_ok=True)
        shutil.copy("data/thunar/pardus-paylasim-thunar.desktop", f"{BUILD_DIR}/usr/share/Thunar/sendto/")

    # 4.5. i18n Translations (Locale)
    if os.path.exists("locale"):
        for lang in os.listdir("locale"):
            po_path = os.path.join("locale", lang, "LC_MESSAGES", "pardus-paylasim.po")
            mo_path = os.path.join("locale", lang, "LC_MESSAGES", "pardus-paylasim.mo")
            if os.path.exists(po_path):
                # Try to compile with msgfmt if available (usually available on Linux CI)
                try:
                    subprocess.run(["msgfmt", "-o", mo_path, po_path], check=True, capture_output=True)
                except Exception:
                    pass

                # Copy .mo file if it exists (either just compiled or pre-compiled)
                if os.path.exists(mo_path):
                    target_dir = f"{BUILD_DIR}/usr/share/locale/{lang}/LC_MESSAGES"
                    os.makedirs(target_dir, exist_ok=True)
                    shutil.copy(mo_path, target_dir)

    # 5. Pure-Python Ar Archive Builder (Çapraz Platform ve %100 Reproducible)
    now = int(os.environ.get("SOURCE_DATE_EPOCH", 1700000000))

    # control.tar.gz
    control_buf = io.BytesIO()
    with tarfile.open(fileobj=control_buf, mode="w:gz") as tar:
        for f_name in ["control", "postinst"]:
            f_path = f"{BUILD_DIR}/DEBIAN/{f_name}"
            if os.path.exists(f_path):
                data = open(f_path, "rb").read()
                ti = tarfile.TarInfo(f_name)
                ti.size = len(data)
                ti.mtime = now
                ti.uid = 0
                ti.gid = 0
                ti.uname = "root"
                ti.gname = "root"
                ti.mode = 0o755 if f_name == "postinst" else 0o644
                tar.addfile(ti, io.BytesIO(data))
    control_gz = control_buf.getvalue()

    # data.tar.gz
    data_buf = io.BytesIO()
    with tarfile.open(fileobj=data_buf, mode="w:gz") as tar:
        for root, dirs, files in os.walk(BUILD_DIR):
            dirs.sort()
            files.sort()
            if "DEBIAN" in root or "DEBIAN" == os.path.basename(root):
                continue

            rel_dir = os.path.relpath(root, BUILD_DIR).replace("\\", "/")
            if rel_dir != "." and rel_dir != "":
                ti = tarfile.TarInfo(rel_dir)
                ti.type = tarfile.DIRTYPE
                ti.mode = 0o755
                ti.uid = 0
                ti.gid = 0
                ti.uname = "root"
                ti.gname = "root"
                ti.mtime = now
                tar.addfile(ti)

            for file in files:
                full_path = os.path.join(root, file)
                validate_path_for_packaging(full_path, BUILD_DIR)
                rel_path = os.path.relpath(full_path, BUILD_DIR).replace("\\", "/")
                with open(full_path, "rb") as f:
                    content = f.read()
                ti = tarfile.TarInfo(rel_path)
                ti.size = len(content)
                ti.mtime = now
                ti.uid = 0
                ti.gid = 0
                ti.uname = "root"
                ti.gname = "root"
                ti.mode = 0o755 if "bin" in rel_path else 0o644
                tar.addfile(ti, io.BytesIO(content))
    data_gz = data_buf.getvalue()

    # Ar Archive
    debian_binary = b"2.0\n"

    with open(SINGLE_DEB_NAME, "wb") as deb:
        deb.write(b"!<arch>\n")

        # 1. debian-binary
        deb.write(create_ar_header("debian-binary", len(debian_binary), now))
        deb.write(debian_binary)
        if len(debian_binary) % 2 != 0:
            deb.write(b"\n")

        # 2. control.tar.gz
        deb.write(create_ar_header("control.tar.gz", len(control_gz), now))
        deb.write(control_gz)
        if len(control_gz) % 2 != 0:
            deb.write(b"\n")

        # 3. data.tar.gz
        deb.write(create_ar_header("data.tar.gz", len(data_gz), now))
        deb.write(data_gz)
        if len(data_gz) % 2 != 0:
            deb.write(b"\n")

    # Mirror to standard name as well
    shutil.copy(SINGLE_DEB_NAME, f"{APP_NAME}_1.0.0_all.deb")

    generate_receipt(SINGLE_DEB_NAME)
    generate_receipt(f"{APP_NAME}_1.0.0_all.deb")

    print(f"[SUCCESS] TEK PARÇA PARDUS PAKETİ DERLENDİ: {os.path.abspath(SINGLE_DEB_NAME)}")


if __name__ == "__main__":
    build_all_in_one_deb()
