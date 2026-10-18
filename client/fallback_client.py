#!/usr/bin/env python3
"""
Klient TLS z niebezpiecznym mechanizmem ponawiania połączenia (fallback).

Odtwarza zachowanie dawnych przeglądarek: gdy połączenie z najlepszą konfiguracją
się nie uda, klient ponawia próbę ze starszą wersją protokołu i słabszym szyfrem.
Do zestawiania połączeń używa OpenSSL 1.0.2u z /opt/openssl-legacy
(build-legacy-openssl.sh), bo współczesny OpenSSL nie obsługuje RC4.

Użycie:
  python3 fallback_client.py                      # serwer 10.10.10.30:4433, bez SCSV
  python3 fallback_client.py --scsv               # próby zapasowe z TLS_FALLBACK_SCSV (RFC 7507)
  python3 fallback_client.py --host 10.10.10.30 --port 4433 --loop 5
"""

import argparse
import re
import subprocess
import time

OPENSSL = "/opt/openssl-legacy/bin/openssl"

# Kolejne konfiguracje, od najlepszej do najsłabszej.
ATTEMPTS = [
    ("TLS 1.2 + AES-GCM (AEAD)", ["-tls1_2", "-cipher", "ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384"]),
    ("TLS 1.0 + AES-CBC",        ["-tls1",   "-cipher", "ECDHE-RSA-AES128-SHA:AES128-SHA"]),
    ("TLS 1.0 + RC4",            ["-tls1",   "-cipher", "RC4-SHA:RC4-MD5"]),
]


def try_connect(host, port, opts, scsv, timeout):
    cmd = [OPENSSL, "s_client", "-connect", f"{host}:{port}"] + opts
    if scsv:
        cmd.append("-fallback_scsv")
    try:
        out = subprocess.run(cmd, input=b"\n", capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "przekroczono czas oczekiwania"
    text = (out.stdout + out.stderr).decode(errors="replace")
    m = re.search(r"Cipher is (\S+)", text)
    proto = re.search(r"Protocol\s*:\s*(\S+)", text)
    if m and m.group(1) != "(NONE)":
        return (proto.group(1) if proto else "?", m.group(1)), None
    if "inappropriate fallback" in text:
        return None, "serwer odrzucił próbę zapasową (inappropriate_fallback)"
    err = re.search(r"(alert [a-z ]+|Connection reset|Connection refused|wrong version number|handshake failure)", text)
    return None, err.group(1) if err else "nieudany handshake"


def run_once(args):
    for i, (label, opts) in enumerate(ATTEMPTS):
        use_scsv = args.scsv and i > 0           # SCSV dodaje się tylko w próbach zapasowych
        print(f"  próba {i + 1}: {label}{' [SCSV]' if use_scsv else ''} ... ", end="", flush=True)
        result, err = try_connect(args.host, args.port, opts, use_scsv, args.timeout)
        if result:
            print(f"OK -> {result[0]}, {result[1]}")
            return result
        print(f"błąd: {err}")
    print("  wszystkie próby nieudane")
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="10.10.10.30")
    p.add_argument("--port", type=int, default=4433)
    p.add_argument("--scsv", action="store_true", help="wysyłaj TLS_FALLBACK_SCSV w próbach zapasowych")
    p.add_argument("--loop", type=int, default=1, help="liczba połączeń (np. do generowania ruchu)")
    p.add_argument("--interval", type=float, default=3.0)
    p.add_argument("--timeout", type=float, default=8.0)
    args = p.parse_args()

    for n in range(args.loop):
        print(f"[{time.strftime('%H:%M:%S')}] połączenie {n + 1}/{args.loop} z {args.host}:{args.port}")
        run_once(args)
        if n + 1 < args.loop:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
