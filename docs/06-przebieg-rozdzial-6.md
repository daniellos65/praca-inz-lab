# Rozdział 6 — przebieg badania

Budowa i weryfikacja wielowarstwowego systemu obronnego. Dwie warstwy:
detekcja w sieci (IDS, 6.1) i detekcja eksfiltracji po entropii (6.2).

| Podrozdz. | Co robimy | Maszyny | Narzędzie |
|---|---|---|---|
| 6.1 | reguły Snorta: downgrade TLS + słaby szyfr | sensor + `r4.pcap` (offline) | `sensor/local.rules` |
| 6.2 | detekcja danych zaszyfrowanych po entropii | dowolna (host/klient, bez VM) | `tools/r6-gen-zbior.py`, `tools/r6-entropia.py` |
| 6.3 | zebranie skuteczności obu warstw w tabele | — | — |
| 6.4 | ograniczenia rozwiązania | — (opis) | — |

---

## 6.2. Detekcja entropijna (bez maszyn wirtualnych)

Można wykonać na kliencie lub dowolnej maszynie z Pythonem 3 — nie wymaga sieci
laboratoryjnej. Oba skrypty używają wyłącznie biblioteki standardowej.

### Krok 1 — pobierz narzędzia

```
curl -fL -o r6-gen-zbior.py https://raw.githubusercontent.com/daniellos65/praca-inz-lab/main/tools/r6-gen-zbior.py
curl -fL -o r6-entropia.py https://raw.githubusercontent.com/daniellos65/praca-inz-lab/main/tools/r6-entropia.py
```

### Krok 2 — wygeneruj zbiór testowy

```
python3 r6-gen-zbior.py zbior
```

Tworzy katalog `zbior/` z trzema grupami po 20 plików: `jawne`, `skompresowane`,
`zaszyfrowane`. Zbiór jest syntetyczny i powtarzalny (stałe ziarno 20261029).
Opcjonalnie do `zbior/zaszyfrowane/` można dołożyć realne kontenery (kopie
`.kdbx`, archiwum 7z z hasłem) — zwiększa realizm.

### Krok 3 — uruchom analizę

```
python3 r6-entropia.py zbior --out wyniki-R6
```

Dla każdego pliku liczy entropię Shannona, statystykę chi-kwadrat rozkładu
bajtów i rozpoznaje typ po nagłówku. Porównuje dwa klasyfikatory i wypisuje
macierze pomyłek.

### Wynik oczekiwany (przebieg testowy)

| Grupa | Entropia [bit/bajt] | chi-kwadrat |
|---|---|---|
| jawne | ~4,3 | ~440 000 |
| skompresowane | ~7,8 | ~570 |
| zaszyfrowane | ~8,0 | ~258 |

- **Klasyfikator A (sama entropia):** czułość 100 %, ale **FPR 40 %** — myli dane
  skompresowane z zaszyfrowanymi, bo obie grupy mają wysoką entropię.
- **Klasyfikator B (entropia + chi-kwadrat + brak nagłówka):** FPR 0 %, precyzja
  100 %, dokładność ~97 %. Pojedyncze pominięcia (FN) wynikają z naturalnej
  zmienności statystyki chi-kwadrat dla małych plików — to oczekiwane zachowanie,
  nie błąd metody (omówić w 6.4).
- **Ograniczenie Base64:** zakodowanie danych zaszyfrowanych obniża entropię do
  ~6 bit/bajt, przez co klasyfikator A je przeocza.

### Materiał dowodowy

`wyniki-R6/pliki.csv` (cechy każdego pliku), `wyniki-R6/podsumowanie.txt`
(macierze pomyłek, metryki). Folder wgrać do repo jako `wyniki/R6`.

---

## 6.1. Detekcja w warstwie sieciowej (IDS)

Reguły działają na nagraniu `r4.pcap` z rozdziału 4 (zawiera negocjacje TLS obu
serwerów), więc analiza jest **offline** — nie trzeba odtwarzać ataków.

### Krok 1 — wgraj zaktualizowane reguły na sensor

Na sensorze pobierz nowy plik reguł i umieść go w katalogu reguł Snorta:

```
curl -fL -o local.rules https://raw.githubusercontent.com/daniellos65/praca-inz-lab/main/sensor/local.rules
sudo cp local.rules /usr/local/etc/rules/local.rules
```

### Krok 2 — uruchom Snort na nagraniu

```
sudo snort -c /usr/local/etc/snort/snort.lua --tweaks lab -r ~/r4.pcap -A alert_fast -q 2>&1 | grep "LAB 6.1" | sort | uniq -c
```

`grep "LAB 6.1" | sort | uniq -c` zlicza alerty według treści.

### Wynik oczekiwany

| Reguła (sid) | Treść | Liczba |
|---|---|---|
| 1000010 | ServerHello: SSLv3 | 2 |
| 1000011 | ServerHello: TLS 1.0 | 2 |
| 1000012 | ServerHello: TLS 1.1 | 2 |
| 1000013 | słaby szyfr ECDHE-RSA-AES256-SHA (CBC/SHA1) | 6 |

Reguły wykrywają wyłącznie ruch serwera przestarzałego (:4433); serwer
współczesny (:443) negocjuje TLS 1.2/1.3 i nie wyzwala żadnego alertu — co jest
dowodem skuteczności rozróżnienia.

Do tego z rozdziału 4.1 mamy już działającą detekcję `arp_spoof` (alerty
`112:3`/`112:4`). Trzy warstwy detekcji sieciowej: zatrucie ARP, obniżenie wersji
TLS, słaby szyfr.

### Materiał dowodowy

Pełne wyjście Snorta zapisać do pliku i wgrać do `wyniki/R6`:

```
sudo snort -c /usr/local/etc/snort/snort.lua --tweaks lab -r ~/r4.pcap -A alert_fast -q > ~/r6-ids-alerty.txt 2>&1
```

---

## 6.3 i 6.4

- **6.3** — zebranie wyników: skuteczność IDS (liczba wykrytych klas ataków na
  `r4.pcap`) oraz skuteczność detekcji entropijnej (macierz pomyłek, TPR/FPR)
  w jedną tabelę zbiorczą.
- **6.4** — ograniczenia: Base64 obniżający entropię, dane skompresowane o
  rozkładzie zbliżonym do losowego, wolne zatruwanie ARP poniżej progu, szyfrowany
  kanał dowodzenia niewidoczny dla reguł treściowych.
