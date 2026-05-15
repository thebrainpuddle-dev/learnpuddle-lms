#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${1:-learnpuddle.com}"
SSL_DIR="${2:-nginx/ssl}"

mkdir -p "$SSL_DIR"

copy_if_missing() {
  local source="$1"
  local target="$2"
  if [ -s "$source" ] && [ ! -s "$target" ]; then
    cp -L "$source" "$target"
  fi
}

normalize_names() {
  copy_if_missing "$SSL_DIR/fullchain.pem" "$SSL_DIR/origin.pem"
  copy_if_missing "$SSL_DIR/privkey.pem" "$SSL_DIR/origin-key.pem"
  copy_if_missing "$SSL_DIR/origin.pem" "$SSL_DIR/fullchain.pem"
  copy_if_missing "$SSL_DIR/origin-key.pem" "$SSL_DIR/privkey.pem"
}

certs_ready() {
  [ -s "$SSL_DIR/fullchain.pem" ] \
    && [ -s "$SSL_DIR/privkey.pem" ] \
    && [ -s "$SSL_DIR/origin.pem" ] \
    && [ -s "$SSL_DIR/origin-key.pem" ]
}

normalize_names

if ! certs_ready; then
  letsencrypt_dir="/etc/letsencrypt/live/$DOMAIN"
  if [ -s "$letsencrypt_dir/fullchain.pem" ] && [ -s "$letsencrypt_dir/privkey.pem" ]; then
    echo "Using Let's Encrypt certificate from $letsencrypt_dir"
    cp -L "$letsencrypt_dir/fullchain.pem" "$SSL_DIR/fullchain.pem"
    cp -L "$letsencrypt_dir/privkey.pem" "$SSL_DIR/privkey.pem"
  else
    if ! command -v openssl >/dev/null 2>&1; then
      echo "ERROR: nginx SSL files are missing and openssl is not installed." >&2
      exit 1
    fi
    echo "WARNING: nginx SSL files were missing; generating a temporary self-signed origin certificate for $DOMAIN." >&2
    openssl req -x509 -nodes -newkey rsa:2048 -days 30 \
      -subj "/CN=$DOMAIN" \
      -keyout "$SSL_DIR/privkey.pem" \
      -out "$SSL_DIR/fullchain.pem" >/dev/null 2>&1
  fi

  normalize_names
fi

if ! certs_ready; then
  echo "ERROR: nginx SSL files are still incomplete in $SSL_DIR." >&2
  exit 1
fi

chmod 644 "$SSL_DIR/fullchain.pem" "$SSL_DIR/origin.pem"
chmod 600 "$SSL_DIR/privkey.pem" "$SSL_DIR/origin-key.pem"

echo "nginx SSL files ready in $SSL_DIR"
