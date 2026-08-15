# BrickHoard

BrickHoard ist eine selbst gehostete Webanwendung für LEGO-Setlisten, Teile-Checklisten, Sortierprojekte und Fehlteile. Sie verbindet persönliche Rebrickable-Sammlungen mit dauerhaft gespeichertem Fortschritt und optionalen Social-Funktionen.

**Live:** [brickhoard.julianverse.de](https://brickhoard.julianverse.de/)

BrickHoard ist ein unabhängiges Fanprojekt und steht in keiner Verbindung zur LEGO Group oder zu Rebrickable.

## Funktionen

- Lokale Registrierung und Anmeldung mit Benutzername oder E-Mail-Adresse
- E-Mail-Bestätigung mit erneutem Versand und zeitlich begrenzten Links
- selbstständiger Passwort-Reset per E-Mail
- persönliche Kontoverwaltung mit Profiländerung, Passwortwechsel und Kontolöschung
- geführtes, überspringbares Onboarding mit direkter Rebrickable-Einrichtung
- Profilbilder mit sicherer Bildprüfung, Zuschnitt und Initialen-Fallback
- erneute Bestätigung nach Änderung der E-Mail-Adresse
- zentrale Admin-Benutzerverwaltung mit Rollen, Sperren, Bestätigungsstatus, Reset-Mails und temporären Passwortresets
- sichere Passwort-Hashes, CSRF-Schutz und „Angemeldet bleiben“
- eigene Rebrickable-Zugangsdaten je BrickHoard-Benutzer
- verschlüsselte Speicherung von API-Key und User Token
- automatische User-Token-Erzeugung aus Rebrickable-Login und Passwort; vorhandene Token können optional eingetragen werden
- Dashboard mit Sammlungskennzahlen, Projektfortschritt und Wiedereinstieg
- Listenübersicht und paginierte Setkarten
- globale Suche über alle persönlichen Rebrickable-Setlisten
- Setdetails aus dem Rebrickable-Katalog
- benutzerspezifische lokale Notizen, Lagerort, Kaufdatum/-preis und Status
- mengenbasierte, dauerhaft gespeicherte Teile-Checklisten mit Bildern und Live-Fortschritt
- automatische Fehlteilelisten mit Druckansicht und CSV-Export
- sammlungsweite, aggregierte Fehlteilezentrale mit Gruppierung und Sortierung
- Sammelaktionen zum vollständigen Aus- oder Abwählen sichtbarer Checklistenpositionen
- installierbare Progressive Web App mit Offline-Ansicht und Synchronisationswarteschlange
- tabletfreundlicher Ein-Teil-Sortiermodus mit großen Bildern und Bedienelementen
- frei wählbare Sortierreihenfolge in Checkliste und Großsortierung
- gespeicherte Zustände wie „fehlt sicher“, „falsche Farbe“ und „Alternative vorhanden“
- globale Großansicht, Wiedereinstieg ins letzte Projekt und druckbare Sortierbögen
- responsive Bootstrap-5-Oberfläche, persistenter Darkmode und benutzerfreundliche Fehlerseiten
- deutsche und englische Oberfläche mit Browsererkennung, Sprachumschalter und dauerhaft gespeicherter Kontosprache
- Freundschaftsanfragen mit Rolling-Usersuche ausschließlich über Benutzernamen
- E-Mail-Benachrichtigungen bei Anfrage, Annahme, Ablehnung und Projektfreigabe
- optionale öffentliche Sammlerprofile mit zusammengefassten Statistiken
- Projektfreigaben mit getrennten Ansichts- und Bearbeitungsrechten
- gemeinsame Checklisten und Großsortierung mit regelmäßiger Fortschrittssynchronisation
- Teileangebote für Fehlteile mit Annahme- und Ablehnungsstatus
- technische SEO-Basis mit Canonicals, Open Graph, Twitter Cards und strukturierten Daten
- öffentliche `robots.txt` und XML-Sitemap bei gleichzeitigem `noindex` für private Bereiche
- öffentliche Kontakt-, Datenschutz- und Impressumsseiten

## Technik und Architektur

Die Anwendung benötigt Python 3.12 oder neuer und verwendet Flask, Flask-Babel, Flask-SQLAlchemy, Flask-Login, Flask-WTF/WTForms, SQLite, Requests, Jinja2, Bootstrap 5, Cryptography und Pillow. Eine Application Factory initialisiert die Erweiterungen und registriert getrennte Blueprints für Authentifizierung, Konten, Administration, Hauptseiten, Sets und Social-Funktionen. Sämtliche HTTP-Kommunikation mit Rebrickable liegt zentral in `app/services/rebrickable.py`.

Es gibt bewusst keine vollständige lokale Kopie des Rebrickable-Katalogs. Listen und Setdaten werden bei Bedarf von der API geladen. Teileinventare können für Fehlteileübersichten zwischengespeichert werden; persönliche Ergänzungen und Fortschritte werden dauerhaft lokal gespeichert.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Erzeuge für `SECRET_KEY` eine lange zufällige Zeichenfolge, zum Beispiel:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Optional kann ein eigener Fernet-Schlüssel für `CREDENTIAL_ENCRYPTION_KEY` erzeugt werden:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Anschließend `.env` bearbeiten:

```env
SECRET_KEY=dein-langer-zufaelliger-wert
DATABASE_URL=sqlite:///brickshelf.db
REBRICKABLE_API_KEY=
CREDENTIAL_ENCRYPTION_KEY=dein-fernet-schluessel
FLASK_ENV=development

MAIL_SERVER=mail.example.de
MAIL_PORT=465
MAIL_USE_SSL=true
MAIL_USE_TLS=false
MAIL_USERNAME=brickhoard@example.de
MAIL_PASSWORD=dein-smtp-app-passwort
MAIL_DEFAULT_SENDER=BrickHoard <brickhoard@example.de>
EMAIL_LINK_BASE_URLS=http://localhost:5000,https://brickhoard.example.de
PUBLIC_BASE_URL=https://brickhoard.example.de

LEGAL_OPERATOR_NAME=Vorname Nachname
LEGAL_POSTAL_ADDRESS=Straße Hausnummer|PLZ Ort|Deutschland
LEGAL_CONTACT_EMAIL=brickhoard@example.de
PRIVACY_LAST_UPDATED=13. August 2026
```

Die echte `.env` ist über `.gitignore` ausgeschlossen.

## E-Mail-Versand

BrickHoard verschickt Bestätigungs-, Passwort-Reset- und Social-Benachrichtigungen über SMTP. Dazu gehören Freundschaftsanfragen und deren Annahme oder Ablehnung sowie neue Projektfreigaben. Port 465 verwendet direktes SSL/TLS (`MAIL_USE_SSL=true`). Für einen Server mit STARTTLS wird stattdessen `MAIL_USE_SSL=false` und `MAIL_USE_TLS=true` gesetzt. IMAP wird nicht benötigt, da BrickHoard keine eingehenden Nachrichten liest.

`EMAIL_LINK_BASE_URLS` nimmt eine kommaseparierte Liste an und wird für Bestätigungs-, Reset- und Social-Links verwendet. In der Entwicklung können dadurch ein localhost-Link und die spätere Serveradresse gemeinsam in einer Mail erscheinen. In einer reinen Produktionsumgebung kann die Liste auf die öffentliche HTTPS-Adresse reduziert werden.

Bestätigungslinks sind standardmäßig 24 Stunden, Passwort-Reset-Links 60 Minuten gültig. Eine Passwortänderung macht ältere Reset-Links automatisch unbrauchbar. Wiederholte Mailanforderungen werden kurzzeitig gedrosselt. Für Tests unterdrückt BrickHoard den echten SMTP-Versand und legt Nachrichten in einer Test-Outbox ab.

Der erste registrierte Benutzer wird automatisch Administrator. Alternativ kann ein Administrator über die CLI angelegt werden:

```bash
flask --app run.py create-admin
```

## Datenbank und Start

```bash
flask --app run.py init-db
flask --app run.py run --debug
```

Die Standard-SQLite-Datenbank und das rotierende Anwendungslog liegen im Flask-`instance`-Verzeichnis. Die Anwendung ist anschließend unter <http://127.0.0.1:5000> erreichbar.

## Sprachen und Übersetzungen

Deutsch ist die Standardsprache, Englisch liegt als gettext-Katalog unter `app/translations/en/LC_MESSAGES/messages.po`. Gäste erhalten zunächst die passendste unterstützte Browsersprache und können sie in der Navigation wechseln. Bei angemeldeten Benutzern wird die Auswahl im Konto gespeichert und auch für Bestätigungs-, Reset- und Social-Mails verwendet.

Für eine weitere Sprache wird sie zuerst in `LANGUAGES` in `app/__init__.py` ergänzt. Anschließend kann ein neuer Katalog angelegt und kompiliert werden:

```bash
pybabel extract -F babel.cfg -k _ -k gettext -k ngettext -k _l -o messages.pot .
pybabel init -i messages.pot -d app/translations -l fr
# app/translations/fr/LC_MESSAGES/messages.po übersetzen
pybabel compile -d app/translations
```

Neue Python- und Template-Texte sollten mit `gettext`, `lazy_gettext` beziehungsweise `_()` markiert werden. Der zentrale Locale-Selector, Formulare, gerenderte HTML-Texte und JavaScript-Livezustände greifen auf denselben Katalog zurück.

## Rebrickable einrichten

Laut offizieller [Rebrickable API-v3-Dokumentation](https://rebrickable.com/api/v3/docs/) braucht jede Anfrage einen API-Key. Private Sammlungsendpunkte adressieren den Benutzer zusätzlich über dessen `user_token`. Der in BrickHoard angebotene Rebrickable-Benutzername ist daher optional und dient nur der leichteren Zuordnung.

1. Bei Rebrickable anmelden und im API-Bereich einen API-Key erzeugen.
2. In BrickHoard registrieren und die E-Mail-Adresse bestätigen.
3. Im geführten Setup Rebrickable-Login, Passwort und gegebenenfalls den persönlichen API-Key eintragen.
4. BrickHoard erzeugt den benötigten User Token automatisch und verwirft das eingegebene Rebrickable-Passwort unmittelbar.
5. Wer bereits einen User Token besitzt, kann ihn stattdessen optional direkt eintragen.

Falls noch kein User Token vorhanden ist, kann BrickHoard ihn über den offiziellen Endpoint `POST /api/v3/users/_token/` erzeugen. Das dafür eingegebene Rebrickable-Passwort wird nur an Rebrickable übertragen und weder gespeichert noch protokolliert.

Standardmäßig hinterlegt jeder Benutzer seinen eigenen API-Key. Lediglich als optionale Betreiber-Alternative aus der ursprünglichen Konfiguration kann `REBRICKABLE_API_KEY` global in `.env` gesetzt werden. Ein persönlicher Benutzer-Key überschreibt diesen Rückfallwert immer.

Verwendete API-v3-Endpunkte:

- `GET /api/v3/users/{user_token}/profile/`
- `GET /api/v3/users/{user_token}/setlists/`
- `GET /api/v3/users/{user_token}/setlists/{list_id}/`
- `GET /api/v3/users/{user_token}/setlists/{list_id}/sets/`
- `GET /api/v3/lego/sets/{set_num}/`
- `GET /api/v3/lego/themes/{id}/`

## Freunde und gemeinsame Projekte

Im Bereich **Freunde** können aktive, bestätigte Konten per Rolling-Suche ausschließlich anhand ihres Benutzernamens gefunden werden. E-Mail-Adressen werden in der Social-Oberfläche nicht angezeigt und können nicht zur Nutzersuche verwendet werden.

Bestätigte Freunde können einzelne Sets miteinander teilen. Die Freigabe erlaubt entweder nur die Ansicht oder das gemeinsame Bearbeiten von Checkliste und Großsortierung. Gemeinsame Ansichten gleichen Fortschritte regelmäßig ab. Private Set-Notizen, Lagerorte, Kaufpreise und Kaufdaten werden nicht freigegeben. Freunde können zu sichtbaren Fehlteilen passende Teile anbieten; der Projektbesitzer kann Angebote annehmen oder ablehnen. Öffentliche Profile sind standardmäßig deaktiviert und müssen ausdrücklich freigeschaltet werden.

## Sicherheit

Passwörter werden ausschließlich als sichere Hashes gespeichert. Bestätigungs- und Reset-Links sind signiert, zeitlich begrenzt und an den aktuellen Kontozustand gebunden. API-Key und User Token werden mit Fernet verschlüsselt. Ist kein expliziter `CREDENTIAL_ENCRYPTION_KEY` gesetzt, wird aus `SECRET_KEY` ein Schlüssel abgeleitet. Für produktiven Betrieb sollten beide Werte unabhängig, zufällig, stabil und über eine Secret-Verwaltung bereitgestellt werden. Ein Wechsel des Verschlüsselungsschlüssels ohne vorherige Migration macht bestehende Zugangsdaten unlesbar.

Profilbilder werden dekodiert, von Metadaten befreit, quadratisch auf 512 × 512 Pixel zugeschnitten und als WebP neu gespeichert. Private Bilder sind nur angemeldet beziehungsweise in der Benutzerverwaltung nur für Administratoren abrufbar. Öffentliche Profilbilder werden nur nach ausdrücklicher Freigabe des öffentlichen Profils ausgeliefert.

Geheimnisse erscheinen nie vollständig in Formularen oder Logs. Produktionsbetrieb sollte außerdem HTTPS, sichere Dateirechte für `instance/`, Backups, einen produktionsgeeigneten WSGI-Server und eine vorgeschaltete Rate-Begrenzung nutzen. `FLASK_ENV=production` aktiviert sichere Cookies; diese Einstellung setzt HTTPS voraus.

## Tests

Die API-Tests verwenden ausschließlich Mocks und benötigen keine Rebrickable-Verbindung:

```bash
python -m compileall .
pytest
```

Die Tests decken unter anderem Registrierung, E-Mail-Flows, Kontoverwaltung, Profilbilder, Onboarding, Routenschutz, Rebrickable-Service, Notizen, Checklisten, Sortierung, Social-Suche, Freundschaften, E-Mail-Benachrichtigungen, Freigaberechte, gemeinsame Fortschritte, öffentliche Profile und Teileangebote ab.

## Projektstruktur

```text
app/
├── auth/             # Registrierung, Login, Logout
├── account/          # Konto, Onboarding und Profilbilder
├── admin/            # Benutzerverwaltung
├── main/             # Startseite und Dashboard
├── sets/             # Einstellungen, Listen, Setdetails und Formulare
├── social/           # Freunde, Profile, Freigaben und Teileangebote
├── services/         # Rebrickable-API-Client und E-Mail-Versand
├── static/           # CSS und JavaScript
├── templates/        # Jinja2-Templates und Fehlerseiten
├── __init__.py       # Application Factory, CLI, Fehler und Logging
├── extensions.py
└── models.py
tests/
deploy/                # systemd-, Screen-, Nginx- und Certbot-Hilfen
run.py
requirements.txt
```

## Betriebshinweise

Rebrickable-Fehler (ungültige Zugangsdaten, Rate Limits, Timeouts, Verbindungs- und Serverfehler) werden als verständliche Meldungen innerhalb des Layouts angezeigt. Technische Details und Zugangsdaten werden nicht an Benutzer ausgegeben. `init-db` erstellt fehlende Tabellen und ergänzt die bisher vorgesehenen Spalten, ist jedoch kein allgemeines Migrationssystem. Für umfangreichere Schemaänderungen in einem dauerhaft betriebenen System empfiehlt sich Flask-Migrate/Alembic.

Die mitgelieferten Dateien unter `deploy/` starten BrickHoard produktiv über Gunicorn in einer GNU-Screen-Sitzung, integrieren den Prozess als systemd-User-Service und enthalten Vorlagen beziehungsweise Installationsskripte für Nginx, Certbot und Zertifikatserneuerung. Die Produktionsinstanz verwendet einen freien, ausschließlich lokal gebundenen Port hinter dem Reverse Proxy.
