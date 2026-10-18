#!/bin/sh
# Przestarzały serwer TLS: akceptuje SSLv3 - TLS 1.2, w tym zestawy CBC i RC4.
# Domyślnie obsługuje TLS_FALLBACK_SCSV (OpenSSL 1.0.2), co wykorzystuje się w demonstracji ochrony.
exec /opt/openssl-legacy/bin/openssl s_server \
  -accept 4433 \
  -cert /certs/server.crt -key /certs/server.key \
  -cipher 'ALL:RC4:!aNULL:!eNULL' \
  -www
