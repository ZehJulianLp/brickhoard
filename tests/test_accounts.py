from io import BytesIO

from PIL import Image

from app.extensions import db
from app.models import SetNote, SetPartProgress, User, utcnow


def test_user_can_change_password(logged_in_client, app, user):
    response = logged_in_client.post(
        "/settings/account/password",
        data={
            "current_password": "sicheres-passwort",
            "new_password": "noch-sicherer-2026",
            "new_password_repeat": "noch-sicherer-2026",
        },
        follow_redirects=True,
    )
    assert "Passwort wurde geändert" in response.text
    logged_in_client.post("/logout")
    old_login = logged_in_client.post(
        "/login",
        data={"identity": "sammler", "password": "sicheres-passwort"},
        follow_redirects=True,
    )
    assert "Anmeldedaten ungültig" in old_login.text
    new_login = logged_in_client.post(
        "/login",
        data={"identity": "sammler", "password": "noch-sicherer-2026"},
        follow_redirects=True,
    )
    assert "Hallo, sammler" in new_login.text


def test_user_can_update_profile(logged_in_client, app, user):
    response = logged_in_client.post(
        "/settings/account",
        data={"username": "neuer-name", "email": "neu@example.com"},
        follow_redirects=True,
    )
    assert "Kontodaten wurden gespeichert" in response.text
    with app.app_context():
        saved = db.session.get(User, user)
        assert saved.username == "neuer-name"
        assert saved.email == "neu@example.com"


def test_user_can_upload_and_remove_profile_picture(logged_in_client, app, user):
    source = BytesIO()
    Image.new("RGB", (900, 500), "#e69a2c").save(source, format="PNG")
    source.seek(0)

    upload = logged_in_client.post(
        "/settings/account/profile-picture",
        data={"picture": (source, "avatar.png"), "upload": "Profilbild speichern"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "Profilbild wurde gespeichert" in upload.text

    picture = logged_in_client.get("/profile-picture")
    assert picture.status_code == 200
    assert picture.content_type == "image/webp"
    with Image.open(BytesIO(picture.data)) as rendered:
        assert rendered.size == (512, 512)
        assert rendered.format == "WEBP"

    with app.app_context():
        saved = db.session.get(User, user)
        assert saved.profile_picture
        assert saved.profile_picture_updated_at is not None

    remove = logged_in_client.post(
        "/settings/account/profile-picture",
        data={"remove": "Profilbild entfernen"},
        follow_redirects=True,
    )
    assert "Profilbild wurde entfernt" in remove.text
    assert logged_in_client.get("/profile-picture").status_code == 404


def test_invalid_profile_picture_is_rejected(logged_in_client, app, user):
    response = logged_in_client.post(
        "/settings/account/profile-picture",
        data={
            "picture": (BytesIO(b"not-an-image"), "avatar.png"),
            "upload": "Profilbild speichern",
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "gültiges JPG-, PNG- oder WebP-Bild" in response.text
    with app.app_context():
        assert db.session.get(User, user).profile_picture is None


def test_user_can_delete_own_account_and_local_data(logged_in_client, app, user):
    with app.app_context():
        db.session.add(SetNote(user_id=user, set_number="1000-1", note="weg"))
        db.session.add(
            SetPartProgress(
                user_id=user,
                set_number="1000-1",
                item_key="inventory:1",
            )
        )
        db.session.commit()
    response = logged_in_client.post(
        "/settings/account/delete",
        data={
            "current_password": "sicheres-passwort",
            "username_confirmation": "sammler",
            "confirmation": "y",
        },
        follow_redirects=True,
    )
    assert "Konto und alle lokalen Benutzerdaten wurden gelöscht" in response.text
    with app.app_context():
        assert db.session.get(User, user) is None
        assert not db.session.scalar(
            db.select(SetPartProgress).where(SetPartProgress.user_id == user)
        )


def test_non_admin_cannot_open_admin_center(logged_in_client):
    response = logged_in_client.get("/admin/users")
    assert response.status_code == 403


def test_admin_can_reset_and_disable_user(client, app):
    with app.app_context():
        admin = User(
            username="admin",
            email="admin@example.com",
            is_admin=True,
            is_enabled=True,
            email_verified_at=utcnow(),
        )
        admin.set_password("admin-password")
        target = User(
            username="target",
            email="target@example.com",
            is_enabled=True,
        )
        target.set_password("target-password")
        db.session.add_all([admin, target])
        db.session.commit()
        target_id = target.id
    client.post(
        "/login", data={"identity": "admin", "password": "admin-password"}
    )
    reset = client.post(
        "/admin/users/reset-password", data={"user_id": str(target_id)}
    )
    assert reset.status_code == 200
    assert "Einmalige Anzeige" in reset.text
    with app.app_context():
        target = db.session.get(User, target_id)
        assert target.must_change_password is True
        assert not target.check_password("target-password")

    disabled = client.post(
        "/admin/users/toggle-enabled",
        data={"user_id": str(target_id)},
        follow_redirects=True,
    )
    assert "gesperrt" in disabled.text
    with app.app_context():
        assert db.session.get(User, target_id).is_enabled is False
