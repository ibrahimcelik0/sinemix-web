"""Auth feature endpoint'leri (/auth/login, /auth/register, /auth/logout)."""

from urllib.parse import urlparse
from flask import Blueprint, flash, redirect, render_template, request, url_for
from app.features.auth.services import (
    authenticate_user,
    get_current_user,
    login_user_session,
    logout_user_session,
    register_new_user,
)

auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/auth",
    template_folder="templates",
)


def _get_safe_next_url(default_endpoint: str = "catalog.discover") -> str:
    """Giriş sonrası yönlendirilecek güvenli `next` adresini döndürür."""
    next_url = (request.args.get("next") or request.form.get("next") or "").strip()
    if next_url:
        parsed = urlparse(next_url)
        if not parsed.netloc and next_url.startswith("/"):
            return next_url
    return url_for(default_endpoint)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Oturum Açma (Login) sayfası ve form işlemi."""
    if get_current_user():
        return redirect(_get_safe_next_url())

    next_url = request.args.get("next") or request.form.get("next") or ""

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        user, error = authenticate_user(identifier=identifier, password=password)
        if error:
            flash(error, "error")
            return render_template("auth/login.html", next_url=next_url, identifier=identifier)

        login_user_session(user)
        flash(f"Tekrar hoş geldin, {user['username']}! Kalıcı izleme listen aktif.", "success")
        return redirect(_get_safe_next_url())

    return render_template("auth/login.html", next_url=next_url)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Yeni Kullanıcı Kayıt (Register) sayfası ve form işlemi."""
    if get_current_user():
        return redirect(_get_safe_next_url())

    next_url = request.args.get("next") or request.form.get("next") or ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        if password != password_confirm:
            flash("Girdiğiniz şifreler birbiriyle eşleşmiyor.", "error")
            return render_template(
                "auth/register.html",
                next_url=next_url,
                username=username,
                email=email,
            )

        new_user, error = register_new_user(username=username, email=email, password=password)
        if error:
            flash(error, "error")
            return render_template(
                "auth/register.html",
                next_url=next_url,
                username=username,
                email=email,
            )

        login_user_session(new_user)
        flash(f"SineMix'e hoş geldin, {new_user['username']}! Kişisel izleme listen oluşturuldu.", "success")
        return redirect(_get_safe_next_url())

    return render_template("auth/register.html", next_url=next_url)


@auth_bp.route("/logout", methods=["POST", "GET"])
def logout():
    """Aktif kullanıcı oturumunu kapatır ve misafir moduna döner."""
    logout_user_session()
    flash("Oturumunuz kapatıldı. Şu an Misafir Modundasınız.", "info")
    return redirect(url_for("catalog.discover"))
