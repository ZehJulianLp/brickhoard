# BrickHoard

BrickHoard ist eine private, lokal betriebene Webanwendung für persönliche LEGO-Setlisten. Sie liest die Listen eines Benutzers über die Rebrickable API v3 und ergänzt sie um lokale Notizen, Lagerorte, Kaufdaten und Zustandsangaben.

BrickHoard ist ein unabhängiges Fanprojekt und steht in keiner Verbindung zur LEGO Group oder zu Rebrickable.

## Funktionen

- Lokale Registrierung und Anmeldung mit Benutzername oder E-Mail-Adresse
- E-Mail-Bestätigung mit erneutem Versand und zeitlich begrenzten Links
- selbstständiger Passwort-Reset per E-Mail
- persönliche Kontoverwaltung mit Profiländerung, Passwortwechsel und Kontolöschung
- erneute Bestätigung nach Änderung der E-Mail-Adresse
- zentrale Admin-Benutzerverwaltung mit Rollen, Sperren, Bestätigungsstatus, Reset-Mails und temporären Passwortresets
- sichere Passwort-Hashes, CSRF-Schutz und „Angemeldet bleiben“
- eigene Rebrickable-Zugangsdaten je BrickHoard-Benutzer
- verschlüsselte Speicherung von API-Key und User Token
- Verbindungstest gegen das Rebrickable-Benutzerprofil
- Dashboard mit Anzahl der Listen und Listeneinträge
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
- gespeicherte Zustände wie „fehlt sicher“, „falsche Farbe“ und „Alternative vorhanden“
- globale Großansicht, Wiedereinstieg ins letzte Projekt und druckbare Sortierbögen
- responsive Bootstrap-5-Oberfläche und benutzerfreundliche Fehlerseiten

## Technik und Architektur

Die Anwendung benötigt Python 3.12 oder neuer und verwendet Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF/WTForms, SQLite, Requests, Jinja2, Bootstrap 5 und Cryptography. Eine Application Factory initialisiert die Erweiterungen und registriert getrennte Blueprints für Authentifizierung, Hauptseiten und Sets. Sämtliche HTTP-Kommunikation mit Rebrickable liegt zentral in `app/services/rebrickable.py`.

Es gibt bewusst keine lokale Kopie des Rebrickable-Katalogs. Listen und Setdaten bleiben aktuell, weil sie bei Bedarf von der API geladen werden. Nur persönliche Ergänzungen werden lokal gespeichert.

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
```

Die echte `.env` ist über `.gitignore` ausgeschlossen.

## E-Mail-Versand

BrickHoard verschickt Bestätigungs- und Passwort-Reset-Mails über SMTP. Port 465 verwendet direktes SSL/TLS (`MAIL_USE_SSL=true`). Für einen Server mit STARTTLS wird stattdessen `MAIL_USE_SSL=false` und `MAIL_USE_TLS=true` gesetzt. IMAP wird nicht benötigt, da BrickHoard keine eingehenden Nachrichten liest.

`EMAIL_LINK_BASE_URLS` nimmt eine kommaseparierte Liste an. In der Entwicklung können dadurch ein localhost-Link und die spätere Serveradresse gemeinsam in einer Mail erscheinen. In einer reinen Produktionsumgebung kann die Liste auf die öffentliche HTTPS-Adresse reduziert werden.

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

## Rebrickable einrichten

Laut offizieller [Rebrickable API-v3-Dokumentation](https://rebrickable.com/api/v3/docs/) braucht jede Anfrage einen API-Key. Private Sammlungsendpunkte adressieren den Benutzer zusätzlich über dessen `user_token`. Der in BrickHoard angebotene Rebrickable-Benutzername ist daher optional und dient nur der leichteren Zuordnung.

1. Bei Rebrickable anmelden und im API-Bereich einen API-Key erzeugen.
2. In BrickHoard registrieren und **Einstellungen → Rebrickable** öffnen.
3. API-Key und persönlichen User Token eintragen.
4. Mit **Verbindung testen** das Profil abrufen.
5. Einstellungen speichern und die Setlisten öffnen.

Falls noch kein User Token vorhanden ist, kann BrickHoard ihn über den offiziellen Endpoint `POST /api/v3/users/_token/` erzeugen. Das dafür eingegebene Rebrickable-Passwort wird nur an Rebrickable übertragen und weder gespeichert noch protokolliert.

Standardmäßig hinterlegt jeder Benutzer seinen eigenen API-Key. Lediglich als optionale Betreiber-Alternative aus der ursprünglichen Konfiguration kann `REBRICKABLE_API_KEY` global in `.env` gesetzt werden. Ein persönlicher Benutzer-Key überschreibt diesen Rückfallwert immer.

Verwendete API-v3-Endpunkte:

- `GET /api/v3/users/{user_token}/profile/`
- `GET /api/v3/users/{user_token}/setlists/`
- `GET /api/v3/users/{user_token}/setlists/{list_id}/`
- `GET /api/v3/users/{user_token}/setlists/{list_id}/sets/`
- `GET /api/v3/lego/sets/{set_num}/`
- `GET /api/v3/lego/themes/{id}/`

## Sicherheit

Passwörter werden ausschließlich als Werkzeug-Hash gespeichert. Bestätigungs- und Reset-Links sind signiert, zeitlich begrenzt und an den aktuellen Kontozustand gebunden. API-Key und User Token werden mit Fernet verschlüsselt. Ist kein expliziter `CREDENTIAL_ENCRYPTION_KEY` gesetzt, wird aus `SECRET_KEY` ein Schlüssel abgeleitet. Für produktiven Betrieb sollten beide Werte unabhängig, zufällig, stabil und über eine Secret-Verwaltung bereitgestellt werden. Ein Wechsel des Verschlüsselungsschlüssels ohne vorherige Migration macht bestehende Zugangsdaten unlesbar.

Geheimnisse erscheinen nie vollständig in Formularen oder Logs. Produktionsbetrieb sollte außerdem HTTPS, sichere Dateirechte für `instance/`, Backups, einen produktionsgeeigneten WSGI-Server und eine vorgeschaltete Rate-Begrenzung nutzen. `FLASK_ENV=production` aktiviert sichere Cookies; diese Einstellung setzt HTTPS voraus.

## Tests

Die API-Tests verwenden ausschließlich Mocks und benötigen keine Rebrickable-Verbindung:

```bash
python -m compileall .
pytest
```

Abgedeckt sind Registrierung, richtiger und falscher Login, Routenschutz, sichere Weiterleitung, Isolation/Speicherung lokaler Notizen sowie Erfolg, Pagination, API-Fehler und Timeout des Rebrickable-Service.

## Projektstruktur

```text
app/
├── auth/             # Registrierung, Login, Logout
├── main/             # Startseite und Dashboard
├── sets/             # Einstellungen, Listen, Setdetails und Formulare
├── services/         # Rebrickable-API-Client
├── static/           # CSS und JavaScript
├── templates/        # Jinja2-Templates und Fehlerseiten
├── __init__.py       # Application Factory, CLI, Fehler und Logging
├── extensions.py
└── models.py
tests/
run.py
requirements.txt
```

## Betriebshinweise

Rebrickable-Fehler (ungültige Zugangsdaten, Rate Limits, Timeouts, Verbindungs- und Serverfehler) werden als verständliche Meldungen innerhalb des Layouts angezeigt. Technische Details und Zugangsdaten werden nicht an Benutzer ausgegeben. `init-db` erstellt fehlende Tabellen, ist jedoch kein Migrationssystem. Für spätere Schemaänderungen in einem dauerhaft betriebenen System empfiehlt sich Flask-Migrate/Alembic.
