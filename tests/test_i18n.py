from app.extensions import db
from app.models import User


def test_browser_language_selects_english_for_guests(client):
    response = client.get("/", headers={"Accept-Language": "en-US,en;q=0.9"})

    assert response.status_code == 200
    assert '<html lang="en">' in response.text
    assert "Your digital sorting table" in response.text
    assert "Get started for free" in response.text
    assert "Frequently asked questions" in response.text
    assert "BrickHoard – Sort LEGO Sets & Find Missing Parts" in response.text
    assert '<meta property="og:locale" content="en_US">' in response.text
    assert '"inLanguage": "en-US"' in response.text


def test_language_switch_is_kept_in_session(client):
    switched = client.post("/language/en", data={"next": "/login"})
    assert switched.headers["Location"] == "/login"

    login = client.get("/login")
    assert '<html lang="en">' in login.text
    assert "Welcome back" in login.text
    assert "Email address or username" in login.text
    assert "Keep me signed in" in login.text
    assert 'name="identity"' in login.text
    assert 'name="identity" required type="text" value=""' in login.text
    assert "Project-Id-Version" not in login.text

    client.post("/language/de", data={"next": "/login"})
    german = client.get("/login")
    assert '<html lang="de">' in german.text
    assert "Willkommen zurück" in german.text


def test_authenticated_language_is_saved_to_profile(logged_in_client, app, user):
    response = logged_in_client.post("/language/en", data={"next": "/dashboard"})
    assert response.headers["Location"] == "/dashboard"

    dashboard = logged_in_client.get("/dashboard")
    assert '<html lang="en">' in dashboard.text
    assert "Your collection, sorting projects and missing parts at a glance." in dashboard.text
    with app.app_context():
        assert db.session.get(User, user).preferred_locale == "en"


def test_authenticated_navigation_groups_secondary_actions(logged_in_client):
    response = logged_in_client.get("/dashboard")

    assert response.text.count('id="theme-toggle"') == 1
    assert 'class="dropdown-menu dropdown-menu-end nav-account-menu"' in response.text
    assert ">Sammlung</button>" in response.text
    assert "Profil und Sicherheit" in response.text
    assert "API-Zugang verwalten" in response.text
    assert 'id="logout-form"' in response.text
    assert 'id="install-help-modal"' in response.text
    assert "Firefox unter Linux" in response.text


def test_unknown_language_is_rejected(client):
    assert client.post("/language/fr").status_code == 404


def test_linux_desktop_launcher_is_downloadable(client):
    response = client.get("/install/brickhoard.desktop")

    assert response.status_code == 200
    assert response.mimetype == "application/x-desktop"
    assert 'filename="brickhoard.desktop"' in response.headers["Content-Disposition"]
    assert "Exec=xdg-open https://brickhoard.julianverse.de/" in response.text
    assert "Terminal=false" in response.text


def test_registration_email_uses_selected_english_locale(client, app):
    client.post("/language/en")
    response = client.post(
        "/register",
        data={
            "username": "englishfan",
            "email": "english@example.com",
            "password": "secure-password",
            "password_repeat": "secure-password",
        },
    )

    assert response.status_code == 302
    message = app.extensions["mail_outbox"][-1]
    assert message["Subject"] == "Confirm your email address for BrickHoard"
    assert "Hello englishfan" in message.get_body(preferencelist=("plain",)).get_content()
    assert '<html lang="en">' in message.get_body(preferencelist=("html",)).get_content()
    with app.app_context():
        saved = db.session.scalar(db.select(User).where(User.email == "english@example.com"))
        assert saved.preferred_locale == "en"
