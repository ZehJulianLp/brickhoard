from flask_wtf import FlaskForm
from flask_babel import lazy_gettext as _l
from wtforms import BooleanField, DateField, DecimalField, PasswordField, StringField, SubmitField, TextAreaField
from wtforms.validators import Length, NumberRange, Optional


class RebrickableSettingsForm(FlaskForm):
    rebrickable_username = StringField(
        _l("Rebrickable-Benutzername (optional)"), validators=[Optional(), Length(max=120)]
    )
    api_key = PasswordField(
        _l("Dein persönlicher Rebrickable API-Key"), validators=[Optional(), Length(max=255)]
    )
    user_token = PasswordField(
        _l("Dein persönlicher Rebrickable User Token"), validators=[Optional(), Length(max=255)]
    )
    rebrickable_login = StringField(
        _l("Rebrickable-Benutzername oder E-Mail"), validators=[Optional(), Length(max=255)]
    )
    rebrickable_password = PasswordField(
        _l("Rebrickable-Passwort"), validators=[Optional(), Length(max=255)]
    )
    clear_api_key = BooleanField(_l("Gespeicherten persönlichen API-Key entfernen"))
    clear_user_token = BooleanField(_l("Gespeicherten User Token entfernen"))
    save = SubmitField(_l("Einstellungen speichern"))
    test = SubmitField(_l("Verbindung testen"))
    generate_token = SubmitField(_l("User Token automatisch erzeugen"))


class SetNoteForm(FlaskForm):
    note = TextAreaField(_l("Notiz"), validators=[Optional(), Length(max=5000)])
    storage_location = StringField(_l("Lagerort"), validators=[Optional(), Length(max=255)])
    purchase_date = DateField(_l("Kaufdatum"), validators=[Optional()])
    purchase_price = DecimalField(
        _l("Kaufpreis"), validators=[Optional(), NumberRange(min=0, max=9_999_999)], places=2
    )
    is_complete = BooleanField(_l("Set ist vollständig"))
    is_built = BooleanField(_l("Set ist aufgebaut"))
    submit = SubmitField(_l("Lokale Angaben speichern"))
