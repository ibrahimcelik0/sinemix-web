"""
Auth feature iş mantığı:
Kullanıcı kaydı, `werkzeug.security` ile şifre doğrulama, Flask `session` yönetimi
ve `@login_required` rota koruma dekoratörü.
"""

from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple
from flask import flash, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.features.auth.repository import UserRepository


def get_current_user() -> Optional[Dict[str, Any]]:
    """Aktif Flask oturumundaki (session) kullanıcı bilgilerini döndürür."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = UserRepository.get_by_id(str(user_id))
    if not user:
        session.clear()
        return None
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "created_at": user.get("created_at", ""),
        "avatar_initial": (user["username"][0].upper() if user.get("username") else "S"),
    }


def login_user_session(user: Dict[str, Any]) -> None:
    """Kullanıcıyı Flask session içine kaydeder."""
    session["user_id"] = str(user["id"])
    session["username"] = user["username"]
    session["email"] = user["email"]
    session.permanent = True


def logout_user_session() -> None:
    """Kullanıcı oturumunu sonlandırır."""
    session.clear()


def register_new_user(username: str, email: str, password: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Yeni kullanıcı kaydı oluşturur.
    Şifreyi `generate_password_hash` ile hash'ler ve kullanıcıya özel boş
    `data/watchlists/<user_id>.json` dosyasını hazırlar.
    """
    clean_username = (username or "").strip()
    clean_email = (email or "").strip().lower()

    if len(clean_username) < 3:
        return None, "Kullanıcı adı en az 3 karakter olmalıdır."
    if "@" not in clean_email or "." not in clean_email:
        return None, "Lütfen geçerli bir e-posta adresi girin."
    if len(password or "") < 6:
        return None, "Şifreniz en az 6 karakter olmalıdır."

    if UserRepository.get_by_username(clean_username):
        return None, f"'{clean_username}' kullanıcı adı zaten kullanılıyor."
    if UserRepository.get_by_email(clean_email):
        return None, f"'{clean_email}' e-posta adresi ile kayıtlı bir hesap zaten var."

    password_hash = generate_password_hash(password)
    new_user = UserRepository.create_user(
        username=clean_username,
        email=clean_email,
        password_hash=password_hash,
    )

    from app.features.watchlist.repository import WatchlistRepository
    WatchlistRepository.ensure_user_watchlist_file(new_user["id"])

    return new_user, None


def authenticate_user(identifier: str, password: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Kullanıcı adı veya e-posta ve şifre ile kimlik doğrulaması yapar."""
    clean_id = (identifier or "").strip()
    if not clean_id or not password:
        return None, "Lütfen kullanıcı adı/e-posta ve şifrenizi girin."

    user = UserRepository.get_by_identifier(clean_id)
    if not user:
        return None, "Bu bilgilere ait bir SineMix hesabı bulunamadı."

    if not check_password_hash(user.get("password_hash", ""), password):
        return None, "Girdiğiniz şifre hatalı. Lütfen tekrar deneyin."

    return user, None


def login_required(view_func: Callable) -> Callable:
    """
    Oturum açmamış (misafir) kullanıcıları `/auth/login` sayfasına yönlendirir.
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
                    "message": "Kalıcı kayıt için lütfen oturum açın.",
                    "login_url": login_target,
                }), 401

            flash("İzleme listenize ve profilinize erişmek için lütfen oturum açın.", "warning")
            return redirect(login_target)
        return view_func(*args, **kwargs)

    return wrapped_view
