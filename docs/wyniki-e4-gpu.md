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

### Własne pliki compute-hard: 7-Zip i KeePass AES-KDF, 24.10.2026

Pomiar na własnych plikach z realnymi parametrami. Skrypt: `tools/pomiar-hash.ps1`; dane: `wyniki/E4/pozostale/`. Hash 7-Zip wyciągnięto narzędziem `7z2hashcat`, hash KeePass KDBX 3.1 — `keepass2john`.

| Plik | Parametr kosztu | Tryb | Prędkość GPU [H/s] | Odch. | Benchmark `-b` [H/s] |
|---|---|---:|---:|---:|---:|
| 7-Zip AES-256 | 2^19 iteracji SHA-256 + weryfikacja danych | 11600 | 6 735 | 5,8% | 309 633 |
| KeePass AES-KDF (KDBX 3.1) | 100 000 rund AES | 13400 | 4 734 | 0,5% | 19 638 |

**Interpretacja.** Oba pliki łamią się wyraźnie wolniej niż w benchmarku `-b`, bo mają realne, wyższe parametry kosztu niż uproszczone próbki wbudowane w Hashcata. Dla KeePass stosunek 19 638 / 4 734 ≈ 4,1× odpowiada większej liczbie rund w pliku testowym (100 000) niż w próbce benchmarku. Dla 7-Zip różnica jest większa, bo przy realnym archiwum Hashcat musi dla każdego kandydata odszyfrować i zweryfikować rzeczywiste dane (CRC), a nie tylko sprawdzić dopełnienie próbki; stąd też wyższe odchylenie (5,8%), zależne od zawartości archiwum. Wniosek: benchmark `-b` zawyża prędkość atakującego względem realnych plików z poprawnie dobranym kosztem.

Stan karty pod obciążeniem: 7-Zip temp. średnio 56,1 °C (maks. 62), KeePass średnio 50,2 °C (maks. 53). Brak ograniczania termicznego.

### KeePass z Argon2 – ograniczenie narzędzia

Dla własnych baz KDBX4 z Argon2 (64/256/1024 MiB) nie udało się wyciągnąć skrótu: `keepass2john` (John 1.8.0-jumbo) zgłasza „file version 40000 is currently not supported”, bo parser zna tylko starszy format KDBX 3.1. Udało się wyciągnąć jedynie bazę KDBX 3.1 z AES-KDF (tryb 13400). Skalowanie pamięci Argon2 zrealizowano ostatecznie bez KeePass — w generycznym trybie Argon2 Hashcata (34000) na hashach wygenerowanych wprost dla zadanej pamięci (pomiar 4).

## Pomiar 3 – porównanie GPU i CPU, 24.10.2026

Benchmark Hashcata (`-b`) uruchomiony osobno na GPU (CUDA) i na CPU (Intel CPU Runtime for OpenCL, `--backend-ignore-cuda -D 1`). Skrypt: `tools/pomiar-gpu-cpu.ps1`; dane: `wyniki/E4/gpu-cpu/`. Każdy pomiar 2 razy, wyniki zgodne.

| Algorytm | GPU [H/s] | CPU [H/s] | GPU/CPU |
|---|---:|---:|---:|
| MD5 | 20 016 200 000 | 1 218 600 000 | 16,4× |
| 7-Zip (SHA-256) | 310 100 | 7 478 | 41,5× |
| KeePass AES-KDF | 19 794 | 2 666 | 7,4× |
| VeraCrypt (PBKDF2-HMAC-SHA-512) | 786 | 70 | 11,2× |
| KeePass Argon2 (64 MiB) | 461 | 36 | 12,8× |

**Interpretacja.** Przewaga GPU nad CPU nie zależy wprost od podziału compute-hard / memory-hard, lecz od tego, jak algorytm mapuje się na sprzęt:

- **AES-KDF ma najniższy stosunek (7,4×)**, ponieważ procesor Ryzen 5 5600 ma sprzętowe wsparcie AES (AES-NI). Procesor liczy operacje AES bardzo wydajnie, więc przewaga GPU maleje.
- **7-Zip ma najwyższy (41,5×)** — używa SHA-256 (operacje 32-bitowe), w których procesory graficzne są szczególnie wydajne.
- **VeraCrypt (11,2×)** opiera się na PBKDF2-HMAC-SHA-512; operacje 64-bitowe są mniej korzystne dla konsumenckiego GPU, więc procesor relatywnie nadrabia.
- **Argon2 przy 64 MiB daje wciąż 12,8× na korzyść GPU.** Przy tej ilości pamięci karta z 6 GB VRAM mieści wiele równoległych instancji, więc własność memory-hard nie ogranicza jeszcze istotnie zrównoleglenia. Spadek przewagi GPU dla Argon2 ujawnia się dopiero przy większym zużyciu pamięci (pomiar 4).

**Wniosek cząstkowy.** Sama klasyfikacja „memory-hard” nie gwarantuje najmniejszej przewagi GPU przy niskich parametrach pamięci. Najskuteczniej przewagę GPU ogranicza tu funkcja oparta na operacjach sprzętowo przyspieszanych w CPU (AES-KDF) oraz — co pokazuje pomiar 4 — Argon2 przy odpowiednio dużej pamięci.

## Pomiar 4 – skalowanie pamięci Argon2, 24.10.2026

Hashe Argon2id wygenerowano w Pythonie (`tools/gen-argon2.py`, argon2-cffi), różniące się tylko pamięcią (64 / 256 / 1024 MiB) przy stałych t=3 i p=1. Pomiar w trybie generycznym Hashcata (34000), GPU i CPU. Skrypt: `tools/pomiar-argon2.ps1`; dane: `wyniki/E4/argon2-skalowanie/`.

| Pamięć Argon2 | GPU [H/s] | CPU [H/s] | GPU/CPU |
|---|---:|---:|---:|
| 64 MiB | 286,5 | 34,0 | 8,4× |
| 256 MiB | 29,0 | 7,5 | 3,9× |
| 1024 MiB | — (błąd alokacji) | 1,0 | GPU nie uruchomił |

**Interpretacja — to właściwy dowód tezy.** Wraz ze wzrostem wymaganej pamięci przewaga GPU nad CPU gwałtownie maleje: z 8,4× przy 64 MiB do 3,9× przy 256 MiB. Przy 1024 MiB karta GTX 1660 **w ogóle nie wykonała obliczeń** — Hashcat zakończył się błędem `clCreateBuffer(): CL_INVALID_BUFFER_SIZE`, ponieważ pojedynczy bufor Argon2 o rozmiarze 1 GiB przekracza pamięć dostępną dla Hashcata na tej karcie (6 GB fizycznie, ok. 1,5 GB alokowalne). Procesor, dysponując 16 GB RAM, policzył wszystkie warianty, choć bardzo wolno (1 H/s przy 1 GiB).

Mechanizm jest następujący: efektywność GPU bierze się z masowej równoległości (tysiące jednoczesnych instancji). Funkcja memory-hard wymaga, by każda instancja miała do dyspozycji duży, osobny blok pamięci. Pamięć karty szybko się wyczerpuje, liczba równoległych instancji spada, a przy odpowiednio dużym parametrze pamięci akceleracja na GPU staje się niemożliwa. To jest istota ochrony, jaką memory-hard daje przeciwko atakom z użyciem GPU.

(Wartości bezwzględne przy 64 MiB różnią się od pomiaru `-b` trybu 34300, bo tu użyto t=3, a przykład benchmarku t=2 — porównywalny jest trend stosunku GPU/CPU, nie liczby bezwzględne.)
