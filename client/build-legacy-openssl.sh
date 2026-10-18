#!/bin/sh
# Kompiluje OpenSSL 1.0.2u (z obsługą RC4, SSLv3, TLS 1.0) do /opt/openssl-legacy.
# Używane w kontenerze serwera oraz bezpośrednio na maszynie klienta (sudo sh build-legacy-openssl.sh).
# NIE instaluje się jako systemowy OpenSSL - nie wpływa na resztę systemu.
set -e
VER=1.0.2u
PREFIX=/opt/openssl-legacy
apt-get update
apt-get install -y --no-install-recommends build-essential perl wget ca-certificates
WORK=$(mktemp -d)
cd "$WORK"
if wget -q "https://www.openssl.org/source/old/1.0.2/openssl-$VER.tar.gz"; then
  tar xzf "openssl-$VER.tar.gz" && cd "openssl-$VER"
else
  wget -q -O src.tar.gz "https://github.com/openssl/openssl/archive/refs/tags/OpenSSL_1_0_2u.tar.gz"
  tar xzf src.tar.gz && cd openssl-OpenSSL_1_0_2u
fi
./config --prefix="$PREFIX" --openssldir="$PREFIX/ssl" no-shared no-asm
make depend >/dev/null 2>&1 || true
make
make install_sw
cd / && rm -rf "$WORK"
"$PREFIX/bin/openssl" version
