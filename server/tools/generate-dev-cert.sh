#!/usr/bin/env bash
set -euo pipefail

# Generates a self-signed certificate for local HTTPS API testing.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="$ROOT_DIR/certs"

mkdir -p "$CERT_DIR"

openssl req \
  -x509 \
  -nodes \
  -days 365 \
  -newkey rsa:2048 \
  -keyout "$CERT_DIR/server.key" \
  -out "$CERT_DIR/server.crt" \
  -subj "/CN=127.0.0.1"

echo "Generated:"
echo "  $CERT_DIR/server.crt"
echo "  $CERT_DIR/server.key"
