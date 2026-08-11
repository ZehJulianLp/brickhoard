from flask import flash, redirect, render_template, url_for
from flask_login import current_user, login_required, logout_user
from sqlalchemy import delete, func, or_

from app.account import bp
from app.account.forms import ChangePasswordForm, DeleteAccountForm, ProfileForm
from app.extensions import db
from app.models import SetPartProgress, User, utcnow
from app.services.mail import MailService, MailServiceError


@bp.route("/settings/account", methods=["GET", "POST"])
@login_required
def account_settings():
    profile_form = ProfileForm(obj=current_user)
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
        password_form=password_form,
        delete_form=delete_form,
    )


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
