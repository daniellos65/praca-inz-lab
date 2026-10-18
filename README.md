# Laboratorium do pracy inżynierskiej: instrukcja uruchomienia

> **Bezpieczeństwo.** Aplikacja i serwer TLS w tym pakiecie są **celowo podatne**. Uruchamiaj je wyłącznie w izolowanej sieci wewnętrznej maszyn wirtualnych, nigdy w sieci domowej ani firmowej.

## Zawartość pakietu

```
lab/
├── setup-lab.ps1               automatyczna konfiguracja (Windows, PowerShell)
├── vm-bootstrap.sh             konfiguracja wnętrza maszyny (nazwa, adres, rola)
├── vm-roles.sh                 instalacja oprogramowania roli (w tle)
├── server/                     -> VM serwer (10.10.10.30)
│   ├── docker-compose.yml      aplikacja + nowoczesny TLS + przestarzały TLS
│   ├── certs/gen-certs.sh      generowanie certyfikatu
│   ├── webapp/                 aplikacja Flask (CBC vs GCM, SHA-256 vs HMAC)
│   ├── nginx-modern/           nginx: tylko TLS 1.2/1.3, szyfry AEAD
│   └── legacy-tls/             OpenSSL 1.0.2u: SSLv3-TLS 1.2, CBC, RC4
├── client/                     -> VM klient (10.10.10.20)
│   ├── build-legacy-openssl.sh kompilacja OpenSSL 1.0.2u do /opt/openssl-legacy
│   └── fallback_client.py      klient z niebezpiecznym mechanizmem fallback
└── sensor/                     -> VM czujnik IDS (10.10.10.40)
    ├── install-snort3.sh       kompilacja Snort 3
    ├── lab.lua                 konfiguracja laboratorium (arp_spoof, reguły)
    └── local.rules             reguły własne (plik startowy)
```

## Topologia

| Maszyna | System | Adres | RAM | Dysk |
|---|---|---|---|---|
| attacker | Kali Linux (aktualny) | 10.10.10.10/24 | 4 GB | 40 GB |
| client | Ubuntu 24.04 Server | 10.10.10.20/24 | 2 GB | 20 GB |
| server | Ubuntu 24.04 Server | 10.10.10.30/24 | 2 GB | 25 GB |
| sensor | Ubuntu 24.04 Server | 10.10.10.40/24 | 4 GB na czas kompilacji, potem 2 GB | 25 GB |

Wszystkie maszyny w jednej sieci wewnętrznej `labnet`, bez bramy i bez DNS. GPU i Hashcat zostają na hoście (punkt 7).

---

## Szybki start: automatyczna konfiguracja (zalecane)

Na komputerze z VirtualBoxem, gdy masz już zainstalowaną i **wyłączoną** maszynę `ubuntu-base` (Ubuntu Server 24.04, karta 1 = labnet, karta 2 = NAT, OpenSSH):

1. Rozpakuj `lab.zip`, np. do `C:\lab`.
2. Otwórz PowerShell w tym folderze (Shift + prawy przycisk w folderze → „Otwórz okno programu PowerShell tutaj”, albo `cd C:\lab`).
3. Uruchom:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup-lab.ps1
   ```

Skrypt usuwa niedziałające klony, tworzy klony połączone `server`, `client`, `sensor`, ustawia sieć i SSH, przesyła pliki do maszyn, nadaje adresy i uruchamia w tle instalację Dockera, OpenSSL 1.0.2u i Snorta 3. Każda maszyna zapyta dwa razy o hasło użytkownika Ubuntu. Na końcu sprawdza pingi i dodaje skróty `ssh lab-server`, `ssh lab-client`, `ssh lab-sensor`.

Postęp instalacji w tle: `ssh lab-sensor "sudo tail -f /var/log/lab-role.log"`.

Punkty 1–6 poniżej opisują to samo krok po kroku, na wypadek konfiguracji ręcznej.

---

## 1. Sieć w hipernadzorcy

**VirtualBox:** każda VM ma dwie karty sieciowe:

- **Karta 1:** „Sieć wewnętrzna” (Internal Network), nazwa `labnet`. Na maszynie `sensor` dodatkowo: Zaawansowane → Tryb nasłuchiwania (Promiscuous Mode) → **Zezwalaj wszystkim** (Allow All).
- **Karta 2:** „NAT”, tylko na czas instalacji pakietów. Po zakończeniu konfiguracji odznacz „Kabel podłączony” albo wyłącz kartę.

**VMware Workstation:** karta 1 = LAN Segment `labnet`, karta 2 = NAT. Tryb nasłuchu w segmentach LAN jest zwykle dostępny domyślnie; jeśli czujnik nie widzi ruchu między innymi maszynami, sprawdź ustawienia promiscuous dla hosta.

## 2. Instalacja systemów i adresacja

Zainstaluj Ubuntu 24.04 Server na `client`, `server`, `sensor` (podczas instalacji zaznacz OpenSSH server) i Kali na `attacker`.

**Ubuntu: statyczny adres na karcie wewnętrznej.** Sprawdź nazwy interfejsów (`ip link`). Zwykle `enp0s3` to karta 1 (labnet), `enp0s8` to karta 2 (NAT). Utwórz `/etc/netplan/60-lab.yaml` (przykład dla serwera; zmień adres dla każdej maszyny):

```yaml
network:
  version: 2
  ethernets:
    enp0s3:
      dhcp4: false
      addresses: [10.10.10.30/24]
    enp0s8:
      dhcp4: true
```

```bash
sudo chmod 600 /etc/netplan/60-lab.yaml
sudo netplan apply
ip -br addr
```

**Kali (NetworkManager):**

```bash
nmcli con show                                    # znajdź połączenie dla karty labnet, np. "Wired connection 1"
sudo nmcli con mod "Wired connection 1" ipv4.method manual ipv4.addresses 10.10.10.10/24 ipv4.gateway "" ipv4.never-default yes
sudo nmcli con up "Wired connection 1"
```

**Sprawdzenie:** z każdej maszyny `ping` do pozostałych trzech adresów.

**Przeniesienie plików pakietu do VM.** Najprościej przez folder współdzielony hipernadzorcy albo przez `scp` z maszyny, która już ma pliki (wszystkie są w tej samej sieci `labnet`, np. z Kali: `scp -r lab/server student@10.10.10.30:~/`).

## 3. Serwer (10.10.10.30)

```bash
# Docker (z repozytorium Ubuntu - wystarczy do laboratorium)
sudo apt update && sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER && newgrp docker

cd ~/server
sh certs/gen-certs.sh
docker compose up -d --build        # pierwsza budowa trwa kilka minut (kompilacja OpenSSL 1.0.2u)
docker compose ps
```

**Weryfikacja (na serwerze):**

```bash
curl -s http://localhost:5000/ | head
curl -sk https://localhost/                         # oczekiwane: TLSv1.3 / TLS_AES_...
docker compose exec legacy-tls /opt/openssl-legacy/bin/openssl s_client -connect localhost:4433 -tls1 -cipher RC4-SHA </dev/null 2>/dev/null | grep "Cipher is"
                                                    # oczekiwane: Cipher is RC4-SHA
```

Usługi:

| Port | Usługa | Przeznaczenie |
|---|---|---|
| 5000/tcp | aplikacja Flask (HTTP) | ataki CBC i rozszerzenia długości skrótu |
| 443/tcp | nginx, TLS 1.2/1.3, AEAD | punkt odniesienia: downgrade ma się nie udać |
| 4433/tcp | OpenSSL 1.0.2u | przestarzały serwer: TLS 1.0, CBC, RC4; obsługuje TLS_FALLBACK_SCSV |

**Aplikacja (port 5000):**

| Endpoint | Mechanizm |
|---|---|
| `/login?user=NAZWA`, `/profile` | ciasteczko AES-128-CBC bez MAC, format `user=NAZWA;admin=0;uid=1001` |
| `/secure/login`, `/secure/profile` | ciasteczko AES-128-GCM |
| `/api/sample`, `/api/transfer?msg=..&sig=..` | podpis SHA-256(sekret ∥ msg), sekret 16 B |
| `/api/secure/sample`, `/api/secure/transfer` | podpis HMAC-SHA-256 |

Klucze i sekret są losowane przy każdym starcie kontenera (`docker compose restart webapp`).

## 4. Klient (10.10.10.20)

```bash
sudo apt update && sudo apt install -y python3
cd ~/client
sudo sh build-legacy-openssl.sh        # kilka minut; instaluje do /opt/openssl-legacy, nie rusza systemowego OpenSSL
python3 fallback_client.py             # oczekiwane: próba 1 OK -> TLSv1.2, ECDHE-RSA-AES128-GCM-SHA256
python3 fallback_client.py --scsv      # to samo, ale próby zapasowe wysyłają TLS_FALLBACK_SCSV
```

Bez atakującego pierwsza próba zawsze się udaje. Kolejne próby (TLS 1.0 + CBC, TLS 1.0 + RC4) uruchamiają się dopiero wtedy, gdy ktoś zerwie pierwsze połączenie, i to jest temat demonstracji downgrade w rozdziale 4. Z opcją `--scsv` serwer odrzuci próbę zapasową alertem `inappropriate_fallback`.

Do generowania ruchu w tle (np. podczas nagrywania pcap): `python3 fallback_client.py --loop 20 --interval 5`.

## 5. Czujnik IDS (10.10.10.40)

```bash
cd ~/sensor
sudo bash install-snort3.sh            # 15-40 min; najlepiej z 4 GB RAM i 2+ vCPU
sudo mkdir -p /usr/local/etc/rules
sudo cp local.rules /usr/local/etc/rules/
sudo cp lab.lua /usr/local/etc/snort/
```

W `lab.lua` uzupełnij adresy MAC klienta i serwera (`ip link` na tych maszynach, karta labnet).

```bash
# test konfiguracji
sudo snort -c /usr/local/etc/snort/snort.lua --tweaks lab -T

# nasłuch na karcie labnet (włącz tryb nasłuchu na interfejsie)
sudo ip link set enp0s3 promisc on
sudo snort -c /usr/local/etc/snort/snort.lua --tweaks lab -i enp0s3 -A alert_fast -k none
```

Sprawdzenie: z klienta `curl http://10.10.10.30:5000/`. Snort powinien wypisać alert `LAB test - ruch HTTP do aplikacji` (sid 1000001). Jeśli alertu nie ma, czujnik nie widzi ruchu między innymi maszynami: wróć do ustawień trybu nasłuchu w punkcie 1.

**Nagrywanie ruchu do późniejszej analizy:**

```bash
sudo tcpdump -i enp0s3 -w ~/pcap/$(date +%F_%H%M)_opis.pcap
sudo snort -c /usr/local/etc/snort/snort.lua --tweaks lab -r plik.pcap -A alert_fast -k none
```

## 6. Atakujący (10.10.10.10)

Kali ma potrzebne narzędzia (Ettercap, Bettercap, Wireshark, Scapy). Dodatkowo:

```bash
sudo apt update && sudo apt install -y python3-pycryptodome python3-requests
```

Skrypty ataków przygotujemy w kolejnym etapie (rozdział 4).

## 7. Migawki (snapshoty)

Po skonfigurowaniu i sprawdzeniu wszystkiego:

1. Odłącz kartę NAT na wszystkich maszynach.
2. Wyłącz maszyny i zrób migawkę każdej z nazwą `baseline`.

Przed każdym eksperymentem przywracasz `baseline`. Warto to opisać w metodyce: powtarzalność pomiarów wynika z identycznego stanu początkowego.

## 8. Host z GPU (badania wydajności)

Hashcat uruchamiamy bezpośrednio na hoście, bez maszyn wirtualnych.

1. Zainstaluj najnowszy sterownik NVIDIA i Hashcat z [hashcat.net](https://hashcat.net/hashcat/).
2. Zapisz wersje do opisu środowiska: `nvidia-smi`, `hashcat --version`, `hashcat -I`.
3. Pierwszy pomiar kontrolny: `hashcat -b -m 0` (MD5).
4. Sprawdź obsługę formatów:
   ```
   hashcat --help | findstr /i "7-Zip VeraCrypt KeePass"     (Windows)
   hashcat --help | grep -iE "7-Zip|VeraCrypt|KeePass"         (Linux)
   ```
   Dla KeePass sprawdź, czy wersja obsługuje KDBX4 z Argon2, a nie tylko AES-KDF.
5. Pliki testowe (ze znanymi hasłami) utworzymy w etapie pomiarów: 7-Zip z AES-256, VeraCrypt z kilkoma wartościami PIM, KeePassXC KDBX4 z AES-KDF oraz z Argon2 o różnych rozmiarach pamięci.

## Stan sprawdzenia pakietu

- Aplikacja Flask: przetestowana. Wariant CBC daje się zmodyfikować do `admin=1`, wariant GCM odrzuca modyfikację (403). Wariant SHA-256 przyjmuje zlecenie rozszerzone o `&amount=10000`, wariant HMAC je odrzuca.
- OpenSSL 1.0.2u: kompiluje się na GCC 13 (Ubuntu 24.04), obsługuje RC4.
- Klient fallback: przetestowany z serwerem 1.0.2u. Bez SCSV serwer przyjmuje TLS 1.0 z RC4, z SCSV odrzuca próbę zapasową.
- Konfiguracja Docker Compose i Snort 3: składnia sprawdzona, ale nieuruchomiona w tym środowisku. Ewentualne błędy przy instalacji wklej do rozmowy.
