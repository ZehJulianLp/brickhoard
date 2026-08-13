from io import BytesIO

from flask import Response, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import delete, func, or_

from app.account import bp
from app.account.forms import ChangePasswordForm, DeleteAccountForm, ProfileForm, ProfilePictureForm
from app.extensions import db
from app.models import SetPartProgress, User, utcnow
from app.services.mail import MailService, MailServiceError
from app.services.rebrickable import RebrickableAPIError, RebrickableService
from app.sets.forms import RebrickableSettingsForm


ONBOARDING_STEPS = {
    1: {
        "eyebrow": "Willkommen bei BrickHoard",
        "title": "Dein Konto ist startklar",
        "lead": "In wenigen Schritten lernst du die wichtigsten Funktionen kennen.",
        "symbol": "✓",
    },
    2: {
        "eyebrow": "Deine Sammlung verbinden",
        "title": "Rebrickable einrichten",
        "lead": "BrickHoard liest deine privaten Setlisten über deinen eigenen Rebrickable-Zugang.",
        "symbol": "↻",
    },
    3: {
        "eyebrow": "Sets auswählen",
        "title": "Deine Setlisten öffnen",
        "lead": "Nach der Verbindung findest du alle Listen und Sets direkt in BrickHoard.",
        "symbol": "▦",
    },
    4: {
        "eyebrow": "Loslegen",
        "title": "Teile prüfen und sortieren",
        "lead": "Für jedes Set stehen dir Checkliste, Großsortierung und Fehlteile-Übersicht zur Verfügung.",
        "symbol": "◆",
    },
}


@bp.get("/setup")
@bp.route("/setup/<int:step>", methods=["GET", "POST"])
@login_required
def onboarding(step: int = 1):
    if step not in ONBOARDING_STEPS:
        abort(404)
    rebrickable_form = None
    if step == 2:
        rebrickable_form = RebrickableSettingsForm()
        if rebrickable_form.validate_on_submit():
            api_key = (
                rebrickable_form.api_key.data.strip()
                if rebrickable_form.api_key.data
                else None
            )
            user_token = (
                rebrickable_form.user_token.data.strip()
                if rebrickable_form.user_token.data
                else None
            )
            effective_api_key = (
                api_key
                or current_user.rebrickable_api_key
                or current_app.config.get("REBRICKABLE_API_KEY", "")
            )
            login_name = (
                rebrickable_form.rebrickable_login.data.strip()
                if rebrickable_form.rebrickable_login.data
                else ""
            )
            password = rebrickable_form.rebrickable_password.data or ""

            if not effective_api_key:
                flash("Bitte trage deinen Rebrickable API-Key ein.", "warning")
            elif user_token:
                try:
                    profile = RebrickableService(
                        effective_api_key, user_token
                    ).test_connection()
                    if api_key:
                        current_user.rebrickable_api_key = api_key
                    current_user.rebrickable_user_token = user_token
                    current_user.rebrickable_username = (
                        login_name or profile.get("username") or None
                    )
                    db.session.commit()
                    flash("Rebrickable-Verbindung erfolgreich gespeichert.", "success")
                    return redirect(url_for("account.onboarding", step=3))
                except RebrickableAPIError as error:
                    flash(str(error), "danger")
            elif login_name and password:
                try:
                    generated_token = RebrickableService(
                        effective_api_key
                    ).generate_user_token(login_name, password)
                    if api_key:
                        current_user.rebrickable_api_key = api_key
                    current_user.rebrickable_user_token = generated_token
                    current_user.rebrickable_username = login_name
                    db.session.commit()
                    flash(
                        "User Token automatisch erzeugt und sicher gespeichert. Dein Rebrickable-Passwort wurde verworfen.",
                        "success",
                    )
                    return redirect(url_for("account.onboarding", step=3))
                except RebrickableAPIError as error:
                    flash(str(error), "danger")
            else:
                flash(
                    "Trage Rebrickable-Login und Passwort ein oder nutze optional einen vorhandenen User Token.",
                    "warning",
                )
    return render_template(
        "account/onboarding.html",
        step=step,
        total_steps=len(ONBOARDING_STEPS),
        setup=ONBOARDING_STEPS[step],
        rebrickable_form=rebrickable_form,
        has_api_key=bool(current_user.rebrickable_api_key),
        has_global_api_key=bool(current_app.config.get("REBRICKABLE_API_KEY")),
        has_token=bool(current_user.rebrickable_user_token),
    )


@bp.post("/setup/finish")
@login_required
def finish_onboarding():
    user = db.session.get(User, current_user.id)
    user.onboarding_pending = False
    db.session.commit()
    flash("Setup abgeschlossen. Willkommen in deinem BrickHoard-Dashboard!", "success")
    return redirect(url_for("main.dashboard"))


@bp.route("/settings/account", methods=["GET", "POST"])
@login_required
def account_settings():
    profile_form = ProfileForm(obj=current_user)
    picture_form = ProfilePictureForm()
    password_form = ChangePasswordForm()
    delete_form = DeleteAccountForm()
    if profile_form.validate_on_submit():
        username = profile_form.username.data.strip()
        email = profile_form.email.data.strip().lower()
        duplicate = db.session.scalar(
            db.select(User).where(
                User.id != current_user.id,
                or_(
                    func.lower(User.username) == username.lower(),
                    User.email == email,
                ),
            )
        )
        if duplicate:
            flash("Benutzername oder E-Mail-Adresse wird bereits verwendet.", "danger")
        else:
            email_changed = current_user.email != email
            current_user.username = username
            current_user.email = email
            if email_changed:
                current_user.email_verified_at = None
            db.session.commit()
            if email_changed:
                try:
                    mailer = MailService()
                    token = mailer.create_confirmation_token(current_user)
                    mailer.send_confirmation(
                        current_user,
                        url_for("auth.confirm_email", token=token),
                    )
                    current_user.confirmation_sent_at = utcnow()
                    db.session.commit()
                    flash(
                        "Deine Kontodaten wurden gespeichert. Bitte bestätige die neue E-Mail-Adresse.",
                        "success",
                    )
                except MailServiceError as error:
                    flash(
                        f"Deine Kontodaten wurden gespeichert. {error}", "warning"
                    )
            else:
                flash("Deine Kontodaten wurden gespeichert.", "success")
            return redirect(url_for("account.account_settings"))
    return render_template(
        "account/settings.html",
        profile_form=profile_form,
        picture_form=picture_form,
        password_form=password_form,
        delete_form=delete_form,
    )


@bp.post("/settings/account/profile-picture")
@login_required
def update_profile_picture():
    form = ProfilePictureForm()
    if not form.validate_on_submit():
        flash("Das Profilbild konnte nicht verarbeitet werden.", "danger")
        return redirect(url_for("account.account_settings"))
    if form.remove.data:
        current_user.profile_picture = None
        current_user.profile_picture_updated_at = None
        db.session.commit()
        flash("Dein Profilbild wurde entfernt.", "info")
        return redirect(url_for("account.account_settings"))

    upload = form.picture.data
    if upload is None or not upload.filename:
        flash("Bitte wähle zuerst ein Bild aus.", "warning")
        return redirect(url_for("account.account_settings"))
    raw = upload.read(current_app.config["MAX_PROFILE_PICTURE_SIZE"] + 1)
    if len(raw) > current_app.config["MAX_PROFILE_PICTURE_SIZE"]:
        flash("Das Profilbild darf höchstens 5 MB groß sein.", "danger")
        return redirect(url_for("account.account_settings"))
    try:
        with Image.open(BytesIO(raw)) as source:
            source.verify()
        with Image.open(BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image = ImageOps.fit(image, (512, 512), method=Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="WEBP", quality=86, method=6)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        flash("Bitte lade ein gültiges JPG-, PNG- oder WebP-Bild hoch.", "danger")
        return redirect(url_for("account.account_settings"))

    current_user.profile_picture = output.getvalue()
    current_user.profile_picture_updated_at = utcnow()
    db.session.commit()
    flash("Dein Profilbild wurde gespeichert.", "success")
    return redirect(url_for("account.account_settings"))


@bp.get("/profile-picture")
@login_required
def profile_picture():
    if not current_user.profile_picture:
        abort(404)
    response = Response(current_user.profile_picture, mimetype="image/webp")
    response.headers["Cache-Control"] = "private, max-age=86400"
    if current_user.profile_picture_updated_at:
        response.last_modified = current_user.profile_picture_updated_at
        response.make_conditional(request)
    return response


@bp.post("/settings/account/password")
@login_required
def change_password():
    form = ChangePasswordForm()
    if not form.validate_on_submit():
        flash("Bitte prüfe die Eingaben für das neue Passwort.", "danger")
    elif not current_user.check_password(form.current_password.data):
        flash("Das aktuelle Passwort ist nicht korrekt.", "danger")
    elif current_user.check_password(form.new_password.data):
        flash("Das neue Passwort muss sich vom aktuellen Passwort unterscheiden.", "warning")
    else:
        current_user.set_password(form.new_password.data)
        current_user.must_change_password = False
        db.session.commit()
        flash("Dein Passwort wurde geändert.", "success")
    return redirect(url_for("account.account_settings"))


@bp.post("/settings/account/delete")
@login_required
def delete_account():
    form = DeleteAccountForm()
    if not form.validate_on_submit():
        flash("Die Löschbestätigung ist unvollständig.", "danger")
        return redirect(url_for("account.account_settings"))
    if not current_user.check_password(form.current_password.data):
        flash("Das aktuelle Passwort ist nicht korrekt.", "danger")
        return redirect(url_for("account.account_settings"))
    if form.username_confirmation.data.strip() != current_user.username:
        flash("Der eingegebene Benutzername stimmt nicht überein.", "danger")
        return redirect(url_for("account.account_settings"))
    if (
        current_user.is_admin
        and db.session.scalar(
            db.select(func.count(User.id)).where(User.is_admin.is_(True))
        )
        <= 1
        and db.session.scalar(db.select(func.count(User.id))) > 1
    ):
        flash(
            "Du bist der letzte Administrator. Übertrage zuerst einem anderen Konto Adminrechte.",
            "danger",
        )
        return redirect(url_for("account.account_settings"))
    user_id = current_user.id
    user = db.session.get(User, user_id)
    db.session.execute(
        delete(SetPartProgress).where(SetPartProgress.user_id == user_id)
    )
    logout_user()
    db.session.delete(user)
    db.session.commit()
    flash("Dein BrickHoard-Konto und alle lokalen Benutzerdaten wurden gelöscht.", "info")
    return redirect(url_for("main.index"))
