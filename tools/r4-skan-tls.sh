#!/usr/bin/env bash
# r4-skan-tls.sh - rozdzial 4, E3: inwentaryzacja negocjacji TLS obu serwerow
#
# Sprawdza, ktore wersje protokolu i ktore zestawy szyfrow akceptuje kazdy
# z dwoch serwerow laboratorium:
#
#   server:443   nginx, konfiguracja wspolczesna  (TLS 1.2 / 1.3)
#   server:4433  OpenSSL 1.0.2u, konfiguracja stara (wariant podatny)
#
# Dodatkowo sprawdza, czy serwer honoruje TLS_FALLBACK_SCSV - mechanizm, ktory
# pozwala serwerowi odrzucic polaczenie, gdy klient probuje polaczyc sie
# protokolem nizszym niz ten, ktory obie strony potrafia obsluzyc.
#
# Uruchomienie (na maszynie client):
#     bash r4-skan-tls.sh                      # domyslnie 10.10.10.30
#     bash r4-skan-tls.sh 10.10.10.30 ~/wyniki/R4
#
# Wyniki:
#     tls-wersje.csv       tabela: serwer, wersja, wynik negocjacji, szyfr
#     tls-scsv.txt         wynik testu TLS_FALLBACK_SCSV
#     logi/                pelne wyjscie kazdego polaczenia

set -u

HOST="${1:-10.10.10.30}"
OUT="${2:-$HOME/wyniki/R4}"
LOGI="$OUT/logi"

# Stary OpenSSL potrafi SSLv3/TLS 1.0/1.1, ktorych nowy juz nie oferuje.
OSSL_NOWY="$(command -v openssl)"
OSSL_STARY="/opt/openssl-legacy/bin/openssl"

mkdir -p "$LOGI"

if [ ! -x "$OSSL_STARY" ]; then
    echo "[!] Nie znaleziono $OSSL_STARY - stare wersje protokolu zostana pominiete."
    OSSL_STARY=""
fi

echo "==> Skan negocjacji TLS serwera $HOST"
echo "    OpenSSL wspolczesny: $("$OSSL_NOWY" version)"
[ -n "$OSSL_STARY" ] && echo "    OpenSSL stary:       $("$OSSL_STARY" version)"
echo

CSV="$OUT/tls-wersje.csv"
echo "serwer;port;wersja;wynik;szyfr" > "$CSV"

sprawdz_wersje() {
    local opis="$1" port="$2" flaga="$3" etykieta="$4" binarka="$5"
    local plik="$LOGI/${port}-${etykieta}.txt"

    if [ -z "$binarka" ]; then
        echo "${opis};${port};${etykieta};pominieto;-" >> "$CSV"
        printf '    %-22s %-9s %s\n' "$opis" "$etykieta" "pominieto (brak starego OpenSSL)"
        return
    fi

    echo | timeout 15 "$binarka" s_client -connect "${HOST}:${port}" "$flaga" \
        -servername lab.local > "$plik" 2>&1 || true

    # Sukces negocjacji rozpoznajemy po wynegocjowanym szyfrze, nie po obecnosci
    # bloku certyfikatu: w TLS 1.3 certyfikat bywa zapisany inaczej, co dawalo
    # falszywie negatywny wynik. Linia "New, <wersja>, Cipher is <nazwa>"
    # pojawia sie dla obu wersji; przy nieudanym handshake ma wartosc (NONE).
    local szyfr wynik
    szyfr="$(grep -oP 'Cipher is \K\S+' "$plik" | head -1)"
    [ -z "$szyfr" ] && szyfr="$(grep -oP '^\s*Cipher\s*:\s*\K\S+' "$plik" | head -1)"
    if [ -n "$szyfr" ] && [ "$szyfr" != "0000" ] && [ "$szyfr" != "(NONE)" ]; then
        wynik="zaakceptowana"
    else
        wynik="odrzucona"
        szyfr="-"
    fi

    echo "${opis};${port};${etykieta};${wynik};${szyfr}" >> "$CSV"
    printf '    %-22s %-9s %-14s %s\n' "$opis" "$etykieta" "$wynik" "$szyfr"
}

for cel in "nginx wspolczesny:443" "OpenSSL 1.0.2u:4433"; do
    opis="${cel%%:*}"
    port="${cel##*:}"
    echo "--- ${opis} (port ${port}) ---"
    sprawdz_wersje "$opis" "$port" "-ssl3"    "SSLv3"   "$OSSL_STARY"
    sprawdz_wersje "$opis" "$port" "-tls1"    "TLS1.0"  "$OSSL_STARY"
    sprawdz_wersje "$opis" "$port" "-tls1_1"  "TLS1.1"  "$OSSL_STARY"
    sprawdz_wersje "$opis" "$port" "-tls1_2"  "TLS1.2"  "$OSSL_NOWY"
    sprawdz_wersje "$opis" "$port" "-tls1_3"  "TLS1.3"  "$OSSL_NOWY"
    echo
done

# --- TLS_FALLBACK_SCSV -----------------------------------------------------
# Klient, ktory po nieudanej probie polaczenia ponawia ja nizsza wersja
# protokolu, dolacza znacznik TLS_FALLBACK_SCSV. Serwer, ktory obsluguje
# wersje wyzsza niz zadana, powinien wtedy zerwac polaczenie alertem
# inappropriate fallback (alert 86). Brak tej reakcji oznacza, ze wymuszenie
# nizszej wersji przez posrednika w sieci pozostaje niezauwazone.

echo "--- Test TLS_FALLBACK_SCSV ---" | tee "$OUT/tls-scsv.txt"
for cel in "nginx wspolczesny:443" "OpenSSL 1.0.2u:4433"; do
    opis="${cel%%:*}"
    port="${cel##*:}"
    plik="$LOGI/${port}-scsv.txt"
    echo | timeout 15 "$OSSL_NOWY" s_client -connect "${HOST}:${port}" \
        -tls1_2 -fallback_scsv -servername lab.local > "$plik" 2>&1 || true

    if grep -qi "inappropriate fallback" "$plik"; then
        wynik="serwer odrzucil polaczenie (alert inappropriate fallback) - ochrona dziala"
    elif grep -q "BEGIN CERTIFICATE" "$plik"; then
        wynik="serwer zaakceptowal polaczenie mimo znacznika - brak ochrony"
    else
        wynik="polaczenie nieudane z innego powodu - sprawdz $plik"
    fi
    printf '    %-22s port %-5s %s\n' "$opis" "$port" "$wynik" | tee -a "$OUT/tls-scsv.txt"
done

echo
echo "Gotowe. Wyniki w $OUT - wgraj folder do repozytorium jako wyniki/R4."
