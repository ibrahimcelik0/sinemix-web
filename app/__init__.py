"""Application Factory (create_app), Blueprint kayıtları ve küresel kullanıcı bağlamı."""

import os
from flask import Flask

from app.config import config_by_name
from app.extensions import init_extensions
from app.features.auth.routes import auth_bp
from app.features.auth.services import get_current_user
from app.features.catalog.routes import catalog_bp
from app.features.watchlist.routes import watchlist_bp
from app.features.watchlist.repository import WatchlistRepository
from app.features.recommendations.routes import recommendations_bp
from app.features.main import main_bp
from app.features.movies import movies_bp
from app.features.profile import profile_bp


def create_app(config_name: str = None) -> Flask:
    """Flask uygulamasını oluşturur, yapılandırır ve Blueprint'leri kaydeder."""
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "default")

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # Yapılandırmayı yükle
    config_class = config_by_name.get(config_name, config_by_name["default"])
    app.config.from_object(config_class)

    # Eklentileri başlat
    init_extensions(app)

    # Küresel şablon değişkenleri (current_user ve aktif kullanıcının watchlist_count değeri)
    @app.context_processor
    def inject_user_context():
        user = get_current_user()
        count = len(WatchlistRepository.get_all(user_id=user["id"])) if user else 0
        return {
            "current_user": user,
            "watchlist_count": count,
        }

    # Feature Blueprint'lerini kaydet
    register_blueprints(app)

    return app


def register_blueprints(app: Flask) -> None:
    """Tüm özellik (feature) Blueprint'lerini uygulamaya kaydeder."""
    app.register_blueprint(auth_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(watchlist_bp)
    app.register_blueprint(recommendations_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(movies_bp)
    app.register_blueprint(profile_bp)
