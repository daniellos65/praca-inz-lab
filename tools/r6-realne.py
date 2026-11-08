#!/usr/bin/env python3
"""
r6-realne.py - rozdzial 6.2: klasyfikatory A i B na RZECZYWISTYCH kontenerach

Uzupelnienie zbioru syntetycznego (r6-gen-zbior.py). W zbiorze syntetycznym
role danych zaszyfrowanych pelnily dane losowe bez naglowka. Tu sprawdzamy,
jak te same klasyfikatory zachowuja sie dla prawdziwych plikow zaszyfrowanych
utworzonych w rozdziale 5:
  - kontenery VeraCrypt (.hc)   - z zalozenia bez rozpoznawalnego naglowka,
  - bazy KeePass (.kdbx)        - maja wlasna sygnature na poczatku pliku,
  - archiwum 7-Zip z haslem     - ma naglowek formatu 7z.

Dla kazdego pliku: entropia Shannona, statystyka chi-kwadrat (256 wartosci
bajtow wzgledem rozkladu jednostajnego), rozpoznany naglowek oraz decyzje
klasyfikatorow A (H >= 7,5) i B (H >= 7,5, chi2 <= 293,25, brak naglowka).
Progi identyczne jak w r6-entropia.py. Duze pliki sa analizowane na probce
z poczatku pliku (domyslnie 8 MiB) - tak, jak robilby to system DLP.

Uruchomienie (Windows, w folderze ze skryptem):
    py r6-realne.py                                   # F:\\praca-inz\\pliki-testowe
    py r6-realne.py F:\\inny\\folder --out wyniki-R6

Wyniki: <out>/realne.csv oraz <out>/realne-podsumowanie.txt
Wymaga wylacznie biblioteki standardowej.
"""
import argparse
import csv
import math
import os

PROG_H = 7.5
PROG_CHI2 = 293.25
PROBKA = 8 * 1024 * 1024

# Te same sygnatury co w r6-entropia.py + sygnatura bazy KeePass (KDBX).
MAGIC = {
    b"\x1f\x8b": "gzip",
    b"PK\x03\x04": "zip",
    b"7z\xbc\xaf\x27\x1c": "7z",
    b"\x89PNG": "png",
    b"\xff\xd8\xff": "jpeg",
    b"%PDF": "pdf",
    b"BZh": "bzip2",
    b"\xfd7zXZ\x00": "xz",
    b"Rar!": "rar",
    b"\x03\xd9\xa2\x9a": "kdbx (KeePass)",
}


def cechy(dane):
    n = len(dane)
    if n == 0:
        return 0.0, 0.0
    licz = [dane.count(bytes([b])) for b in range(256)]   # szybkie zliczanie w C
    H = -sum((c / n) * math.log2(c / n) for c in licz if c)
    e = n / 256.0
    chi2 = sum((c - e) ** 2 / e for c in licz)
    return H, chi2


def naglowek(dane):
    for sygn, nazwa in MAGIC.items():
        if dane.startswith(sygn):
            return nazwa
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("folder", nargs="?", default=r"F:\praca-inz\pliki-testowe")
    p.add_argument("--out", default="wyniki-R6")
    a = p.parse_args()
    os.makedirs(a.out, exist_ok=True)

    wiersze = []
    for nazwa in sorted(os.listdir(a.folder)):
        sc = os.path.join(a.folder, nazwa)
        if not os.path.isfile(sc):
            continue
        rozmiar = os.path.getsize(sc)
        with open(sc, "rb") as f:
            dane = f.read(PROBKA)
        H, chi2 = cechy(dane)
        mg = naglowek(dane)
        A = H >= PROG_H
        B = A and chi2 <= PROG_CHI2 and mg is None
        wiersze.append({"plik": nazwa, "rozmiar_B": rozmiar, "analizowano_B": len(dane),
                        "entropia": round(H, 4), "chi2": round(chi2, 1),
                        "naglowek": mg or "-", "A_zaszyfrowany": "tak" if A else "nie",
                        "B_zaszyfrowany": "tak" if B else "nie"})

    if not wiersze:
        print(f"[!] Brak plikow w {a.folder}")
        return
    with open(os.path.join(a.out, "realne.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(wiersze[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(wiersze)

    L = ["Klasyfikatory A i B na rzeczywistych plikach z rozdzialu 5",
         f"folder: {a.folder}", "",
         "{:<28} {:>10} {:>9} {:>10} {:<16} {:>4} {:>4}".format(
             "plik", "rozmiar", "H", "chi2", "naglowek", "A", "B")]
    for w in wiersze:
        L.append("{:<28} {:>10} {:>9.4f} {:>10.1f} {:<16} {:>4} {:>4}".format(
            w["plik"][:28], w["rozmiar_B"], w["entropia"], w["chi2"], w["naglowek"],
            w["A_zaszyfrowany"], w["B_zaszyfrowany"]))
    tekst = "\n".join(L)
    print(tekst)
    with open(os.path.join(a.out, "realne-podsumowanie.txt"), "w", encoding="utf-8") as f:
        f.write(tekst + "\n")
    print(f"\nWyniki: {os.path.abspath(a.out)} (realne.csv, realne-podsumowanie.txt)")


if __name__ == "__main__":
    main()
