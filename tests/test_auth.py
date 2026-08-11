from app.extensions import db
from app.models import User


def test_registration(client, app):
    response = client.post(
        "/register",
        data={
            "username": "brickfan",
            "email": "fan@example.com",
            "password": "sehr-geheim",
            "password_repeat": "sehr-geheim",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Account wurde erstellt" in response.text
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == "fan@example.com"))
        assert user is not None
        assert user.password_hash != "sehr-geheim"
        assert user.is_admin is True


def test_login_with_correct_password(client, user):
    response = client.post(
        "/login",
        data={"identity": "SAMMLER", "password": "sicheres-passwort"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Hallo, sammler" in response.text


def test_login_with_wrong_password(client, user):
    response = client.post(
        "/login",
        data={"identity": "sammler", "password": "falsch"},
        follow_redirects=True,
    )
    assert "Anmeldedaten ungültig" in response.text
    assert "Willkommen zurück" in response.text


def test_dashboard_is_protected(client):
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login?next=" in response.headers["Location"]


def test_external_next_url_is_not_used(client, user):
    response = client.post(
        "/login?next=https://example.org/phishing",
        data={"identity": "sammler", "password": "sicheres-passwort"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_pwa_service_worker_is_available(client):
    response = client.get("/service-worker.js")
    assert response.status_code == 200
    assert "brickshelf-static" in response.text


def test_forgot_password_offers_email_reset(client):
    response = client.get("/forgot-password")
    assert response.status_code == 200
    assert "Reset-Link" in response.text
