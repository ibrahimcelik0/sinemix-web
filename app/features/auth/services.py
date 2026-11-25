"""
Tamamen Şifresiz (Passwordless) 6 Haneli E-Posta OTP Kimlik Doğrulama & Kayıt Servisi.

Özellikler:
1. İki Sekmeli Modern OTP Akışı (**Oturum Aç** / **Kayıt Ol**):
   - **Oturum Aç (`mode="login"`):** Yalnızca kayıtlı E-Posta Adresi girilir; `data/users.json` içinde
     kayıtlıysa 6 haneli tek kullanımlık giriş kodu gönderilir.
   - **Kayıt Ol (`mode="register"`):** İsim (`first_name`), Soyisim (`last_name`), Kullanıcı Adı (`username`)
     ve E-Posta Adresi (`email`) alınır.
   - **Büyük/Küçük Harf Duyarsız (Case-Insensitive) Tekillik Kontrolü:**
     - Kullanıcı adı alınmışsa kod gönderilmez:
       *"Bu kullanıcı adı zaten kullanılıyor, lütfen başka bir kullanıcı adı seçin."*
     - E-posta adresi zaten kayıtlıysa kod gönderilmez:
       *"Bu e-posta adresi zaten kayıtlı, Oturum Aç sekmesini kullanın."*
2. Güvenlik Kuralları:
   - Python `secrets` modülüyle kriptografik 6 haneli OTP üretimi.
   - 5 dakika (300 saniye) geçerlilik süresi ve doğrulandığı an tek kullanımlık silinme.
   - Maksimum 3 hatalı deneme (Brute-Force) koruması; 3. hatada kod derhal iptal edilir.
   - Aynı e-postaya art arda kod gönderiminde 60 saniye bekleme süresi (Rate-Limit).
3. Gerçek E-Posta Gönderimi (`smtplib`):
   - `.env` içindeki `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` ile koyu/altın SineMix HTML e-postası gönderir;
     SMTP ayarlı değilse çökmeden kodu terminal konsoluna da yazdırır.
"""

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps
import math
import os
import secrets
import smtplib
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from flask import flash, jsonify, redirect, request, session, url_for

from app.features.auth.repository import UserRepository, normalize_username

OTP_EXPIRY_SECONDS = 300       # 5 dakika geçerlilik süresi
OTP_MAX_ATTEMPTS = 3           # En fazla 3 hatalı deneme hakkı
OTP_COOLDOWN_SECONDS = 60      # Aynı e-postaya yeniden kod gönderimi için 60 saniye bekleme süresi

# Bellek içi aktif OTP doğrulama kayıtları (email -> challenge dict)
_ACTIVE_OTP_STORE: Dict[str, Dict[str, Any]] = {}


def generate_six_digit_otp() -> str:
    """Python `secrets` modülüyle kriptografik olarak rastgele 6 haneli (100000-999999) OTP kodu üretir."""
    return f"{secrets.randbelow(900000) + 100000:06d}"


def clear_all_otp_challenges() -> None:
    """Test ve bakım amaçlı aktif OTP belleğini sıfırlar."""
    _ACTIVE_OTP_STORE.clear()


def get_active_otp_challenge(email: str) -> Optional[Dict[str, Any]]:
    """Belirtilen e-posta için aktif (süresi dolmamış) OTP kaydını döndürür."""
    clean_email = (email or "").strip().lower()
    challenge = _ACTIVE_OTP_STORE.get(clean_email)
    if not challenge:
        return None
    if time.time() > float(challenge.get("expires_at", 0)):
        _ACTIVE_OTP_STORE.pop(clean_email, None)
        return None
    return challenge


def get_otp_cooldown_remaining(email: str) -> int:
    """Aynı e-posta adresine yeni kod göndermeden önce beklenmesi gereken saniyeyi (0-60) döndürür."""
    clean_email = (email or "").strip().lower()
    challenge = _ACTIVE_OTP_STORE.get(clean_email)
    if not challenge:
        return 0
    elapsed = time.time() - float(challenge.get("last_sent_at", 0))
    if elapsed >= OTP_COOLDOWN_SECONDS:
        return 0
    return max(1, int(math.ceil(OTP_COOLDOWN_SECONDS - elapsed)))


def get_current_user() -> Optional[Dict[str, Any]]:
    """Aktif Flask oturumundaki (session) şifresiz kullanıcı bilgilerini döndürür."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = UserRepository.get_by_id(str(user_id))
    if not user and session.get("email"):
        user = UserRepository.get_by_email(str(session.get("email")))
        if user:
            session["user_id"] = str(user["id"])
    if not user:
        session.clear()
        return None
    first_name = user.get("first_name") or ""
    last_name = user.get("last_name") or ""
    full_name = user.get("full_name") or f"{first_name} {last_name}".strip() or user.get("username") or "SineMix Üyesi"
    username = user.get("username") or "kullanici"
    return {
        "id": user["id"],
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "username": username,
        "email": user["email"],
        "role": user.get("role", "SineMix Üyesi"),
        "bio": user.get("bio", ""),
        "created_at": user.get("created_at", ""),
        "last_login_at": user.get("last_login_at", user.get("created_at", "")),
        "avatar_initial": user.get("avatar_initial") or (full_name[0].upper() if full_name else "S"),
    }


def login_user_session(user: Dict[str, Any]) -> None:
    """Kullanıcıyı Flask session içine kaydeder."""
    session["user_id"] = str(user["id"])
    session["username"] = user["username"]
    session["full_name"] = user.get("full_name") or user["username"]
    session["email"] = user["email"]
    session.permanent = True


def logout_user_session() -> None:
    """Kullanıcı oturumunu sonlandırır."""
    session.clear()


def _build_otp_email_html(recipient_name: str, otp_code: str, is_new_user: bool) -> str:
    """SineMix koyu & altın (#facc15) temalı tek kullanımlık 6 haneli doğrulama kodu HTML e-posta şablonu."""
    greeting = f"Merhaba {recipient_name}," if recipient_name else "Merhaba,"
    action_title = (
        "SineMix Hesabınızı Doğrulayın ve Kaydınızı Tamamlayın"
        if is_new_user
        else "SineMix Şifresiz Giriş Doğrulama Kodunuz"
    )
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <title>{action_title}</title>
</head>
<body style="margin:0;padding:28px;background-color:#090b12;font-family:'Segoe UI',Arial,sans-serif;color:#f8fafc;">
    <div style="max-width:520px;margin:0 auto;padding:34px 30px;border-radius:22px;background:#121522;border:1px solid rgba(250,204,21,0.35);">
        <div style="text-align:center;margin-bottom:22px;">
            <span style="display:inline-block;padding:6px 14px;border-radius:999px;background:rgba(250,204,21,0.16);color:#facc15;font-weight:700;font-size:13px;">
                🎬 SineMix Passwordless OTP
            </span>
            <h2 style="margin:14px 0 6px;color:#ffffff;font-size:22px;">{action_title}</h2>
            <p style="margin:0;color:#94a3b8;font-size:14px;">{greeting}</p>
        </div>
        <p style="color:#cbd5e1;font-size:14px;line-height:1.6;text-align:center;margin-bottom:22px;">
            SineMix hesabınıza şifresiz giriş yapmak için aşağıdaki <strong>6 haneli tek kullanımlık doğrulama kodunu</strong> ekrandaki 6 kutucuklu alana girin:
        </p>
        <div style="text-align:center;margin:24px 0;padding:20px;border-radius:16px;background:#090b12;border:2px solid #facc15;">
            <span style="font-size:34px;font-weight:800;letter-spacing:10px;color:#facc15;font-family:'Courier New',monospace;">
                {otp_code}
            </span>
        </div>
        <p style="color:#94a3b8;font-size:12.5px;line-height:1.6;text-align:center;margin:0;">
            ⏱️ Bu kod güvenlik nedeniyle yalnızca <strong>5 dakika</strong> geçerlidir ve tek kullanımlıktır.<br>
            🔒 En fazla 3 hatalı deneme hakkı bulunur.
        </p>
    </div>
</body>
</html>"""


def send_otp_email(
    recipient_email: str,
    otp_code: str,
    recipient_name: str = "",
    is_new_user: bool = False,
) -> Tuple[bool, str]:
    """
    6 haneli OTP doğrulama kodunu `smtplib` (STARTTLS) üzerinden gerçek e-posta olarak gönderir.
    `.env` ayarlı değilse veya yerel ortamda bağlantı kurulamazsa çökmeden kodu terminal konsoluna yazdırır.
    """
    from app.config import refresh_dotenv_variables
    refresh_dotenv_variables()

    smtp_host = (os.environ.get("SMTP_HOST", "smtp.gmail.com") or "smtp.gmail.com").strip()
    smtp_port_raw = (os.environ.get("SMTP_PORT", "587") or "587").strip()
    try:
        smtp_port = int(smtp_port_raw)
    except ValueError:
        smtp_port = 587

    smtp_user = (os.environ.get("SMTP_USER", "") or "").strip()
    smtp_pass = (os.environ.get("SMTP_PASS", "") or "").strip()

    if smtp_user and smtp_pass:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"SineMix Doğrulama Kodunuz: {otp_code}"
            msg["From"] = f"SineMix <{smtp_user}>"
            msg["To"] = recipient_email

            text_body = (
                f"Merhaba {recipient_name or 'SineMix Üyesi'},\n\n"
                f"SineMix 6 haneli tek kullanımlık doğrulama kodunuz: {otp_code}\n"
                f"Bu kod 5 dakika boyunca geçerlidir.\n"
            )
            html_body = _build_otp_email_html(recipient_name, otp_code, is_new_user)

            msg.attach(MIMEText(text_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, [recipient_email], msg.as_string())

            return True, "smtp"
        except Exception as exc:
            print(
                f"\n[SineMix SMTP Uyarısı] E-posta sunucusuna bağlanılamadı ({exc}). "
                f"Geliştirici konsol yedek modu devreye alındı."
            )

    print(
        "\n============================================================\n"
        f" 🎬 [SineMix Şifresiz OTP Doğrulama Kodu]\n"
        f" ✉️  Alıcı E-Posta : {recipient_email}\n"
        f" 👤 Kullanıcı     : {recipient_name or 'SineMix Üyesi'} ({'Yeni Kayıt' if is_new_user else 'Kayıtlı Üye'})\n"
        f" 🔑 6 Haneli Kod  : {otp_code}  (5 Dakika Geçerli • Tek Kullanımlık)\n"
        "============================================================\n",
        flush=True,
    )
    return True, "console"


def request_email_otp(
    email: str,
    mode: str = "auto",
    first_name: str = "",
    last_name: str = "",
    full_name: str = "",
    username: str = "",
) -> Dict[str, Any]:
    """
    Oturum Aç (`mode="login"`) ve Kayıt Ol (`mode="register"`) sekmeleri için OTP gönderimini yönetir.

    - `mode == "register"`:
      1. `username` için `data/users.json` içinde case-insensitive benzersizlik kontrolü yapar.
         Alınmışsa kod göndermez ve *"Bu kullanıcı adı zaten kullanılıyor, lütfen başka bir kullanıcı adı seçin."* döner.
      2. `email` için `data/users.json` içinde case-insensitive kontrol yapar.
         Kayıtlıysa kod göndermez ve *"Bu e-posta adresi zaten kayıtlı, Oturum Aç sekmesini kullanın."* döner.
      3. İsim (`first_name`), Soyisim (`last_name`) ve temizlenmiş Kullanıcı Adı (`username`) ile 6 haneli OTP üretip gönderir.

    - `mode == "login"`:
      1. `email` adresinin `data/users.json` içinde kayıtlı olup olmadığını kontrol eder.
      2. Kayıtlı değilse *"Bu e-posta adresiyle kayıtlı bir hesap bulunamadı. Lütfen Kayıt Ol sekmesini kullanın."* uyarısı döner.
      3. Kayıtlıysa 60 saniye rate-limit kontrolüyle 6 haneli giriş kodunu gönderir.
    """
    clean_email = (email or "").strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        return {
            "ok": False,
            "status": "invalid_email",
            "message": "Lütfen geçerli bir e-posta adresi girin.",
        }

    clean_mode = (mode or "auto").strip().lower()
    existing_user_by_email = UserRepository.get_by_email(clean_email)

    # Kullanıcı adının temizlenmiş küçük harf hali
    clean_username = normalize_username(username)

    # İsim ve soyisim ayrıştırma
    clean_first = (first_name or "").strip()
    clean_last = (last_name or "").strip()
    clean_full = (full_name or "").strip()
    if (not clean_first and not clean_last) and clean_full:
        parts = clean_full.split()
        clean_first = " ".join(parts[:-1]) if len(parts) > 1 else parts[0]
        clean_last = parts[-1] if len(parts) > 1 else ""

    # Eğer aynı yeni kullanıcı için daha önce bekleyen kayıt oluşturulmuşsa ve "Tekrar Kod Gönder" deniyorsa:
    prev_challenge = _ACTIVE_OTP_STORE.get(clean_email)
    if prev_challenge and prev_challenge.get("pending_profile"):
        pend = prev_challenge["pending_profile"]
        if not clean_first:
            clean_first = pend.get("first_name", "")
        if not clean_last:
            clean_last = pend.get("last_name", "")
        if not clean_username:
            clean_username = pend.get("username", "")

    # =========================================================================
    # A) KAYIT OL SEKMESİ (mode == "register")
    # =========================================================================
    if clean_mode == "register":
        # 1. Kullanıcı adı benzersizlik kontrolü (case-insensitive)
        if clean_username and UserRepository.get_by_username(clean_username):
            return {
                "ok": False,
                "status": "username_taken",
                "is_new_user": True,
                "email": clean_email,
                "username": clean_username,
                "message": "Bu kullanıcı adı zaten kullanılıyor, lütfen başka bir kullanıcı adı seçin.",
            }

        # 2. E-posta benzersizlik kontrolü (case-insensitive)
        if existing_user_by_email is not None:
            return {
                "ok": False,
                "status": "email_already_registered",
                "is_new_user": False,
                "email": clean_email,
                "message": "Bu e-posta adresi zaten kayıtlı, Oturum Aç sekmesini kullanın.",
            }

        if len(clean_first) < 2:
            return {
                "ok": False,
                "status": "invalid_registration_fields",
                "is_new_user": True,
                "email": clean_email,
                "message": "Lütfen geçerli bir İsim girin (en az 2 karakter).",
            }

        if len(clean_last) < 2:
            return {
                "ok": False,
                "status": "invalid_registration_fields",
                "is_new_user": True,
                "email": clean_email,
                "message": "Lütfen geçerli bir Soyisim girin (en az 2 karakter).",
            }

        if len(clean_username) < 3:
            return {
                "ok": False,
                "status": "invalid_registration_fields",
                "is_new_user": True,
                "email": clean_email,
                "message": "Kullanıcı adı en az 3 karakter olmalı ve yalnızca küçük harf/rakam içermelidir.",
            }

        cooldown_rem = get_otp_cooldown_remaining(clean_email)
        if cooldown_rem > 0:
            return {
                "ok": False,
                "status": "cooldown",
                "is_new_user": True,
                "email": clean_email,
                "cooldown_remaining": cooldown_rem,
                "message": f"Aynı e-posta adresine yeni kod göndermek için lütfen {cooldown_rem} saniye bekleyin.",
            }

        computed_full = f"{clean_first} {clean_last}".strip()
        now = time.time()
        otp_code = generate_six_digit_otp()
        _ACTIVE_OTP_STORE[clean_email] = {
            "email": clean_email,
            "code": otp_code,
            "created_at": now,
            "last_sent_at": now,
            "expires_at": now + OTP_EXPIRY_SECONDS,
            "attempts": 0,
            "is_new_user": True,
            "pending_profile": {
                "first_name": clean_first,
                "last_name": clean_last,
                "full_name": computed_full,
                "username": clean_username,
            },
        }

        _, delivery_mode = send_otp_email(
            recipient_email=clean_email,
            otp_code=otp_code,
            recipient_name=computed_full,
            is_new_user=True,
        )

        return {
            "ok": True,
            "status": "otp_sent",
            "is_new_user": True,
            "email": clean_email,
            "username": clean_username,
            "recipient_name": computed_full,
            "cooldown_seconds": OTP_COOLDOWN_SECONDS,
            "expires_in_seconds": OTP_EXPIRY_SECONDS,
            "max_attempts": OTP_MAX_ATTEMPTS,
            "delivery_mode": delivery_mode,
            "message": f"6 haneli doğrulama kodun {clean_email} adresine gönderildi. Kodu girdiğin an @{clean_username} hesabın kalıcı olarak oluşturulacak.",
        }

    # =========================================================================
    # B) OTURUM AÇ SEKMESİ (mode == "login")
    # =========================================================================
    if clean_mode == "login":
        if existing_user_by_email is None:
            return {
                "ok": False,
                "status": "email_not_registered",
                "is_new_user": True,
                "email": clean_email,
                "message": "Bu e-posta adresiyle kayıtlı bir hesap bulunamadı. Lütfen 'Kayıt Ol' sekmesinden yeni hesap oluşturun.",
            }

    # =========================================================================
    # C) KAYITLI KULLANICI GİRİŞ KODU GÖNDERİMİ (mode == "login" veya "auto")
    # =========================================================================
    if existing_user_by_email is not None:
        cooldown_rem = get_otp_cooldown_remaining(clean_email)
        if cooldown_rem > 0:
            return {
                "ok": False,
                "status": "cooldown",
                "is_new_user": False,
                "email": clean_email,
                "cooldown_remaining": cooldown_rem,
                "message": f"Aynı e-posta adresine yeni kod göndermek için lütfen {cooldown_rem} saniye bekleyin.",
            }

        now = time.time()
        otp_code = generate_six_digit_otp()
        _ACTIVE_OTP_STORE[clean_email] = {
            "email": clean_email,
            "code": otp_code,
            "created_at": now,
            "last_sent_at": now,
            "expires_at": now + OTP_EXPIRY_SECONDS,
            "attempts": 0,
            "is_new_user": False,
            "pending_profile": None,
        }

        recipient_name = (
            existing_user_by_email.get("full_name")
            or existing_user_by_email.get("first_name")
            or existing_user_by_email.get("username")
            or ""
        )
        _, delivery_mode = send_otp_email(
            recipient_email=clean_email,
            otp_code=otp_code,
            recipient_name=recipient_name,
            is_new_user=False,
        )

        return {
            "ok": True,
            "status": "otp_sent",
            "is_new_user": False,
            "email": clean_email,
            "recipient_name": recipient_name,
            "cooldown_seconds": OTP_COOLDOWN_SECONDS,
            "expires_in_seconds": OTP_EXPIRY_SECONDS,
            "max_attempts": OTP_MAX_ATTEMPTS,
            "delivery_mode": delivery_mode,
            "message": f"Tekrar hoş geldin {recipient_name}! 6 haneli tek kullanımlık giriş kodun {clean_email} adresine gönderildi.",
        }

    # =========================================================================
    # D) AUTO MODDA YENİ KULLANICI GERİ UYUMLULUK
    # =========================================================================
    if not clean_first or not clean_username:
        return {
            "ok": True,
            "status": "needs_registration_fields",
            "is_new_user": True,
            "email": clean_email,
            "message": "Bu e-posta adresiyle ilk kez giriş yapıyorsunuz. Hesabınızı oluşturmak için İsim, Soyisim ve Kullanıcı Adı bilgilerinizi tamamlayın.",
        }

    if UserRepository.get_by_username(clean_username):
        return {
            "ok": False,
            "status": "username_taken",
            "is_new_user": True,
            "email": clean_email,
            "username": clean_username,
            "message": "Bu kullanıcı adı zaten kullanılıyor, lütfen başka bir kullanıcı adı seçin.",
        }

    return request_email_otp(
        email=clean_email,
        mode="register",
        first_name=clean_first,
        last_name=clean_last or "Üye",
        username=clean_username,
    )


def verify_email_otp(
    email: str,
    code: str,
    guest_watchlist: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    6 haneli OTP kodunu doğrular:
    - 5 dakikalık süreyi kontrol eder.
    - Yanlış girişlerde deneme sayısını artırır; 3. hatalı denemede kodu tamamen iptal eder.
    - Doğru girişte kodu tek kullanımlık olarak derhal siler.
    - Yeni kullanıcıysa profilini `data/users.json` içine şifresiz olarak kaydeder; mevcut kullanıcıysa
      `last_login_at` alanını günceller.
    - Misafir modunda verilen geçici izleme/puan verileri varsa kullanıcının kalıcı
      `data/watchlists/<user_id>.json` dosyasına aktarır.
    """
    clean_email = (email or "").strip().lower()
    clean_code = "".join(ch for ch in (code or "").strip() if ch.isdigit())

    if not clean_email:
        return {
            "ok": False,
            "status": "missing_email",
            "message": "E-posta adresi bulunamadı. Lütfen baştan kod isteyin.",
        }

    challenge = _ACTIVE_OTP_STORE.get(clean_email)
    if not challenge:
        return {
            "ok": False,
            "status": "no_active_code",
            "message": "Bu e-posta için aktif bir doğrulama kodu bulunamadı veya kod iptal edildi. Lütfen yeni kod isteyin.",
        }

    now = time.time()
    if now > float(challenge.get("expires_at", 0)):
        _ACTIVE_OTP_STORE.pop(clean_email, None)
        return {
            "ok": False,
            "status": "expired",
            "message": "Doğrulama kodunuzun 5 dakikalık geçerlilik süresi doldu. Lütfen yeni bir kod isteyin.",
        }

    if len(clean_code) != 6:
        return {
            "ok": False,
            "status": "invalid_format",
            "attempts_remaining": max(0, OTP_MAX_ATTEMPTS - int(challenge.get("attempts", 0))),
            "message": "Lütfen e-postanıza gelen 6 haneli sayısal doğrulama kodunu eksiksiz girin.",
        }

    expected_code = str(challenge.get("code", ""))
    if not secrets.compare_digest(clean_code, expected_code):
        challenge["attempts"] = int(challenge.get("attempts", 0)) + 1
        attempts_used = challenge["attempts"]
        remaining = max(0, OTP_MAX_ATTEMPTS - attempts_used)

        if attempts_used >= OTP_MAX_ATTEMPTS:
            _ACTIVE_OTP_STORE.pop(clean_email, None)
            return {
                "ok": False,
                "status": "max_attempts_exceeded",
                "attempts_remaining": 0,
                "message": "3 kez hatalı kod girdiğiniz için güvenlik nedeniyle doğrulama kodunuz iptal edildi. Lütfen yeni bir kod isteyin.",
            }

        return {
            "ok": False,
            "status": "invalid_code",
            "attempts_remaining": remaining,
            "message": f"Girdiğiniz doğrulama kodu hatalı. Kalan deneme hakkınız: {remaining}.",
        }

    # Kod doğrulandı -> Tek kullanımlık olduğu için anında sil!
    _ACTIVE_OTP_STORE.pop(clean_email, None)

    user = UserRepository.get_by_email(clean_email)
    is_new_user = False

    if user is None:
        pending = challenge.get("pending_profile") or {}
        pending_first = (pending.get("first_name") or "").strip()
        pending_last = (pending.get("last_name") or "").strip()
        pending_full = (pending.get("full_name") or "").strip()
        pending_username = normalize_username(pending.get("username") or "")

        if not pending_username:
            pending_username = normalize_username(clean_email.split("@")[0][:16]) or "sinemasever"

        if UserRepository.get_by_username(pending_username):
            pending_username = f"{pending_username}_{secrets.randbelow(900) + 100}"

        user = UserRepository.create_user(
            username=pending_username,
            email=clean_email,
            first_name=pending_first,
            last_name=pending_last,
            full_name=pending_full,
        )
        is_new_user = True
    else:
        updated = UserRepository.update_last_login(user["id"])
        if updated:
            user = updated

    from app.features.watchlist.repository import WatchlistRepository
    WatchlistRepository.ensure_user_watchlist_file(user["id"])

    transferred_count = 0
    if isinstance(guest_watchlist, list) and len(guest_watchlist) > 0:
        valid_guest_records = [
            item for item in guest_watchlist
            if isinstance(item, dict) and item.get("tmdb_id")
        ]
        if valid_guest_records:
            merge_res = WatchlistRepository.bulk_upsert(
                records=valid_guest_records,
                skip_existing=True,
                user_id=user["id"],
            )
            transferred_count = int(merge_res.get("added_count", 0))

    login_user_session(user)

    display_name = user.get("full_name") or user.get("username")
    if is_new_user:
        welcome_msg = f"SineMix'e hoş geldin, {display_name} (@{user['username']})! Hesabın şifresiz olarak oluşturuldu."
    else:
        welcome_msg = f"Tekrar hoş geldin, {display_name}! Şifresiz oturumun açıldı."

    if transferred_count > 0:
        welcome_msg += f" Misafir modundaki {transferred_count} yapım kalıcı listene aktarıldı."

    return {
        "ok": True,
        "status": "verified",
        "is_new_user": is_new_user,
        "user": user,
        "transferred_count": transferred_count,
        "message": welcome_msg,
    }


def login_required(view_func: Callable) -> Callable:
    """
    Oturum açmamış (misafir) kullanıcıları şifresiz `/auth/login` sayfasına yönlendirir.
    """
    @wraps(view_func)
    def wrapped_view(*args: Any, **kwargs: Any) -> Any:
        user = get_current_user()
        if user is None:
            next_url = request.full_path if request.query_string else request.path
            login_target = url_for("auth.login", next=next_url)

            if request.path.startswith("/api/") or request.is_json:
                return jsonify({
                    "error": "login_required",
                    "message": "Kalıcı kayıt için lütfen e-posta kodunuzla oturum açın.",
                    "login_url": login_target,
                }), 401

            flash("İzleme listenize ve profilinize erişmek için lütfen e-posta doğrulama koduyla giriş yapın.", "warning")
            return redirect(login_target)
        return view_func(*args, **kwargs)

    return wrapped_view



def send_content_request_admin_email(request_record: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Kullanıcının gönderdiği Film / Dizi talebini (Kullanıcı Adı, E-Posta, Yapım Adı, Tür, Yıl, Not)
    `.env` içerisindeki `ADMIN_EMAIL` (veya `SMTP_USER`) adresine `smtplib` ile e-posta olarak gönderir.
    """
    from app.config import refresh_dotenv_variables
    refresh_dotenv_variables()

    smtp_host = (os.environ.get("SMTP_HOST", "smtp.gmail.com") or "smtp.gmail.com").strip()
    smtp_port_raw = (os.environ.get("SMTP_PORT", "587") or "587").strip()
    try:
        smtp_port = int(smtp_port_raw)
    except ValueError:
        smtp_port = 587

    smtp_user = (os.environ.get("SMTP_USER", "") or "").strip()
    smtp_pass = (os.environ.get("SMTP_PASS", "") or "").strip()
    admin_email = (os.environ.get("ADMIN_EMAIL", "") or smtp_user).strip()

    title = request_record.get("title", "Bilinmeyen Yapım")
    media_type = request_record.get("media_type", "Film")
    year = request_record.get("year") or "Belirtilmedi"
    note = request_record.get("note") or "Yok"
    requester_username = request_record.get("requester_username") or request_record.get("requested_by") or "misafir"
    requester_email = request_record.get("requester_email") or "Belirtilmedi"
    req_count = request_record.get("request_count", 1)
    created_at = request_record.get("created_at", "")

    if smtp_user and smtp_pass and admin_email:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[SineMix İçerik Talebi] {title} ({media_type}) - @{requester_username}"
            msg["From"] = f"SineMix İstek Kutusu <{smtp_user}>"
            msg["To"] = admin_email
            if "@" in requester_email:
                msg["Reply-To"] = requester_email

            text_body = (
                f"SineMix Yeni Film / Dizi Talebi\n"
                f"====================================\n"
                f"Yapım Adı      : {title}\n"
                f"Türü           : {media_type}\n"
                f"Çıkış Yılı     : {year}\n"
                f"Talep Eden     : @{requester_username}\n"
                f"Kullanıcı Mail : {requester_email}\n"
                f"Kısa Not       : {note}\n"
                f"Talep Sayısı   : {req_count}\n"
                f"Tarih          : {created_at}\n"
            )

            html_body = f"""<!DOCTYPE html>
<html lang="tr">
<head><meta charset="UTF-8"><title>SineMix İçerik Talebi</title></head>
<body style="margin:0;padding:26px;background-color:#090b12;font-family:'Segoe UI',Arial,sans-serif;color:#f8fafc;">
    <div style="max-width:540px;margin:0 auto;padding:30px;border-radius:20px;background:#121522;border:1px solid rgba(250,204,21,0.35);">
        <div style="margin-bottom:18px;">
            <span style="display:inline-block;padding:5px 12px;border-radius:999px;background:rgba(250,204,21,0.16);color:#facc15;font-weight:700;font-size:12px;">
                🎬 SineMix Film / Dizi İstek Kutusu
            </span>
            <h2 style="margin:12px 0 4px;color:#ffffff;font-size:21px;">Yeni İçerik Talebi: {title}</h2>
            <p style="margin:0;color:#94a3b8;font-size:13px;">Toplam Talep Sayısı: <strong style="color:#facc15;">{req_count}</strong></p>
        </div>
        <table style="width:100%;border-collapse:collapse;background:#090b12;border-radius:14px;overflow:hidden;border:1px solid rgba(255,255,255,0.08);">
            <tr>
                <td style="padding:11px 14px;color:#94a3b8;font-size:13px;border-bottom:1px solid rgba(255,255,255,0.06);">👤 Kullanıcı Adı</td>
                <td style="padding:11px 14px;color:#facc15;font-weight:700;font-size:14px;border-bottom:1px solid rgba(255,255,255,0.06);">@{requester_username}</td>
            </tr>
            <tr>
                <td style="padding:11px 14px;color:#94a3b8;font-size:13px;border-bottom:1px solid rgba(255,255,255,0.06);">✉️ Kullanıcı E-Posta</td>
                <td style="padding:11px 14px;color:#ffffff;font-weight:600;font-size:14px;border-bottom:1px solid rgba(255,255,255,0.06);">{requester_email}</td>
            </tr>
            <tr>
                <td style="padding:11px 14px;color:#94a3b8;font-size:13px;border-bottom:1px solid rgba(255,255,255,0.06);">🎬 Yapım Adı & Türü</td>
                <td style="padding:11px 14px;color:#ffffff;font-weight:700;font-size:14px;border-bottom:1px solid rgba(255,255,255,0.06);">{title} ({media_type})</td>
            </tr>
            <tr>
                <td style="padding:11px 14px;color:#94a3b8;font-size:13px;border-bottom:1px solid rgba(255,255,255,0.06);">📅 Çıkış Yılı</td>
                <td style="padding:11px 14px;color:#cbd5e1;font-size:13.5px;border-bottom:1px solid rgba(255,255,255,0.06);">{year}</td>
            </tr>
            <tr>
                <td style="padding:11px 14px;color:#94a3b8;font-size:13px;">📝 Kısa Not</td>
                <td style="padding:11px 14px;color:#cbd5e1;font-size:13.5px;">{note}</td>
            </tr>
        </table>
    </div>
</body>
</html>"""

            msg.attach(MIMEText(text_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, [admin_email], msg.as_string())

            return True, "smtp"
        except Exception as exc:
            print(f"\n[SineMix Talep Mail Uyarısı] Admin e-postası gönderilemedi ({exc}). Konsol logu yazılıyor.")

    print(
        "\n============================================================\n"
        f" 📨 [SineMix Yeni Film/Dizi Talebi -> ADMIN_EMAIL: {admin_email or 'Tanımsız'}]\n"
        f" 👤 Kullanıcı Adı : @{requester_username}\n"
        f" ✉️  Kullanıcı Mail: {requester_email}\n"
        f" 🎬 Yapım         : {title} ({media_type} • {year})\n"
        f" 📝 Not           : {note}\n"
        "============================================================\n",
        flush=True,
    )
    return True, "console"
