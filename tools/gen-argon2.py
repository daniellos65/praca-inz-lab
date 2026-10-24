#!/usr/bin/env python3
"""
gen-argon2.py - generuje hashe Argon2id do pomiaru skalowania pamieci (hashcat -m 34000).

Tworzy trzy hashe roznaice sie TYLKO zuzyciem pamieci (64 / 256 / 1024 MiB),
przy stalej liczbie iteracji (t) i rownoleglosci (p). Haslo jest znane i takie
samo dla wszystkich; dla pomiaru predkosci i tak nie jest odgadywane.

Wymaga biblioteki argon2-cffi:
    pip install argon2-cffi

Uruchomienie:
    python gen-argon2.py                 # zapis do F:\\praca-inz\\e4b
    python gen-argon2.py C:\\inna\\sciezka
"""
import sys
import os

try:
    from argon2 import PasswordHasher
    from argon2.low_level import Type
except ImportError:
    print("Brak biblioteki argon2-cffi. Zainstaluj poleceniem:")
    print("    pip install argon2-cffi")
    sys.exit(1)

OUT = sys.argv[1] if len(sys.argv) > 1 else r"F:\praca-inz\e4b"
HASLO = "Laboratorium2026!"
T = 3   # iteracje - stale
P = 1   # rownoleglosc - stala

warianty = [("m64", 65536), ("m256", 262144), ("m1024", 1048576)]  # pamiec w KiB

os.makedirs(OUT, exist_ok=True)
print(f"Generowanie hashy Argon2id (t={T}, p={P}), haslo: {HASLO}")
for label, m_kib in warianty:
    ph = PasswordHasher(time_cost=T, memory_cost=m_kib, parallelism=P, hash_len=32, salt_len=16, type=Type.ID)
    h = ph.hash(HASLO)
    sciezka = os.path.join(OUT, f"argon2-{label}.hash")
    with open(sciezka, "w", encoding="ascii", newline="\n") as f:
        f.write(h + "\n")
    print(f"  {label}: m={m_kib} KiB ({m_kib // 1024} MiB) -> {sciezka}")
    print(f"       {h}")
print("Gotowe.")
