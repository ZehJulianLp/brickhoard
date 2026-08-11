import pytest

from app import create_app
from app.extensions import db
from app.models import User, utcnow


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "test.db"
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            "REBRICKABLE_API_KEY": "",
            "EMAIL_LINK_BASE_URLS": (
                "http://localhost:5000",
                "https://brickhoard.julianverse.de",
            ),
        }
    )
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def user(app):
    with app.app_context():
        user = User(
            username="sammler",
            email="sammler@example.com",
            email_verified_at=utcnow(),
        )
        user.set_password("sicheres-passwort")
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture()
def logged_in_client(client, user):
    client.post(
        "/login",
        data={"identity": "sammler", "password": "sicheres-passwort"},
    )
    return client
