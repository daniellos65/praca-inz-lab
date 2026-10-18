"""
Aplikacja testowa do laboratorium pracy inżynierskiej.

UWAGA: aplikacja jest CELOWO PODATNA. Uruchamiać wyłącznie w izolowanej sieci laboratoryjnej.

Zawiera dwie pary mechanizmów (wariant podatny / wariant poprawiony):
  1. Ciasteczko sesyjne:
       /login, /profile                -> AES-128-CBC bez MAC (podatne na modyfikację bitów)
       /secure/login, /secure/profile  -> AES-128-GCM (AEAD, modyfikacja wykrywana)
  2. Podpisywanie żądań API:
       /api/sample, /api/transfer                -> SHA-256(sekret || wiadomość) (podatne na rozszerzenie długości)
       /api/secure/sample, /api/secure/transfer  -> HMAC-SHA-256(sekret, wiadomość)

Klucze i sekret są losowane przy każdym starcie aplikacji.
"""

import base64
import hashlib
import hmac
import os
from urllib.parse import quote_from_bytes, unquote_to_bytes

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad
from flask import Flask, jsonify, make_response, request

app = Flask(__name__)

KEY_CBC = get_random_bytes(16)
KEY_GCM = get_random_bytes(16)
# Długość sekretu jest nieznana atakującemu (domyślnie 16 bajtów).
API_SECRET = get_random_bytes(int(os.environ.get("API_SECRET_LEN", "16")))

SAMPLE_ORDER = b"from=student&to=shop&amount=10"


# ---------------------------------------------------------------------------
# Wspólne funkcje pomocnicze
# ---------------------------------------------------------------------------

def parse_pairs(data: bytes, sep: bytes) -> dict:
    """Parsuje ciąg 'klucz=wartość' rozdzielony separatorem. Późniejsze wystąpienie klucza wygrywa."""
    result = {}
    for part in data.split(sep):
        if b"=" in part:
            k, v = part.split(b"=", 1)
            result[k.decode("latin-1")] = v.decode("latin-1")
    return result


def session_plaintext(username: str) -> bytes:
    return f"user={username};admin=0;uid=1001".encode()


def get_raw_query_param(name: str) -> bytes | None:
    """Zwraca surowe bajty parametru z query stringu (bez dekodowania do str)."""
    prefix = name.encode() + b"="
    for part in request.query_string.split(b"&"):
        if part.startswith(prefix):
            return unquote_to_bytes(part[len(prefix):])
    return None


# ---------------------------------------------------------------------------
# Strona główna
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return jsonify({
        "info": "Aplikacja laboratoryjna (celowo podatna)",
        "endpoints": {
            "GET /login?user=NAZWA": "ustawia ciasteczko AES-CBC bez MAC",
            "GET /profile": "odczytuje ciasteczko AES-CBC",
            "GET /secure/login?user=NAZWA": "ustawia ciasteczko AES-GCM",
            "GET /secure/profile": "odczytuje ciasteczko AES-GCM",
            "GET /api/sample": "przykładowe zlecenie podpisane SHA-256(sekret||msg)",
            "GET /api/transfer?msg=...&sig=...": "weryfikuje SHA-256(sekret||msg)",
            "GET /api/secure/sample": "przykładowe zlecenie podpisane HMAC-SHA-256",
            "GET /api/secure/transfer?msg=...&sig=...": "weryfikuje HMAC-SHA-256",
        },
    })


# ---------------------------------------------------------------------------
# 1a. Ciasteczko AES-CBC bez MAC (podatne)
# ---------------------------------------------------------------------------

@app.get("/login")
def login_cbc():
    username = request.args.get("user", "student")
    if ";" in username or "=" in username:
        return jsonify({"error": "niedozwolone znaki w nazwie użytkownika"}), 400
    iv = get_random_bytes(16)
    ct = AES.new(KEY_CBC, AES.MODE_CBC, iv).encrypt(pad(session_plaintext(username), 16))
    resp = make_response(jsonify({"status": "zalogowano", "mode": "AES-CBC bez MAC"}))
    resp.set_cookie("session", base64.urlsafe_b64encode(iv + ct).decode())
    return resp


@app.get("/profile")
def profile_cbc():
    token = request.cookies.get("session")
    if not token:
        return jsonify({"error": "brak ciasteczka"}), 401
    try:
        raw = base64.urlsafe_b64decode(token)
        iv, ct = raw[:16], raw[16:]
        pt = unpad(AES.new(KEY_CBC, AES.MODE_CBC, iv).decrypt(ct), 16)
    except Exception:
        # Jednolity komunikat błędu (bez rozróżniania błędu dopełnienia).
        return jsonify({"error": "nieprawidłowe ciasteczko"}), 400
    fields = parse_pairs(pt, b";")
    return jsonify({
        "mode": "AES-CBC bez MAC",
        "fields": fields,
        "admin_panel": fields.get("admin") == "1",
    })


# ---------------------------------------------------------------------------
# 1b. Ciasteczko AES-GCM (poprawione)
# ---------------------------------------------------------------------------

@app.get("/secure/login")
def login_gcm():
    username = request.args.get("user", "student")
    if ";" in username or "=" in username:
        return jsonify({"error": "niedozwolone znaki w nazwie użytkownika"}), 400
    nonce = get_random_bytes(12)
    ct, tag = AES.new(KEY_GCM, AES.MODE_GCM, nonce=nonce).encrypt_and_digest(session_plaintext(username))
    resp = make_response(jsonify({"status": "zalogowano", "mode": "AES-GCM"}))
    resp.set_cookie("secure_session", base64.urlsafe_b64encode(nonce + ct + tag).decode())
    return resp


@app.get("/secure/profile")
def profile_gcm():
    token = request.cookies.get("secure_session")
    if not token:
        return jsonify({"error": "brak ciasteczka"}), 401
    try:
        raw = base64.urlsafe_b64decode(token)
        nonce, ct, tag = raw[:12], raw[12:-16], raw[-16:]
        pt = AES.new(KEY_GCM, AES.MODE_GCM, nonce=nonce).decrypt_and_verify(ct, tag)
    except Exception:
        return jsonify({"error": "naruszona integralność ciasteczka"}), 403
    fields = parse_pairs(pt, b";")
    return jsonify({
        "mode": "AES-GCM",
        "fields": fields,
        "admin_panel": fields.get("admin") == "1",
    })


# ---------------------------------------------------------------------------
# 2a. API podpisywane SHA-256(sekret || wiadomość) (podatne)
# ---------------------------------------------------------------------------

def naive_sig(msg: bytes) -> str:
    return hashlib.sha256(API_SECRET + msg).hexdigest()


@app.get("/api/sample")
def api_sample():
    return jsonify({
        "msg": SAMPLE_ORDER.decode(),
        "sig": naive_sig(SAMPLE_ORDER),
        "example": f"/api/transfer?msg={quote_from_bytes(SAMPLE_ORDER, safe='')}&sig={naive_sig(SAMPLE_ORDER)}",
    })


@app.get("/api/transfer")
def api_transfer():
    msg = get_raw_query_param("msg")
    sig = request.args.get("sig", "")
    if msg is None or not hmac.compare_digest(naive_sig(msg), sig):
        return jsonify({"error": "nieprawidłowy podpis"}), 403
    order = parse_pairs(msg, b"&")
    return jsonify({"status": "zlecenie przyjęte", "mode": "SHA-256(sekret||msg)", "order": order})


# ---------------------------------------------------------------------------
# 2b. API podpisywane HMAC-SHA-256 (poprawione)
# ---------------------------------------------------------------------------

def hmac_sig(msg: bytes) -> str:
    return hmac.new(API_SECRET, msg, hashlib.sha256).hexdigest()


@app.get("/api/secure/sample")
def api_secure_sample():
    return jsonify({
        "msg": SAMPLE_ORDER.decode(),
        "sig": hmac_sig(SAMPLE_ORDER),
        "example": f"/api/secure/transfer?msg={quote_from_bytes(SAMPLE_ORDER, safe='')}&sig={hmac_sig(SAMPLE_ORDER)}",
    })


@app.get("/api/secure/transfer")
def api_secure_transfer():
    msg = get_raw_query_param("msg")
    sig = request.args.get("sig", "")
    if msg is None or not hmac.compare_digest(hmac_sig(msg), sig):
        return jsonify({"error": "nieprawidłowy podpis"}), 403
    order = parse_pairs(msg, b"&")
    return jsonify({"status": "zlecenie przyjęte", "mode": "HMAC-SHA-256", "order": order})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
