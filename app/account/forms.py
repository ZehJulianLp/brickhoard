from flask_wtf import FlaskForm
from flask_babel import lazy_gettext as _l
from flask_wtf.file import FileField
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length


class ProfileForm(FlaskForm):
    username = StringField(
        _l("Benutzername"), validators=[DataRequired(), Length(min=3, max=80)]
    )
    email = StringField(
        _l("E-Mail-Adresse"), validators=[DataRequired(), Email(), Length(max=255)]
    )
    submit = SubmitField(_l("Profildaten speichern"))


class ProfilePictureForm(FlaskForm):
    picture = FileField(_l("Neues Profilbild"))
    upload = SubmitField(_l("Profilbild speichern"))
    remove = SubmitField(_l("Profilbild entfernen"))


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField(_l("Aktuelles Passwort"), validators=[DataRequired()])
    new_password = PasswordField(
        _l("Neues Passwort"), validators=[DataRequired(), Length(min=8, max=128)]
    )
    new_password_repeat = PasswordField(
        _l("Neues Passwort wiederholen"),
        validators=[DataRequired(), EqualTo("new_password")],
    )
    submit = SubmitField(_l("Passwort ändern"))


class DeleteAccountForm(FlaskForm):
    current_password = PasswordField(_l("Aktuelles Passwort"), validators=[DataRequired()])
    username_confirmation = StringField(
        _l("Benutzername zur Bestätigung"), validators=[DataRequired()]
    )
    confirmation = BooleanField(
        _l("Ich verstehe, dass meine lokalen Daten unwiderruflich gelöscht werden."),
        validators=[DataRequired()],
    )
    submit = SubmitField(_l("Konto endgültig löschen"))
