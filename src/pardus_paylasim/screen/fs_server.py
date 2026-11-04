import json
import os
import urllib.parse
from typing import Any

from pardus_paylasim.platform_info import downloads_dir


class PathTraversalError(Exception):
    pass


def get_allowed_roots() -> dict[str, str]:
    # Basit güvenlik için sadece "İndirilenler" (Downloads) klasörü
    return {"downloads": downloads_dir()}


def resolve_path(root_key: str, subpath: str) -> str:
    roots = get_allowed_roots()
    if root_key not in roots:
        raise PathTraversalError("Yetkisiz kök dizin")

    # Windows'ta os.path.join("C:\\...", "D:\\...") D: sürücüsüne atlar.
    if ":" in subpath:
        raise PathTraversalError("Geçersiz yol (sürücü harfi yasak)")

    base = os.path.realpath(roots[root_key])
    # Path traversal önlemi: symlink ve .. engeli
    normalized = os.path.realpath(os.path.join(base, subpath.lstrip("/\\")))
    if not normalized.startswith(base + os.sep) and normalized != base:
        raise PathTraversalError("Geçersiz yol (path traversal)")

    return normalized


def list_directory(root_key: str, subpath: str) -> str:
    path = resolve_path(root_key, subpath)
    if not os.path.isdir(path):
        raise ValueError("Dizin bulunamadı")

    entries: list[dict[str, Any]] = []
    for entry in os.scandir(path):
        entries.append(
            {
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size": entry.stat().st_size if not entry.is_dir() else 0,
                "modified": entry.stat().st_mtime,
            }
        )

    return json.dumps({"status": "ok", "entries": entries})


def serve_download(root_key: str, subpath: str, handler) -> None:
    path = resolve_path(root_key, subpath)
    if not os.path.isfile(path):
        handler._send_json('{"error": "Dosya bulunamadı"}', 404)
        return

    size = os.path.getsize(path)
    raw_filename = os.path.basename(path).replace("\r", "").replace("\n", "")
    # RFC 5987 / RFC 6266 uyumlu UTF-8 dosya adı kodlaması + ASCII fallback
    ascii_fallback = raw_filename.encode("ascii", "ignore").decode("ascii").replace('"', "")
    if not ascii_fallback:
        ascii_fallback = "download"
    encoded_filename = urllib.parse.quote(raw_filename, encoding="utf-8")

    handler.send_response(200)
    handler.send_header("Content-Type", "application/octet-stream")
    handler.send_header(
        "Content-Disposition",
        f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded_filename}',
    )
    handler.send_header("Content-Length", str(size))
    handler.end_headers()

    with open(path, "rb") as f:
        while chunk := f.read(8192):
            handler.wfile.write(chunk)
