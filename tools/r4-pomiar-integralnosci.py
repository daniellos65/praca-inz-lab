#!/usr/bin/env python3
"""
r4-pomiar-integralnosci.py - rozdzial 4: pomiar odpornosci komunikatu na modyfikacje

Trzy czesci odpowiadaja podrozdzialom pracy:

  4.3  ciasteczko, szyfr strumieniowy
         /ctr/profile      AES-128-CTR bez MAC     (wariant podatny)
         /secure/profile   AES-128-GCM             (wariant poprawiony)

  4.4  ciasteczko, szyfr blokowy
         /profile          AES-128-CBC bez MAC     (wariant podatny)
         /secure/profile   AES-128-GCM             (wariant poprawiony)

  4.5  podpis zlecenia API
         /api/transfer          SHA-256(sekret||msg)   (wariant podatny)
         /api/secure/transfer   HMAC-SHA-256           (wariant poprawiony)

Metryka glowna (4.3 i 4.4): odsetek zmodyfikowanych komunikatow przyjetych
przez serwer (HTTP 200). Dla wariantu z AEAD oczekiwana wartosc wynosi 0%.

Czesc 4.3 i 4.4 wykonuje dwa rodzaje prob:
  - seria losowa: zmiana jednego losowego bajtu tokenu, zliczenie przyjec;
  - proba celowana: zmiana bajtu pola 'admin' z 0 na 1 przy zalozeniu znajomosci
    struktury tekstu jawnego (typowe zalozenie o atakujacym). Pokazuje roznice
    miedzy plastycznoscia (CTR - zmiana wprost), zaleznoscia od polozenia (CBC)
    a wykryciem modyfikacji (GCM).

Uruchomienie (na maszynie client, aplikacja na server):
    python3 r4-pomiar-integralnosci.py --host 10.10.10.30

Opcje:
    --host 10.10.10.30        adres serwera aplikacji
    --port 5000               port aplikacji
    --proby 200               liczba prob serii losowej na wariant
    --out  ~/wyniki/R4        folder na wyniki
    --ziarno 20261025         ziarno generatora, dla powtarzalnosci pomiaru

Wyniki:
    43-strumien-proby.csv   seria losowa 4.3 (CTR, GCM)
    44-blokowy-proby.csv    seria losowa 4.4 (CBC, GCM)
    celowane-proby.csv      proby celowane (admin 0->1) dla CTR, CBC, GCM
    45-podpis-proby.csv     weryfikacja podpisu 4.5
    podsumowanie.txt        tabele zbiorcze do pracy
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

# Zalozona przez atakujacego struktura tekstu jawnego sesji (por. app.py:
# session_plaintext). Atakujacy nie zna klucza, ale zna format ciasteczka.
SZABLON_SESJI = "user={user};admin=0;uid=1001"


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


def pobierz_ciasteczko(baza, sciezka_login, nazwa, user="student"):
    """Loguje sie i zwraca wartosc ciasteczka o podanej nazwie."""
    kod, tresc, naglowki = http_get(f"{baza}{sciezka_login}?user={user}")
    if kod != 200:
        print(f"[!] Logowanie {sciezka_login} zwrocilo {kod}: {tresc}", file=sys.stderr)
        sys.exit(1)
    for naglowek in naglowki.get_all("Set-Cookie") or []:
        if naglowek.startswith(nazwa + "="):
            return naglowek.split(";", 1)[0].split("=", 1)[1]
    print(f"[!] Serwer nie ustawil ciasteczka '{nazwa}'.", file=sys.stderr)
    sys.exit(1)


# Definicje wariantow ciasteczka: (sciezka_login, sciezka_profilu, nazwa_ciasteczka,
# opis, dlugosc_prefiksu_przed_kryptogramem).
#   CTR: nonce 8 B + kryptogram
#   CBC: IV 16 B + kryptogram
#   GCM: nonce 12 B + kryptogram + tag 16 B
WARIANTY = {
    "ctr": ("/ctr/login", "/ctr/profile", "ctr_session", "AES-CTR bez MAC", 8, 0),
    "cbc": ("/login", "/profile", "session", "AES-CBC bez MAC", 16, 0),
    "gcm": ("/secure/login", "/secure/profile", "secure_session", "AES-GCM", 12, 16),
}


# ---------------------------------------------------------------------------
# Seria losowa (4.3, 4.4)
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


def seria_losowa(baza, wariant, proby, rng):
    """Serie prob z losowa zmiana jednego bajtu tokenu. Zwraca liste wierszy."""
    login, profil, nazwa_c, opis, _pref, _tag = WARIANTY[wariant]
    token = pobierz_ciasteczko(baza, login, nazwa_c)
    surowe = base64.urlsafe_b64decode(token)
    dlugosc = len(surowe)

    kod, tresc, _ = http_get(f"{baza}{profil}", f"{nazwa_c}={token}")
    if kod != 200:
        print(f"[!] Token nienaruszony odrzucony ({kod}) na {profil}: {tresc}", file=sys.stderr)
        sys.exit(1)
    pola_wzorcowe = tresc.get("fields", {}) if isinstance(tresc, dict) else {}
    print(f"    odniesienie {opis}: HTTP 200, pola {pola_wzorcowe}")

    wiersze = []
    for nr in range(1, proby + 1):
        pozycja = rng.randrange(dlugosc)
        zmieniony = base64.urlsafe_b64encode(zmien_bajt(surowe, pozycja, rng)).decode()
        kod, tresc, _ = http_get(f"{baza}{profil}", f"{nazwa_c}={zmieniony}")
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
        })
        if nr % 50 == 0:
            print(f"    {opis}: {nr}/{proby}")
    return wiersze


# ---------------------------------------------------------------------------
# Proba celowana: zmiana pola admin z 0 na 1 (4.3, 4.4)
# ---------------------------------------------------------------------------

def proba_celowana(baza, wariant, user="student"):
    """
    Przy zalozeniu znajomosci struktury tekstu jawnego zmienia bajt pola 'admin'.
    Dla szyfrow bez kontroli integralnosci (CTR, CBC) modyfikacja kryptogramu
    przeklada sie na tekst jawny; dla GCM modyfikacja zostaje wykryta.
    Zwraca jeden wiersz wyniku.
    """
    login, profil, nazwa_c, opis, pref, _tag = WARIANTY[wariant]
    token = pobierz_ciasteczko(baza, login, nazwa_c, user=user)
    surowe = bytearray(base64.urlsafe_b64decode(token))

    jawny = SZABLON_SESJI.format(user=user).encode()
    idx = jawny.index(b"admin=") + len(b"admin=")   # pozycja cyfry pola admin w tekscie jawnym

    # Dla CTR i GCM kryptogram jest rownolegly do tekstu jawnego (bez dopelnienia),
    # wiec bajt kryptogramu pod pozycja 'pref + idx' odpowiada cyfrze admin.
    # Dla CBC zmiana bajtu w bloku poprzednim (tu: IV, bo admin lezy w 1. bloku)
    # zmienia odpowiadajacy bajt tekstu jawnego - pozycja 'idx' liczona od IV.
    if wariant == "cbc":
        cel = idx            # bajt IV sterujacy pierwszym blokiem tekstu jawnego
    else:
        cel = pref + idx     # bajt kryptogramu odpowiadajacy cyfrze admin

    surowe[cel] ^= (ord("0") ^ ord("1"))             # 0 -> 1 na poziomie tekstu jawnego
    zmieniony = base64.urlsafe_b64encode(bytes(surowe)).decode()
    kod, tresc, _ = http_get(f"{baza}{profil}", f"{nazwa_c}={zmieniony}")

    pola = tresc.get("fields", {}) if isinstance(tresc, dict) else {}
    admin = isinstance(tresc, dict) and tresc.get("admin_panel") is True
    print(f"    {opis:18} | admin_panel po modyfikacji: {admin} (HTTP {kod})")
    return {
        "wariant": opis,
        "pozycja_bajtu": cel,
        "kod_http": kod,
        "admin_uzyskany": int(admin),
        "pola": json.dumps(pola, ensure_ascii=False),
    }


# ---------------------------------------------------------------------------
# Weryfikacja podpisu (4.5)
# ---------------------------------------------------------------------------

def pomiar_podpis(baza, wariant, rng):
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


def tabela_serii(wiersze, warianty):
    linie = ["{:<22} {:>8} {:>10} {:>12} {:>18}".format(
        "Wariant", "Proby", "Przyjete", "Odsetek [%]", "Zmieniona tresc")]
    for opis in warianty:
        grupa = [w for w in wiersze if w["wariant"] == opis]
        if not grupa:
            continue
        przyjete = sum(w["przyjete"] for w in grupa)
        zmienione = sum(w["tresc_zmieniona"] for w in grupa)
        linie.append("{:<22} {:>8} {:>10} {:>12.1f} {:>18}".format(
            opis, len(grupa), przyjete, 100.0 * przyjete / len(grupa), zmienione))
    return linie


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

    kod, _, _ = http_get(baza + "/")
    if kod != 200:
        print(f"[!] Aplikacja pod {baza} nie odpowiada poprawnie (HTTP {kod}).", file=sys.stderr)
        sys.exit(1)
    print(f"==> Aplikacja {baza} odpowiada. Ziarno generatora: {a.ziarno}\n")

    print(f"==> 4.3: ciasteczko, szyfr strumieniowy - seria losowa ({a.proby} prob na wariant)")
    s43 = seria_losowa(baza, "ctr", a.proby, rng) + seria_losowa(baza, "gcm", a.proby, rng)
    zapisz_csv(os.path.join(a.out, "43-strumien-proby.csv"), s43)

    print(f"\n==> 4.4: ciasteczko, szyfr blokowy - seria losowa ({a.proby} prob na wariant)")
    s44 = seria_losowa(baza, "cbc", a.proby, rng) + seria_losowa(baza, "gcm", a.proby, rng)
    zapisz_csv(os.path.join(a.out, "44-blokowy-proby.csv"), s44)

    print("\n==> Proba celowana: zmiana pola admin z 0 na 1")
    celowane = [proba_celowana(baza, w) for w in ("ctr", "cbc", "gcm")]
    zapisz_csv(os.path.join(a.out, "celowane-proby.csv"), celowane)

    print("\n==> 4.5: weryfikacja podpisu zlecenia")
    p45 = pomiar_podpis(baza, "naive", rng) + pomiar_podpis(baza, "hmac", rng)
    zapisz_csv(os.path.join(a.out, "45-podpis-proby.csv"), p45)

    # --- tabele zbiorcze ---
    L = []
    L.append("4.3. Ciasteczko, szyfr strumieniowy - odsetek przyjetych modyfikacji")
    L.append("")
    L += tabela_serii(s43, ["AES-CTR bez MAC", "AES-GCM"])

    L.append("")
    L.append("4.4. Ciasteczko, szyfr blokowy - odsetek przyjetych modyfikacji")
    L.append("")
    L += tabela_serii(s44, ["AES-CBC bez MAC", "AES-GCM"])

    L.append("")
    L.append("4.4a. Wariant AES-CBC bez MAC w podziale na obszar modyfikacji")
    L.append("")
    L.append("{:<18} {:>8} {:>10} {:>12}".format("Obszar tokenu", "Proby", "Przyjete", "Odsetek [%]"))
    for obszar in ["IV", "blok posredni", "blok ostatni"]:
        grupa = [w for w in s44 if w["wariant"] == "AES-CBC bez MAC" and w["obszar"] == obszar]
        if not grupa:
            continue
        przyjete = sum(w["przyjete"] for w in grupa)
        L.append("{:<18} {:>8} {:>10} {:>12.1f}".format(
            obszar, len(grupa), przyjete, 100.0 * przyjete / len(grupa)))

    L.append("")
    L.append("Proba celowana: zmiana pola admin z 0 na 1 przy znanej strukturze tekstu jawnego")
    L.append("")
    L.append("{:<22} {:>14} {:>10} {:>16}".format("Wariant", "Pozycja bajtu", "HTTP", "admin uzyskany"))
    for w in celowane:
        L.append("{:<22} {:>14} {:>10} {:>16}".format(
            w["wariant"], w["pozycja_bajtu"], w["kod_http"], "tak" if w["admin_uzyskany"] else "nie"))

    L.append("")
    L.append("4.5. Reakcja na naruszenie pary (wiadomosc, podpis)")
    L.append("")
    L.append("{:<22} {:<38} {:>10} {:>10}".format("Wariant", "Przypadek", "HTTP", "Przyjete"))
    for w in p45:
        L.append("{:<22} {:<38} {:>10} {:>10}".format(
            w["wariant"], w["przypadek"], w["kod_http"], "tak" if w["przyjete"] else "nie"))

    raport = "\n".join(L)
    print("\n" + raport)
    with open(os.path.join(a.out, "podsumowanie.txt"), "w", encoding="utf-8") as f:
        f.write(raport + "\n")
    print(f"\nGotowe. Wyniki w {a.out} - wgraj folder do repozytorium jako wyniki/R4.")


if __name__ == "__main__":
    main()
