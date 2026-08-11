from __future__ import annotations

from xml.etree import ElementTree


def test_public_home_has_complete_search_metadata(client):
    response = client.get("/")

    assert response.status_code == 200
    assert '<meta name="robots" content="index, follow' in response.text
    assert '<link rel="canonical" href="https://brickhoard.julianverse.de/">' in response.text
    assert '<meta name="description" content="Verwalte deine LEGO-Sammlung' in response.text
    assert '<meta property="og:title" content="BrickHoard – deine Sets, Teile und Fortschritte">' in response.text
    assert '<meta name="twitter:card" content="summary">' in response.text
    assert '<script type="application/ld+json">' in response.text
    assert '"WebApplication"' in response.text
    assert 'id="theme-toggle"' in response.text
    assert "localStorage.getItem('brickhoard-theme')" in response.text


def test_private_and_auth_pages_are_noindex(client):
    login = client.get("/login")
    dashboard = client.get("/dashboard")

    assert '<meta name="robots" content="noindex, nofollow">' in login.text
    assert login.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert dashboard.status_code == 302
    assert dashboard.headers["X-Robots-Tag"] == "noindex, nofollow"


def test_robots_txt_points_to_canonical_sitemap(client):
    response = client.get("/robots.txt")

    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert "Disallow: /dashboard" in response.text
    assert "Disallow: /sets/" in response.text
    assert "Sitemap: https://brickhoard.julianverse.de/sitemap.xml" in response.text


def test_sitemap_only_contains_public_canonical_pages(client):
    response = client.get("/sitemap.xml")
    root = ElementTree.fromstring(response.data)
    namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locations = [node.text for node in root.findall("s:url/s:loc", namespace)]

    assert response.status_code == 200
    assert response.mimetype == "application/xml"
    assert locations == [
        "https://brickhoard.julianverse.de/",
        "https://brickhoard.julianverse.de/kontakt",
        "https://brickhoard.julianverse.de/datenschutz",
        "https://brickhoard.julianverse.de/impressum",
    ]
    assert not any("login" in location or "dashboard" in location for location in locations)


def test_legal_and_contact_pages_are_public_and_linked(client):
    home = client.get("/")
    privacy = client.get("/datenschutz")
    imprint = client.get("/impressum")
    contact = client.get("/kontakt")

    assert 'href="/datenschutz"' in home.text
    assert 'href="/impressum"' in home.text
    assert 'href="mailto:brickhoard@julianverse.de"' in home.text
    assert "Rebrickable-Anbindung" in privacy.text
    assert "E-Mail-Versand" in privacy.text
    assert "Deine Rechte" in privacy.text
    assert "Julian" in imprint.text
    assert "brickhoard@julianverse.de" in contact.text
    assert privacy.headers.get("X-Robots-Tag") is None
