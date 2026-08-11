from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, DecimalField, PasswordField, StringField, SubmitField, TextAreaField
from wtforms.validators import Length, NumberRange, Optional


class RebrickableSettingsForm(FlaskForm):
    rebrickable_username = StringField(
        "Rebrickable-Benutzername (optional)", validators=[Optional(), Length(max=120)]
    )
    api_key = PasswordField(
        "Dein persönlicher Rebrickable API-Key", validators=[Optional(), Length(max=255)]
    )
    user_token = PasswordField(
        "Dein persönlicher Rebrickable User Token", validators=[Optional(), Length(max=255)]
    )
    rebrickable_login = StringField(
        "Rebrickable-Benutzername oder E-Mail", validators=[Optional(), Length(max=255)]
    )
    rebrickable_password = PasswordField(
        "Rebrickable-Passwort", validators=[Optional(), Length(max=255)]
    )
    clear_api_key = BooleanField("Gespeicherten persönlichen API-Key entfernen")
    clear_user_token = BooleanField("Gespeicherten User Token entfernen")
    save = SubmitField("Einstellungen speichern")
    test = SubmitField("Verbindung testen")
    generate_token = SubmitField("User Token automatisch erzeugen")


class SetNoteForm(FlaskForm):
    note = TextAreaField("Notiz", validators=[Optional(), Length(max=5000)])
    storage_location = StringField("Lagerort", validators=[Optional(), Length(max=255)])
    purchase_date = DateField("Kaufdatum", validators=[Optional()])
    purchase_price = DecimalField(
        "Kaufpreis", validators=[Optional(), NumberRange(min=0, max=9_999_999)], places=2
    )
    is_complete = BooleanField("Set ist vollständig")
    is_built = BooleanField("Set ist aufgebaut")
    submit = SubmitField("Lokale Angaben speichern")
