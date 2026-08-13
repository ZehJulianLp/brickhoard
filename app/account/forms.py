from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length


class ProfileForm(FlaskForm):
    username = StringField(
        "Benutzername", validators=[DataRequired(), Length(min=3, max=80)]
    )
    email = StringField(
        "E-Mail-Adresse", validators=[DataRequired(), Email(), Length(max=255)]
    )
    submit = SubmitField("Profildaten speichern")


class ProfilePictureForm(FlaskForm):
    picture = FileField("Neues Profilbild")
    upload = SubmitField("Profilbild speichern")
    remove = SubmitField("Profilbild entfernen")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Aktuelles Passwort", validators=[DataRequired()])
    new_password = PasswordField(
        "Neues Passwort", validators=[DataRequired(), Length(min=8, max=128)]
    )
    new_password_repeat = PasswordField(
        "Neues Passwort wiederholen",
        validators=[DataRequired(), EqualTo("new_password")],
    )
    submit = SubmitField("Passwort ändern")


class DeleteAccountForm(FlaskForm):
    current_password = PasswordField("Aktuelles Passwort", validators=[DataRequired()])
    username_confirmation = StringField(
        "Benutzername zur Bestätigung", validators=[DataRequired()]
    )
    confirmation = BooleanField(
        "Ich verstehe, dass meine lokalen Daten unwiderruflich gelöscht werden.",
        validators=[DataRequired()],
    )
    submit = SubmitField("Konto endgültig löschen")
