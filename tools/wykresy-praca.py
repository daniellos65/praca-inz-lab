#!/usr/bin/env python3
"""
wykresy-praca.py - wykresy do pracy (wektorowe PDF, czcionka szeryfowa zgodna z Times)

Dane czytane wprost z plikow wynikow w repozytorium (wyniki/...), wykresy
zapisywane do praca/rysunki/. Uruchomienie z korzenia repozytorium:

    python3 tools/wykresy-praca.py            # wszystkie wykresy
    python3 tools/wykresy-praca.py r4         # tylko rozdzial 4

Wymaga: matplotlib.
"""
import csv
import os
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, PathPatch
from matplotlib.path import Path

KORZEN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WYN = os.path.join(KORZEN, "wyniki")
OUT = os.path.join(KORZEN, "praca", "rysunki")

# Paleta (zwalidowana: lightness, chroma, CVD, kontrast) - kolejność stała
SERIA_1 = "#2a78d6"   # niebieski  - wynik "pozytywny"/pierwsza seria
SERIA_2 = "#eb6834"   # pomarańczowy - druga seria
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SZER = 6.1            # szerokość kolumny tekstu (15,5 cm) w calach


def _czcionka():
    dostepne = {f.name for f in font_manager.fontManager.ttflist}
    for nazwa in ("Liberation Serif", "TeX Gyre Termes", "Times New Roman", "DejaVu Serif"):
        if nazwa in dostepne:
            return nazwa
    return "serif"


plt.rcParams.update({
    "font.family": _czcionka(),
    "font.size": 9.5,
    "pdf.fonttype": 42,
    "axes.edgecolor": AXIS,
    "axes.linewidth": 0.8,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelcolor": INK2,
    "ytick.labelcolor": INK2,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})


def pl(x, nd=1):
    """Liczba z przecinkiem dziesiętnym, bez zbędnego ,0."""
    s = f"{x:.{nd}f}".replace(".", ",")
    return s[:-2] if s.endswith(",0") else s


def per_inch(ax):
    fig = ax.figure
    fig.canvas.draw()
    bb = ax.get_window_extent().transformed(fig.dpi_scale_trans.inverted())
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    return abs(x1 - x0) / bb.width, abs(y1 - y0) / bb.height


def slupek(ax, x0, y0, w, h, kolor, poziomy=False, r_pt=3.0):
    """Słupek jako jedna ścieżka: zaokrąglony koniec danych, prosty przy osi."""
    if (w if poziomy else h) <= 0:
        return
    xpi, ypi = per_inch(ax)
    rx, ry = r_pt / 72 * xpi, r_pt / 72 * ypi
    k = 0.5523
    if not poziomy:
        rx, ry = min(rx, w / 2), min(ry, h)
        x1, yt = x0 + w, y0 + h
        verts = [(x0, y0), (x0, yt - ry),
                 (x0, yt - ry + k * ry), (x0 + rx - k * rx, yt), (x0 + rx, yt),
                 (x1 - rx, yt),
                 (x1 - rx + k * rx, yt), (x1, yt - ry + k * ry), (x1, yt - ry),
                 (x1, y0), (x0, y0)]
    else:
        rx, ry = min(rx, w), min(ry, h / 2)
        xr, y1 = x0 + w, y0 + h
        verts = [(x0, y0), (xr - rx, y0),
                 (xr - rx + k * rx, y0), (xr, y0 + ry - k * ry), (xr, y0 + ry),
                 (xr, y1 - ry),
                 (xr, y1 - ry + k * ry), (xr - rx + k * rx, y1), (xr - rx, y1),
                 (x0, y1), (x0, y0)]
    codes = [Path.MOVETO, Path.LINETO,
             Path.CURVE4, Path.CURVE4, Path.CURVE4,
             Path.LINETO,
             Path.CURVE4, Path.CURVE4, Path.CURVE4,
             Path.LINETO, Path.CLOSEPOLY]
    ax.add_patch(PathPatch(Path(verts, codes), fc=kolor, ec="none", zorder=3))


def oczysc(ax, siatka="y"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    if siatka == "y":
        ax.spines["left"].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.yaxis.grid(True, color=GRID, lw=0.75, zorder=0)
        ax.tick_params(axis="y", length=0)
        ax.tick_params(axis="x", length=0, pad=5)
    else:
        ax.spines["bottom"].set_visible(False)
        ax.spines["left"].set_color(AXIS)
        ax.xaxis.grid(True, color=GRID, lw=0.75, zorder=0)
        ax.tick_params(axis="x", length=0)
        ax.tick_params(axis="y", length=0, pad=6)
    ax.set_axisbelow(True)


def legenda(fig, uchwyty, opisy, x=0.0, y=1.0, ncol=2):
    leg = fig.legend(uchwyty, opisy, loc="upper left", bbox_to_anchor=(x, y), ncol=ncol,
                     frameon=False, handlelength=1.2, handletextpad=0.5, columnspacing=1.8)
    for t in leg.get_texts():
        t.set_color(INK2)
    return leg


def zapisz(fig, nazwa):
    sc = os.path.join(OUT, nazwa)
    fig.savefig(sc)
    plt.close(fig)
    print("  zapisano", os.path.relpath(sc, KORZEN))


def czytaj(sc):
    with open(sc, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


# =====================================================================
# Rozdział 4
# =====================================================================
def r4_odsetek():
    """Odsetek przyjętych zmodyfikowanych ciasteczek: CTR, CBC, GCM."""
    s43 = czytaj(os.path.join(WYN, "R4", "43-strumien-proby.csv"))
    s44 = czytaj(os.path.join(WYN, "R4", "44-blokowy-proby.csv"))

    def licz(rows, war):
        r = [w for w in rows if w["wariant"] == war]
        return sum(int(w["przyjete"]) for w in r), len(r)

    ctr = licz(s43, "AES-CTR bez MAC")
    cbc = licz(s44, "AES-CBC bez MAC")
    g1, g2 = licz(s43, "AES-GCM"), licz(s44, "AES-GCM")
    gcm = (g1[0] + g2[0], g1[1] + g2[1])
    dane = [("AES-128-CTR bez uwierzytelnienia", ctr),
            ("AES-128-CBC bez uwierzytelnienia", cbc),
            ("AES-128-GCM (obie serie)", gcm)]

    fig, ax = plt.subplots(figsize=(SZER, 1.55))
    fig.subplots_adjust(left=0.335, right=0.8, top=0.95, bottom=0.2)
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.6, 2.6)
    oczysc(ax, siatka="x")
    ax.set_yticks(range(3))
    ax.set_yticklabels([d[0] for d in dane])
    ax.invert_yaxis()
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels([f"{t}%" for t in [0, 25, 50, 75, 100]])
    _, ypi = per_inch(ax)
    h = min(0.55, 0.2 * ypi)
    for i, (_, (a, n)) in enumerate(dane):
        v = 100.0 * a / n
        slupek(ax, 0, i - h / 2, v, h, SERIA_1, poziomy=True)
        ax.text(v + 1.5, i, f"{pl(v)}%  ({a}/{n})", va="center", ha="left",
                color=INK, fontweight="bold", zorder=4)
    zapisz(fig, "r4-odsetek.pdf")


def r4_cbc_obszary():
    """CBC: odsetek przyjętych wg obszaru tokenu + wartość oczekiwana."""
    s44 = [w for w in czytaj(os.path.join(WYN, "R4", "44-blokowy-proby.csv"))
           if w["wariant"] == "AES-CBC bez MAC"]
    obszary = [("IV", "wektor inicjujący", 100.0),
               ("blok posredni", "blok pośredni", 13 / 16 * 100),
               ("blok ostatni", "blok ostatni (z dopełnieniem)", 100 / 256)]
    fig, ax = plt.subplots(figsize=(SZER, 1.75))
    fig.subplots_adjust(left=0.29, right=0.8, top=0.8, bottom=0.17)
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.6, 2.6)
    oczysc(ax, siatka="x")
    ax.set_yticks(range(3))
    ax.set_yticklabels([o[1] for o in obszary])
    ax.invert_yaxis()
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels([f"{t}%" for t in [0, 25, 50, 75, 100]])
    _, ypi = per_inch(ax)
    h = min(0.55, 0.19 * ypi)
    for i, (klucz, _, ocz) in enumerate(obszary):
        r = [w for w in s44 if w["obszar"] == klucz]
        a, n = sum(int(w["przyjete"]) for w in r), len(r)
        v = 100.0 * a / n
        slupek(ax, 0, i - h / 2, v, h, SERIA_1, poziomy=True)
        ax.plot([ocz, ocz], [i - h * 0.9, i + h * 0.9], color=INK, lw=1.8,
                solid_capstyle="butt", zorder=5)
        ax.text(max(v, ocz) + 2, i, f"{pl(v)}%  ({a}/{n})", va="center", ha="left",
                color=INK, fontweight="bold", zorder=6)
    legenda(fig, [Patch(fc=SERIA_1, ec="none"), Line2D([0], [0], color=INK, lw=1.8)],
            ["zmierzony odsetek przyjętych tokenów", "wartość wynikająca z budowy tokenu"],
            x=0.0, y=1.0)
    zapisz(fig, "r4-cbc-obszary.pdf")


def r4_pozycje():
    """Wynik serii losowej wg pozycji zmienionego bajtu tokenu (CTR i CBC)."""
    s43 = [w for w in czytaj(os.path.join(WYN, "R4", "43-strumien-proby.csv"))
           if w["wariant"] == "AES-CTR bez MAC"]
    s44 = [w for w in czytaj(os.path.join(WYN, "R4", "44-blokowy-proby.csv"))
           if w["wariant"] == "AES-CBC bez MAC"]

    def agreguj(rows):
        d = defaultdict(lambda: [0, 0])
        for w in rows:
            p = int(w["pozycja"])
            d[p][0] += 1
            d[p][1] += int(w["przyjete"])
        return d

    panele = [
        ("AES-128-CTR bez uwierzytelnienia", agreguj(s43), 37,
         [(0, 8, "licznik (8 B)"), (8, 37, "kryptogram (29 B)")]),
        ("AES-128-CBC bez uwierzytelnienia", agreguj(s44), 48,
         [(0, 16, "wektor inicjujący (16 B)"), (16, 32, "blok 1 (16 B)"),
          (32, 48, "blok 2 (16 B, z dopełnieniem)")]),
    ]
    ymax = max(n for _, d, _, _ in panele for n, _ in d.values())
    fig, osie = plt.subplots(2, 1, figsize=(SZER, 3.55),
                             gridspec_kw={"height_ratios": [1, 1], "hspace": 0.95})
    fig.subplots_adjust(left=0.075, right=0.985, top=0.84, bottom=0.11)
    for ax, (tytul, d, dl, obszary) in zip(osie, panele):
        ax.set_xlim(-0.8, 47.8)
        ax.set_ylim(0, ymax + 5.2)
        oczysc(ax, siatka="y")
        ax.set_yticks(range(0, ymax + 1, 4))
        ax.set_xticks(range(0, 48, 4))
        ax.set_title(tytul, loc="left", fontsize=9.5, color=INK, pad=4)
        xpi, _ = per_inch(ax)
        gap = 2 / 96 * xpi                       # 2 px odstępu między słupkami
        w = 1 - gap
        for p in range(dl):
            n, a = d.get(p, [0, 0])
            if n == 0:
                continue
            kol = SERIA_1 if a == n else SERIA_2
            if 0 < a < n:                        # pozycja mieszana: przyjęte na dole
                slupek(ax, p - w / 2, 0, w, a, SERIA_1, r_pt=0)
                slupek(ax, p - w / 2, a, w, n - a, SERIA_2, r_pt=1.5)
            else:
                slupek(ax, p - w / 2, 0, w, n, kol, r_pt=1.5)
        for x0, x1, et in obszary:
            if x0 > 0:
                ax.axvline(x0 - 0.5, color=INK2, lw=0.8, ls=(0, (3, 2)), zorder=2)
            ax.text((x0 + x1 - 1) / 2, ymax + 3.3, et, ha="center", va="center",
                    color=INK2, fontsize=8.5)
        if dl < 48:
            ax.axvspan(dl - 0.5, 47.8, color="#f3f2ee", zorder=0, lw=0)
            ax.text((dl + 47.8) / 2 - 0.3, ymax / 2, "token krótszy\n(37 B)",
                    ha="center", va="center", color=MUTED, fontsize=8)
    osie[1].set_xlabel("pozycja zmienionego bajtu w tokenie", color=INK2, labelpad=4)
    fig.text(0.012, 0.47, "liczba prób", rotation=90, va="center", color=INK2)
    legenda(fig, [Patch(fc=SERIA_1, ec="none"), Patch(fc=SERIA_2, ec="none")],
            ["token przyjęty (HTTP 200)", "token odrzucony (HTTP 400)"], x=0.06, y=1.0)
    zapisz(fig, "r4-pozycje.pdf")


# =====================================================================
# Rozdział 5
# =====================================================================
SERIA_3 = "#1baf7a"   # trzeci slot palety (zwalidowany all-pairs; etykiety zawsze widoczne)
KLASY = [("szybka funkcja skrótu", SERIA_1),
         ("funkcja compute-hard", SERIA_2),
         ("funkcja memory-hard", SERIA_3)]
KOLOR_KLASY = {n: k for n, k in KLASY}
E4 = os.path.join(WYN, "E4")


def pl_hs(v):
    """Prędkość w zapisie polskim: mld/s, mln/s, tys./s."""
    if v >= 1e9:
        return f"{pl(v / 1e9)} mld/s"
    if v >= 1e6:
        return f"{pl(v / 1e6)} mln/s"
    if v >= 1e4:
        return f"{pl(v / 1e3, 1 if v < 1e5 else 0)} tys./s"
    if v >= 10:
        return f"{v:.0f}/s".replace(".", ",")
    return f"{pl(v, 2)}/s"


def czytaj_bom(sc):
    with open(sc, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


def srednia(xs):
    xs = list(xs)
    return sum(xs) / len(xs)


def predkosc_z_postepu(sc):
    """H/s z przyrostu licznika Progress między 1. i 2. odczytem statusu Hashcata."""
    import re
    t = open(sc, encoding="utf-8-sig", errors="replace").read()
    sek = [int(m.group(1) or 0) * 60 + int(m.group(2)) for m in
           re.finditer(r"Time\.Started\.+: .*?\((?:(\d+) mins?, )?(\d+) secs?\)", t)]
    post = [int(x) for x in re.findall(r"Progress\.+: (\d+)/", t)]
    acc = re.findall(r"Speed\.#\d+\.+:.*?Accel:(\d+)", t)
    if len(post) < 2:
        return None, None
    return (post[1] - post[0]) / (sek[1] - sek[0]), int(acc[0])


def argon2_dane():
    """[(MiB, GPU H/s, CPU H/s, Accel GPU)] - 64/256 z 24.10, 1024 z powtórki 8.11."""
    wyn = []
    for mib, folder in ((64, "argon2-skalowanie"), (256, "argon2-skalowanie"),
                        (1024, "argon2-1024-powtorka")):
        d = os.path.join(E4, folder)
        pliki = sorted(f for f in os.listdir(d) if f.startswith(f"argon2-{mib}-"))
        g = [predkosc_z_postepu(os.path.join(d, f)) for f in pliki if "-gpu-" in f]
        c = [predkosc_z_postepu(os.path.join(d, f)) for f in pliki if "-cpu-" in f]
        g = [x for x in g if x[0] is not None]
        c = [x for x in c if x[0] is not None]
        wyn.append((mib, srednia(x[0] for x in g), srednia(x[0] for x in c), g[0][1]))
    return wyn


def r5_predkosci():
    """Benchmark Hashcata (-b): prędkość wg formatu, skala logarytmiczna."""
    rows = czytaj_bom(os.path.join(E4, "wyniki-surowe.csv"))
    opis = {"0": ("MD5", "szybka funkcja skrótu"),
            "1000": ("NTLM", "szybka funkcja skrótu"),
            "11600": ("7-Zip (SHA-256, 2¹⁹ iteracji)", "funkcja compute-hard"),
            "13400": ("KeePass KDBX 3.1 (AES-KDF)", "funkcja compute-hard"),
            "13721": ("VeraCrypt (PBKDF2-HMAC-SHA-512)", "funkcja compute-hard"),
            "34300": ("KeePass KDBX 4 (Argon2d, 64 MiB)", "funkcja memory-hard")}
    sr = defaultdict(list)
    for w in rows:
        sr[w["Tryb"]].append(float(w["HS"]))
    dane = sorted(((opis[t][0], opis[t][1], srednia(v)) for t, v in sr.items()),
                  key=lambda x: -x[2])
    fig, ax = plt.subplots(figsize=(SZER, 2.45))
    fig.subplots_adjust(left=0.4, right=0.97, top=0.86, bottom=0.12)
    ax.set_xscale("log")
    ax.set_xlim(1e2, 1e12)
    ax.set_ylim(len(dane) - 0.4, -0.6)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.set_yticks(range(len(dane)))
    ax.set_yticklabels([d[0] for d in dane])
    ax.tick_params(axis="y", length=0, pad=6)
    ax.tick_params(axis="x", length=0, pad=4)
    ax.minorticks_off()
    ax.set_xticks([1e2, 1e4, 1e6, 1e8, 1e10, 1e12])
    ax.set_xticklabels(["100", "10 tys.", "1 mln", "100 mln", "10 mld", "1 bln"])
    ax.xaxis.grid(True, color=GRID, lw=0.75, zorder=0)
    ax.set_axisbelow(True)
    for i, (_, kl, v) in enumerate(dane):
        ax.plot([1e2, v], [i, i], color=GRID, lw=1.2, zorder=1)
        ax.scatter([v], [i], s=46, color=KOLOR_KLASY[kl], edgecolors="white",
                   linewidths=1.4, zorder=4)
        ax.text(v * 1.9, i, pl_hs(v), va="center", ha="left", color=INK,
                fontweight="bold", zorder=5)
    legenda(fig, [Line2D([0], [0], marker="o", ls="", ms=7, mfc=k, mec="none") for _, k in KLASY],
            [n for n, _ in KLASY], x=0.0, y=1.0, ncol=3)
    zapisz(fig, "r5-predkosci.pdf")


def r5_karta():
    """Stan karty w trakcie pomiaru VeraCrypt (najdłuższe ciągłe obciążenie)."""
    from datetime import datetime
    sc = os.path.join(E4, "veracrypt", "gpu-log.csv")
    t, temp, takt = [], [], []
    with open(sc, encoding="utf-8-sig") as f:
        next(f)
        for linia in f:
            p = [x.strip() for x in linia.split(",")]
            if len(p) < 6:
                continue
            t.append(datetime.strptime(p[0], "%Y/%m/%d %H:%M:%S.%f"))
            temp.append(float(p[1]))
            takt.append(float(p[2].split()[0]))
    t0 = t[0]
    x = [(a - t0).total_seconds() / 60 for a in t]
    przebiegi = []
    for pim in (1, 250, 500):
        for n in (1, 2, 3):
            tekst = open(os.path.join(E4, "veracrypt", f"vc-pim{pim}-{n}.txt"),
                         encoding="utf-8-sig", errors="replace").read()
            import re
            st = re.search(r"Started: \w+ (\w+ \d+ [\d:]+ \d+)", tekst).group(1)
            sp = re.search(r"Stopped: \w+ (\w+ \d+ [\d:]+ \d+)", tekst).group(1)
            a = datetime.strptime(st, "%b %d %H:%M:%S %Y")
            b = datetime.strptime(sp, "%b %d %H:%M:%S %Y")
            przebiegi.append((pim, (a - t0).total_seconds() / 60, (b - t0).total_seconds() / 60))
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(SZER, 3.0), sharex=True,
                                 gridspec_kw={"hspace": 0.35})
    fig.subplots_adjust(left=0.1, right=0.98, top=0.8, bottom=0.13)
    for ax, y, tyt, lim in ((a1, temp, "temperatura GPU [°C]", (30, 75)),
                            (a2, takt, "taktowanie rdzeni (SM) [MHz]", (1400, 2100))):
        oczysc(ax, siatka="y")
        ax.set_ylim(*lim)
        for _, s0, s1 in przebiegi:
            ax.axvspan(s0, s1, color="#f1f0eb", lw=0, zorder=0)
        ax.plot(x, y, color=SERIA_1, lw=1.5, zorder=3)
        ax.set_title(tyt, loc="left", fontsize=9.5, color=INK, pad=3)
    a1.set_yticks([30, 45, 60, 75])
    a2.set_yticks([1500, 1750, 2000])
    for pim in (1, 250, 500):
        p = [pr for pr in przebiegi if pr[0] == pim]
        a1.text((p[0][1] + p[-1][2]) / 2, 90, f"PIM {pim} (3 próby)", ha="center",
                va="bottom", color=INK2, fontsize=8.5, clip_on=False)
    a2.set_xlabel("czas od rozpoczęcia pomiaru [min]", color=INK2, labelpad=3)
    zapisz(fig, "r5-karta.pdf")


def r5_pim():
    """VeraCrypt: prędkość a liczba iteracji PBKDF2 (skala log-log)."""
    rows = czytaj_bom(os.path.join(E4, "veracrypt", "wyniki-surowe.csv"))
    sr = defaultdict(list)
    it = {}
    for w in rows:
        sr[w["PIM"]].append(float(w["HS"]))
        it[w["PIM"]] = int(w["Iteracje"])
    dane = sorted(((int(p), it[p], srednia(v)) for p, v in sr.items()))
    C = srednia(i * v for _, i, v in dane)
    fig, ax = plt.subplots(figsize=(SZER, 2.5))
    fig.subplots_adjust(left=0.12, right=0.97, top=0.86, bottom=0.17)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(1e4, 1e6)
    ax.set_ylim(3e2, 5e4)
    oczysc(ax, siatka="y")
    ax.xaxis.grid(True, color=GRID, lw=0.75, zorder=0)
    ax.minorticks_off()
    ax.set_xticks([1e4, 3e4, 1e5, 3e5, 1e6])
    ax.set_xticklabels(["10 tys.", "30 tys.", "100 tys.", "300 tys.", "1 mln"])
    ax.set_yticks([1e3, 1e4])
    ax.set_yticklabels(["1 tys.", "10 tys."])
    xs = [1e4, 1e6]
    ax.plot(xs, [C / v for v in xs], color=INK2, lw=1.0, ls=(0, (4, 3)), zorder=2)
    ax.scatter([d[1] for d in dane], [d[2] for d in dane], s=50, color=SERIA_1,
               edgecolors="white", linewidths=1.4, zorder=4)
    for pim, i, v in dane:
        et = f"PIM {pim}: {v:,.0f} H/s".replace(",", "\u2009")
        if pim == 1:
            ax.text(i * 1.13, v * 1.12, et, ha="left", va="bottom", color=INK, fontweight="bold")
        else:
            ax.text(i / 1.1, v / 1.18, et, ha="right", va="top", color=INK, fontweight="bold")
    ax.set_xlabel("liczba iteracji PBKDF2-HMAC-SHA-512", color=INK2, labelpad=3)
    ax.set_ylabel("prędkość [H/s]", color=INK2)
    legenda(fig, [Line2D([0], [0], marker="o", ls="", ms=7, mfc=SERIA_1, mec="none"),
                  Line2D([0], [0], color=INK2, lw=1.0, ls=(0, (4, 3)))],
            ["pomiar (średnia z 3 prób)",
             f"prędkość × iteracje = {pl(C / 1e6, 0)} mln (stała)"], x=0.06, y=1.0)
    zapisz(fig, "r5-pim.pdf")


def r5_argon2():
    """Argon2id: prędkość GPU i CPU oraz ich stosunek w funkcji pamięci."""
    dane = argon2_dane()
    kat = ["64 MiB", "256 MiB", "1 GiB"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(SZER, 2.45),
                                 gridspec_kw={"width_ratios": [1.25, 1], "wspace": 0.38})
    fig.subplots_adjust(left=0.1, right=0.98, top=0.8, bottom=0.12)
    # panel 1: prędkości (log)
    a1.set_yscale("log")
    a1.set_ylim(0.3, 1000)
    a1.set_xlim(-0.4, 2.6)
    oczysc(a1, siatka="y")
    a1.minorticks_off()
    a1.set_yticks([1, 10, 100, 1000])
    a1.set_yticklabels(["1", "10", "100", "1000"])
    a1.set_xticks(range(3))
    a1.set_xticklabels(kat)
    a1.set_title("prędkość [H/s]", loc="left", fontsize=9.5, color=INK, pad=4)
    for j, (kol, nazwa) in enumerate(((SERIA_1, "GPU"), (SERIA_2, "CPU"))):
        ys = [d[1 + j] for d in dane]
        a1.plot(range(3), ys, color=kol, lw=1.5, zorder=3)
        a1.scatter(range(3), ys, s=40, color=kol, edgecolors="white", linewidths=1.4, zorder=4)
        for i, v in enumerate(ys):
            nd = 0 if v >= 100 else (1 if v >= 10 else 2)
            if j == 0:
                a1.text(i + 0.08, v * 1.45, pl(v, nd), ha="left", va="bottom",
                        color=INK, fontsize=8.5, fontweight="bold")
            else:
                a1.text(i - 0.08, v / 1.45, pl(v, nd), ha="right", va="top",
                        color=INK, fontsize=8.5, fontweight="bold")
    # panel 2: stosunek GPU/CPU
    a2.set_xlim(-0.6, 2.6)
    a2.set_ylim(0, 10)
    oczysc(a2, siatka="y")
    a2.set_xticks(range(3))
    a2.set_xticklabels(kat)
    a2.set_yticks([0, 2, 4, 6, 8, 10])
    a2.set_yticklabels([f"{t}×" for t in [0, 2, 4, 6, 8, 10]])
    a2.set_title("przewaga GPU nad CPU", loc="left", fontsize=9.5, color=INK, pad=4)
    xpi, _ = per_inch(a2)
    w = min(0.55, 0.32 * xpi)
    for i, d in enumerate(dane):
        r = d[1] / d[2]
        slupek(a2, i - w / 2, 0, w, r, SERIA_3)
        a2.text(i, r + 0.25, f"{pl(r)}×", ha="center", va="bottom", color=INK, fontweight="bold")
    legenda(fig, [Line2D([0], [0], color=SERIA_1, lw=1.5, marker="o", ms=6, mec="white"),
                  Line2D([0], [0], color=SERIA_2, lw=1.5, marker="o", ms=6, mec="white")],
            ["GPU (GTX 1660)", "CPU (Ryzen 5 5600)"], x=0.08, y=1.0)
    zapisz(fig, "r5-argon2.pdf")


def r5_gpu_cpu():
    """Przewaga GPU nad CPU dla wszystkich badanych funkcji."""
    rows = czytaj_bom(os.path.join(E4, "gpu-cpu", "wyniki-surowe.csv"))
    opis = {"0": ("MD5", "szybka funkcja skrótu"),
            "11600": ("7-Zip (SHA-256)", "funkcja compute-hard"),
            "13400": ("KeePass AES-KDF", "funkcja compute-hard"),
            "13721": ("VeraCrypt (PBKDF2-SHA-512)", "funkcja compute-hard"),
            "34300": ("KeePass Argon2d, 64 MiB (próbka)", "funkcja memory-hard")}
    sr = defaultdict(lambda: defaultdict(list))
    for w in rows:
        sr[w["Tryb"]][w["Urzadzenie"]].append(float(w["HS"]))
    dane = [(opis[t][0], opis[t][1], srednia(v["gpu"]) / srednia(v["cpu"])) for t, v in sr.items()]
    for mib, g, c, _ in argon2_dane():
        et = "1 GiB" if mib == 1024 else f"{mib} MiB"
        dane.append((f"Argon2id, {et}", "funkcja memory-hard", g / c))
    dane.sort(key=lambda d: -d[2])
    fig, ax = plt.subplots(figsize=(SZER, 2.85))
    fig.subplots_adjust(left=0.36, right=0.93, top=0.88, bottom=0.1)
    ax.set_xlim(0, 45)
    ax.set_ylim(len(dane) - 0.4, -0.6)
    oczysc(ax, siatka="x")
    ax.set_yticks(range(len(dane)))
    ax.set_yticklabels([d[0] for d in dane])
    ax.set_xticks([0, 10, 20, 30, 40])
    ax.set_xticklabels([f"{t}×" for t in [0, 10, 20, 30, 40]])
    _, ypi = per_inch(ax)
    h = min(0.6, 0.15 * ypi)
    for i, (_, kl, r) in enumerate(dane):
        slupek(ax, 0, i - h / 2, r, h, KOLOR_KLASY[kl], poziomy=True)
        ax.text(r + 0.6, i, f"{pl(r)}×", va="center", ha="left", color=INK, fontweight="bold")
    legenda(fig, [Patch(fc=k, ec="none") for _, k in KLASY], [n for n, _ in KLASY],
            x=0.0, y=1.0, ncol=3)
    zapisz(fig, "r5-gpu-cpu.pdf")


ROZDZIALY = {"r4": [r4_odsetek, r4_cbc_obszary, r4_pozycje],
             "r5": [r5_predkosci, r5_karta, r5_pim, r5_argon2, r5_gpu_cpu]}

if __name__ == "__main__":
    wybor = sys.argv[1:] or list(ROZDZIALY)
    os.makedirs(OUT, exist_ok=True)
    print("czcionka:", plt.rcParams["font.family"])
    for r in wybor:
        for f in ROZDZIALY[r]:
            f()
