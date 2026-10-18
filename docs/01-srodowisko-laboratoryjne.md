# Dziennik laboratorium: środowisko badawcze

Stan na 18.10.2026. Materiał roboczy do rozdziału „Środowisko badawcze”, pisany stylem bezosobowym, aby fragmenty można było przenosić do pracy.

## 1. Cel środowiska

Zbudowano izolowane środowisko wirtualne umożliwiające powtarzalne przeprowadzanie ataków na mechanizmy negocjacji sesji i integralność danych, rejestrację ruchu sieciowego oraz weryfikację mechanizmów detekcji. Środowisko odseparowano od sieci domowej i internetu; dostęp do internetu wykorzystywano wyłącznie na etapie instalacji oprogramowania.

## 2. Platforma

| Element | Wartość |
|---|---|
| Hipernadzorca | Oracle VirtualBox 7.x (dokładna wersja: `VBoxManage --version`) |
| System gościa | Ubuntu Server 24.04 LTS |
| Sposób powielania maszyn | klony połączone (linked clones) z migawki `czysta-baza` maszyny `ubuntu-base` |
| Lokalizacja maszyn | dysk F: (`F:\VirtualBox VMs`) |
| Automatyzacja | `setup-lab.ps1` (host), `vm-bootstrap.sh`, `vm-roles.sh` (goście) |

Klony połączone wybrano ze względu na ograniczoną przestrzeń dyskową: przechowują one wyłącznie różnice względem dysku maszyny bazowej, dzięki czemu każda maszyna zajmuje na starcie kilkadziesiąt MB zamiast kilku GB.

## 3. Topologia

| Maszyna | Adres labnet | Rola | RAM / vCPU | SSH z hosta |
|---|---|---|---|---|
| attacker | 10.10.10.10 | Kali Linux, ataki (do utworzenia) | 4 GB / 2 | – |
| client | 10.10.10.20 | ofiara: klient TLS, użytkownik aplikacji | 1 GB / 1 | `ssh lab-client` (127.0.0.1:2220) |
| server | 10.10.10.30 | usługi celowo podatne i poprawione | 2 GB / 2 | `ssh lab-server` (127.0.0.1:2230) |
| sensor | 10.10.10.40 | czujnik IDS (Snort 3), tryb nasłuchu | 4 GB / 2 | `ssh lab-sensor` (127.0.0.1:2240) |

Każda maszyna posiada dwie karty sieciowe:

- **karta 1** – sieć wewnętrzna VirtualBox `labnet` (10.10.10.0/24), adresacja statyczna, bez bramy; na czujniku włączony tryb nasłuchu (promiscuous, „allow-all”) zarówno w VirtualBox, jak i w systemie;
- **karta 2** – NAT VirtualBox, używana do instalacji pakietów i zarządzania przez SSH (przekierowanie portów 127.0.0.1:22x0 → 22).

## 4. Usługi na serwerze (Docker Compose)

| Port | Usługa | Przeznaczenie |
|---|---|---|
| 5000/tcp | aplikacja Flask (HTTP) | ciasteczko AES-CBC bez MAC vs AES-GCM; podpis SHA-256(sekret ∥ msg) vs HMAC-SHA-256 |
| 443/tcp | nginx, TLS 1.2/1.3, wyłącznie szyfry AEAD | punkt odniesienia – próby osłabienia sesji powinny się nie udać |
| 4433/tcp | OpenSSL 1.0.2u `s_server` | serwer przestarzały: TLS 1.0, CBC, RC4; obsługa TLS_FALLBACK_SCSV |

Klient (10.10.10.20) posiada OpenSSL 1.0.2u w `/opt/openssl-legacy` (niezależnie od systemowego OpenSSL) oraz skrypt `fallback_client.py`, odtwarzający niebezpieczny mechanizm ponawiania połączenia ze słabszą konfiguracją.

Czujnik (10.10.10.40) posiada Snort 3 skompilowany ze źródeł, konfigurację laboratorium `lab.lua` (inspektor `arp_spoof` z powiązaniami IP–MAC klienta i serwera, reguły wbudowane) oraz plik reguł własnych `local.rules`.

## 5. Procedura budowy

1. Instalacja Ubuntu Server 24.04 w maszynie `ubuntu-base`; konfiguracja kart (labnet + NAT), sieci niezależnej od adresów MAC (netplan po nazwach interfejsów) i serwera OpenSSH.
2. Uruchomienie `setup-lab.ps1` na hoście: migawka bazy, klony połączone, konfiguracja kart i przekierowań, instalacja klucza SSH, przesłanie plików do maszyn.
3. W każdej maszynie `vm-bootstrap.sh`: nazwa hosta, nowy `machine-id` i klucze hosta SSH, statyczny adres w labnet (interfejs wybierany po adresie MAC), na czujniku tryb nasłuchu.
4. Instalacja oprogramowania ról w tle (`vm-roles.sh`, jednostka systemd `lab-role`, log `/var/log/lab-role.log`).
5. Weryfikacja: ping między wszystkimi maszynami (6/6), poprawne zakończenie instalacji ról na wszystkich maszynach.

## 6. Napotkane problemy i rozwiązania

| Problem | Przyczyna | Rozwiązanie |
|---|---|---|
| VirtualBox 6.1 nie uruchamiał instalatora z ISO | przestarzała wersja hipernadzorcy | aktualizacja do VirtualBox 7.x |
| Klony nie uruchamiały systemu, błąd VERR_DISK_FULL | brak miejsca na dysku C:, pełne klony zapisane częściowo | klony połączone, przeniesienie folderu maszyn na dysk F: |
| Brak serwera SSH i nieznane konto w maszynie bazowej | instalacja nienadzorowana VirtualBox (użytkownik `vboxuser`, bez OpenSSH) | doinstalowanie `openssh-server` w bazie |
| Klony bez sieci | konfiguracja netplan powiązana z adresem MAC bazy | konfiguracja netplan po nazwach interfejsów (`enp0s3`, `enp0s8`) |
| Brak klienta OpenSSH w Windows | funkcja opcjonalna niezainstalowana, instalacja przez Windows Update zawiodła | instalacja Win32-OpenSSH z pakietu MSI |

## 7. Do uzupełnienia

- [ ] Wersje oprogramowania (wynik `inwentarz.txt`).
- [ ] Parametry hosta: CPU, RAM, GPU (GTX 1660), system, wersja sterownika NVIDIA.
- [ ] Maszyna attacker (Kali) – wersja i konfiguracja.
- [ ] Migawki `baseline` wszystkich maszyn.
- [ ] Schemat topologii (rysunek do pracy).
