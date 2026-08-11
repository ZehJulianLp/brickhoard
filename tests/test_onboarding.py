from app.extensions import db
from app.models import User, utcnow


def test_new_verified_user_is_sent_to_setup_after_login(client, app):
    client.post(
        "/register",
        data={
            "username": "neuerfan",
            "email": "neu@example.com",
            "password": "sicheres-passwort",
            "password_repeat": "sicheres-passwort",
        },
    )
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == "neu@example.com"))
        assert user.onboarding_pending is True
        user.email_verified_at = utcnow()
        db.session.commit()

    response = client.post(
        "/login",
        data={"identity": "neuerfan", "password": "sicheres-passwort"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/setup/1")


def test_setup_can_be_skipped_and_marks_it_complete(client, app, user):
    with app.app_context():
        saved_user = db.session.get(User, user)
        saved_user.onboarding_pending = True
        db.session.commit()
    client.post(
        "/login",
        data={"identity": "sammler", "password": "sicheres-passwort"},
    )

    response = client.post("/setup/finish", follow_redirects=True)

    assert response.status_code == 200
    assert "Setup abgeschlossen" in response.text
    assert "Hallo, sammler" in response.text
    with app.app_context():
        db.session.expire_all()
        assert db.session.get(User, user).onboarding_pending is False


def test_existing_user_can_restart_all_setup_steps(logged_in_client):
    account = logged_in_client.get("/settings/account")
    connection_step = logged_in_client.get("/setup/2")
    last_step = logged_in_client.get("/setup/4")

    assert "Setup starten" in account.text
    assert "Dein persönlicher Rebrickable API-Key" in connection_step.text
    assert "Speichern, testen und weiter" in connection_step.text
    assert last_step.status_code == 200
    assert "Schritt 4 von 4" in last_step.text
    assert "Setup abschließen" in last_step.text


def test_unknown_setup_step_returns_not_found(logged_in_client):
    assert logged_in_client.get("/setup/5").status_code == 404


def test_rebrickable_credentials_can_be_entered_inside_setup(
    logged_in_client, app, user, monkeypatch
):
    class FakeRebrickableService:
        def __init__(self, api_key, user_token):
            assert api_key == "setup-api-key"
            assert user_token == "setup-user-token"

        def test_connection(self):
            return {"username": "setup-sammler"}

    monkeypatch.setattr(
        "app.account.routes.RebrickableService", FakeRebrickableService
    )
    response = logged_in_client.post(
        "/setup/2",
        data={
            "rebrickable_username": "setup-sammler",
            "api_key": "setup-api-key",
            "user_token": "setup-user-token",
            "save": "Speichern, testen und weiter",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/setup/3")
    with app.app_context():
        db.session.expire_all()
        saved_user = db.session.get(User, user)
        assert saved_user.rebrickable_username == "setup-sammler"
        assert saved_user.rebrickable_api_key == "setup-api-key"
        assert saved_user.rebrickable_user_token == "setup-user-token"
