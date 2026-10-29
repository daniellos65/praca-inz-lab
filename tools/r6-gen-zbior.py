#!/usr/bin/env python3
"""
r6-gen-zbior.py - generuje zbior testowy do detekcji entropijnej (rozdzial 6.2)

Tworzy trzy grupy plikow roznia​ce sie charakterem rozkladu bajtow:

  jawne/          tekst, kod, CSV, JSON, log, HTML - niska entropia, rozklad
                  silnie nierownomierny (dominacja znakow ASCII)
  skompresowane/  te same dane po kompresji (gzip, zip) oraz dane
                  pseudo-losowe o strukturze naglowka - WYSOKA entropia, ale
                  rozklad bajtow nie jest idealnie jednostajny i zwykle jest
                  obecny rozpoznawalny naglowek (magic bytes)
  zaszyfrowane/   dane nieodroznialne od losowych (os.urandom jako model
                  dobrego szyfru strumieniowego/AEAD) oraz kontenery bez
                  rozpoznawalnego naglowka - entropia bliska 8 bit/bajt,
                  rozklad jednostajny, brak magic bytes

Cel zbioru: pokazac, ze sama entropia nie wystarcza do odroznienia danych
skompresowanych od zaszyfrowanych (obie grupy maja wysoka entropie), i ze
dopiero test rownomiernosci rozkladu (chi-kwadrat) oraz rozpoznanie naglowka
pozwalaja te grupy rozdzielic. To jest teza podrozdzialu 6.2.

Zbior jest w pelni syntetyczny i powtarzalny (stale ziarno) - nie korzysta
z zadnych prywatnych plikow. Do grupy 'zaszyfrowane' mozna dodatkowo wrzucic
realne kontenery (np. kopie .kdbx, archiwum 7z z haslem) recznie.

Uruchomienie:
    python3 r6-gen-zbior.py                  # zapis do ./zbior
    python3 r6-gen-zbior.py /sciezka/zbior   # wlasna lokalizacja

Wymaga wylacznie biblioteki standardowej.
"""

import gzip
import io
import json
import os
import random
import sys
import zipfile
import zlib

ZIARNO = 20261029
LICZBA = 20          # plikow na grupe (orientacyjnie)


def katalogi(baza):
    sciezki = {g: os.path.join(baza, g) for g in ("jawne", "skompresowane", "zaszyfrowane")}
    for s in sciezki.values():
        os.makedirs(s, exist_ok=True)
    return sciezki


# ---------------------------------------------------------------------------
# Generatory tresci jawnej (niska entropia, rozklad nierownomierny)
# ---------------------------------------------------------------------------

SLOWA = ("sieci protokol analiza bezpieczenstwo system dane pakiet warstwa "
         "klucz szyfr integralnosc detekcja ruch adres host serwer klient "
         "sesja naglowek wartosc pole rekord zapis odczyt test wynik pomiar").split()


def tekst_naturalny(rng, zdan=400):
    linie = []
    for _ in range(zdan):
        n = rng.randint(6, 14)
        zdanie = " ".join(rng.choice(SLOWA) for _ in range(n))
        linie.append(zdanie.capitalize() + ".")
    return ("\n".join(linie) + "\n").encode("utf-8")


def kod_python(rng, funkcji=60):
    out = ["#!/usr/bin/env python3", "import os, sys", ""]
    for i in range(funkcji):
        out.append(f"def funkcja_{i}(a, b):")
        out.append(f"    # obliczenie pomocnicze numer {i}")
        out.append("    wynik = (a * b) + "
                   f"{rng.randint(1, 999)}")
        out.append("    return wynik")
        out.append("")
    return ("\n".join(out)).encode("utf-8")


def csv_liczbowy(rng, wierszy=800):
    out = ["id;czas;adres;port;dlugosc;flaga"]
    for i in range(wierszy):
        out.append(f"{i};{rng.randint(0, 99999)};10.10.10.{rng.randint(1, 254)};"
                   f"{rng.choice((80, 443, 5000, 4433))};{rng.randint(40, 1500)};"
                   f"{rng.choice(('ACK', 'SYN', 'PSH', 'FIN'))}")
    return ("\n".join(out) + "\n").encode("utf-8")


def json_rekordy(rng, rekordow=300):
    dane = [{"id": i, "host": f"host-{rng.randint(1, 50)}",
             "status": rng.choice(["ok", "blad", "nieznany"]),
             "wartosc": rng.randint(0, 100000)} for i in range(rekordow)]
    return json.dumps(dane, ensure_ascii=False, indent=2).encode("utf-8")


def log_serwera(rng, linii=600):
    out = []
    for _ in range(linii):
        out.append(f"[2026-10-29 {rng.randint(0,23):02d}:{rng.randint(0,59):02d}] "
                   f"INFO zadanie z 10.10.10.{rng.randint(1,254)} "
                   f"kod={rng.choice((200,301,403,404,500))} "
                   f"czas={rng.randint(1,900)}ms")
    return ("\n".join(out) + "\n").encode("utf-8")


def html_strona(rng, sekcji=80):
    out = ["<!doctype html>", "<html><head><title>Raport</title></head><body>"]
    for i in range(sekcji):
        out.append(f"<h2>Sekcja {i}</h2><p>" +
                   " ".join(rng.choice(SLOWA) for _ in range(rng.randint(20, 60))) +
                   "</p>")
    out.append("</body></html>")
    return ("\n".join(out)).encode("utf-8")


GENERATORY_JAWNE = [
    ("txt", tekst_naturalny), ("py", kod_python), ("csv", csv_liczbowy),
    ("json", json_rekordy), ("log", log_serwera), ("html", html_strona),
]


# ---------------------------------------------------------------------------
# Budowa grup
# ---------------------------------------------------------------------------

def zapisz(sciezka, dane):
    with open(sciezka, "wb") as f:
        f.write(dane)


def main():
    baza = sys.argv[1] if len(sys.argv) > 1 else "zbior"
    kat = katalogi(baza)
    rng = random.Random(ZIARNO)

    # --- grupa jawne: rotacja po typach az do LICZBA plikow ---
    jawne_dane = []
    for i in range(LICZBA):
        ext, gen = GENERATORY_JAWNE[i % len(GENERATORY_JAWNE)]
        dane = gen(rng)
        nazwa = f"jawny-{i:02d}.{ext}"
        zapisz(os.path.join(kat["jawne"], nazwa), dane)
        jawne_dane.append((nazwa, dane))

    # --- grupa skompresowane: gzip i zip danych jawnych ---
    # Kompresja usuwa redundancje, wiec entropia rosnie niemal do maksimum,
    # ale pozostaje naglowek formatu i rozklad nie jest idealnie jednostajny.
    for i in range(LICZBA):
        nazwa_src, dane = jawne_dane[i % len(jawne_dane)]
        if i % 2 == 0:
            spakowane = gzip.compress(dane, compresslevel=9)
            ext = "gz"
        else:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
                z.writestr(nazwa_src, dane)
            spakowane = buf.getvalue()
            ext = "zip"
        zapisz(os.path.join(kat["skompresowane"], f"skompresowany-{i:02d}.{ext}"), spakowane)

    # --- grupa zaszyfrowane: dane nieodroznialne od losowych ---
    # os.urandom to model wyjscia dobrego szyfru (AEAD / strumieniowego):
    # rozklad jednostajny, entropia ~8 bit/bajt, brak rozpoznawalnego naglowka.
    for i in range(LICZBA):
        rozmiar = rng.randint(4096, 65536)
        dane = os.urandom(rozmiar)
        zapisz(os.path.join(kat["zaszyfrowane"], f"zaszyfrowany-{i:02d}.bin"), dane)

    # Podsumowanie
    for g, s in kat.items():
        pliki = os.listdir(s)
        laczny = sum(os.path.getsize(os.path.join(s, p)) for p in pliki)
        print(f"{g:14} {len(pliki):3} plikow, {laczny/1024:8.1f} kB")
    print(f"\nZbior gotowy w: {os.path.abspath(baza)}")
    print("Do grupy 'zaszyfrowane' mozesz dodac realne kontenery (kopie .kdbx,")
    print("archiwum 7z z haslem) - zwiekszy to realizm oceny.")


if __name__ == "__main__":
    main()
