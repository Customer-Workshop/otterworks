"""Settings must never carry an embedded database password by default."""

from urllib.parse import urlparse

from app.config import Settings


def test_default_database_url_has_no_password(monkeypatch):
    monkeypatch.delenv("DOC_SVC_DATABASE_URL", raising=False)
    url = urlparse(Settings(_env_file=None).database_url)
    assert url.password is None
    assert "otterworks_dev" not in url.geturl()


def test_database_url_comes_from_environment(monkeypatch):
    monkeypatch.setenv(
        "DOC_SVC_DATABASE_URL", "postgresql+asyncpg://u:secret@db:5432/otterworks"
    )
    assert Settings(_env_file=None).database_url.endswith("@db:5432/otterworks")
