#!/usr/bin/env python3
"""Saf-Python .po -> .mo derleyici (msgfmt/xgettext yoksa kullanilir).

GNU .mo ikili bicimini uretir. msgid/msgstr (tekil), coklu-satir ("..." "...")
ve temel kacis dizilerini (\\n \\t \\" \\\\) destekler. Bos msgstr atlanir
(cevrilmemis -> gettext fallback kaynak string'e duser). Header (key == "")
her zaman dahil edilir.

Kullanim:
    python tools/compile_mo.py [locale_dir]

locale_dir varsayilan "locale". Icindeki her <lang>/LC_MESSAGES/*.po derlenir.
Windows'ta msgfmt bulunmadigi icin bu araç CI ve dev'de tek-kaynak derleyici.
"""
import ast
import os
import struct
import sys

DOMAIN = "pardus-paylasim"


def _unescape(parts: list[str]) -> str:
    # Her parca bir C-string literali ("...") — ast.literal_eval ile coz.
    return "".join(ast.literal_eval(p) for p in parts)


def parse_po(path: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    msgid_parts: list[str] = []
    msgstr_parts: list[str] = []
    state: str | None = None  # 'id' | 'str'

    def flush() -> None:
        if state is not None and msgid_parts:
            key = _unescape(msgid_parts)
            val = _unescape(msgstr_parts) if msgstr_parts else ""
            # Bos msgstr = cevrilmemis; header (key=="") dahil et.
            if val or key == "":
                entries[key] = val

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("msgid "):
                flush()
                msgid_parts = [line[len("msgid "):].strip()]
                msgstr_parts = []
                state = "id"
            elif line.startswith("msgstr "):
                msgstr_parts = [line[len("msgstr "):].strip()]
                state = "str"
            elif line.startswith('"'):
                if state == "id":
                    msgid_parts.append(line)
                elif state == "str":
                    msgstr_parts.append(line)
        flush()
    return entries


def compile_mo(entries: dict[str, str], out_path: str) -> None:
    keys = sorted(entries.keys())
    offsets = []
    ids = b""
    strs = b""
    for k in keys:
        v = entries[k]
        kb = k.encode("utf-8")
        vb = v.encode("utf-8")
        offsets.append((len(ids), len(kb), len(strs), len(vb)))
        ids += kb + b"\x00"
        strs += vb + b"\x00"

    keystart = 7 * 4 + 16 * len(keys)
    valuestart = keystart + len(ids)
    koffsets: list[int] = []
    voffsets: list[int] = []
    for o1, l1, o2, l2 in offsets:
        koffsets += [l1, o1 + keystart]
        voffsets += [l2, o2 + valuestart]

    output = struct.pack(
        "Iiiiiii",
        0x950412DE,             # magic
        0,                      # version
        len(keys),              # num strings
        7 * 4,                  # offset of key table
        7 * 4 + len(keys) * 8,  # offset of value table
        0, 0,                   # hash size, hash offset
    )
    output += struct.pack("i" * len(koffsets), *koffsets)
    output += struct.pack("i" * len(voffsets), *voffsets)
    output += ids
    output += strs

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(output)


def main() -> int:
    locale_dir = sys.argv[1] if len(sys.argv) > 1 else "locale"
    if not os.path.isdir(locale_dir):
        print(f"HATA: locale dizini yok: {locale_dir}", file=sys.stderr)
        return 1

    total = 0
    for lang in sorted(os.listdir(locale_dir)):
        lc_dir = os.path.join(locale_dir, lang, "LC_MESSAGES")
        po = os.path.join(lc_dir, f"{DOMAIN}.po")
        mo = os.path.join(lc_dir, f"{DOMAIN}.mo")
        if not os.path.isfile(po):
            continue
        entries = parse_po(po)
        compile_mo(entries, mo)
        translated = sum(1 for k, v in entries.items() if k and v)
        print(f"OK {lang}: {mo} ({len(entries)} girdi, {translated} ceviri)")
        total += 1

    if not total:
        print(f"UYARI: {locale_dir} altinda .po bulunamadi", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
