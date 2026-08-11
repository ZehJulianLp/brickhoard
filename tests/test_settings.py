from app.extensions import db
from app.models import User


def test_rebrickable_credentials_are_saved_per_user_and_encrypted(
    logged_in_client, app, user
):
    response = logged_in_client.post(
        "/settings/rebrickable",
        data={
            "rebrickable_username": "rb-sammler",
            "api_key": "personal-api-key",
            "user_token": "personal-user-token",
            "save": "Einstellungen speichern",
        },
    )
    assert response.status_code == 302

    with app.app_context():
        saved_user = db.session.get(User, user)
        assert saved_user.rebrickable_api_key == "personal-api-key"
        assert saved_user.rebrickable_user_token == "personal-user-token"
        assert "personal-api-key" not in saved_user._rebrickable_api_key
        assert "personal-user-token" not in saved_user._rebrickable_user_token

