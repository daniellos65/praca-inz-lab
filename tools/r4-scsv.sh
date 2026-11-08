#!/usr/bin/env bash
# r4-scsv.sh - rozdzial 4.2: uzupelniajacy test TLS_FALLBACK_SCSV
#
# Serwer odrzuca polaczenie ze znacznikiem TLS_FALLBACK_SCSV tylko wtedy,
# gdy sam obsluguje wersje WYZSZA niz zaoferowana przez klienta (RFC 7507).
# W pierwszym tescie (r4-skan-tls.sh) serwer przestarzaly dostal oferte
# TLS 1.2, czyli swoja wersje maksymalna - przyjecie polaczenia bylo wiec
# zgodne ze standardem i nie rozstrzygalo o obsludze mechanizmu.
# Ten test oferuje serwerowi przestarzalemu wersje NIZSZE niz TLS 1.2.
#
# Przypadki:
#   1. :4433  TLS 1.1 + SCSV          (wlasciwy test)
#   2. :4433  TLS 1.0 + SCSV          (wlasciwy test)
#   3. :4433  TLS 1.1 bez SCSV        (kontrola: ta sama wersja bez znacznika)
#   4. :443   TLS 1.2 + SCSV          (kontrola: serwer wspolczesny)
#
# Uruchomienie (na maszynie client):
#     bash r4-scsv.sh                 # domyslnie 10.10.10.30, wyniki w ~/wyniki/R4
#
# Wyniki: ~/wyniki/R4/scsv-uzupelnienie.txt oraz logi w ~/wyniki/R4/logi/scsv-*.txt

set -u
HOST="${1:-10.10.10.30}"
OUT="${2:-$HOME/wyniki/R4}"
STARY="/opt/openssl-legacy/bin/openssl"
NOWY="$(command -v openssl)"
mkdir -p "$OUT/logi"
RAPORT="$OUT/scsv-uzupelnienie.txt"

if [ ! -x "$STARY" ]; then
    echo "[!] Brak $STARY - test wymaga starego OpenSSL na kliencie."; exit 1
fi

{
  echo "Test uzupelniajacy TLS_FALLBACK_SCSV, serwer $HOST, $(date '+%Y-%m-%d %H:%M')"
  echo "Klient: $("$STARY" version) / $("$NOWY" version)"
  echo
} > "$RAPORT"

test_scsv() {
    local nr="$1" opis="$2" bin="$3" port="$4"; shift 4
    local plik="$OUT/logi/scsv-$nr.txt"
    echo | timeout 15 "$bin" s_client -connect "${HOST}:${port}" "$@" > "$plik" 2>&1 || true
    local szyfr wynik
    szyfr="$(grep -oP 'Cipher is \K\S+' "$plik" | head -1)"
    if grep -qi "inappropriate fallback" "$plik"; then
        wynik="ODRZUCONE - alert inappropriate_fallback (ochrona dziala)"
    elif [ -n "$szyfr" ] && [ "$szyfr" != "(NONE)" ]; then
        wynik="POLACZENIE ZESTAWIONE ($(grep -oP 'Protocol\s*:\s*\K\S+' "$plik" | head -1), $szyfr)"
    else
        wynik="NIEUDANE z innego powodu - zob. logi/scsv-$nr.txt"
    fi
    printf '%s. %-34s -> %s\n' "$nr" "$opis" "$wynik" | tee -a "$RAPORT"
}

echo "==> Test uzupelniajacy SCSV ($HOST)"
test_scsv 1 ":4433 TLS 1.1 + SCSV"           "$STARY" 4433 -tls1_1 -fallback_scsv
test_scsv 2 ":4433 TLS 1.0 + SCSV"           "$STARY" 4433 -tls1   -fallback_scsv
test_scsv 3 ":4433 TLS 1.1 bez SCSV (kontr.)" "$STARY" 4433 -tls1_1
test_scsv 4 ":443  TLS 1.2 + SCSV (kontr.)"   "$NOWY"  443  -tls1_2 -fallback_scsv
echo
echo "Gotowe. Raport: $RAPORT"
