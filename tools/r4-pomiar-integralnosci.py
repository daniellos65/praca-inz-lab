#!/usr/bin/env python3
"""
r4-pomiar-integralnosci.py - rozdzial 4: pomiar odpornosci komunikatu na modyfikacje

Bada, jak kazdy z wariantow aplikacji laboratoryjnej reaguje na komunikat
zmodyfikowany w drodze miedzy klientem a serwerem:

  E1  ciasteczko sesyjne
        /profile          AES-128-CBC bez MAC     (wariant podatny)
        /secure/profile   AES-128-GCM             (wariant poprawiony)

  E2  podpis zlecenia API
        /api/transfer          SHA-256(sekret||msg)   (wariant podatny)
        /api/secure/transfer   HMAC-SHA-256           (wariant poprawiony)

Metryka glowna: odsetek zmodyfikowanych komunikatow przyjetych przez serwer
(HTTP 200). Dla wariantu z AEAD lub MAC oczekiwana wartosc wynosi 0%.

W czesci E1 kazda proba zmienia jeden losowy bajt tokenu i zapisuje, w ktorym
obszarze tokenu lezal ten bajt (IV, blok posredni, blok ostatni). Pozwala to
pokazac, ze w trybie CBC bez kontroli integralnosci skutek modyfikacji zalezy
od jej polozenia, podczas gdy w trybie GCM kazda modyfikacja jest wykrywana
niezaleznie od polozenia.

Uruchomienie (na maszynie client, aplikacja na server):
    python3 r4-pomiar-integralnosci.py --host 10.10.10.30

Opcje:
    --host 10.10.10.30        adres serwera aplikacji
    --port 5000               port aplikacji
    --proby 200               liczba prob na wariant
    --out  ~/wyniki/R4        folder na wyniki
    --ziarno 20261025         ziarno generatora, dla powtarzalnosci pomiaru

Wyniki:
    e1-proby.csv        kazda proba E1 osobno
    e2-proby.csv        kazda proba E2 osobno
    podsumowanie.txt    tabele zbiorcze do pracy
"""

import argparse
import base64
import csv
import json
import os
import random
import sys
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 10


# ---------------------------------------------------------------------------
# Warstwa HTTP (tylko biblioteka standardowa - na kliencie nie ma 'requests')
# ---------------------------------------------------------------------------

def http_get(url, cookie=None):
    """Zwraca (kod_http, tresc_jako_slownik_lub_tekst, naglowki)."""
    req = urllib.request.Request(url)
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            kod, surowe, naglowki = r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        kod, surowe, naglowki = e.code, e.read(), e.headers
    except urllib.error.URLError as e:
        print(f"[!] Brak polaczenia z {url}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    try:
        tresc = json.loads(surowe.decode("utf-8"))
    except Exception:
        tresc = surowe.decode("utf-8", "replace")
    return kod, tresc, naglowki


def pobierz_ciasteczko(baza, sciezka_login, nazwa):
    """Loguje sie i zwraca wartosc ciasteczka o podanej nazwie."""
    kod, tresc, naglowki = http_get(f"{baza}{sciezka_login}?user=student")
    if kod != 200:
        print(f"[!] Logowanie {sciezka_login} zwrocilo {kod}: {tresc}", file=sys.stderr)
        sys.exit(1)
    for naglowek in naglowki.get_all("Set-Cookie") or []:
        if naglowek.startswith(nazwa + "="):
            return naglowek.split(";", 1)[0].split("=", 1)[1]
    print(f"[!] Serwer nie ustawil ciasteczka '{nazwa}'.", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# E1 - odpornosc ciasteczka na modyfikacje
# ---------------------------------------------------------------------------

def obszar_cbc(pozycja, dlugosc):
    """Nazwa obszaru tokenu CBC: IV, blok posredni albo blok ostatni."""
    if pozycja < 16:
        return "IV"
    if pozycja >= dlugosc - 16:
        return "blok ostatni"
    return "blok posredni"


def zmien_bajt(surowe, pozycja, rng):
    """Zwraca kopie bufora z jednym bajtem zmienionym na inna wartosc."""
    bufor = bytearray(surowe)
    bufor[pozycja] ^= rng.randrange(1, 256)
    return bytes(bufor)


def pomiar_e1(baza, wariant, proby, rng):
    """Wykonuje serie prob dla jednego wariantu ciasteczka. Zwraca liste wierszy."""
    if wariant == "cbc":
        token = pobierz_ciasteczko(baza, "/login", "session")
        sciezka, nazwa_ciasteczka, opis = "/profile", "session", "AES-CBC bez MAC"
    else:
        token = pobierz_ciasteczko(baza, "/secure/login", "secure_session")
        sciezka, nazwa_ciasteczka, opis = "/secure/profile", "secure_session", "AES-GCM"

    surowe = base64.urlsafe_b64decode(token)
    dlugosc = len(surowe)

    # Proba odniesienia: token nienaruszony musi zostac przyjety.
    kod, tresc, _ = http_get(f"{baza}{sciezka}", f"{nazwa_ciasteczka}={token}")
    if kod != 200:
        print(f"[!] Token nienaruszony odrzucony ({kod}) na {sciezka}: {tresc}", file=sys.stderr)
        sys.exit(1)
    pola_wzorcowe = tresc.get("fields", {}) if isinstance(tresc, dict) else {}
    print(f"    odniesienie {opis}: HTTP 200, pola {pola_wzorcowe}")

    wiersze = []
    for nr in range(1, proby + 1):
        pozycja = rng.randrange(dlugosc)
        zmieniony = base64.urlsafe_b64encode(zmien_bajt(surowe, pozycja, rng)).decode()
        kod, tresc, _ = http_get(f"{baza}{sciezka}", f"{nazwa_ciasteczka}={zmieniony}")

        pola = tresc.get("fields", {}) if isinstance(tresc, dict) else {}
        przyjete = kod == 200
        wiersze.append({
            "wariant": opis,
            "proba": nr,
            "pozycja": pozycja,
            "obszar": obszar_cbc(pozycja, dlugosc) if wariant == "cbc" else "caly token",
            "kod_http": kod,
            "przyjete": int(przyjete),
            "tresc_zmieniona": int(przyjete and pola != pola_wzorcowe),
            "pola": json.dumps(pola, ensure_ascii=False),
        })
        if nr % 50 == 0:
            print(f"    {opis}: {nr}/{proby}")
    return wiersze


# ---------------------------------------------------------------------------
# E2 - weryfikacja podpisu zlecenia
# ---------------------------------------------------------------------------

def pomiar_e2(baza, wariant, rng):
    """Sprawdza, czy serwer wykrywa rozne rodzaje naruszenia pary (wiadomosc, podpis)."""
    if wariant == "naive":
        sciezka_wzor, sciezka_test, opis = "/api/sample", "/api/transfer", "SHA-256(sekret||msg)"
    else:
        sciezka_wzor, sciezka_test, opis = "/api/secure/sample", "/api/secure/transfer", "HMAC-SHA-256"

    kod, wzor, _ = http_get(f"{baza}{sciezka_wzor}")
    if kod != 200 or not isinstance(wzor, dict):
        print(f"[!] {sciezka_wzor} zwrocilo {kod}: {wzor}", file=sys.stderr)
        sys.exit(1)
    msg, sig = wzor["msg"].encode(), wzor["sig"]

    def wyslij(m, s):
        url = f"{baza}{sciezka_test}?msg={urllib.parse.quote_from_bytes(m, safe='')}&sig={s}"
        kod, tresc, _ = http_get(url)
        return kod, tresc

    # Zestaw prob: komunikat nienaruszony oraz cztery rodzaje naruszenia.
    przypadki = [
        ("komunikat nienaruszony", msg, sig, True),
        ("zmieniona wartosc pola w wiadomosci", msg.replace(b"amount=10", b"amount=99"), sig, False),
        ("sufiks doklejony do wiadomosci", msg + b"&amount=99", sig, False),
        ("jeden znak podpisu zmieniony", msg, ("0" if sig[0] != "0" else "1") + sig[1:], False),
        ("podpis losowy", msg, "%064x" % rng.getrandbits(256), False),
    ]

    wiersze = []
    for nazwa, m, s, oczekiwane_przyjecie in przypadki:
        kod, tresc = wyslij(m, s)
        przyjete = kod == 200
        wiersze.append({
            "wariant": opis,
            "przypadek": nazwa,
            "kod_http": kod,
            "przyjete": int(przyjete),
            "zgodne_z_oczekiwaniem": int(przyjete == oczekiwane_przyjecie),
            "odpowiedz": json.dumps(tresc, ensure_ascii=False)[:200],
        })
        znacznik = "OK " if przyjete == oczekiwane_przyjecie else "!! "
        print(f"    {znacznik}{opis:22} | {nazwa:36} | HTTP {kod}")
    return wiersze


# ---------------------------------------------------------------------------
# Raport
# ---------------------------------------------------------------------------

def zapisz_csv(sciezka, wiersze):
    if not wiersze:
        return
    with open(sciezka, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(wiersze[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(wiersze)


def main():
    p = argparse.ArgumentParser(description="Rozdzial 4: pomiar odpornosci na modyfikacje komunikatu")
    p.add_argument("--host", default="10.10.10.30")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--proby", type=int, default=200)
    p.add_argument("--out", default=os.path.expanduser("~/wyniki/R4"))
    p.add_argument("--ziarno", type=int, default=20261025)
    a = p.parse_args()

    baza = f"http://{a.host}:{a.port}"
    rng = random.Random(a.ziarno)
    os.makedirs(a.out, exist_ok=True)

    kod, tresc, _ = http_get(baza + "/")
    if kod != 200:
        print(f"[!] Aplikacja pod {baza} nie odpowiada poprawnie (HTTP {kod}).", file=sys.stderr)
        sys.exit(1)
    print(f"==> Aplikacja {baza} odpowiada. Ziarno generatora: {a.ziarno}\n")

    print(f"==> E1: odpornosc ciasteczka na modyfikacje ({a.proby} prob na wariant)")
    e1 = pomiar_e1(baza, "cbc", a.proby, rng) + pomiar_e1(baza, "gcm", a.proby, rng)
    zapisz_csv(os.path.join(a.out, "e1-proby.csv"), e1)

    print("\n==> E2: weryfikacja podpisu zlecenia")
    e2 = pomiar_e2(baza, "naive", rng) + pomiar_e2(baza, "hmac", rng)
    zapisz_csv(os.path.join(a.out, "e2-proby.csv"), e2)

    # --- tabele zbiorcze ---
    linie = []
    linie.append("E1. Odsetek zmodyfikowanych ciasteczek przyjetych przez serwer")
    linie.append("")
    linie.append("{:<22} {:>8} {:>10} {:>12} {:>18}".format(
        "Wariant", "Proby", "Przyjete", "Odsetek [%]", "Zmieniona tresc"))
    for opis in ["AES-CBC bez MAC", "AES-GCM"]:
        grupa = [w for w in e1 if w["wariant"] == opis]
        if not grupa:
            continue
        przyjete = sum(w["przyjete"] for w in grupa)
        zmienione = sum(w["tresc_zmieniona"] for w in grupa)
        linie.append("{:<22} {:>8} {:>10} {:>12.1f} {:>18}".format(
            opis, len(grupa), przyjete, 100.0 * przyjete / len(grupa), zmienione))

    linie.append("")
    linie.append("E1a. Wariant AES-CBC bez MAC w podziale na obszar modyfikacji")
    linie.append("")
    linie.append("{:<18} {:>8} {:>10} {:>12}".format("Obszar tokenu", "Proby", "Przyjete", "Odsetek [%]"))
    for obszar in ["IV", "blok posredni", "blok ostatni"]:
        grupa = [w for w in e1 if w["wariant"] == "AES-CBC bez MAC" and w["obszar"] == obszar]
        if not grupa:
            continue
        przyjete = sum(w["przyjete"] for w in grupa)
        linie.append("{:<18} {:>8} {:>10} {:>12.1f}".format(
            obszar, len(grupa), przyjete, 100.0 * przyjete / len(grupa)))

    linie.append("")
    linie.append("E2. Reakcja na naruszenie pary (wiadomosc, podpis)")
    linie.append("")
    linie.append("{:<22} {:<38} {:>10} {:>10}".format("Wariant", "Przypadek", "HTTP", "Przyjete"))
    for w in e2:
        linie.append("{:<22} {:<38} {:>10} {:>10}".format(
            w["wariant"], w["przypadek"], w["kod_http"], "tak" if w["przyjete"] else "nie"))

    raport = "\n".join(linie)
    print("\n" + raport)
    with open(os.path.join(a.out, "podsumowanie.txt"), "w", encoding="utf-8") as f:
        f.write(raport + "\n")
    print(f"\nGotowe. Wyniki w {a.out} - wgraj folder do repozytorium jako wyniki/R4.")


if __name__ == "__main__":
    main()
