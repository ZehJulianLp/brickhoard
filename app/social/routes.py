from __future__ import annotations

import re

from flask import Response, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import and_, delete, func, or_

from app.extensions import db
from app.models import (
    CachedInventoryPart,
    Friendship,
    PartOffer,
    ProjectShare,
    SetPartProgress,
    User,
)
from app.services.mail import MailService, MailServiceError
from app.social import bp


def _friendship_between(first_id: int, second_id: int) -> Friendship | None:
    return db.session.scalar(
        db.select(Friendship).where(
            or_(
                and_(Friendship.requester_id == first_id, Friendship.addressee_id == second_id),
                and_(Friendship.requester_id == second_id, Friendship.addressee_id == first_id),
            )
        )
    )


def _accepted_friends(user_id: int) -> list[User]:
    friendships = list(
        db.session.scalars(
            db.select(Friendship).where(
                Friendship.status == "accepted",
                or_(Friendship.requester_id == user_id, Friendship.addressee_id == user_id),
            )
        )
    )
    return sorted((friendship.other_user(user_id) for friendship in friendships), key=lambda user: user.username.lower())


@bp.get("/social")
@login_required
def center():
    incoming_requests = list(
        db.session.scalars(
            db.select(Friendship)
            .where(Friendship.addressee_id == current_user.id, Friendship.status == "pending")
            .order_by(Friendship.created_at.desc())
        )
    )
    outgoing_requests = list(
        db.session.scalars(
            db.select(Friendship)
            .where(Friendship.requester_id == current_user.id, Friendship.status == "pending")
            .order_by(Friendship.created_at.desc())
        )
    )
    outgoing_shares = list(
        db.session.scalars(
            db.select(ProjectShare)
            .where(ProjectShare.owner_id == current_user.id)
            .order_by(ProjectShare.created_at.desc())
        )
    )
    incoming_shares = list(
        db.session.scalars(
            db.select(ProjectShare)
            .where(ProjectShare.shared_with_id == current_user.id)
            .order_by(ProjectShare.created_at.desc())
        )
    )
    offers_received = list(
        db.session.scalars(
            db.select(PartOffer)
            .where(PartOffer.project_owner_id == current_user.id)
            .order_by(PartOffer.created_at.desc())
        )
    )
    return render_template(
        "social/center.html",
        friends=_accepted_friends(current_user.id),
        incoming_requests=incoming_requests,
        outgoing_requests=outgoing_requests,
        outgoing_shares=outgoing_shares,
        incoming_shares=incoming_shares,
        offers_received=offers_received,
    )


@bp.get("/social/users/search")
@login_required
def search_users():
    query = (request.args.get("q") or "").strip()[:80]
    if len(query) < 2:
        return jsonify({"results": []})
    escaped_query = (
        query.lower()
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    users = list(
        db.session.scalars(
            db.select(User)
            .where(
                User.id != current_user.id,
                User.is_enabled.is_(True),
                User.email_verified_at.is_not(None),
                func.lower(User.username).like(f"%{escaped_query}%", escape="\\"),
            )
            .order_by(User.username)
            .limit(12)
        )
    )
    results = []
    for user in users:
        friendship = _friendship_between(current_user.id, user.id)
        if friendship is None:
            state = "available"
        elif friendship.status == "accepted":
            state = "friends"
        elif friendship.requester_id == current_user.id:
            state = "outgoing"
        else:
            state = "incoming"
        results.append({"username": user.username, "state": state})
    return jsonify({"results": results})


@bp.post("/social/friends/request")
@login_required
def request_friend():
    username = (request.form.get("username") or "").strip().lower()
    target = db.session.scalar(
        db.select(User).where(
            User.is_enabled.is_(True),
            User.email_verified_at.is_not(None),
            func.lower(User.username) == username,
        )
    )
    if target is None:
        flash("Kein BrickHoard-Konto mit diesem Benutzernamen gefunden.", "warning")
    elif target.id == current_user.id:
        flash("Du kannst dich nicht selbst als Freund hinzufügen.", "warning")
    elif _friendship_between(current_user.id, target.id):
        flash("Zwischen euch besteht bereits eine Anfrage oder Freundschaft.", "info")
    else:
        friendship = Friendship(requester_id=current_user.id, addressee_id=target.id)
        db.session.add(friendship)
        db.session.commit()
        try:
            MailService().send_friend_request(
                target,
                current_user,
                url_for("social.center"),
            )
            flash(f"Freundschaftsanfrage an {target.username} gesendet.", "success")
        except MailServiceError as error:
            flash(f"Anfrage gespeichert. {error}", "warning")
    return redirect(url_for("social.center"))


@bp.post("/social/friends/<int:friendship_id>/<action>")
@login_required
def answer_friend(friendship_id: int, action: str):
    friendship = db.session.get(Friendship, friendship_id)
    if friendship is None or friendship.addressee_id != current_user.id or friendship.status != "pending":
        abort(404)
    if action == "accept":
        friendship.status = "accepted"
        db.session.commit()
        flash(f"Du und {friendship.requester.username} seid jetzt Freunde.", "success")
    elif action == "decline":
        db.session.delete(friendship)
        db.session.commit()
        flash("Anfrage abgelehnt.", "info")
    else:
        abort(404)
    return redirect(url_for("social.center"))


@bp.post("/social/friends/<int:user_id>/remove")
@login_required
def remove_friend(user_id: int):
    friendship = _friendship_between(current_user.id, user_id)
    if friendship is None or friendship.status != "accepted":
        abort(404)
    db.session.execute(
        delete(ProjectShare).where(
            or_(
                and_(ProjectShare.owner_id == current_user.id, ProjectShare.shared_with_id == user_id),
                and_(ProjectShare.owner_id == user_id, ProjectShare.shared_with_id == current_user.id),
            )
        )
    )
    db.session.delete(friendship)
    db.session.commit()
    flash("Freundschaft und gegenseitige Projektfreigaben wurden entfernt.", "info")
    return redirect(url_for("social.center"))


@bp.post("/social/profile")
@login_required
def update_public_profile():
    bio = (request.form.get("bio") or "").strip()
    if len(bio) > 500:
        flash("Deine Profilbeschreibung darf höchstens 500 Zeichen lang sein.", "danger")
    else:
        current_user.profile_bio = bio or None
        current_user.profile_is_public = request.form.get("profile_is_public") == "1"
        db.session.commit()
        flash("Öffentliches Profil gespeichert.", "success")
    return redirect(url_for("social.center"))


@bp.get("/u/<username>")
def public_profile(username: str):
    user = db.session.scalar(db.select(User).where(func.lower(User.username) == username.lower()))
    if user is None or not user.profile_is_public or not user.is_enabled:
        abort(404)
    progress = list(db.session.scalars(db.select(SetPartProgress).where(SetPartProgress.user_id == user.id)))
    set_numbers = sorted({row.set_number for row in progress})
    complete_sets = sum(
        all(row.required_quantity > 0 and row.found_quantity >= row.required_quantity for row in progress if row.set_number == number)
        for number in set_numbers
    )
    friendship = None
    if current_user.is_authenticated and current_user.id != user.id:
        friendship = _friendship_between(current_user.id, user.id)
    return render_template(
        "social/profile.html",
        profile_user=user,
        project_count=len(set_numbers),
        complete_sets=complete_sets,
        found_parts=sum(min(max(row.found_quantity, 0), max(row.required_quantity, 0)) for row in progress),
        friendship=friendship,
    )


@bp.get("/u/<username>/picture")
def public_profile_picture(username: str):
    user = db.session.scalar(db.select(User).where(func.lower(User.username) == username.lower()))
    if user is None or not user.is_enabled or not user.profile_is_public or not user.profile_picture:
        abort(404)
    return Response(user.profile_picture, mimetype="image/webp", headers={"Cache-Control": "public, max-age=86400"})


@bp.post("/social/projects/share")
@login_required
def share_project():
    friend_id = request.form.get("friend_id", type=int)
    set_number = (request.form.get("set_number") or "").strip()
    permission = request.form.get("permission") or "view"
    friend = db.session.get(User, friend_id) if friend_id else None
    friendship = _friendship_between(current_user.id, friend_id) if friend_id else None
    if not re.fullmatch(r"[A-Za-z0-9-]{1,40}", set_number):
        flash("Bitte gib eine gültige Setnummer ein.", "danger")
    elif friend is None or friendship is None or friendship.status != "accepted":
        flash("Projekte können nur mit bestätigten Freunden geteilt werden.", "danger")
    elif permission not in {"view", "edit"}:
        abort(400)
    else:
        share = db.session.scalar(
            db.select(ProjectShare).where(
                ProjectShare.owner_id == current_user.id,
                ProjectShare.shared_with_id == friend.id,
                ProjectShare.set_number == set_number,
            )
        )
        if share is None:
            share = ProjectShare(owner_id=current_user.id, shared_with_id=friend.id, set_number=set_number)
            db.session.add(share)
        share.permission = permission
        db.session.commit()
        try:
            MailService().send_project_share(
                friend,
                current_user,
                set_number,
                permission,
                url_for("social.open_shared_project", share_id=share.id),
            )
            flash(f"Set {set_number} wurde mit {friend.username} geteilt und per E-Mail angekündigt.", "success")
        except MailServiceError as error:
            flash(f"Projekt geteilt. {error}", "warning")
    return redirect(url_for("social.center"))


@bp.post("/social/projects/<int:share_id>/revoke")
@login_required
def revoke_share(share_id: int):
    share = db.session.get(ProjectShare, share_id)
    if share is None or share.owner_id != current_user.id:
        abort(404)
    db.session.delete(share)
    db.session.commit()
    flash("Projektfreigabe aufgehoben.", "info")
    return redirect(url_for("social.center"))


@bp.get("/social/projects/<int:share_id>")
@login_required
def open_shared_project(share_id: int):
    share = db.session.get(ProjectShare, share_id)
    if share is None or share.shared_with_id != current_user.id:
        abort(404)
    return redirect(url_for("sets.set_detail", set_number=share.set_number, owner=share.owner_id))


@bp.post("/social/parts/offer")
@login_required
def offer_part():
    owner_id = request.form.get("owner_id", type=int)
    set_number = (request.form.get("set_number") or "")[:40]
    item_key = (request.form.get("item_key") or "")[:180]
    quantity = request.form.get("quantity", type=int) or 1
    message = (request.form.get("message") or "").strip()[:500] or None
    share = db.session.scalar(
        db.select(ProjectShare).where(
            ProjectShare.owner_id == owner_id,
            ProjectShare.shared_with_id == current_user.id,
            ProjectShare.set_number == set_number,
        )
    )
    cached = db.session.scalar(
        db.select(CachedInventoryPart).where(
            CachedInventoryPart.set_number == set_number,
            CachedInventoryPart.item_key == item_key,
        )
    )
    progress = db.session.scalar(
        db.select(SetPartProgress).where(
            SetPartProgress.user_id == owner_id,
            SetPartProgress.set_number == set_number,
            SetPartProgress.item_key == item_key,
        )
    )
    missing = max((progress.required_quantity if progress else cached.required_quantity if cached else 0) - (progress.found_quantity if progress else 0), 0)
    if share is None or cached is None or quantity < 1 or quantity > missing:
        abort(400)
    offer = PartOffer(
        project_owner_id=owner_id,
        offered_by_id=current_user.id,
        set_number=set_number,
        item_key=item_key,
        part_number=cached.part_number,
        part_name=cached.part_name,
        color_name=cached.color_name,
        quantity=quantity,
        message=message,
    )
    db.session.add(offer)
    db.session.commit()
    flash("Dein Teileangebot wurde gesendet.", "success")
    return redirect(url_for("sets.missing_parts", set_number=set_number, owner=owner_id))


@bp.post("/social/parts/offers/<int:offer_id>/<action>")
@login_required
def answer_offer(offer_id: int, action: str):
    offer = db.session.get(PartOffer, offer_id)
    if offer is None or offer.project_owner_id != current_user.id or offer.status != "offered":
        abort(404)
    if action not in {"accept", "decline"}:
        abort(404)
    offer.status = "accepted" if action == "accept" else "declined"
    db.session.commit()
    flash("Teileangebot aktualisiert.", "success")
    return redirect(url_for("social.center"))
