#!/bin/bash
# Instalacja oprogramowania dla roli maszyny. Uruchamiany w tle przez vm-bootstrap.sh
# (jednostka systemd "lab-role"), log: /var/log/lab-role.log
#   sudo bash ~/lab/vm-roles.sh server|client|sensor UZYTKOWNIK
set -euo pipefail
ROLE=$1
USER_NAME=$2
LAB="$(getent passwd "$USER_NAME" | cut -d: -f6)/lab"
export DEBIAN_FRONTEND=noninteractive

echo "=== $(date '+%F %T') START: rola $ROLE ==="

# apt bywa zablokowany zaraz po starcie (automatyczne aktualizacje) - poczekaj
for _ in $(seq 1 60); do
  fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || break
  echo "czekam na zwolnienie apt..."; sleep 10
done

case "$ROLE" in
  server)
    apt-get update
    apt-get install -y docker.io docker-compose-v2
    usermod -aG docker "$USER_NAME"
    systemctl enable --now docker
    cd "$LAB/server"
    [ -f certs/server.crt ] || sh certs/gen-certs.sh
    docker compose up -d --build
    docker compose ps
    ;;
  client)
    apt-get update
    apt-get install -y python3 tcpdump curl
    if [ -x /opt/openssl-legacy/bin/openssl ]; then
      echo "OpenSSL legacy juz zainstalowany"
    else
      sh "$LAB/client/build-legacy-openssl.sh"
    fi
    ;;
  sensor)
    if [ -x /usr/local/bin/snort ]; then
      echo "Snort juz zainstalowany"
    else
      bash "$LAB/sensor/install-snort3.sh"
    fi
    mkdir -p /usr/local/etc/rules
    cp "$LAB/sensor/local.rules" /usr/local/etc/rules/local.rules
    cp "$LAB/sensor/lab.lua" /usr/local/etc/snort/lab.lua
    snort -c /usr/local/etc/snort/snort.lua --tweaks lab -T
    ;;
  *)
    echo "Nieznana rola: $ROLE"; exit 2 ;;
esac

echo "=== $(date '+%F %T') KONIEC: rola $ROLE - OK ==="
