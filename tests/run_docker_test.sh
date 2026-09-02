#!/bin/sh
# Linux esdegeri: tests/run_docker_test.ps1
# .deb derle -> Pardus test imajini kur -> container icinde entegrasyon testleri.
# CI (GitHub/GitLab) ve Pardus host ayni script'i kullanir — tek-kaynak bakim.
set -e

# Repo koku (bu script tests/ altinda).
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
ROOT_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
cd "$ROOT_DIR"

PY=${PYTHON:-python3}

echo "1. .deb Paketi Derleniyor..."
"$PY" build_deb.py

echo "2. Pardus Test Imaji Hazirlaniyor..."
docker build -t pardus-paylasim-test -f tests/docker/Dockerfile tests/docker

echo "3. Container Icinde Testler Calistiriliyor..."
docker run --rm \
  -v "$ROOT_DIR/pardus-paylasim.deb:/app/pardus-paylasim.deb" \
  -v "$ROOT_DIR/tests:/app/project-tests:ro" \
  pardus-paylasim-test
