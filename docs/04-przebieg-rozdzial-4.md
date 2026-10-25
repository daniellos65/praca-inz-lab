# Rozdział 4 — przebieg badania

Dokument opisuje kolejność czynności przy zbieraniu materiału do rozdziału
„Analiza ataków na mechanizmy negocjacji sesji i integralność danych”. Każdy
eksperyment zestawia wariant podatny z poprawionym i kończy się wynikiem
liczbowym. Numeracja eksperymentów odpowiada podrozdziałom pracy.

| Podrozdz. | Mechanizm | Wariant podatny | Wariant poprawiony | Narzędzie |
|---|---|---|---|---|
| 4.2 | negocjacja TLS | OpenSSL 1.0.2u, :4433 | nginx TLS 1.2/1.3, :443 | `r4-skan-tls.sh` |
| 4.3 | ciasteczko, szyfr strumieniowy | AES-CTR bez MAC, `/ctr/profile` | AES-GCM, `/secure/profile` | `r4-pomiar-integralnosci.py` |
| 4.4 | ciasteczko, szyfr blokowy | AES-CBC bez MAC, `/profile` | AES-GCM, `/secure/profile` | `r4-pomiar-integralnosci.py` |
| 4.5 | podpis żądań API | SHA-256(sekret‖msg), `/api/transfer` | HMAC-SHA-256, `/api/secure/transfer` | `r4-pomiar-integralnosci.py` |

Podrozdział 4.1 (uzyskanie pozycji pośrednika) jest opisowy — materiałem są logi
inspektora `arp_spoof` na sensorze i plik pcap z etapu 0.

Adresy maszyn: `server` 10.10.10.30, `client` 10.10.10.20, `sensor` 10.10.10.40.

---

## Etap 0. Uruchomienie laboratorium

1. W VirtualBox uruchom `server`, `client` i `sensor`. Maszyna `kali` nie jest
   w tym etapie potrzebna.
2. Na `server` uruchom usługi:

   ```
   cd ~/lab/server && sudo docker compose up -d
   ```

3. Sprawdź z `client`, że aplikacja odpowiada:

   ```
   curl -s http://10.10.10.30:5000/ | head -c 200
   ```

4. Na `sensor` uruchom nagrywanie ruchu — ten sam plik posłuży później
   w rozdziale 6 do oceny skuteczności IDS:

   ```
   sudo tcpdump -i enp0s3 -w ~/r4.pcap
   ```

   Nagrywanie zatrzymujesz skrótem `Ctrl+C` po zakończeniu etapu 4.5.

---

## 4.2. Negocjacja TLS

Skan wykonuje `tools/r4-skan-tls.sh`. Na `client`:

```
curl -sO https://raw.githubusercontent.com/daniellos65/praca-inz-lab/main/tools/r4-skan-tls.sh
```

```
bash r4-skan-tls.sh 10.10.10.30
```

Skrypt sprawdza dla obu serwerów, które wersje protokołu (SSLv3, TLS 1.0, 1.1,
1.2, 1.3) kończą się zestawieniem połączenia i jaki zestaw szyfrów zostaje
wynegocjowany. Starsze wersje bada starym OpenSSL-em z `/opt/openssl-legacy`,
bo współczesny ich już nie oferuje.

Osobno sprawdza `TLS_FALLBACK_SCSV`. Klient, który po nieudanej próbie
połączenia ponawia ją niższą wersją protokołu, dołącza ten znacznik. Serwer
obsługujący wersję wyższą niż żądana powinien wtedy zerwać połączenie alertem
*inappropriate fallback*. Brak tej reakcji oznacza, że obniżenie wersji
protokołu wymuszone przez pośrednika w sieci przechodzi niezauważone — to jest
sedno różnicy między obiema konfiguracjami serwera.

Materiał dowodowy: `tls-wersje.csv`, `tls-scsv.txt`, folder `logi/`.

---

## 4.3, 4.4, 4.5. Integralność komunikatu

Wszystkie trzy wykonuje jeden skrypt `tools/r4-pomiar-integralnosci.py`. Na
`client`:

```
curl -sO https://raw.githubusercontent.com/daniellos65/praca-inz-lab/main/tools/r4-pomiar-integralnosci.py
```

```
python3 r4-pomiar-integralnosci.py --host 10.10.10.30 --proby 200
```

Trwa to około dwóch minut. Skrypt wykonuje dla każdego wariantu dwa rodzaje prób.

### Seria losowa (4.3 i 4.4)

Dla każdego wariantu ciasteczka 200 prób: zmiana jednego losowego bajtu tokenu
i sprawdzenie, czy serwer go przyjął (HTTP 200). Wynik dla CBC rozbity dodatkowo
według obszaru zmienionego bajtu (wektor inicjujący, blok pośredni, blok
ostatni).

Wyniki oczekiwane (zmierzone na kopii aplikacji, ziarno 20261025):

- **AES-CTR bez MAC** — przyjęte 100 % modyfikacji. Szyfr strumieniowy nie ma
  dopełnienia ani znacznika, więc każdy kryptogram tej samej długości zostaje
  odszyfrowany i sparsowany. To jest istota plastyczności.
- **AES-CBC bez MAC** — przyjęte ok. 60 %. W rozbiciu: wektor inicjujący 100 %,
  blok pośredni ok. 80 %, blok ostatni 0 % (tam leży dopełnienie, którego
  naruszenie wykrywa `unpad`).
- **AES-GCM** — przyjęte 0 % w obu seriach. Znacznik uwierzytelniający wykrywa
  każdą modyfikację niezależnie od położenia.

### Próba celowana (4.3 i 4.4)

Przy założeniu, że atakujący zna strukturę tekstu jawnego (typowe założenie —
format ciasteczka bywa przewidywalny), skrypt zmienia bajt pola `admin` z 0 na 1
i sprawdza, czy serwer zgłosił `admin_panel = true`. Wyniki:

| Wariant | Efekt | Wyjaśnienie |
|---|---|---|
| AES-CTR bez MAC | **admin uzyskany** | Zmiana bajtu kryptogramu przekłada się 1:1 na bajt tekstu jawnego; reszta pól nienaruszona. |
| AES-CBC bez MAC | **nie uzyskany** | Pole `admin` leży na granicy dwóch bloków; wymuszenie zmiany jego bajtu psuje poprzedni blok, w którym jest nazwa klucza `adm…`. Pole przestaje się nazywać `admin`. |
| AES-GCM | **nie uzyskany** (HTTP 403) | Modyfikacja wykryta, token odrzucony. |

Wynik dla CBC jest cenny dydaktycznie: pokazuje, że plastyczność szyfru
blokowego jest **zależna od układu danych w blokach** — atak celowany wymaga
poświęcenia sąsiedniego bloku. W odróżnieniu od tego CTR pozwala na zmianę
punktową bez skutków ubocznych. To uzasadnia odrębność podrozdziałów 4.3 i 4.4.

### Weryfikacja podpisu (4.5)

Dla obu wariantów podpisu pięć żądań: nienaruszone oraz cztery rodzaje
naruszenia pary (wiadomość, podpis). Oba warianty odrzucą wszystkie cztery
naruszenia — i tak ma być.

**Jak to opisać w pracy.** Test czarnoskrzynkowy nie odróżnia konstrukcji
`SHA-256(sekret‖msg)` od HMAC, bo różnica nie leży w odporności na przypadkową
zmianę komunikatu, lecz we właściwościach konstrukcji. SHA-256 należy do rodziny
Merkle–Damgård: jej wynik jest stanem wewnętrznym po przetworzeniu ostatniego
bloku, a ten stan wystarcza, by przetwarzać dalej. Kto zna `SHA-256(sekret‖msg)`
i długość sekretu, potrafi wyznaczyć `SHA-256(sekret‖msg‖dopełnienie‖sufiks)`
dla wybranego sufiksu, nie znając sekretu. HMAC używa dwóch przebiegów funkcji
skrótu z różnymi kluczami wewnętrznymi i tej własności nie ma. Podrozdział 4.5
opisz więc jako **analizę konstrukcji** popartą pomiarem strony obronnej:
tabela pokazuje, że wariant poprawiony odrzuca naruszenia, a wybór HMAC
uzasadnia właściwość konstrukcji, nie statystyka.

### Materiał dowodowy

- `43-strumien-proby.csv`, `44-blokowy-proby.csv` — serie losowe
- `celowane-proby.csv` — próby celowane (CTR, CBC, GCM)
- `45-podpis-proby.csv` — weryfikacja podpisu
- `podsumowanie.txt` — wszystkie tabele zbiorcze, gotowe do przeniesienia

---

## Etap 4. Zebranie wyników

1. Zatrzymaj `tcpdump` na `sensor` (`Ctrl+C`).
2. Skopiuj wyniki z `client` na host:

   ```
   scp -r -P 2220 vboxuser@127.0.0.1:~/wyniki/R4 .
   ```

3. Wgraj folder do repozytorium jako `wyniki/R4` (Add file → Upload files).
4. Plik pcap zachowaj — posłuży w rozdziale 6 do oceny skuteczności reguł IDS.

---

## Uwagi do redakcji rozdziału

- Teoria pod każdy podrozdział jest już w rozdziale 2: tryby szyfrów (2.3) →
  4.3 i 4.4; Merkle–Damgård i HMAC (2.4) → 4.5; negocjacja TLS (2.6) → 4.2.
- Najmocniejsze wyniki liczbowe to tabela 4.4a (podział CBC na obszary) oraz
  zestawienie prób celowanych — oba pokazują, że skutek ingerencji jest
  przewidywalny, a nie przypadkowy.
- Przy każdej tabeli podaj ziarno generatora (20261025) — pomiar jest wtedy
  powtarzalny, co warto zaznaczyć w metodyce (3.5).
- Wyniki 4.2 zestaw w jednej tabeli dla obu serwerów obok siebie.
