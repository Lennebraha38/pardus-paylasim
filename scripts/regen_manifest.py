#!/usr/bin/env python3
"""Regenerate dist evidence artifacts after a rebuild, then verify.

Steps:
  1. Rebuild dist/pardus-paylasim-agent.zip from the freshly built
     dist/pardus-paylasim-agent/ folder (so the zip carries the real EXE).
  2. Regenerate dist/SHA256SUMS.txt (zip hash, CSV) with clean UTF-8 paths.
  3. Regenerate dist/manifest.sha256 listing every dist file except the
     manifest itself, format: "<UPPER-SHA256>  .\\<windows-path>".
  4. Verify: re-read every manifest entry, re-hash, and compare against disk.
     Also detect files on disk that are not listed (Unlisted).
     Emit exactly: Missing / Mismatch / Unlisted counts.

Exit 0 only when Missing == Mismatch == Unlisted == 0.
"""
from __future__ import annotations

import hashlib
import os
import sys
import zipfile
from pathlib import Path

DIST = Path("dist")
AGENT_DIR = DIST / "pardus-paylasim-agent"
ZIP_PATH = DIST / "pardus-paylasim-agent.zip"
SHA256SUMS = DIST / "SHA256SUMS.txt"
MANIFEST = DIST / "manifest.sha256"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def win_rel(path: Path) -> str:
    """dist-relative path in Windows manifest style: .\\a\\b\\c."""
    rel = path.relative_to(DIST).as_posix().replace("/", "\\")
    return ".\\" + rel


def rebuild_zip() -> None:
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    files = sorted(p for p in AGENT_DIR.rglob("*") if p.is_file())
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            arc = p.relative_to(DIST).as_posix()  # pardus-paylasim-agent/...
            z.write(p, arc)
    print(f"[zip] rebuilt {ZIP_PATH} from {len(files)} files")


def regen_sha256sums() -> None:
    zip_hash = sha256_file(ZIP_PATH)
    abspath = str(ZIP_PATH.resolve())
    lines = ['"Hash","Path"', f'"{zip_hash}","{abspath}"', ""]
    SHA256SUMS.write_text("\n".join(lines), encoding="utf-8")
    print(f"[sha256sums] zip={zip_hash}")


def dist_files_for_manifest() -> list[Path]:
    """All files under dist/ except the manifest itself."""
    out: list[Path] = []
    for p in sorted(DIST.rglob("*")):
        if p.is_file() and p.resolve() != MANIFEST.resolve():
            out.append(p)
    return out


def regen_manifest() -> list[Path]:
    # Deterministic order: top-level artifacts first, then agent tree.
    top = [ZIP_PATH, DIST / "sbom.json", SHA256SUMS]
    top = [p for p in top if p.exists()]
    agent = sorted(p for p in AGENT_DIR.rglob("*") if p.is_file())
    listed = top + agent
    lines = [f"{sha256_file(p)}  {win_rel(p)}" for p in listed]
    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[manifest] wrote {len(listed)} entries to {MANIFEST}")
    return listed


def parse_manifest() -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for raw in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        sha, _, rel = raw.partition("  ")
        entries.append((sha.strip().upper(), rel.strip()))
    return entries


def verify() -> int:
    entries = parse_manifest()
    listed_paths: set[Path] = set()
    missing = 0
    mismatch = 0
    for sha, rel in entries:
        # .\a\b -> dist/a/b
        clean = rel[2:] if rel.startswith(".\\") else rel
        disk = DIST / clean.replace("\\", "/")
        listed_paths.add(disk.resolve())
        if not disk.is_file():
            print(f"  MISSING: {rel}")
            missing += 1
            continue
        actual = sha256_file(disk)
        if actual != sha:
            print(f"  MISMATCH: {rel}\n    manifest={sha}\n    actual  ={actual}")
            mismatch += 1

    unlisted = 0
    for p in dist_files_for_manifest():
        if p.resolve() not in listed_paths:
            print(f"  UNLISTED: {win_rel(p)}")
            unlisted += 1

    print("")
    print(f"Missing: {missing}")
    print(f"Mismatch: {mismatch}")
    print(f"Unlisted: {unlisted}")
    return 0 if (missing == 0 and mismatch == 0 and unlisted == 0) else 1


def main() -> int:
    if not AGENT_DIR.is_dir():
        print(f"FATAL: {AGENT_DIR} not found (build first)", file=sys.stderr)
        return 2
    rebuild_zip()
    regen_sha256sums()
    regen_manifest()
    print("--- VERIFY (re-read + re-hash every manifest entry) ---")
    return verify()


if __name__ == "__main__":
    raise SystemExit(main())
