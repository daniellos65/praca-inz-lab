#!/bin/bash
# Wstepna konfiguracja sklonowanej maszyny Ubuntu w laboratorium.
# Uruchamiany automatycznie przez setup-lab.ps1, recznie:
#   sudo bash ~/lab/vm-bootstrap.sh --role server --ip 10.10.10.30 --lab-mac 08:00:27:aa:bb:cc
# Opcje:
#   --role server|client|sensor   rola maszyny (= hostname)
#   --ip ADRES                    adres w sieci labnet (/24)
#   --lab-mac MAC                 MAC karty podlaczonej do labnet (karta 1 w VirtualBox)
#   --client-mac MAC --server-mac MAC   (tylko sensor) wpisywane do konfiguracji arp_spoof
#   --no-roles                    nie uruchamiaj instalacji oprogramowania roli
set -euo pipefail

ROLE="" IP="" LAB_MAC="" CLIENT_MAC="" SERVER_MAC="" RUN_ROLES=1
while [ $# -gt 0 ]; do
  case "$1" in
    --role) ROLE=$2; shift 2 ;;
    --ip) IP=$2; shift 2 ;;
    --lab-mac) LAB_MAC=${2,,}; shift 2 ;;
    --client-mac) CLIENT_MAC=${2,,}; shift 2 ;;
    --server-mac) SERVER_MAC=${2,,}; shift 2 ;;
    --no-roles) RUN_ROLES=0; shift ;;
    *) echo "Nieznana opcja: $1"; exit 2 ;;
  esac
done

log() { echo "[bootstrap:${ROLE}] $*"; }
die() { echo "[bootstrap:${ROLE}] BLAD: $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "uruchom przez sudo"
case "$ROLE" in server|client|sensor) ;; *) die "nieprawidlowa rola: '$ROLE'" ;; esac
[[ "$IP" =~ ^10\.10\.10\.[0-9]+$ ]] || die "nieprawidlowy adres: '$IP'"

USER_NAME=${SUDO_USER:-root}
HOME_DIR=$(getent passwd "$USER_NAME" | cut -d: -f6)
LAB="$HOME_DIR/lab"
[ -d "$LAB" ] || die "brak katalogu $LAB"

# Pliki przeniesione z Windows moga miec konce linii CRLF.
find "$LAB" -type f \( -name '*.sh' -o -name '*.lua' -o -name '*.rules' -o -name '*.yml' -o -name '*.conf' -o -name '*.py' \) \
  -exec sed -i 's/\r$//' {} +

# ---------------------------------------------------------------------------
# 1. Tozsamosc maszyny (tylko przy pierwszym uruchomieniu dla danej roli)
# ---------------------------------------------------------------------------
MARKER=/etc/lab-bootstrap
if [ "$(cat "$MARKER" 2>/dev/null)" != "$ROLE" ]; then
  log "nazwa hosta, machine-id, klucze SSH"
  hostnamectl set-hostname "$ROLE"
  sed -i '/^127\.0\.1\.1[[:space:]]/d' /etc/hosts
  sed -i "1a 127.0.1.1 $ROLE" /etc/hosts

  rm -f /etc/machine-id /var/lib/dbus/machine-id
  systemd-machine-id-setup >/dev/null
  ln -sf /etc/machine-id /var/lib/dbus/machine-id

  rm -f /etc/ssh/ssh_host_*
  ssh-keygen -A >/dev/null
  systemctl restart ssh || true
  echo "$ROLE" > "$MARKER"
else
  log "tozsamosc juz ustawiona, pomijam"
fi

if ! grep -q '^# lab-hosts' /etc/hosts; then
  cat >> /etc/hosts <<'EOF'
# lab-hosts
10.10.10.10 attacker
10.10.10.20 client
10.10.10.30 server
10.10.10.40 sensor
EOF
fi

# ---------------------------------------------------------------------------
# 2. Siec labnet: interfejs wyszukiwany po adresie MAC
# ---------------------------------------------------------------------------
LAB_IF=""
if [ -n "$LAB_MAC" ]; then
  for p in /sys/class/net/*; do
    if [ "$(cat "$p/address")" = "$LAB_MAC" ]; then LAB_IF=${p##*/}; break; fi
  done
  [ -n "$LAB_IF" ] || die "nie znaleziono interfejsu o MAC $LAB_MAC (sprawdz: ip -br link)"
else
  # bez MAC: pierwszy interfejs, ktory nie ma trasy domyslnej (NAT)
  NAT_IF=$(ip -o -4 route show default | awk '{print $5; exit}')
  for p in /sys/class/net/*; do
    i=${p##*/}
    case "$i" in lo|docker*|br-*|veth*|"$NAT_IF") continue ;; esac
    LAB_IF=$i; break
  done
  [ -n "$LAB_IF" ] || die "nie znaleziono interfejsu labnet"
fi
log "interfejs labnet: $LAB_IF -> $IP/24"

cat > /etc/netplan/60-lab.yaml <<EOF
# Siec laboratoryjna labnet (wygenerowane przez vm-bootstrap.sh)
network:
  version: 2
  ethernets:
    $LAB_IF:
      dhcp4: false
      dhcp6: false
      addresses: [$IP/24]
EOF
chmod 600 /etc/netplan/60-lab.yaml

# Zastosowanie tylko dla interfejsu labnet, bez ruszania karty NAT (po niej idzie SSH).
netplan generate
if networkctl reload && networkctl reconfigure "$LAB_IF"; then
  sleep 2
fi
if ! ip -4 addr show dev "$LAB_IF" | grep -q "inet $IP/"; then
  ip addr add "$IP/24" dev "$LAB_IF" 2>/dev/null || true
  ip link set "$LAB_IF" up
fi
ip -br -4 addr show dev "$LAB_IF"

# ---------------------------------------------------------------------------
# 3. Czujnik: tryb nasluchu na stale i adresy MAC w konfiguracji arp_spoof
# ---------------------------------------------------------------------------
if [ "$ROLE" = sensor ]; then
  cat > /etc/systemd/system/lab-promisc.service <<EOF
[Unit]
Description=Tryb nasluchu na interfejsie labnet ($LAB_IF)
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/sbin/ip link set $LAB_IF promisc on
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now lab-promisc.service >/dev/null
  log "tryb nasluchu wlaczony na $LAB_IF"

  if [ -n "$CLIENT_MAC" ]; then sed -i "s/08:00:27:00:00:20/$CLIENT_MAC/" "$LAB/sensor/lab.lua"; fi
  if [ -n "$SERVER_MAC" ]; then sed -i "s/08:00:27:00:00:30/$SERVER_MAC/" "$LAB/sensor/lab.lua"; fi
  echo "$LAB_IF" > /etc/lab-interface
fi

# ---------------------------------------------------------------------------
# 4. Instalacja oprogramowania roli w tle (przezywa rozlaczenie SSH)
# ---------------------------------------------------------------------------
if [ "$RUN_ROLES" -eq 1 ]; then
  if systemctl is-active --quiet lab-role.service; then
    log "instalacja roli juz trwa (journalctl -fu lab-role)"
  else
    systemctl reset-failed lab-role.service 2>/dev/null || true
    systemd-run --unit=lab-role --description="Instalacja roli $ROLE" \
      -p StandardOutput=append:/var/log/lab-role.log \
      -p StandardError=append:/var/log/lab-role.log \
      /bin/bash "$LAB/vm-roles.sh" "$ROLE" "$USER_NAME" >/dev/null
    log "instalacja roli uruchomiona w tle; postep: sudo tail -f /var/log/lab-role.log"
  fi
fi

chown -R "$USER_NAME:$USER_NAME" "$LAB"
log "gotowe"
