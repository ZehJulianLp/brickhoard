from __future__ import annotations

import secrets
from functools import wraps

from flask import Response, abort, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import delete, func, or_

from app.admin import bp
from app.admin.forms import AdminUserActionForm
from app.extensions import db
from app.models import Friendship, PartOffer, ProjectShare, SetPartProgress, User, utcnow
from app.services.mail import MailService, MailServiceError


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def _form_user() -> User:
    form = AdminUserActionForm()
    if not form.validate_on_submit():
        abort(400)
    user = db.session.get(User, int(form.user_id.data))
    if user is None:
        abort(404)
    return user


@bp.get("/users")
@admin_required
def users():
    all_users = list(db.session.scalars(db.select(User).order_by(User.username)))
    return render_template(
        "admin/users.html", users=all_users, action_form=AdminUserActionForm()
    )


@bp.get("/users/<int:user_id>/profile-picture")
@admin_required
def user_profile_picture(user_id: int):
    user = db.session.get(User, user_id)
    if user is None or not user.profile_picture:
        abort(404)
    response = Response(user.profile_picture, mimetype="image/webp")
    response.headers["Cache-Control"] = "private, max-age=86400"
    if user.profile_picture_updated_at:
        response.last_modified = user.profile_picture_updated_at
        response.make_conditional(request)
    return response


@bp.post("/users/toggle-enabled")
@admin_required
def toggle_enabled():
    user = _form_user()
    if user.id == current_user.id:
        flash("Du kannst dein eigenes Administratorkonto nicht sperren.", "danger")
    else:
        user.is_enabled = not user.is_enabled
        db.session.commit()
        flash(
            f"Das Konto {user.username} wurde {'aktiviert' if user.is_enabled else 'gesperrt'}.",
            "success",
        )
    return redirect(url_for("admin.users"))


@bp.post("/users/toggle-admin")
@admin_required
def toggle_admin():
    user = _form_user()
    if user.id == current_user.id:
        flash("Eigene Adminrechte können hier nicht entfernt werden.", "danger")
    elif user.is_admin and db.session.scalar(
        db.select(func.count(User.id)).where(User.is_admin.is_(True))
    ) <= 1:
        flash("Der letzte Administrator kann nicht herabgestuft werden.", "danger")
    else:
        user.is_admin = not user.is_admin
        db.session.commit()
        flash(
            f"Adminrechte für {user.username} wurden {'erteilt' if user.is_admin else 'entzogen'}.",
            "success",
        )
    return redirect(url_for("admin.users"))


@bp.post("/users/reset-password")
@admin_required
def reset_password():
    user = _form_user()
    temporary_password = secrets.token_urlsafe(14)
    user.set_password(temporary_password)
    user.must_change_password = True
    user.is_enabled = True
    db.session.commit()
    response = make_response(
        render_template(
            "admin/reset_password.html",
            target_user=user,
            temporary_password=temporary_password,
        )
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


@bp.post("/users/send-password-reset")
@admin_required
def send_password_reset():
    user = _form_user()
    mailer = MailService()
    token = mailer.create_password_reset_token(user)
    try:
        mailer.send_password_reset(
            user, url_for("auth.reset_password", token=token)
        )
        user.password_reset_sent_at = utcnow()
        db.session.commit()
        flash(f"Ein Passwort-Reset-Link wurde an {user.email} versendet.", "success")
    except MailServiceError as error:
        flash(str(error), "danger")
    return redirect(url_for("admin.users"))


@bp.post("/users/send-verification")
@admin_required
def send_verification():
    user = _form_user()
    if user.email_verified_at is not None:
        flash(f"Die E-Mail-Adresse von {user.username} ist bereits bestätigt.", "info")
    else:
        mailer = MailService()
        token = mailer.create_confirmation_token(user)
        try:
            mailer.send_confirmation(
                user, url_for("auth.confirm_email", token=token)
            )
            user.confirmation_sent_at = utcnow()
            db.session.commit()
            flash(f"Eine Bestätigungsmail wurde an {user.email} versendet.", "success")
        except MailServiceError as error:
            flash(str(error), "danger")
    return redirect(url_for("admin.users"))


@bp.post("/users/mark-email-verified")
@admin_required
def mark_email_verified():
    user = _form_user()
    user.email_verified_at = utcnow()
    db.session.commit()
    flash(f"Die E-Mail-Adresse von {user.username} wurde bestätigt.", "success")
    return redirect(url_for("admin.users"))


@bp.post("/users/delete")
@admin_required
def delete_user():
    user = _form_user()
    if user.id == current_user.id:
        flash("Das eigene Konto löschst du in deinen Kontoeinstellungen.", "danger")
        return redirect(url_for("admin.users"))
    if user.is_admin and db.session.scalar(
        db.select(func.count(User.id)).where(User.is_admin.is_(True))
    ) <= 1:
        flash("Der letzte Administrator kann nicht gelöscht werden.", "danger")
        return redirect(url_for("admin.users"))
    username = user.username
    db.session.execute(delete(PartOffer).where(or_(PartOffer.project_owner_id == user.id, PartOffer.offered_by_id == user.id)))
    db.session.execute(delete(ProjectShare).where(or_(ProjectShare.owner_id == user.id, ProjectShare.shared_with_id == user.id)))
    db.session.execute(delete(Friendship).where(or_(Friendship.requester_id == user.id, Friendship.addressee_id == user.id)))
    db.session.execute(
        delete(SetPartProgress).where(SetPartProgress.user_id == user.id)
    )
    db.session.delete(user)
    db.session.commit()
    flash(f"Das Konto {username} wurde gelöscht.", "info")
    return redirect(url_for("admin.users"))
