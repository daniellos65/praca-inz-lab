#!/bin/bash
# Instalacja Snort 3 ze źródeł na Ubuntu 24.04 (maszyna-czujnik 10.10.10.40).
# Uruchomić: sudo bash install-snort3.sh   (wymaga dostępu do internetu, np. przez tymczasową kartę NAT)
# Kompilacja trwa ok. 15-40 minut w zależności od liczby rdzeni VM.
set -e
apt-get update
apt-get install -y build-essential cmake pkg-config git autoconf automake libtool flex bison \
  libpcap-dev libpcre2-dev libpcre3-dev libdumbnet-dev libluajit-5.1-dev libssl-dev zlib1g-dev \
  libhwloc-dev liblzma-dev uuid-dev libunwind-dev libsqlite3-dev tcpdump

SRC=/opt/src && mkdir -p $SRC && cd $SRC

# libdaq - warstwa akwizycji pakietów wymagana przez Snort 3
[ -d libdaq ] || git clone --depth 1 https://github.com/snort3/libdaq.git
cd libdaq && ./bootstrap && ./configure && make -j"$(nproc)" && make install && ldconfig && cd ..

# Snort 3
[ -d snort3 ] || git clone --depth 1 https://github.com/snort3/snort3.git
cd snort3 && ./configure_cmake.sh --prefix=/usr/local
cd build && make -j"$(nproc)" && make install && ldconfig

/usr/local/bin/snort -V
echo "Gotowe. Wersję z 'snort -V' zapisz do opisu środowiska."
