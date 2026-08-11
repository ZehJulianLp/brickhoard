from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length


class RegistrationForm(FlaskForm):
    username = StringField("Benutzername", validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField("E-Mail-Adresse", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Passwort", validators=[DataRequired(), Length(min=8, max=128)])
    password_repeat = PasswordField(
        "Passwort wiederholen", validators=[DataRequired(), EqualTo("password")]
    )
    submit = SubmitField("Account erstellen")


class LoginForm(FlaskForm):
    identity = StringField("E-Mail-Adresse oder Benutzername", validators=[DataRequired()])
    password = PasswordField("Passwort", validators=[DataRequired()])
    remember = BooleanField("Angemeldet bleiben")
    submit = SubmitField("Anmelden")


class ForgotPasswordForm(FlaskForm):
    email = StringField(
        "E-Mail-Adresse", validators=[DataRequired(), Email(), Length(max=255)]
    )
    submit = SubmitField("Reset-Link anfordern")


class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        "Neues Passwort", validators=[DataRequired(), Length(min=8, max=128)]
    )
    password_repeat = PasswordField(
        "Neues Passwort wiederholen",
        validators=[DataRequired(), EqualTo("password")],
    )
    submit = SubmitField("Passwort speichern")
