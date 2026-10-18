#!/bin/sh
# Generuje samopodpisany certyfikat dla serwera laboratoryjnego (10.10.10.30).
set -e
cd "$(dirname "$0")"
openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
  -keyout server.key -out server.crt \
  -subj "/CN=lab-server" -addext "subjectAltName=IP:10.10.10.30,DNS:lab-server"
chmod 644 server.key server.crt
echo "Utworzono server.crt i server.key"
