# Rozdział 4 — przebieg badania

Dokument opisuje kolejność czynności przy zbieraniu materiału do rozdziału
„Ataki na integralność i negocjację sesji”. Każdy eksperyment zestawia wariant
podatny z poprawionym i kończy się wynikiem liczbowym.

| Eksperyment | Mechanizm | Wariant podatny | Wariant poprawiony |
|---|---|---|---|
| E1 | ciasteczko sesyjne | AES-128-CBC bez MAC, `/profile` | AES-128-GCM, `/secure/profile` |
| E2 | podpis żądań API | SHA-256(sekret‖msg), `/api/transfer` | HMAC-SHA-256, `/api/secure/transfer` |
| E3 | negocjacja TLS | OpenSSL 1.0.2u, port 4433 | nginx TLS 1.2/1.3, port 443 |

Adresy maszyn: `server` 10.10.10.30, `client` 10.10.10.20, `sensor` 10.10.10.40.

---

## Etap 0. Uruchomienie laboratorium

1. W VirtualBox uruchom `server`, `client` i `sensor` (migawka „czysta-baza” lub
   nowsza). Maszyna `kali` nie jest w tym etapie potrzebna.
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
   sudo tcpdump -i enp0s3 -w ~/pcap/r4-$(date +%H%M).pcap
   ```

   Nagrywanie zatrzymujesz skrótem `Ctrl+C` po zakończeniu etapu E3.

---

## Etap E1 i E2. Odporność komunikatu na modyfikację

Pomiar wykonuje skrypt `tools/r4-pomiar-integralnosci.py`. Pobierz go na
`client` i uruchom:

```
curl -sO https://raw.githubusercontent.com/daniellos65/praca-inz-lab/main/tools/r4-pomiar-integralnosci.py
```

```
python3 r4-pomiar-integralnosci.py --host 10.10.10.30 --proby 200
```

### Co skrypt mierzy

**E1.** Dla każdego z dwóch wariantów ciasteczka wykonuje 200 prób. W każdej
próbie zmienia jeden losowy bajt tokenu i sprawdza, czy serwer przyjął taki
token (HTTP 200), czy odrzucił. Wynik rozbija dodatkowo według obszaru, w którym
leżał zmieniony bajt: wektor inicjujący, blok pośredni, blok ostatni.

Wynik oczekiwany: wariant GCM odrzuca 100 % zmodyfikowanych tokenów. Wariant CBC
bez MAC przyjmuje znaczną ich część, przy czym odsetek zależy od obszaru —
modyfikacja wektora inicjującego nie narusza dopełnienia, więc token przechodzi
weryfikację i zmienia zawartość sesji.

**E2.** Dla każdego z dwóch wariantów podpisu wysyła pięć żądań: nienaruszone
oraz cztery rodzaje naruszenia pary (wiadomość, podpis). Sprawdza, czy serwer
odrzuca każde naruszenie.

### Interpretacja wyniku E2

Oba warianty odrzucą wszystkie cztery naruszenia — i tak ma być. Test
czarnoskrzynkowy nie odróżnia konstrukcji `SHA-256(sekret‖msg)` od HMAC, bo
różnica między nimi nie leży w odporności na przypadkową zmianę komunikatu,
lecz we właściwościach samej konstrukcji. Funkcja SHA-256 należy do rodziny
Merkle–Damgård: jej wynik jest stanem wewnętrznym po przetworzeniu ostatniego
bloku, a ten stan wystarcza, by kontynuować przetwarzanie dalszych bloków.
Kto zna `SHA-256(sekret‖msg)` i długość sekretu, potrafi wyznaczyć wartość
`SHA-256(sekret‖msg‖dopełnienie‖sufiks)` dla wybranego sufiksu, nie znając
sekretu. HMAC używa dwóch przebiegów funkcji skrótu z różnymi kluczami
wewnętrznymi i tej własności nie ma.

W pracy ten eksperyment opisz więc jako **analizę konstrukcji** popartą pomiarem
strony obronnej, a nie jako pomiar różnicy. To uczciwe podejście i częste
w literaturze: tabela z wynikami pokazuje, że wariant poprawiony odrzuca
wszystkie naruszenia, a uzasadnienie wyboru HMAC opiera się na właściwości
konstrukcji, nie na statystyce.

### Materiał dowodowy

- `e1-proby.csv` — każda próba osobno (pozycja bajtu, obszar, kod HTTP, pola sesji)
- `e2-proby.csv` — wynik każdego przypadku
- `podsumowanie.txt` — tabele zbiorcze, gotowe do przeniesienia do pracy

---

## Etap E3. Negocjacja TLS

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

Materiał dowodowy: `tls-wersje.csv`, `tls-scsv.txt`, folder `logi/`
z pełnym zapisem każdego połączenia.

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

- Tabela E1a (podział według obszaru modyfikacji) jest najmocniejszym wynikiem
  tej części: pokazuje, że skutek modyfikacji kryptogramu w trybie CBC jest
  przewidywalny, a nie przypadkowy. To uzasadnia tezę, że poufność bez kontroli
  integralności nie chroni przed ingerencją w treść.
- Przy każdej tabeli podaj ziarno generatora (domyślnie 20261025) — dzięki temu
  pomiar jest powtarzalny, co warto zaznaczyć w opisie metodyki.
- Wyniki E3 zestaw w jednej tabeli dla obu serwerów obok siebie; różnica
  w kolumnie „wynik” jest czytelniejsza niż dwie osobne tabele.
