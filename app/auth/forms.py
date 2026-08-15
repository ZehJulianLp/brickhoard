from flask_wtf import FlaskForm
from flask_babel import lazy_gettext as _l
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length


class RegistrationForm(FlaskForm):
    username = StringField(_l("Benutzername"), validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField(_l("E-Mail-Adresse"), validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField(_l("Passwort"), validators=[DataRequired(), Length(min=8, max=128)])
    password_repeat = PasswordField(
        _l("Passwort wiederholen"), validators=[DataRequired(), EqualTo("password")]
    )
    submit = SubmitField(_l("Account erstellen"))


class LoginForm(FlaskForm):
    identity = StringField(_l("E-Mail-Adresse oder Benutzername"), validators=[DataRequired()])
    password = PasswordField(_l("Passwort"), validators=[DataRequired()])
    remember = BooleanField(_l("Angemeldet bleiben"))
    submit = SubmitField(_l("Anmelden"))


class ForgotPasswordForm(FlaskForm):
    email = StringField(
        _l("E-Mail-Adresse"), validators=[DataRequired(), Email(), Length(max=255)]
    )
    submit = SubmitField(_l("Reset-Link anfordern"))


class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        _l("Neues Passwort"), validators=[DataRequired(), Length(min=8, max=128)]
    )
    password_repeat = PasswordField(
        _l("Neues Passwort wiederholen"),
        validators=[DataRequired(), EqualTo("password")],
    )
    submit = SubmitField(_l("Passwort speichern"))
