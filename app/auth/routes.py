from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

from flask import current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, or_

from app.auth import bp
from app.auth.forms import (
    ForgotPasswordForm,
    LoginForm,
    RegistrationForm,
    ResetPasswordForm,
)
from app.extensions import db
from app.models import User, utcnow
from app.services.mail import AccountTokenError, MailService, MailServiceError


def _is_safe_next_url(target: str) -> bool:
    host_url = urlparse(request.host_url)
    redirect_url = urlparse(urljoin(request.host_url, target))
    return redirect_url.scheme in {"http", "https"} and host_url.netloc == redirect_url.netloc


def _send_confirmation(user: User) -> None:
    mailer = MailService()
    token = mailer.create_confirmation_token(user)
    path = url_for("auth.confirm_email", token=token)
    mailer.send_confirmation(user, path)


def _send_password_reset(user: User) -> None:
    mailer = MailService()
    token = mailer.create_password_reset_token(user)
    path = url_for("auth.reset_password", token=token)
    mailer.send_password_reset(user, path)


def _cooldown_active(last_sent_at: datetime | None) -> bool:
    if last_sent_at is None:
        return False
    if last_sent_at.tzinfo is None:
        last_sent_at = last_sent_at.replace(tzinfo=timezone.utc)
    return utcnow() - last_sent_at < timedelta(
        seconds=current_app.config["MAIL_RESEND_COOLDOWN"]
    )


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    form = RegistrationForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        email = form.email.data.strip().lower()
        duplicate = db.session.scalar(
            db.select(User).where(
                or_(func.lower(User.username) == username.lower(), User.email == email)
            )
        )
        if duplicate:
            if duplicate.email == email:
                form.email.errors.append("Diese E-Mail-Adresse ist bereits registriert.")
            else:
                form.username.errors.append("Dieser Benutzername ist bereits vergeben.")
        else:
            is_first_user = not db.session.scalar(db.select(User.id).limit(1))
            user = User(
                username=username,
                email=email,
                is_admin=is_first_user,
                onboarding_pending=True,
                email_verified_at=None,
                preferred_locale=session.get("locale", current_app.config["BABEL_DEFAULT_LOCALE"]),
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            try:
                _send_confirmation(user)
                user.confirmation_sent_at = utcnow()
                db.session.commit()
                flash(
                    "Dein Account wurde erstellt. Bitte bestätige deine E-Mail-Adresse.",
                    "success",
                )
            except MailServiceError as error:
                flash(
                    f"Dein Account wurde erstellt. {error} Melde dich an, um die Mail erneut anzufordern.",
                    "warning",
                )
            return redirect(url_for("auth.login"))
    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        identity = form.identity.data.strip().lower()
        user = db.session.scalar(
            db.select(User).where(
                or_(func.lower(User.username) == identity, User.email == identity)
            )
        )
        if user and user.is_enabled and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            selected_locale = session.get("locale")
            if selected_locale in current_app.config["LANGUAGES"] and user.preferred_locale != selected_locale:
                user.preferred_locale = selected_locale
                db.session.commit()
            if user.must_change_password:
                flash("Bitte ändere jetzt dein temporäres Passwort.", "warning")
                return redirect(url_for("account.account_settings"))
            if user.email_verified_at is None:
                return redirect(url_for("auth.verification_required"))
            if user.onboarding_pending:
                return redirect(url_for("account.onboarding", step=1))
            next_url = request.args.get("next")
            if next_url and _is_safe_next_url(next_url):
                return redirect(next_url)
            return redirect(url_for("main.dashboard"))
        flash("Anmeldedaten ungültig. Bitte prüfe deine Eingabe.", "danger")
    return render_template("auth/login.html", form=form)


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("account.account_settings"))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = db.session.scalar(db.select(User).where(User.email == email))
        if user and user.is_enabled:
            if not _cooldown_active(user.password_reset_sent_at):
                try:
                    _send_password_reset(user)
                    user.password_reset_sent_at = utcnow()
                    db.session.commit()
                except MailServiceError:
                    pass
        flash(
            "Falls ein aktives Konto zu dieser Adresse gehört, wurde ein Reset-Link versendet.",
            "info",
        )
        return redirect(url_for("auth.forgot_password"))
    return render_template("auth/forgot_password.html", form=form)


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    if current_user.is_authenticated:
        return redirect(url_for("account.account_settings"))
    mailer = MailService()
    try:
        payload = mailer.read_password_reset_token(token)
    except AccountTokenError as error:
        return render_template("auth/reset_password.html", token_error=str(error)), 400
    user = db.session.get(User, payload["user_id"])
    if user is None or not mailer.password_reset_token_matches(payload, user):
        return render_template(
            "auth/reset_password.html", token_error="Der Link ist ungültig oder wurde bereits verwendet."
        ), 400

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        user.must_change_password = False
        user.email_verified_at = user.email_verified_at or utcnow()
        db.session.commit()
        flash("Dein Passwort wurde geändert. Du kannst dich jetzt anmelden.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", form=form, token_error=None)


@bp.get("/verify-email")
@login_required
def verification_required():
    if current_user.email_verified_at is not None:
        return redirect(url_for("main.dashboard"))
    return render_template("auth/verification_required.html")


@bp.post("/verify-email/resend")
@login_required
def resend_confirmation():
    if current_user.email_verified_at is not None:
        flash("Deine E-Mail-Adresse ist bereits bestätigt.", "info")
        return redirect(url_for("account.account_settings"))
    if _cooldown_active(current_user.confirmation_sent_at):
        flash("Bitte warte kurz, bevor du eine weitere Mail anforderst.", "warning")
        return redirect(url_for("auth.verification_required"))
    try:
        _send_confirmation(current_user)
        current_user.confirmation_sent_at = utcnow()
        db.session.commit()
        flash("Eine neue Bestätigungsmail wurde versendet.", "success")
    except MailServiceError as error:
        flash(str(error), "danger")
    return redirect(url_for("auth.verification_required"))


@bp.get("/verify-email/<token>")
def confirm_email(token: str):
    mailer = MailService()
    try:
        payload = mailer.read_confirmation_token(token)
    except AccountTokenError as error:
        flash(str(error), "danger")
        if current_user.is_authenticated:
            return redirect(url_for("auth.verification_required"))
        return redirect(url_for("auth.login"))

    user = db.session.get(User, payload["user_id"])
    if user is None or payload.get("email") != user.email:
        flash("Der Bestätigungslink ist nicht mehr gültig.", "danger")
        return redirect(url_for("auth.login"))
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
        db.session.commit()
        flash("Deine E-Mail-Adresse wurde bestätigt.", "success")
    else:
        flash("Deine E-Mail-Adresse ist bereits bestätigt.", "info")
    if current_user.is_authenticated and current_user.id == user.id:
        return redirect(
            url_for("account.onboarding", step=1)
            if user.onboarding_pending
            else url_for("main.dashboard")
        )
    return redirect(url_for("auth.login"))


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("Du wurdest abgemeldet.", "info")
    return redirect(url_for("main.index"))
