#!/bin/bash
# Pardus Paylaşım — izole test ortamı smoke testi
# Kullanım: ./tests/smoke_test.sh [/tmp/pptr-test/venv/bin/python]
PY="${1:-/tmp/pptr-test/venv/bin/python}"
cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
PASS=0; FAIL=0
OUT_FILE="$(mktemp 2>/dev/null || echo ./.smoke_out.txt)"

check() { # $1=ad $2=komut...
    local name="$1"; shift
    if "$@" >"$OUT_FILE" 2>&1; then
        PASS=$((PASS+1)); echo "PASS: $name"
    else
        FAIL=$((FAIL+1)); echo "FAIL: $name (bkz. $OUT_FILE)"
    fi
}

echo "== 1. Derleme =="
check "compileall" "$PY" -m compileall -q src/pardus_paylasim tests/benchmarks.py tests/test_mesh_e2e.py

echo "== 2. CLI komutları =="
check "mask" "$PY" -m pardus_paylasim.app --mask "Kartim 4532015112830366"
check "mesh-status" "$PY" -m pardus_paylasim.app --mesh-status
check "async-list" "$PY" -m pardus_paylasim.app --async-list

echo "== 3. E2E mesh (gerçek TCP) =="
check "mesh-e2e" "$PY" tests/test_mesh_e2e.py

echo "== 4. Yeni modül API'leri =="
check "api" "$PY" -c "
from pardus_paylasim.discovery.mesh import MeshNode
from pardus_paylasim.clipboard.sensitive_masker import SensitiveMasker
from pardus_paylasim.screen.webrtc import WebRTCScreenNode, SDPMessage
from pardus_paylasim.discovery.async_transfer import AsyncTransferManager
masked = SensitiveMasker.mask_text('a@b.com')
assert masked != 'a@b.com'
print('API import + maskeleme OK')"

echo
echo "SONUÇ: $PASS geçti, $FAIL kaldı"
[ "$FAIL" -eq 0 ]
