"""
Tamamen Şifresiz (Passwordless) 6 Haneli E-Posta OTP Giriş, Kayıt ve Kod Doğrulama Rotaları.

3 Ayrı Ekran Mimarisi:
1. `/auth/login`    -> `auth/login.html`    (Yalnızca kayıtlı e-posta ile Oturum Açma ekranı)
2. `/auth/register` -> `auth/register.html` (İsim, Soyisim, Kullanıcı Adı, E-Posta ile Kayıt Olma ekranı)
3. `/auth/verify`   -> `auth/verify.html`   (6 kutucuklu tek kullanımlık OTP Kod Gir ekranı)
"""

from urllib.parse import urlparse
from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from app.features.auth.services import (
    get_active_otp_challenge,
    get_current_user,
    get_otp_cooldown_remaining,
    logout_user_session,
    request_email_otp,
    verify_email_otp,
)

auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/auth",
    template_folder="templates",
)


def _get_safe_next_url(raw_next: str = "", default_endpoint: str = "catalog.discover") -> str:
    """Giriş sonrası yönlendirilecek güvenli `next` adresini döndürür."""
    candidate = (
        raw_next
        or request.args.get("next")
        or request.form.get("next")
        or session.get("otp_next_url")
        or ""
    ).strip()
    if candidate:
        parsed = urlparse(candidate)
        if not parsed.netloc and candidate.startswith("/"):
            return candidate
    return url_for(default_endpoint)


def _store_pending_otp_session(email: str, mode: str, next_url: str = "") -> None:
    """Kod Gir (`/auth/verify`) sayfasının hangi e-posta için çalışacağını session'a yazar."""
    session["otp_pending_email"] = (email or "").strip().lower()
    session["otp_pending_mode"] = "register" if mode == "register" else "login"
    if next_url:
        session["otp_next_url"] = next_url


def _clear_pending_otp_session() -> None:
    session.pop("otp_pending_email", None)
    session.pop("otp_pending_mode", None)
    session.pop("otp_next_url", None)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    1. EKRAN: Şifresiz Oturum Aç Sayfası (`auth/login.html`).
    Kayıtlı kullanıcı yalnızca e-posta adresini girer; doğrulama kodu gönderildiğinde
    ayrı Kod Gir sayfasına (`/auth/verify`) yönlendirilir.
    """
    if get_current_user():
        return redirect(_get_safe_next_url())

    next_url = (request.args.get("next") or request.form.get("next") or "").strip()

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        result = request_email_otp(email=email, mode="login")

        if not result.get("ok"):
            if result.get("status") == "cooldown":
                _store_pending_otp_session(email=email, mode="login", next_url=next_url)
                flash(result.get("message", "Lütfen bekleyin."), "warning")
                return redirect(url_for("auth.verify", next=next_url))

            flash(result.get("message", "Doğrulama kodu gönderilemedi."), "error")
            return render_template("auth/login.html", next_url=next_url, email=email)

        _store_pending_otp_session(email=email, mode="login", next_url=next_url)
        flash(result.get("message", "6 haneli giriş kodunuz e-postanıza gönderildi."), "info")
        return redirect(url_for("auth.verify", next=next_url))

    prefill_email = (request.args.get("email") or session.get("otp_pending_email") or "").strip()
    return render_template("auth/login.html", next_url=next_url, email=prefill_email)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """
    2. EKRAN: Şifresiz Kayıt Ol Sayfası (`auth/register.html`).
    İsim, Soyisim, Kullanıcı Adı ve E-Posta alır; benzersizlik kontrolleri geçtiğinde
    6 haneli OTP gönderir ve ayrı Kod Gir sayfasına (`/auth/verify`) yönlendirilir.
    """
    if get_current_user():
        return redirect(_get_safe_next_url())

    next_url = (request.args.get("next") or request.form.get("next") or "").strip()

    if request.method == "POST":
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()

        result = request_email_otp(
            email=email,
            mode="register",
            first_name=first_name,
            last_name=last_name,
            username=username,
        )

        if not result.get("ok"):
            if result.get("status") == "cooldown":
                _store_pending_otp_session(email=email, mode="register", next_url=next_url)
                flash(result.get("message", "Lütfen bekleyin."), "warning")
                return redirect(url_for("auth.verify", next=next_url))

            flash(result.get("message", "Doğrulama kodu gönderilemedi."), "error")
            return render_template(
                "auth/register.html",
                next_url=next_url,
                first_name=first_name,
                last_name=last_name,
                username=username,
                email=email,
            )

        _store_pending_otp_session(email=email, mode="register", next_url=next_url)
        flash(result.get("message", "6 haneli doğrulama kodunuz e-postanıza gönderildi."), "info")
        return redirect(url_for("auth.verify", next=next_url))

    return render_template("auth/register.html", next_url=next_url)


@auth_bp.route("/verify", methods=["GET", "POST"])
def verify():
    """
    3. EKRAN: Ayrı 6 Kutucuklu OTP Kod Gir Sayfası (`auth/verify.html`).
    """
    if get_current_user():
        return redirect(_get_safe_next_url())

    next_url = (request.args.get("next") or request.form.get("next") or session.get("otp_next_url") or "").strip()
    email = (
        request.args.get("email")
        or request.form.get("email")
        or session.get("otp_pending_email")
        or ""
    ).strip().lower()
    mode = (
        request.args.get("mode")
        or request.form.get("mode")
        or session.get("otp_pending_mode")
        or "login"
    ).strip().lower()

    if request.method == "POST":
        otp_code = (request.form.get("otp_code") or "").strip()
        result = verify_email_otp(email=email, code=otp_code)
        if not result.get("ok"):
            flash(result.get("message", "Doğrulama kodu hatalı."), "error")
            if result.get("status") in ("max_attempts_exceeded", "expired", "no_active_code"):
                target_back = url_for("auth.register", next=next_url) if mode == "register" else url_for("auth.login", next=next_url)
                return redirect(target_back)
            cooldown_rem = get_otp_cooldown_remaining(email) or 0
            return render_template(
                "auth/verify.html",
                email=email,
                mode=mode,
                next_url=next_url,
                cooldown_seconds=cooldown_rem,
                attempts_remaining=result.get("attempts_remaining", 3),
            )

        _clear_pending_otp_session()
        flash(result.get("message", "Hoş geldiniz!"), "success")
        return redirect(_get_safe_next_url(next_url))

    if not email:
        flash("Lütfen önce e-posta adresinizi girerek 6 haneli doğrulama kodu isteyin.", "info")
        return redirect(url_for("auth.login", next=next_url))

    challenge = get_active_otp_challenge(email)
    cooldown_rem = get_otp_cooldown_remaining(email)
    if challenge and challenge.get("is_new_user"):
        mode = "register"

    return render_template(
        "auth/verify.html",
        email=email,
        mode=mode,
        next_url=next_url,
        cooldown_seconds=cooldown_rem if cooldown_rem > 0 else 60,
        attempts_remaining=max(0, 3 - int(challenge.get("attempts", 0))) if challenge else 3,
    )


@auth_bp.route("/request-otp", methods=["POST"])
def api_request_otp():
    """
    `/auth/login` veya `/auth/register` sayfalarından çağrılan JSON endpoint.
    Başarılı olduğunda ayrı Kod Gir sayfasının adresini (`verify_url`: `/auth/verify`) döndürür.
    """
    payload = request.get_json(silent=True) or {}
    mode = (payload.get("mode") or request.form.get("mode") or "auto").strip().lower()
    email = (payload.get("email") or request.form.get("email") or "").strip().lower()
    first_name = (payload.get("first_name") or request.form.get("first_name") or "").strip()
    last_name = (payload.get("last_name") or request.form.get("last_name") or "").strip()
    full_name = (payload.get("full_name") or request.form.get("full_name") or "").strip()
    username = (payload.get("username") or request.form.get("username") or "").strip()
    next_url = (payload.get("next") or request.form.get("next") or "").strip()

    result = request_email_otp(
        email=email,
        mode=mode,
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        username=username,
    )

    resolved_mode = "register" if result.get("is_new_user") or mode == "register" else "login"

    if result.get("ok") or result.get("status") == "cooldown":
        _store_pending_otp_session(email=email, mode=resolved_mode, next_url=next_url)
        result["verify_url"] = url_for("auth.verify", next=next_url) if next_url else url_for("auth.verify")

    status_code = 200 if result.get("ok") else 400
    if result.get("status") == "cooldown":
        status_code = 429
    return jsonify(result), status_code


@auth_bp.route("/verify-otp", methods=["POST"])
def api_verify_otp():
    """
    `/auth/verify` (Kod Gir) sayfasındaki 6 kutucuklu OTP alanından gönderilen kodu doğrulayan JSON endpoint.
    """
    payload = request.get_json(silent=True) or {}
    email = (
        payload.get("email")
        or request.form.get("email")
        or session.get("otp_pending_email")
        or ""
    ).strip().lower()
    code = (payload.get("code") or payload.get("otp_code") or request.form.get("otp_code") or "").strip()
    next_url = (payload.get("next") or request.form.get("next") or session.get("otp_next_url") or "").strip()
    guest_watchlist = payload.get("guest_watchlist") if isinstance(payload.get("guest_watchlist"), list) else None

    result = verify_email_otp(email=email, code=code, guest_watchlist=guest_watchlist)
    if not result.get("ok"):
        status_code = 429 if result.get("status") == "max_attempts_exceeded" else 400
        return jsonify(result), status_code

    _clear_pending_otp_session()
    flash(result.get("message", "Oturum açıldı!"), "success")
    result["redirect_url"] = _get_safe_next_url(next_url)
    return jsonify(result), 200


@auth_bp.route("/logout", methods=["POST", "GET"])
def logout():
    """Aktif kullanıcı oturumunu kapatır ve misafir moduna döner."""
    _clear_pending_otp_session()
    logout_user_session()
    flash("Oturumunuz kapatıldı. Şu an Misafir Modundasınız.", "info")
    return redirect(url_for("catalog.discover"))
