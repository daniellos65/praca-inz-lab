# Rozdział 6 — szkic treści

Projekt i weryfikacja wielowarstwowego systemu obronnego. Podrozdział 6.2 jest
spisany na gotowo z wynikami pomiaru; 6.1 zawiera analizę i wartości oczekiwane
(do potwierdzenia uruchomieniem Snorta na `r4.pcap`); 6.3 i 6.4 — po zebraniu
obu warstw. Odwołania do literatury wg numeracji ze spisu treści.

---

## 6.1. Detekcja w warstwie sieciowej (IDS)

Pierwszą warstwą obrony jest system detekcji włamań pracujący na kopii ruchu
sieciowego. Na stanowisku rolę tę pełni Snort 3 na maszynie-czujniku
(10.10.10.40), nasłuchujący w trybie promiscuous. Detekcja obejmuje trzy klasy
zdarzeń odpowiadające atakom z rozdziału 4.

**Zatrucie ARP.** Wbudowany inspektor `arp_spoof`, skonfigurowany poprawnymi
powiązaniami IP↔MAC, wykrywa odpowiedzi ARP wiążące znany adres IP z niewłaściwym
adresem sprzętowym (wynik w podrozdziale 4.1: alarmy `112:3` i `112:4`) [5].

**Obniżenie wersji protokołu.** Reguły własne analizują pole wynegocjowanej
wersji w komunikacie ServerHello (offset 9–10 rekordu TLS). Alarm wyzwala
negocjacja SSLv3, TLS 1.0 lub TLS 1.1 — wersji uznanych za przestarzałe.
Wersje TLS 1.2 i 1.3 nie są zgłaszane, dzięki czemu reguła rozróżnia serwer
przestarzały od współczesnego bez fałszywych alarmów [1].

**Słaby zestaw szyfrów.** Dodatkowa reguła wykrywa negocjację zestawu
ECDHE-RSA-AES256-SHA (0xC014), łączącego wymianę klucza ECDHE z szyfrowaniem w
trybie CBC i uwierzytelnieniem SHA-1.

**Wynik.** Reguły uruchomiono offline na nagraniu `r4.pcap` z rozdziału 4.
Zarejestrowano 12 trafień, w całości dla ruchu serwera przestarzałego
(10.10.10.30:4433):

| Reguła | Wykrywane zdarzenie | Trafienia |
|---|---|---|
| 1000010 | ServerHello: SSLv3 | 2 |
| 1000011 | ServerHello: TLS 1.0 | 2 |
| 1000012 | ServerHello: TLS 1.1 | 2 |
| 1000013 | słaby szyfr ECDHE-RSA-AES256-SHA | 6 |

Ruch serwera współczesnego (:443), negocjujący TLS 1.2 i 1.3, nie wyzwolił żadnej
reguły — potwierdza to, że detekcja rozróżnia konfigurację podatną od utwardzonej
bez fałszywych alarmów. Materiał dowodowy: `wyniki/R6/r6-ids-alerty.txt`.

---

## 6.2. Detekcja prób eksfiltracji na podstawie analizy entropii

Druga warstwa obrony dotyczy danych opuszczających sieć. Napastnik, który
wyprowadza skradzione dane, często je szyfruje lub pakuje, aby ukryć ich treść.
Dane takie mają rozkład bajtów zbliżony do losowego, co odróżnia je od typowych
danych jawnych. Miarą tej właściwości jest entropia Shannona [4].

Zbadano zbiór 60 plików w trzech grupach po 20: jawne (tekst, kod, dane
strukturalne), skompresowane (gzip, zip) oraz zaszyfrowane (dane nieodróżnialne
od losowych). Dla każdego pliku wyznaczono entropię Shannona, statystykę
chi-kwadrat rozkładu 256 wartości bajtów względem rozkładu jednostajnego oraz
rozpoznanie typu po nagłówku (magic bytes).

**Niewystarczalność samej entropii.** Średnie wartości cech w grupach (tab. 6.1)
pokazują, że entropia nie rozdziela danych skompresowanych od zaszyfrowanych —
obie grupy mają entropię bliską maksimum (8 bit/bajt). Rozróżnia je dopiero
statystyka chi-kwadrat: dla danych zaszyfrowanych rozkład jest jednostajny
(niskie chi-kwadrat), dla skompresowanych — nie (wyższe chi-kwadrat).

| Grupa | Entropia [bit/bajt] | chi-kwadrat |
|---|---|---|
| jawne | 4,331 | 439 854,8 |
| skompresowane | 7,815 | 575,0 |
| zaszyfrowane | 7,994 | 257,3 |

**Porównanie klasyfikatorów.** Zestawiono klasyfikator oparty na samej entropii
(A: H ≥ 7,5) z klasyfikatorem łączącym entropię, test chi-kwadrat i brak
rozpoznanego nagłówka (B). Klasa pozytywna to pliki zaszyfrowane (tab. 6.2).

| Metryka | Klasyfikator A (entropia) | Klasyfikator B (entropia + chi² + nagłówek) |
|---|---|---|
| czułość (TPR) | 100,0 % | 100,0 % |
| fałszywe alarmy (FPR) | 40,0 % | 0,0 % |
| precyzja | 55,6 % | 100,0 % |
| dokładność | 73,3 % | 100,0 % |

Klasyfikator oparty na samej entropii wykrywa wszystkie pliki zaszyfrowane, ale
błędnie klasyfikuje jako zaszyfrowane 40 % plików skompresowanych (16 z 40
przypadków negatywnych). Dołączenie testu rozkładu i rozpoznania nagłówka
eliminuje te fałszywe alarmy, podnosząc dokładność do 100 %. (W powtórzeniach z
innym losowym wypełnieniem plików zaszyfrowanych klasyfikator B notuje czasem
pojedyncze pominięcia wynikające ze zmienności statystyki chi-kwadrat dla małych
plików — zob. 6.4.)

**Ograniczenie kodowania Base64.** Dane zaszyfrowane zakodowane Base64 używają
alfabetu 64 znaków, co ogranicza entropię do 6 bit/bajt. Wszystkie 10 badanych
plików po zakodowaniu spadło poniżej progu klasyfikatora A i nie zostałoby
wykrytych. Pokazuje to, że detekcja entropijna wymaga uprzedniej normalizacji
kodowania transportowego (szerzej w 6.4).

---

## 6.3. Weryfikacja skuteczności systemu

Zestawienie skuteczności obu warstw obrony na materiale z rozdziału 4 oraz
zbiorze testowym.

**Warstwa sieciowa (IDS).** Na nagraniu ruchu wszystkie trzy klasy zdarzeń
odpowiadające atakom z rozdziału 4 zostały wykryte, przy braku alarmów dla
konfiguracji utwardzonej (tab. 6.3):

| Klasa zdarzenia | Źródło dowodu | Wykrycie |
|---|---|---|
| zatrucie ARP | 4.1 (`arp41.pcap`) | alarmy 112:3 i 112:4, po 3 na ramkę |
| obniżenie wersji TLS | 6.1 (`r4.pcap`) | 6 alarmów (SSLv3, TLS 1.0, TLS 1.1) |
| słaby zestaw szyfrów | 6.1 (`r4.pcap`) | 6 alarmów (ECDHE-RSA-AES256-SHA) |
| ruch utwardzony (TLS 1.2/1.3) | 6.1 (`r4.pcap`) | brak alarmów (poprawnie) |

**Warstwa danych (detekcja entropijna).** Klasyfikator łączący entropię, test
chi-kwadrat i rozpoznanie nagłówka osiągnął na zbiorze 60 plików czułość 100 %,
odsetek fałszywych alarmów 0 % i dokładność 100 % (tab. 6.2), podczas gdy
klasyfikator oparty na samej entropii — dokładność 73,3 % przy 40 % fałszywych
alarmów.

Obie warstwy działają komplementarnie: IDS wykrywa fazę ataku w sieci, detekcja
entropijna — próbę wyprowadzenia danych. Żadna z nich samodzielnie nie pokrywa
obu etapów, co uzasadnia podejście wielowarstwowe.

---

## 6.4. Ograniczenia rozwiązania

- **Base64 i inne kodowania transportowe** obniżają entropię danych
  zaszyfrowanych poniżej progu — bez normalizacji kodowania detekcja entropijna
  je przeocza.
- **Dane skompresowane o rozkładzie zbliżonym do losowego** mogą sporadycznie
  spełnić kryterium rozkładu; stąd niezerowy margines błędu klasyfikatora.
- **Zmienność statystyki dla małych plików** powoduje pojedyncze pominięcia
  (FN) — próg chi-kwadrat jest kompromisem między czułością a liczbą fałszywych
  alarmów.
- **Wolne zatrucie ARP** (pojedyncze ramki w długich odstępach) może pozostać
  poniżej progu uwagi analityka, mimo że inspektor zgłasza każdą ramkę.
- **Szyfrowany kanał dowodzenia** przenoszący dane w ramach dozwolonego,
  szyfrowanego ruchu (np. HTTPS) jest niewidoczny dla reguł treściowych IDS —
  detekcja wymagałaby analizy metadanych lub inspekcji TLS.
