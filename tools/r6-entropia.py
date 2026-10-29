#!/usr/bin/env python3
"""
r6-entropia.py - detekcja danych zaszyfrowanych na podstawie rozkladu bajtow (6.2)

Dla kazdego pliku w zbiorze testowym (podkatalogi: jawne, skompresowane,
zaszyfrowane) liczy trzy cechy i na ich podstawie klasyfikuje plik jako
"zaszyfrowany" albo "inny":

  1. Entropia Shannona [bit/bajt], zakres 0..8. Dane zaszyfrowane maja entropie
     bliska 8. Problem: dane skompresowane rowniez (kompresja usuwa redundancje).
     Sama entropia nie rozdziela tych dwoch grup.

  2. Statystyka chi-kwadrat rozkladu 256 wartosci bajtow wzgledem rozkladu
     jednostajnego. Dane zaszyfrowane sa statystycznie nieodroznialne od
     losowych, wiec chi-kwadrat jest niskie (rozklad jednostajny). Dane
     skompresowane maja wysoka entropie, ale rozklad nie jest idealnie
     jednostajny (obecne naglowki, slowniki), wiec chi-kwadrat jest wyzsze.

  3. Rozpoznanie typu po naglowku (magic bytes). Pliki skompresowane i wiele
     formatow nosnikow maja rozpoznawalny naglowek; dane zaszyfrowane dobrym
     algorytmem go nie maja.

Porownywane sa dwa klasyfikatory:
  A: sama entropia              H >= PROG_H
  B: entropia + chi-kwadrat + brak znanego naglowka
                                H >= PROG_H  oraz  chi2 <= PROG_CHI2  oraz  brak magic

Grupa 'zaszyfrowane' jest klasa pozytywna. Dla kazdego klasyfikatora liczona
jest macierz pomylek oraz czulosc (TPR), odsetek falszywych alarmow (FPR),
precyzja i dokladnosc.

Dodatkowo badane jest ograniczenie: pliki zaszyfrowane zakodowane Base64 maja
nizsza entropie (alfabet 64 znakow => max 6 bit/bajt), przez co klasyfikator
oparty na samej entropii je przeocza.

Literatura: Lyda R., Hamrock J., "Using Entropy Analysis to Find Encrypted and
Packed Malware", IEEE Security & Privacy 2007.

Uruchomienie:
    python3 r6-entropia.py                 # analizuje ./zbior
    python3 r6-entropia.py /sciezka/zbior --out ./wyniki-R6

Wymaga wylacznie biblioteki standardowej.
"""

import argparse
import base64
import csv
import math
import os

PROG_H = 7.5        # bit/bajt - prog wysokiej entropii
# Prog chi-kwadrat: kwantyl 0.95 rozkladu chi2 o 255 stopniach swobody ~= 293.
# Rozklad jednostajny (dane zaszyfrowane) daje chi2 ponizej tej wartosci,
# rozklad danych skompresowanych - zwykle powyzej.
PROG_CHI2 = 293.25

# Sygnatury naglowkow (magic bytes) typowych formatow skompresowanych/nosnikow.
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
}


def entropia_i_chi2(dane):
    """Zwraca (entropia_bit_na_bajt, statystyka_chi2) dla bufora bajtow."""
    n = len(dane)
    if n == 0:
        return 0.0, 0.0
    licznik = [0] * 256
    for b in dane:
        licznik[b] += 1
    H = 0.0
    oczek = n / 256.0
    chi2 = 0.0
    for c in licznik:
        if c:
            p = c / n
            H -= p * math.log2(p)
        chi2 += (c - oczek) * (c - oczek) / oczek
    return H, chi2


def rozpoznaj_naglowek(dane):
    """Zwraca nazwe formatu po magic bytes albo None."""
    for sygn, nazwa in MAGIC.items():
        if dane.startswith(sygn):
            return nazwa
    return None


def klasyfikuj(H, chi2, magic):
    """Zwraca (decyzja_A, decyzja_B) - czy plik uznano za zaszyfrowany."""
    a = H >= PROG_H
    b = (H >= PROG_H) and (chi2 <= PROG_CHI2) and (magic is None)
    return a, b


def metryki(wiersze, pole_decyzji):
    """Liczy TP/FP/TN/FN i pochodne dla jednego klasyfikatora."""
    tp = fp = tn = fn = 0
    for w in wiersze:
        pozytyw_prawda = (w["grupa"] == "zaszyfrowane")
        pozytyw_decyzja = w[pole_decyzji]
        if pozytyw_prawda and pozytyw_decyzja:
            tp += 1
        elif pozytyw_prawda and not pozytyw_decyzja:
            fn += 1
        elif not pozytyw_prawda and pozytyw_decyzja:
            fp += 1
        else:
            tn += 1
    tpr = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    dokl = (tp + tn) / (tp + tn + fp + fn) if wiersze else 0.0
    return dict(TP=tp, FP=fp, TN=tn, FN=fn, TPR=tpr, FPR=fpr, PREC=prec, DOKL=dokl)


def blok_metryk(nazwa, m):
    linie = [f"{nazwa}",
             f"  TP={m['TP']}  FP={m['FP']}  TN={m['TN']}  FN={m['FN']}",
             f"  czulosc (TPR)        = {m['TPR']*100:5.1f} %",
             f"  falszywe alarmy (FPR)= {m['FPR']*100:5.1f} %",
             f"  precyzja             = {m['PREC']*100:5.1f} %",
             f"  dokladnosc           = {m['DOKL']*100:5.1f} %"]
    return "\n".join(linie)


def main():
    p = argparse.ArgumentParser(description="Rozdzial 6.2: detekcja entropijna")
    p.add_argument("zbior", nargs="?", default="zbior")
    p.add_argument("--out", default="wyniki-R6")
    a = p.parse_args()
    os.makedirs(a.out, exist_ok=True)

    wiersze = []
    for grupa in ("jawne", "skompresowane", "zaszyfrowane"):
        kat = os.path.join(a.zbior, grupa)
        if not os.path.isdir(kat):
            print(f"[!] Brak katalogu {kat} - uruchom najpierw r6-gen-zbior.py")
            return
        for nazwa in sorted(os.listdir(kat)):
            sciezka = os.path.join(kat, nazwa)
            if not os.path.isfile(sciezka):
                continue
            with open(sciezka, "rb") as f:
                dane = f.read()
            H, chi2 = entropia_i_chi2(dane)
            magic = rozpoznaj_naglowek(dane)
            dec_a, dec_b = klasyfikuj(H, chi2, magic)
            wiersze.append({
                "grupa": grupa, "plik": nazwa, "rozmiar": len(dane),
                "entropia": round(H, 4), "chi2": round(chi2, 1),
                "magic": magic or "-",
                "decyzja_A": dec_a, "decyzja_B": dec_b,
            })

    # CSV ze szczegolami
    with open(os.path.join(a.out, "pliki.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(wiersze[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(wiersze)

    # Srednie cech w grupach - pokazuja, dlaczego sama entropia nie wystarcza
    srednie = []
    srednie.append("Srednie cechy w grupach")
    srednie.append("{:<16} {:>10} {:>12}".format("Grupa", "entropia", "chi-kwadrat"))
    for grupa in ("jawne", "skompresowane", "zaszyfrowane"):
        g = [w for w in wiersze if w["grupa"] == grupa]
        sh = sum(w["entropia"] for w in g) / len(g)
        sc = sum(w["chi2"] for w in g) / len(g)
        srednie.append("{:<16} {:>10.3f} {:>12.1f}".format(grupa, sh, sc))

    mA = metryki(wiersze, "decyzja_A")
    mB = metryki(wiersze, "decyzja_B")

    # Ograniczenie Base64: zaszyfrowane dane po zakodowaniu Base64
    baza64 = []
    for w in [x for x in wiersze if x["grupa"] == "zaszyfrowane"][:10]:
        sciezka = os.path.join(a.zbior, "zaszyfrowane", w["plik"])
        with open(sciezka, "rb") as f:
            kod = base64.b64encode(f.read())
        H64, _ = entropia_i_chi2(kod)
        baza64.append((w["plik"], w["entropia"], H64, H64 >= PROG_H))
    przeoczone = sum(1 for _, _, _, wykryty in baza64 if not wykryty)

    raport = []
    raport.append("\n".join(srednie))
    raport.append("")
    raport.append("Wniosek: grupy 'skompresowane' i 'zaszyfrowane' maja zblizona,")
    raport.append("wysoka entropie - rozroznia je dopiero chi-kwadrat (nizsze dla")
    raport.append("danych zaszyfrowanych) oraz obecnosc naglowka.")
    raport.append("")
    raport.append(blok_metryk("Klasyfikator A - sama entropia (H >= %.1f)" % PROG_H, mA))
    raport.append("")
    raport.append(blok_metryk("Klasyfikator B - entropia + chi-kwadrat + brak naglowka", mB))
    raport.append("")
    raport.append("Ograniczenie: dane zaszyfrowane zakodowane Base64")
    raport.append("{:<22} {:>12} {:>14} {:>10}".format("plik", "H oryg.", "H po Base64", "wykryty A"))
    for nazwa, h0, h64, wykryty in baza64:
        raport.append("{:<22} {:>12.3f} {:>14.3f} {:>10}".format(
            nazwa, h0, h64, "tak" if wykryty else "NIE"))
    raport.append(f"Base64 obniza entropie ponizej progu - klasyfikator A przeoczyl "
                  f"{przeoczone}/{len(baza64)} plikow.")

    tekst = "\n".join(raport)
    print(tekst)
    with open(os.path.join(a.out, "podsumowanie.txt"), "w", encoding="utf-8") as f:
        f.write(tekst + "\n")
    print(f"\nWyniki w {os.path.abspath(a.out)} (pliki.csv, podsumowanie.txt).")


if __name__ == "__main__":
    main()
