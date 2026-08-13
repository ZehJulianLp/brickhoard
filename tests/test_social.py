from app.extensions import db
from app.models import (
    CachedInventoryPart,
    Friendship,
    PartOffer,
    ProjectShare,
    SetNote,
    SetPartProgress,
    User,
    utcnow,
)


def _create_friend(app, username="freund", email="freund@example.com"):
    with app.app_context():
        friend = User(username=username, email=email, email_verified_at=utcnow())
        friend.set_password("freund-passwort")
        db.session.add(friend)
        db.session.commit()
        return friend.id


def _login(client, identity, password):
    client.post("/logout")
    return client.post("/login", data={"identity": identity, "password": password})


def test_friend_request_acceptance_and_notification(logged_in_client, app, user):
    friend_id = _create_friend(app)
    response = logged_in_client.post(
        "/social/friends/request",
        data={"identity": "freund"},
        follow_redirects=True,
    )
    assert "Freundschaftsanfrage an freund gesendet" in response.text
    with app.app_context():
        friendship = db.session.scalar(db.select(Friendship))
        assert friendship.requester_id == user
        assert friendship.addressee_id == friend_id
        friendship_id = friendship.id
        outbox = app.extensions["mail_outbox"]
        assert "möchte dich auf BrickHoard hinzufügen" in outbox[-1]["Subject"]

    _login(logged_in_client, "freund", "freund-passwort")
    accepted = logged_in_client.post(
        f"/social/friends/{friendship_id}/accept", follow_redirects=True
    )
    assert "seid jetzt Freunde" in accepted.text
    with app.app_context():
        assert db.session.get(Friendship, friendship_id).status == "accepted"


def test_project_share_sends_mail_and_collaborator_writes_owner_progress(
    client, app, user
):
    friend_id = _create_friend(app)
    with app.app_context():
        db.session.add(
            Friendship(
                requester_id=user, addressee_id=friend_id, status="accepted"
            )
        )
        db.session.commit()
    _login(client, "sammler", "sicheres-passwort")
    shared = client.post(
        "/social/projects/share",
        data={"friend_id": friend_id, "set_number": "1000-1", "permission": "edit"},
        follow_redirects=True,
    )
    assert "geteilt und per E-Mail angekündigt" in shared.text
    with app.app_context():
        share = db.session.scalar(db.select(ProjectShare))
        assert share.permission == "edit"
        assert "teilt LEGO-Set 1000-1" in app.extensions["mail_outbox"][-1]["Subject"]

    _login(client, "freund", "freund-passwort")
    saved = client.post(
        f"/sets/1000-1/parts/progress?owner={user}",
        json={
            "item_key": "inventory:1",
            "required_quantity": 4,
            "found_quantity": 2,
            "status": "pending",
        },
    )
    assert saved.status_code == 200
    state = client.get(f"/sets/1000-1/parts/progress/state?owner={user}")
    assert state.status_code == 200
    assert state.json["items"][0]["found_quantity"] == 2
    with app.app_context():
        progress = db.session.scalar(db.select(SetPartProgress))
        assert progress.user_id == user
        assert progress.found_quantity == 2


def test_view_only_share_cannot_change_progress(client, app, user):
    friend_id = _create_friend(app)
    with app.app_context():
        db.session.add_all(
            [
                Friendship(requester_id=user, addressee_id=friend_id, status="accepted"),
                ProjectShare(owner_id=user, shared_with_id=friend_id, set_number="1000-1", permission="view"),
            ]
        )
        db.session.commit()
    _login(client, "freund", "freund-passwort")
    response = client.post(
        f"/sets/1000-1/parts/progress?owner={user}",
        json={"item_key": "inventory:1", "required_quantity": 1, "found_quantity": 1},
    )
    assert response.status_code == 403


def test_shared_project_hides_private_set_notes(client, app, user):
    friend_id = _create_friend(app)
    with app.app_context():
        db.session.add_all(
            [
                Friendship(requester_id=user, addressee_id=friend_id, status="accepted"),
                ProjectShare(owner_id=user, shared_with_id=friend_id, set_number="1000-1", permission="view"),
                SetNote(user_id=user, set_number="1000-1", note="streng privat", storage_location="Keller"),
            ]
        )
        db.session.commit()
    _login(client, "freund", "freund-passwort")
    response = client.get(f"/sets/1000-1?owner={user}")
    assert response.status_code == 200
    assert "Geteiltes Projekt von sammler" in response.text
    assert "streng privat" not in response.text
    assert "Keller" not in response.text


def test_public_profile_is_opt_in(logged_in_client, client, app, user):
    assert client.get("/u/sammler").status_code == 404
    logged_in_client.post(
        "/social/profile",
        data={"bio": "Technic und Weltraum", "profile_is_public": "1"},
    )
    logged_in_client.post("/logout")
    profile = client.get("/u/sammler")
    assert profile.status_code == 200
    assert "Technic und Weltraum" in profile.text


def test_friend_can_offer_a_missing_part(client, app, user):
    friend_id = _create_friend(app)
    with app.app_context():
        db.session.add_all(
            [
                Friendship(requester_id=user, addressee_id=friend_id, status="accepted"),
                ProjectShare(owner_id=user, shared_with_id=friend_id, set_number="1000-1", permission="view"),
                CachedInventoryPart(
                    set_number="1000-1",
                    item_key="inventory:1",
                    part_number="3001",
                    part_name="Brick 2 x 4",
                    color_name="Rot",
                    required_quantity=4,
                    is_spare=False,
                    type_group="Steine",
                ),
                SetPartProgress(
                    user_id=user,
                    set_number="1000-1",
                    item_key="inventory:1",
                    required_quantity=4,
                    found_quantity=1,
                ),
            ]
        )
        db.session.commit()
    _login(client, "freund", "freund-passwort")
    response = client.post(
        "/social/parts/offer",
        data={
            "owner_id": user,
            "set_number": "1000-1",
            "item_key": "inventory:1",
            "quantity": 2,
            "message": "Bringe ich mit",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        offer = db.session.scalar(db.select(PartOffer))
        assert offer.quantity == 2
        assert offer.message == "Bringe ich mit"
