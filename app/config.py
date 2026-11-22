import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv_file(dotenv_path: Path) -> None:
    """Harici paket gerektirmeden .env dosyasındaki değişkenleri os.environ'a yükler."""
    if not dotenv_path.exists():
        return
    try:
        for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass


_load_dotenv_file(BASE_DIR / ".env")


class Config:
    """Temel uygulama yapılandırma sınıfı."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "sinemix-gelistirme-gizli-anahtari")
    DEBUG = False
    TESTING = False
    TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "").strip()
    TMDB_BASE_URL = "https://api.themoviedb.org/3"
    TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
    WATCHLIST_JSON_PATH = str(BASE_DIR / "data" / "watchlist.json")


class DevelopmentConfig(Config):
    """Geliştirme ortamı yapılandırması."""
    DEBUG = True


class TestingConfig(Config):
    """Test ortamı yapılandırması."""
    DEBUG = True
    TESTING = True


class ProductionConfig(Config):
    """Üretim (Production) ortamı yapılandırması."""
    DEBUG = False


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
