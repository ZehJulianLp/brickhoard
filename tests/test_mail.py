import smtplib

import pytest

from app.extensions import db
from app.models import User
from app.services.mail import MailService, MailServiceError


def test_registration_queues_confirmation_with_both_links(client, app):
    response = client.post(
        "/register",
        data={
            "username": "mailfan",
            "email": "mailfan@example.com",
            "password": "sehr-geheim",
            "password_repeat": "sehr-geheim",
        },
        follow_redirects=True,
    )

    assert "Bitte bestätige deine E-Mail-Adresse" in response.text
    message = app.extensions["mail_outbox"][-1]
    body = str(message)
    assert "http://localhost:5000/verify-email/" in body
    assert "https://brickhoard.julianverse.de/verify-email/" in body
    with app.app_context():
        user = db.session.scalar(
            db.select(User).where(User.email == "mailfan@example.com")
        )
        assert user.email_verified_at is None


def test_confirmation_token_unlocks_account(client, app):
    with app.app_context():
        user = User(
            username="unbestaetigt",
            email="offen@example.com",
            email_verified_at=None,
        )
        user.set_password("sicheres-passwort")
        db.session.add(user)
        db.session.commit()
        token = MailService().create_confirmation_token(user)
        user_id = user.id

    response = client.get(f"/verify-email/{token}", follow_redirects=True)
    assert "E-Mail-Adresse wurde bestätigt" in response.text
    with app.app_context():
        assert db.session.get(User, user_id).email_verified_at is not None


def test_unverified_user_is_limited_to_confirmation(client, app):
    with app.app_context():
        user = User(
            username="wartend",
            email="wartend@example.com",
            email_verified_at=None,
        )
        user.set_password("sicheres-passwort")
        db.session.add(user)
        db.session.commit()

    response = client.post(
        "/login",
        data={"identity": "wartend", "password": "sicheres-passwort"},
        follow_redirects=True,
    )
    assert "Bestätige deine E-Mail-Adresse" in response.text
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 302
    assert dashboard.headers["Location"].endswith("/verify-email")


def test_password_reset_changes_password_and_invalidates_link(client, app, user):
    with app.app_context():
        saved_user = db.session.get(User, user)
        token = MailService().create_password_reset_token(saved_user)

    response = client.post(
        f"/reset-password/{token}",
        data={
            "password": "brandneues-passwort",
            "password_repeat": "brandneues-passwort",
        },
        follow_redirects=True,
    )
    assert "Passwort wurde geändert" in response.text
    reused = client.get(f"/reset-password/{token}")
    assert reused.status_code == 400

    login = client.post(
        "/login",
        data={"identity": "sammler", "password": "brandneues-passwort"},
        follow_redirects=True,
    )
    assert "Hallo, sammler" in login.text


def test_forgot_password_response_does_not_reveal_accounts(client, app, user):
    known = client.post(
        "/forgot-password",
        data={"email": "sammler@example.com"},
        follow_redirects=True,
    )
    unknown = client.post(
        "/forgot-password",
        data={"email": "niemand@example.com"},
        follow_redirects=True,
    )
    message = "Falls ein aktives Konto zu dieser Adresse gehört"
    assert message in known.text
    assert message in unknown.text
    assert len(app.extensions["mail_outbox"]) == 1


def test_mail_service_wraps_smtp_errors(app, monkeypatch):
    def fail_smtp(*_args, **_kwargs):
        raise smtplib.SMTPConnectError(421, "nicht erreichbar")

    monkeypatch.setattr(smtplib, "SMTP_SSL", fail_smtp)
    with app.app_context():
        app.config.update(MAIL_SUPPRESS_SEND=False, MAIL_PASSWORD="test-password")
        with pytest.raises(MailServiceError, match="momentan nicht versendet"):
            MailService().send(
                recipient="fan@example.com",
                subject="Test",
                text_body="Testnachricht",
            )
