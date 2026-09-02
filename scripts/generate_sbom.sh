#!/bin/bash
set -e

echo "Generating SBOM using pip-licenses..."

# Install pip-licenses if not available
if ! command -v pip-licenses &> /dev/null; then
    echo "pip-licenses is not installed. Installing..."
    pip install pip-licenses || pip3 install --break-system-packages pip-licenses
fi

# Generate CycloneDX JSON
pip-licenses --format=json --output-file=sbom.json

# Calculate SHA256 sum for the deb package if it exists
if ls ../pardus-paylasim_*.deb 1> /dev/null 2>&1; then
    echo "Calculating SHA256 for DEB package..."
    sha256sum ../pardus-paylasim_*.deb > SHA256SUMS
fi

echo "SBOM and provenance records generated."
