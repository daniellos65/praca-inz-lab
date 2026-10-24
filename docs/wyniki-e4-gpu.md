# E4 – kryptoanaliza offline na GPU: wyniki

Platforma: NVIDIA GeForce GTX 1660, sterownik 610.88 (CUDA 13.3), Hashcat 7.1.2, AMD Ryzen 5 5600, Windows 11 Pro. Maszyny wirtualne wyłączone w trakcie pomiarów.

## Pomiar 1 – wbudowany test wydajności (`hashcat -b`), 22.10.2026

Każdy tryb zmierzono 3 razy; wartość to średnia. Surowe dane w repozytorium: `wyniki/E4/` (pliki `bench-m<tryb>-<próba>.txt`, `wyniki-surowe.csv`, `podsumowanie.txt`). Rozrzut między próbami poniżej 1% (Argon2: ok. 1%).

| Tryb | Algorytm | Średnia [H/s] | Wolniej niż MD5 |
|---|---|---:|---:|
| 0 | MD5 | 20 070 400 000 | 1,00× |
| 1000 | NTLM | 34 954 233 333 | 0,57× |
| 11600 | 7-Zip (AES-256, SHA-256) | 309 633 | 64 820× |
| 13400 | KeePass KDBX 3.1 (AES-KDF) | 19 638 | 1 022 001× |
| 13721 | VeraCrypt (PBKDF2-HMAC-SHA512, AES) | 782 | 25 654 538× |
| 34300 | KeePass KDBX4 (Argon2) | 460 | 43 599 710× |

### Interpretacja i ograniczenie pomiaru

- Szybkie funkcje skrótu (MD5, NTLM) osiągają dziesiątki miliardów prób na sekundę – są nieodpowiednie do ochrony haseł.
- Funkcje derywacji klucza zmniejszają szybkość o 5–8 rzędów wielkości.
- Przykładowy skrót KDBX4 użyty przez Hashcat (`wyniki/E4/tryb-34300.txt`) wykorzystuje Argon2d z pamięcią 67 108 864 B (64 MiB).
- **Ograniczenie:** tryb `-b` używa przykładowych skrótów wbudowanych w Hashcat, z parametrami kosztu (liczba iteracji, pamięć Argon2) dobranymi przez autorów narzędzia, a nie domyślnymi ustawieniami aplikacji. Wartości z różnych algorytmów nie są więc wprost porównywalne – np. wynik Argon2 (460 H/s) zależy od tego, ile pamięci wymaga przykładowy skrót. Rzetelne porównanie wymaga pomiarów na własnych plikach z kontrolowanymi parametrami (pomiar 2) oraz porównania GPU z CPU dla tych samych parametrów (pomiar 3).

### Powtórka z logiem karty, 23.10.2026

Pomiar powtórzono skryptem `tools/pomiar-bench.ps1`, który rejestruje stan karty co ok. 2 s. Dane: `wyniki/E4/pomiar1-powtorka/` (log: `gpu-log.csv`, czasy prób: `przebiegi.csv`).

| Tryb | Algorytm | Pomiar 22.10 [H/s] | Powtórka 23.10 [H/s] | Różnica |
|---|---|---:|---:|---:|
| 0 | MD5 | 20 070 400 000 | 20 083 866 667 | +0,07% |
| 1000 | NTLM | 34 954 233 333 | 35 033 600 000 | +0,23% |
| 11600 | 7-Zip | 309 633 | 309 533 | −0,03% |
| 13400 | KeePass KDBX 3.1 (AES-KDF) | 19 638 | 19 830 | +0,98% |
| 13721 | VeraCrypt | 782 | 782 | 0,00% |
| 34300 | KeePass KDBX4 (Argon2) | 460 | 460 | 0,00% |

Stan karty pod obciążeniem (≥ 90%): temperatura średnio 53 °C, maks. 58 °C; taktowanie SM 1950–1965 MHz (stabilne); pobór mocy średnio 84,6 W, maks. 119 W. Temperatura pozostawała znacznie poniżej progu ograniczania taktowania, a taktowanie nie spadało w trakcie pomiaru – wyniki nie są obciążone wpływem termicznym. Różnice między dniami nie przekraczają 1%, co potwierdza powtarzalność pomiaru.

## Pomiar 2 – własne pliki z kontrolowanymi parametrami

### VeraCrypt: wpływ liczby iteracji (PIM), 24.10.2026

Trzy kontenery AES + SHA-512 różniące się tylko parametrem PIM, który steruje liczbą iteracji PBKDF2 (iteracje = 15000 + PIM × 1000). Hashcat (tryb 13721) czyta kontener bezpośrednio, z ustaloną wartością PIM. Skrypt: `tools/pomiar-veracrypt.ps1`; dane: `wyniki/E4/veracrypt/` (hasło kontenerów: 30-znakowe, wymóg VeraCrypt dla własnego PIM).

| PIM | Iteracje | Średnia [H/s] | Odch. | Prędkość × iteracje |
|---|---:|---:|---:|---:|
| 1 | 16 000 | 20 590,7 | 0,6% | ≈ 329,4 mln |
| 250 | 265 000 | 1 278,3 | 0,0% | ≈ 338,7 mln |
| 500 | 515 000 | 659,0 | 0,0% | ≈ 339,4 mln |

**Interpretacja.** Prędkość łamania jest odwrotnie proporcjonalna do liczby iteracji: iloczyn prędkości i liczby iteracji jest niemal stały (~330–339 mln), a przy 32-krotnym wzroście liczby iteracji (16 k → 515 k) prędkość spada ~31-krotnie (20 591 → 659 H/s). Potwierdza to, że parametr kosztu funkcji compute-hard przekłada się liniowo na nakład pracy atakującego. Nieco niższy iloczyn dla PIM 1 wynika ze stałego narzutu na kandydata (uruchomienie jądra, odczyt kontenera), który przy małej liczbie iteracji waży proporcjonalnie więcej.

Stan karty pod obciążeniem (≥ 90%, 206 z 250 próbek): temperatura średnio 60,2 °C, maks. 66 °C; taktowanie SM 1920–1980 MHz (stabilne); pobór mocy średnio 90,6 W, maks. 105 W. Brak ograniczania termicznego.

### KeePass z Argon2 – ograniczenie narzędzia

Dla własnych baz KDBX4 z Argon2 (64/256/1024 MiB) nie udało się wyciągnąć skrótu: `keepass2john` (John 1.8.0-jumbo) zgłasza „file version 40000 is currently not supported”, bo parser zna tylko starszy format KDBX 3.1. Udało się wyciągnąć jedynie bazę KDBX 3.1 z AES-KDF (tryb 13400). Skalowanie pamięci Argon2 wymaga nowszego ekstraktora (bleeding-jumbo lub narzędzie oparte na pykeepass) i pozostaje do wykonania; teza memory-hard jest już poparta pomiarem `-b` (Argon2 460 H/s wobec AES-KDF 19 638 H/s przy KeePass).

## Pomiar 3 – porównanie GPU i CPU (do wykonania)

Te same pliki i parametry na procesorze Ryzen 5 5600. Kluczowa metryka rozdziału 5: stosunek wydajności GPU do CPU dla każdego algorytmu.
