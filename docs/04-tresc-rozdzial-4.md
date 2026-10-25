# Rozdział 4 — szkic treści

Szkic merytoryczny rozdziału „Analiza ataków na mechanizmy negocjacji sesji
i integralność danych”. Tekst podrozdziałów 4.1 jest kompletny; w 4.2–4.5
wartości liczbowe oznaczone `[…]` i akapity „Wynik” pochodzą z przebiegu
testowego na kopii aplikacji (ziarno 20261025) i wymagają potwierdzenia
pomiarem na stanowisku. Odwołania do literatury w nawiasach kwadratowych wg
numeracji ze spisu treści.

---

## 4.1. Uzyskanie pozycji pośrednika w sieci lokalnej

Każdy z ataków analizowanych w dalszej części rozdziału zakłada, że napastnik
potrafi obserwować i modyfikować ruch między klientem a serwerem. W sieci
lokalnej założenie to sprowadza się do uzyskania pozycji pośrednika
(ang. *man-in-the-middle*), co w modelu Cyber Kill Chain odpowiada fazie
*command and control* — ustanowieniu kontroli nad kanałem komunikacyjnym ofiary.

Mechanizmem wykorzystywanym do uzyskania tej pozycji jest zatruwanie pamięci
podręcznej protokołu ARP. Protokół ten, odpowiedzialny za odwzorowanie adresów
IP na adresy sprzętowe (MAC) w obrębie segmentu sieci, nie przewiduje żadnego
uwierzytelnienia odpowiedzi. Host, który otrzymuje odpowiedź ARP, aktualizuje
swoją pamięć podręczną niezależnie od tego, czy wcześniej wysłał odpowiadające
jej zapytanie. Napastnik może więc rozsyłać spreparowane odpowiedzi, w których
własny adres MAC zostaje przypisany do adresu IP bramy (dla ruchu od ofiary)
oraz do adresu IP ofiary (dla ruchu od bramy). W efekcie oba kierunki
komunikacji przechodzą przez maszynę napastnika, która może je obserwować,
opóźniać lub modyfikować, pozostając dla warstwy wyższej przezroczysta.

Skuteczność tej techniki wynika z właściwości projektowych protokołu, nie z błędu
implementacji — ARP powstał dla sieci zaufanych i nie zawiera mechanizmów
ochrony integralności ani źródła odpowiedzi. Z tego względu obroną nie jest
poprawka protokołu, lecz kontrola w warstwie niższej (statyczne wpisy ARP,
funkcja Dynamic ARP Inspection na przełącznikach) oraz wykrywanie w warstwie
sieciowej, omówione w rozdziale 6.

### Obserwowalność ataku

Zatruwanie ARP pozostawia charakterystyczny ślad: w segmencie pojawiają się
odpowiedzi ARP niepoprzedzone zapytaniem oraz wiele odpowiedzi wiążących ten sam
adres IP z różnymi adresami MAC w krótkim odstępie czasu. Na stanowisku ruch ten
rejestruje sensor pracujący w trybie nasłuchu (port w trybie promiscuous),
na którym uruchomiono inspektor `arp_spoof` systemu Snort. Inspektor porównuje
obserwowane pary (IP, MAC) i zgłasza niezgodność, gdy dla znanego adresu IP
pojawia się odpowiedź z innym adresem MAC niż zarejestrowany.

Materiałem dowodowym do tego podrozdziału są zatem: zrzut ruchu (plik pcap)
z widocznymi zduplikatami odpowiedzi ARP oraz wpisy alarmowe inspektora
`arp_spoof`. Oba artefakty wykorzystano ponownie w rozdziale 6 przy ocenie
skuteczności detekcji.

---

## 4.2. Wymuszenie słabszych parametrów sesji i mechanizmy ochronne

Napastnik dysponujący pozycją pośrednika może ingerować w fazę negocjacji
protokołu TLS, dążąc do wymuszenia najsłabszego wspólnie obsługiwanego zestawu
parametrów (ang. *downgrade*). Podstawą obrony przed taką ingerencją jest
ograniczenie zbioru akceptowanych wersji protokołu po stronie serwera oraz
mechanizm sygnalizujący próbę obniżenia wersji.

Na stanowisku zestawiono dwa serwery różniące się konfiguracją:
usługę zbudowaną na bibliotece OpenSSL 1.0.2u (port 4433), odpowiadającą
konfiguracji przestarzałej, oraz serwer nginx z konfiguracją współczesną
(port 443), ograniczoną do wersji TLS 1.2 i 1.3. Dla obu zinwentaryzowano zbiór
akceptowanych wersji protokołu oraz reakcję na znacznik `TLS_FALLBACK_SCSV`.

Znacznik ten jest sygnałem dołączanym przez klienta, który — po nieudanej próbie
połączenia — ponawia ją, obniżając wersję protokołu. Serwer obsługujący wersję
wyższą niż żądana powinien wówczas odrzucić połączenie alarmem *inappropriate
fallback*, traktując obniżenie jako możliwy objaw ingerencji. Brak tej reakcji
oznacza, że wymuszone przez pośrednika obniżenie wersji przechodzi niezauważone
[1].

**Wynik.** Serwer współczesny akceptuje wyłącznie TLS 1.2 i 1.3 oraz odrzuca
połączenie ze znacznikiem `TLS_FALLBACK_SCSV` (reakcja *inappropriate fallback*).
Serwer przestarzały akceptuje dodatkowo SSLv3, TLS 1.0 i 1.1, a znacznik
obniżenia wersji ignoruje — pozostawia zatem możliwość cichego wymuszenia
słabszej wersji przez pośrednika. Zestawienie obu konfiguracji zawiera tabela 4.1
(pomiar na stanowisku, OpenSSL klienta 3.0.13, OpenSSL przestarzały 1.0.2u).

| Wersja | Serwer współczesny (:443) | Serwer przestarzały (:4433) |
|---|---|---|
| SSLv3 | odrzucona | zaakceptowana |
| TLS 1.0 | odrzucona | zaakceptowana |
| TLS 1.1 | odrzucona | zaakceptowana |
| TLS 1.2 | zaakceptowana | zaakceptowana |
| TLS 1.3 | zaakceptowana | odrzucona |
| reakcja na SCSV | odrzuca próbę obniżenia (ochrona działa) | akceptuje mimo znacznika (brak ochrony) |

Serwer przestarzały odrzuca jedynie TLS 1.3, ponieważ biblioteka OpenSSL 1.0.2u
tej wersji protokołu nie implementuje. Nie jest to więc efekt utwardzenia, lecz
ograniczenia przestarzałej implementacji — pozostałe, słabsze wersje pozostają
dostępne.

---

## 4.3. Plastyczność szyfru strumieniowego

Szyfr strumieniowy (oraz szyfr blokowy w trybie licznikowym CTR) przekształca
tekst jawny przez operację XOR ze strumieniem klucza. Właściwość ta oznacza, że
zmiana dowolnego bitu kryptogramu powoduje zmianę dokładnie odpowiadającego mu
bitu tekstu jawnego, bez wpływu na pozostałe. Jeżeli kryptogram nie jest
chroniony kodem uwierzytelniającym, napastnik znający położenie i wartość
fragmentu tekstu jawnego może dokonać jego dowolnej, punktowej modyfikacji —
jest to tak zwana plastyczność szyfru (ang. *malleability*) [2].

Na stanowisku zbadano ciasteczko sesyjne szyfrowane AES-128 w trybie CTR bez
kodu uwierzytelniającego (wariant podatny) oraz to samo ciasteczko chronione
trybem AES-128-GCM (wariant poprawiony). Wykonano dwa rodzaje prób: serię
losowych modyfikacji pojedynczego bajtu tokenu oraz próbę celowaną, zmieniającą
pole uprawnień `admin` z wartości 0 na 1 przy założeniu znajomości struktury
tekstu jawnego.

**Wynik (przebieg testowy, do potwierdzenia).** Wariant CTR bez
uwierzytelnienia przyjął 100 % (200/200) zmodyfikowanych tokenów; w każdym
przypadku odszyfrowana treść różniła się od pierwotnej. Próba celowana
zakończyła się uzyskaniem podniesionych uprawnień (`admin_panel = true`) bez
naruszenia pozostałych pól. Wariant GCM odrzucił wszystkie modyfikacje
(0/200) oraz próbę celowaną (HTTP 403). Potwierdza to, że w szyfrze
strumieniowym poufność bez kontroli integralności nie chroni treści przed
ukierunkowaną ingerencją, a zastosowanie trybu z uwierzytelnieniem usuwa tę
podatność.

---

## 4.4. Modyfikacja danych zaszyfrowanych w trybie CBC

W trybie wiązania bloków zaszyfrowanych (CBC) tekst jawny bloku *i* powstaje
przez operację XOR odszyfrowanego bloku *i* z blokiem kryptogramu *i−1*
(dla pierwszego bloku — z wektorem inicjującym). Modyfikacja bajtu kryptogramu
w bloku *i−1* powoduje więc kontrolowaną zmianę odpowiadającego bajtu tekstu
jawnego w bloku *i*, kosztem całkowitego zniekształcenia bloku *i−1*. W
odróżnieniu od szyfru strumieniowego plastyczność trybu CBC jest zatem zależna
od położenia zmiany i ograniczona strukturą bloków [2].

Zbadano ciasteczko szyfrowane AES-128-CBC bez kodu uwierzytelniającego (wariant
podatny) wobec tego samego ciasteczka w trybie GCM (wariant poprawiony),
analogicznie do podrozdziału 4.3. Wynik serii losowej rozbito dodatkowo według
obszaru, w którym leżał zmieniony bajt: wektor inicjujący, blok pośredni, blok
ostatni.

**Wynik (przebieg testowy, do potwierdzenia).** Wariant CBC bez uwierzytelnienia
przyjął około 60 % zmodyfikowanych tokenów. Rozkład akceptacji według obszaru:
wektor inicjujący 100 %, blok pośredni około 80 %, blok ostatni 0 % — w ostatnim
bloku znajduje się dopełnienie, którego naruszenie wykrywa funkcja `unpad`
(tab. 4.2). Próba celowana na polu `admin` nie powiodła się: pole to leży na
granicy dwóch bloków, a wymuszenie zmiany jego bajtu zniekształciło blok
poprzedni zawierający nazwę pola, przez co przestało być rozpoznane. Wariant GCM
odrzucił wszystkie modyfikacje. Wynik ten pokazuje, że plastyczność trybu CBC
jest realna, lecz uwarunkowana układem danych w blokach — inaczej niż w
przypadku szyfru strumieniowego z podrozdziału 4.3.

| Obszar tokenu | Próby | Przyjęte | Odsetek [%] |
|---|---|---|---|
| wektor inicjujący | `[…]` | `[…]` | `[…]` |
| blok pośredni | `[…]` | `[…]` | `[…]` |
| blok ostatni | `[…]` | `[…]` | `[…]` |

---

## 4.5. Rozszerzenie długości skrótu w konstrukcji sekret ‖ wiadomość

Uwierzytelnianie żądań API zrealizowano w dwóch wariantach. W wariancie podatnym
podpis wyznaczany jest jako `SHA-256(sekret ‖ wiadomość)`, w poprawionym —
jako `HMAC-SHA-256(sekret, wiadomość)`. Różnica między nimi nie ujawnia się
w teście czarnoskrzynkowym odporności na losową modyfikację, lecz wynika
z właściwości konstrukcji funkcji skrótu [2].

Funkcja SHA-256 należy do rodziny Merkle–Damgård: jej wynikiem jest stan
wewnętrzny po przetworzeniu ostatniego bloku wejścia, a stan ten wystarcza do
kontynuowania przetwarzania kolejnych bloków. Napastnik znający wartość
`SHA-256(sekret ‖ wiadomość)` oraz długość sekretu może — nie znając samego
sekretu — wyznaczyć poprawny skrót dla wiadomości rozszerzonej o wybrany sufiks
(`sekret ‖ wiadomość ‖ dopełnienie ‖ sufiks`). Jest to atak rozszerzenia
długości (ang. *length-extension*). Konstrukcja HMAC, wykorzystująca dwa
przebiegi funkcji skrótu z różnymi kluczami wewnętrznymi, nie udostępnia stanu
wewnętrznego i tej podatności nie posiada.

**Wynik.** Oba warianty odrzucają wszystkie cztery rodzaje naruszenia pary
(wiadomość, podpis) badane w teście czarnoskrzynkowym (tab. 4.3), co potwierdza
poprawność weryfikacji podpisu w warstwie aplikacji. Przewaga HMAC nie polega
więc na wyższej odporności na przypadkową modyfikację, lecz na odporności
konstrukcyjnej na atak rozszerzenia długości, którego konstrukcja naiwna nie
wyklucza. Z tego względu podrozdział traktuje różnicę jako wynik analizy
konstrukcji popartej pomiarem strony obronnej.

| Przypadek | SHA-256(sekret‖msg) | HMAC-SHA-256 |
|---|---|---|
| komunikat nienaruszony | przyjęty | przyjęty |
| zmieniona wartość pola | odrzucony | odrzucony |
| doklejony sufiks | odrzucony | odrzucony |
| zmieniony znak podpisu | odrzucony | odrzucony |
| podpis losowy | odrzucony | odrzucony |

---

## 4.6. Podsumowanie wyników

Zestawienie zbiorcze: dla każdego z analizowanych mechanizmów wariant podatny
oraz skutek wprowadzenia poprawki.

| Mechanizm | Wariant podatny | Obserwowana podatność | Poprawka | Skutek |
|---|---|---|---|---|
| negocjacja TLS | OpenSSL 1.0.2u | akceptacja starszych wersji, brak reakcji na SCSV | ograniczenie do TLS 1.2/1.3, SCSV | ciche obniżenie wersji niemożliwe |
| ciasteczko (strumień) | AES-CTR bez MAC | modyfikacja punktowa, uzyskanie uprawnień | AES-GCM | modyfikacja wykryta |
| ciasteczko (blok) | AES-CBC bez MAC | modyfikacja zależna od bloku | AES-GCM | modyfikacja wykryta |
| podpis API | SHA-256(sekret‖msg) | atak rozszerzenia długości | HMAC-SHA-256 | podatność konstrukcyjnie wykluczona |

Wspólnym wnioskiem rozdziału jest, że zapewnienie poufności danych nie implikuje
ochrony ich integralności: w każdym z trzech mechanizmów danych aplikacyjnych
zabezpieczenie uzyskano dopiero przez zastosowanie konstrukcji uwierzytelniającej
(AEAD lub HMAC). Wniosek ten stanowi przesłankę dla warstwy obronnej
projektowanej w rozdziale 6.
