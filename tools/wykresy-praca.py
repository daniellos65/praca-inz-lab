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


ROZDZIALY = {"r4": [r4_odsetek, r4_cbc_obszary, r4_pozycje]}

if __name__ == "__main__":
    wybor = sys.argv[1:] or list(ROZDZIALY)
    os.makedirs(OUT, exist_ok=True)
    print("czcionka:", plt.rcParams["font.family"])
    for r in wybor:
        for f in ROZDZIALY[r]:
            f()
