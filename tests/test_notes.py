from app.extensions import db
from app.models import CachedInventoryPart, SetNote, SetPartProgress


def test_set_note_is_saved_for_current_user(logged_in_client, app, user):
    response = logged_in_client.post(
        "/sets/10300-1",
        data={
            "note": "Vitrine oben",
            "storage_location": "Regal A3",
            "purchase_date": "2025-02-14",
            "purchase_price": "129.99",
            "is_complete": "y",
            "is_built": "y",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        note = db.session.scalar(
            db.select(SetNote).where(
                SetNote.user_id == user, SetNote.set_number == "10300-1"
            )
        )
        assert note is not None
        assert note.storage_location == "Regal A3"
        assert note.is_complete is True
        assert str(note.purchase_price) == "129.99"


def test_user_cannot_overwrite_another_users_note(logged_in_client, app):
    from app.models import User

    with app.app_context():
        other = User(username="other", email="other@example.com")
        other.set_password("other-password")
        db.session.add(other)
        db.session.flush()
        foreign_note = SetNote(
            user_id=other.id, set_number="10300-1", note="Nicht verändern"
        )
        db.session.add(foreign_note)
        db.session.commit()
        foreign_id = foreign_note.id

    logged_in_client.post("/sets/10300-1", data={"note": "Meine Notiz"})
    with app.app_context():
        assert db.session.get(SetNote, foreign_id).note == "Nicht verändern"


def test_part_check_survives_reload_for_current_user(logged_in_client, app, user):
    response = logged_in_client.post(
        "/sets/10300-1/parts/progress",
        json={"item_key": "inventory:12345", "is_checked": True},
    )
    assert response.status_code == 200
    assert response.get_json() == {
        "saved": True,
        "is_checked": True,
        "found_quantity": 1,
        "status": "found",
    }

    with app.app_context():
        progress = db.session.scalar(
            db.select(SetPartProgress).where(
                SetPartProgress.user_id == user,
                SetPartProgress.set_number == "10300-1",
                SetPartProgress.item_key == "inventory:12345",
            )
        )
        assert progress is not None
        assert progress.is_checked is True


def test_partial_part_quantity_is_saved(logged_in_client, app, user):
    response = logged_in_client.post(
        "/sets/10194-1/parts/progress",
        json={
            "item_key": "inventory:777",
            "found_quantity": 7,
            "required_quantity": 12,
        },
    )
    assert response.status_code == 200
    assert response.get_json()["is_checked"] is False
    with app.app_context():
        progress = db.session.scalar(
            db.select(SetPartProgress).where(
                SetPartProgress.user_id == user,
                SetPartProgress.set_number == "10194-1",
            )
        )
        assert progress.found_quantity == 7


def test_bulk_check_and_uncheck(logged_in_client, app, user):
    items = [
        {
            "item_key": "inventory:bulk-1",
            "found_quantity": 4,
            "required_quantity": 4,
            "status": "found",
        },
        {
            "item_key": "inventory:bulk-2",
            "found_quantity": 2,
            "required_quantity": 2,
            "status": "found",
        },
    ]
    response = logged_in_client.post(
        "/sets/4559-1/parts/progress/bulk", json={"items": items}
    )
    assert response.status_code == 200
    assert response.get_json()["count"] == 2
    with app.app_context():
        rows = list(
            db.session.scalars(
                db.select(SetPartProgress).where(
                    SetPartProgress.user_id == user,
                    SetPartProgress.set_number == "4559-1",
                )
            )
        )
        assert all(row.is_checked for row in rows)

    for item in items:
        item["found_quantity"] = 0
        item["status"] = "pending"
    logged_in_client.post("/sets/4559-1/parts/progress/bulk", json={"items": items})
    with app.app_context():
        assert all(
            row.found_quantity == 0
            for row in db.session.scalars(
                db.select(SetPartProgress).where(
                    SetPartProgress.user_id == user,
                    SetPartProgress.set_number == "4559-1",
                )
            )
        )


def test_all_missing_parts_are_aggregated_across_sets(logged_in_client, app, user):
    with app.app_context():
        for set_number, required, found in [("SET-A", 4, 1), ("SET-B", 3, 1)]:
            db.session.add(
                CachedInventoryPart(
                    set_number=set_number,
                    item_key="part:3001:4:regular",
                    part_number="3001",
                    part_name="Brick 2 x 4",
                    color_name="Red",
                    image_url="https://example.test/3001.png",
                    required_quantity=required,
                    is_spare=False,
                    type_group="Steine",
                )
            )
            db.session.add(
                SetPartProgress(
                    user_id=user,
                    set_number=set_number,
                    item_key="part:3001:4:regular",
                    found_quantity=found,
                    required_quantity=required,
                    status="pending",
                )
            )
        db.session.commit()

    response = logged_in_client.get("/missing?group=color&sort=missing_desc")
    assert response.status_code == 200
    assert "Brick 2 x 4" in response.text
    assert "Gesamt fehlt" in response.text
    assert ">5<" in response.text
    assert "SET-A" in response.text and "SET-B" in response.text

    csv_response = logged_in_client.get("/missing.csv")
    assert csv_response.status_code == 200
    assert ";5;" in csv_response.text


def test_part_status_note_and_dashboard_resume_are_saved(logged_in_client, app, user):
    response = logged_in_client.post(
        "/sets/4559-1/parts/progress",
        json={
            "item_key": "inventory:88",
            "found_quantity": 1,
            "required_quantity": 4,
            "status": "wrong_color",
            "part_note": "Nur in Blau vorhanden",
        },
    )
    assert response.status_code == 200
    with app.app_context():
        progress = db.session.scalar(
            db.select(SetPartProgress).where(
                SetPartProgress.user_id == user,
                SetPartProgress.set_number == "4559-1",
            )
        )
        assert progress.status == "wrong_color"
        assert progress.part_note == "Nur in Blau vorhanden"
        assert progress.required_quantity == 4

    dashboard = logged_in_client.get("/dashboard")
    assert "Set 4559-1" in dashboard.text
    assert "Weitersortieren" in dashboard.text

    position = logged_in_client.post(
        "/sets/4559-1/sort-position", json={"item_key": "inventory:88"}
    )
    assert position.status_code == 200
    with app.app_context():
        saved_note = db.session.scalar(
            db.select(SetNote).where(
                SetNote.user_id == user, SetNote.set_number == "4559-1"
            )
        )
        assert saved_note.last_sort_item_key == "inventory:88"


def test_missing_parts_csv_contains_only_missing_quantities(
    logged_in_client, app, monkeypatch
):
    app.config["REBRICKABLE_API_KEY"] = "test-key"
    inventory = [
        {
            "id": 44,
            "quantity": 3,
            "part": {
                "part_num": "3001",
                "name": "Brick 2 x 4",
                "part_img_url": "https://example.test/3001.png",
            },
            "color": {"id": 4, "name": "Red"},
            "is_spare": False,
        }
    ]
    monkeypatch.setattr(
        "app.services.rebrickable.RebrickableService.get_set_parts",
        lambda _service, _set_number: inventory,
    )

    response = logged_in_client.get("/sets/10300-1/missing.csv")

    assert response.status_code == 200
    assert "3001" in response.text
    assert "Brick 2 x 4" in response.text
    assert ";3;0;3;" in response.text


def test_set_page_renders_quantity_controls_and_part_images(
    logged_in_client, app, user, monkeypatch
):
    app.config["REBRICKABLE_API_KEY"] = "test-key"
    with app.app_context():
        db.session.add(
            SetPartProgress(
                user_id=user,
                set_number="10194-1",
                item_key="inventory:77",
                found_quantity=7,
            )
        )
        db.session.commit()
    monkeypatch.setattr(
        "app.services.rebrickable.RebrickableService.get_set_details",
        lambda _service, _set_number: {
            "set_num": "10194-1",
            "name": "Emerald Night",
            "theme_id": None,
        },
    )
    monkeypatch.setattr(
        "app.services.rebrickable.RebrickableService.get_set_parts",
        lambda _service, _set_number: [
            {
                "id": 77,
                "quantity": 12,
                "part": {
                    "part_num": "3001",
                    "name": "Brick 2 x 4",
                    "part_img_url": "https://example.test/red-brick.png",
                },
                "color": {"id": 4, "name": "Red"},
            }
        ],
    )

    response = logged_in_client.get("/sets/10194-1")

    assert response.status_code == 200
    assert 'value="7"' in response.text
    assert "/ 12" in response.text
    assert "red-brick.png" in response.text

    sort_page = logged_in_client.get("/sets/10194-1/sort")
    assert sort_page.status_code == 200
    assert "Nächstes offenes Teil" in sort_page.text
    assert "Alle 12 gefunden" in sort_page.text

    print_page = logged_in_client.get("/sets/10194-1/sorting-sheet?group=type")
    assert print_page.status_code == 200
    assert "Sortierbogen" in print_page.text
    assert "Steine" in print_page.text


def test_global_collection_search(logged_in_client, app, user, monkeypatch):
    with app.app_context():
        from app.models import User

        saved_user = db.session.get(User, user)
        saved_user.rebrickable_api_key = "test-key"
        saved_user.rebrickable_user_token = "test-token"
        db.session.commit()
    monkeypatch.setattr(
        "app.services.rebrickable.RebrickableService.search_user_sets",
        lambda _service, _query, **_kwargs: {
            "count": 1,
            "results": [
                {
                    "list_id": 12,
                    "quantity": 1,
                    "set": {
                        "set_num": "10194-1",
                        "name": "Emerald Night",
                        "year": 2009,
                        "num_parts": 1085,
                        "set_img_url": "https://example.test/emerald.png",
                    },
                }
            ],
        },
    )

    response = logged_in_client.get("/search?q=Emerald")

    assert response.status_code == 200
    assert "Emerald Night" in response.text
    assert "10194-1" in response.text
    assert "Liste" in response.text
