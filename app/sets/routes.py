from __future__ import annotations

import csv
import io
import math
import time

from flask import Response, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.main.routes import service_for_current_user
from app.models import CachedInventoryPart, SetNote, SetPartProgress, utcnow
from app.services.rebrickable import RebrickableAPIError, RebrickableService
from app.sets import bp
from app.sets.forms import RebrickableSettingsForm, SetNoteForm


@bp.route("/settings/rebrickable", methods=["GET", "POST"])
@login_required
def rebrickable_settings():
    form = RebrickableSettingsForm()
    if request.method == "GET":
        form.rebrickable_username.data = current_user.rebrickable_username

    if form.validate_on_submit():
        api_key = form.api_key.data.strip() if form.api_key.data else None
        user_token = form.user_token.data.strip() if form.user_token.data else None
        effective_api_key = api_key or current_user.rebrickable_api_key or current_app.config.get(
            "REBRICKABLE_API_KEY", ""
        )
        effective_token = user_token or current_user.rebrickable_user_token

        if form.generate_token.data:
            login_name = form.rebrickable_login.data.strip() if form.rebrickable_login.data else ""
            password = form.rebrickable_password.data or ""
            if not effective_api_key or not login_name or not password:
                flash(
                    "Für die automatische Token-Erzeugung werden API-Key, Rebrickable-Benutzername/E-Mail und Passwort benötigt.",
                    "warning",
                )
            else:
                try:
                    generated_token = RebrickableService(effective_api_key).generate_user_token(
                        login_name, password
                    )
                    if api_key:
                        current_user.rebrickable_api_key = api_key
                    current_user.rebrickable_user_token = generated_token
                    current_user.rebrickable_username = login_name
                    db.session.commit()
                    flash(
                        "Der User Token wurde von Rebrickable erzeugt und verschlüsselt gespeichert. Dein Rebrickable-Passwort wurde nicht gespeichert.",
                        "success",
                    )
                    return redirect(url_for("sets.rebrickable_settings"))
                except RebrickableAPIError as exc:
                    flash(str(exc), "danger")
            return render_template(
                "sets/settings.html",
                form=form,
                has_api_key=bool(current_user.rebrickable_api_key),
                has_global_api_key=bool(current_app.config.get("REBRICKABLE_API_KEY")),
                has_token=bool(current_user.rebrickable_user_token),
            )

        if form.test.data:
            try:
                profile = RebrickableService(effective_api_key, effective_token).test_connection()
                display_name = profile.get("username") or "Rebrickable-Benutzer"
                flash(f"Verbindung erfolgreich: {display_name} wurde erkannt.", "success")
            except RebrickableAPIError as exc:
                flash(str(exc), "danger")
            return render_template(
                "sets/settings.html",
                form=form,
                has_api_key=bool(current_user.rebrickable_api_key),
                has_global_api_key=bool(current_app.config.get("REBRICKABLE_API_KEY")),
                has_token=bool(current_user.rebrickable_user_token),
            )

        current_user.rebrickable_username = form.rebrickable_username.data.strip() or None
        if form.clear_api_key.data:
            current_user.rebrickable_api_key = None
        elif api_key:
            current_user.rebrickable_api_key = api_key
        if form.clear_user_token.data:
            current_user.rebrickable_user_token = None
        elif user_token:
            current_user.rebrickable_user_token = user_token
        db.session.commit()
        flash("Die Rebrickable-Einstellungen wurden gespeichert.", "success")
        return redirect(url_for("sets.rebrickable_settings"))

    return render_template(
        "sets/settings.html",
        form=form,
        has_api_key=bool(current_user.rebrickable_api_key),
        has_global_api_key=bool(current_app.config.get("REBRICKABLE_API_KEY")),
        has_token=bool(current_user.rebrickable_user_token),
    )


@bp.get("/lists")
@login_required
def lists():
    if not current_user.has_rebrickable_credentials:
        flash("Richte zuerst API-Key und User Token ein.", "warning")
        return redirect(url_for("sets.rebrickable_settings"))
    try:
        payload = service_for_current_user().get_user_set_lists()
    except RebrickableAPIError as exc:
        flash(str(exc), "danger")
        payload = {"count": 0, "results": []}
    return render_template("sets/lists.html", lists=payload["results"])


@bp.get("/search")
@login_required
def search():
    query = (request.args.get("q") or "").strip()[:100]
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = 24
    results: list[dict] = []
    count = 0
    pages = 1
    if query:
        try:
            payload = service_for_current_user().search_user_sets(
                query, page=page, page_size=page_size
            )
            results = payload.get("results") or []
            count = int(payload.get("count", len(results)))
            pages = max(1, math.ceil(count / page_size))
        except RebrickableAPIError as exc:
            flash(str(exc), "danger")
    return render_template(
        "sets/search.html",
        query=query,
        results=results,
        count=count,
        page=page,
        pages=pages,
    )


@bp.get("/lists/<int:list_id>")
@login_required
def list_detail(list_id: int):
    if not current_user.has_rebrickable_credentials:
        return redirect(url_for("sets.rebrickable_settings"))
    page = request.args.get("page", 1, type=int)
    page = max(page, 1)
    page_size = 24
    try:
        service = service_for_current_user()
        set_list = service.get_user_set_list(list_id)
        payload = service.get_sets_in_list(list_id, page=page, page_size=page_size)
    except RebrickableAPIError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("sets.lists"))
    pages = max(1, math.ceil(int(payload.get("count", 0)) / page_size))
    return render_template(
        "sets/list_detail.html",
        set_list=set_list,
        entries=payload.get("results") or [],
        page=page,
        pages=pages,
    )


@bp.route("/sets/<path:set_number>", methods=["GET", "POST"])
@login_required
def set_detail(set_number: str):
    note = db.session.scalar(
        db.select(SetNote).where(
            SetNote.user_id == current_user.id, SetNote.set_number == set_number
        )
    )
    form = SetNoteForm(obj=note)
    if form.validate_on_submit():
        if note is None:
            note = SetNote(user_id=current_user.id, set_number=set_number)
            db.session.add(note)
        note.note = form.note.data or None
        note.storage_location = form.storage_location.data or None
        note.purchase_date = form.purchase_date.data
        note.purchase_price = form.purchase_price.data
        note.is_complete = form.is_complete.data
        note.is_built = form.is_built.data
        db.session.commit()
        flash("Deine lokalen Set-Angaben wurden gespeichert.", "success")
        return redirect(url_for("sets.set_detail", set_number=set_number))

    set_data = None
    theme_name = None
    parts: list[dict] = []
    api_key = current_user.rebrickable_api_key or current_app.config.get("REBRICKABLE_API_KEY", "")
    if api_key:
        service = RebrickableService(api_key, current_user.rebrickable_user_token)
        try:
            set_data = service.get_set_details(set_number)
        except RebrickableAPIError as exc:
            flash(str(exc), "warning")
        try:
            parts = service.get_set_parts(set_number)
            _enrich_parts_with_progress(parts, set_number)
        except RebrickableAPIError as exc:
            flash(str(exc), "warning")
        if set_data and set_data.get("theme_id"):
            try:
                theme_name = service.get_theme_details(int(set_data["theme_id"])).get("name")
            except RebrickableAPIError:
                theme_name = None
    else:
        flash("Für Setdetails wird ein Rebrickable-API-Key benötigt.", "warning")

    return render_template(
        "sets/set_detail.html",
        set_data=set_data,
        set_number=set_number,
        theme_name=theme_name,
        parts=parts,
        form=form,
    )


def _part_progress_key(entry: dict) -> str:
    if entry.get("id") is not None:
        return f"inventory:{entry['id']}"
    part = entry.get("part") or {}
    color = entry.get("color") or {}
    return ":".join(
        [
            "part",
            str(part.get("part_num") or "unknown"),
            str(color.get("id") if color.get("id") is not None else "unknown"),
            "spare" if entry.get("is_spare") else "regular",
        ]
    )


def _enrich_parts_with_progress(parts: list[dict], set_number: str) -> None:
    progress_by_key = {
        progress.item_key: progress
        for progress in db.session.scalars(
            db.select(SetPartProgress).where(
                SetPartProgress.user_id == current_user.id,
                SetPartProgress.set_number == set_number,
            )
        )
    }
    cached_by_key = {
        cached.item_key: cached
        for cached in db.session.scalars(
            db.select(CachedInventoryPart).where(
                CachedInventoryPart.set_number == set_number
            )
        )
    }
    seen_cache_keys: set[str] = set()
    for entry in parts:
        key = _part_progress_key(entry)
        seen_cache_keys.add(key)
        required = max(int(entry.get("quantity") or 0), 0)
        progress = progress_by_key.get(key)
        found = 0
        if progress:
            found = (
                required
                if progress.is_checked and progress.found_quantity == 0
                else progress.found_quantity
            )
            if progress.required_quantity != required:
                progress.required_quantity = required
            if progress.is_checked and progress.found_quantity == 0:
                progress.found_quantity = required
                progress.status = "found"
        entry["progress_key"] = key
        entry["found_quantity"] = min(max(found, 0), required)
        entry["missing_quantity"] = max(required - entry["found_quantity"], 0)
        entry["progress_status"] = (
            progress.status
            if progress
            and progress.status
            in {"pending", "found", "missing", "wrong_color", "alternative"}
            else ("found" if required and entry["found_quantity"] >= required else "pending")
        )
        entry["part_note"] = progress.part_note if progress else ""
        entry["type_group"] = _part_type_group((entry.get("part") or {}).get("name") or "")
        part = entry.get("part") or {}
        color = entry.get("color") or {}
        cached = cached_by_key.get(key)
        if cached is None:
            cached = CachedInventoryPart(set_number=set_number, item_key=key)
            db.session.add(cached)
        cached.part_number = str(part.get("part_num") or "Unbekannt")
        cached.part_name = str(part.get("name") or "Unbekanntes Teil")
        cached.color_name = str(color.get("name") or "Unbekannte Farbe")
        cached.image_url = part.get("part_img_url") or None
        cached.required_quantity = required
        cached.is_spare = bool(entry.get("is_spare"))
        cached.type_group = entry["type_group"]
        cached.cached_at = utcnow()
    for stale_key, stale in cached_by_key.items():
        if stale_key not in seen_cache_keys:
            db.session.delete(stale)
    if db.session.dirty or db.session.new:
        db.session.commit()


def _part_type_group(name: str) -> str:
    normalized = name.lower()
    groups = [
        (("technic", "axle", "gear", "pin "), "Technic"),
        (("plate",), "Platten"),
        (("tile",), "Fliesen"),
        (("slope",), "Schrägsteine"),
        (("brick",), "Steine"),
        (("wheel", "tyre", "tire"), "Räder & Reifen"),
        (("window", "door", "glass"), "Fenster & Türen"),
        (("minifig", "torso", "head ", "hair"), "Minifiguren"),
        (("plant", "flower"), "Pflanzen"),
    ]
    for needles, label in groups:
        if any(needle in normalized for needle in needles):
            return label
    return "Sonstige Teile"


@bp.post("/sets/<path:set_number>/parts/progress")
@login_required
def save_part_progress(set_number: str):
    payload = request.get_json(silent=True) or {}
    item_key = str(payload.get("item_key") or "")
    required_quantity = payload.get("required_quantity", 1)
    found_quantity = payload.get("found_quantity")
    status = payload.get("status")
    part_note = payload.get("part_note")
    if found_quantity is None and isinstance(payload.get("is_checked"), bool):
        found_quantity = required_quantity if payload["is_checked"] else 0
    if (
        not item_key
        or len(item_key) > 180
        or not isinstance(found_quantity, int)
        or isinstance(found_quantity, bool)
        or not isinstance(required_quantity, int)
        or isinstance(required_quantity, bool)
        or required_quantity < 0
        or required_quantity > 100_000
        or found_quantity < 0
        or found_quantity > required_quantity
        or (
            status is not None
            and status
            not in {"pending", "found", "missing", "wrong_color", "alternative"}
        )
        or (part_note is not None and (not isinstance(part_note, str) or len(part_note) > 500))
    ):
        return jsonify({"error": "Ungültige Fortschrittsdaten."}), 400

    progress = db.session.scalar(
        db.select(SetPartProgress).where(
            SetPartProgress.user_id == current_user.id,
            SetPartProgress.set_number == set_number,
            SetPartProgress.item_key == item_key,
        )
    )
    if progress is None:
        progress = SetPartProgress(
            user_id=current_user.id,
            set_number=set_number,
            item_key=item_key,
        )
        db.session.add(progress)
    progress.found_quantity = found_quantity
    progress.required_quantity = required_quantity
    progress.is_checked = required_quantity > 0 and found_quantity >= required_quantity
    if status is not None:
        progress.status = status
    elif progress.is_checked:
        progress.status = "found"
    elif progress.status == "found":
        progress.status = "pending"
    if part_note is not None:
        progress.part_note = part_note.strip() or None
    db.session.commit()
    return jsonify(
        {
            "saved": True,
            "is_checked": progress.is_checked,
            "found_quantity": progress.found_quantity,
            "status": progress.status,
        }
    )


@bp.post("/sets/<path:set_number>/parts/progress/bulk")
@login_required
def save_part_progress_bulk(set_number: str):
    payload = request.get_json(silent=True) or {}
    items = payload.get("items")
    if not isinstance(items, list) or not items or len(items) > 1000:
        return jsonify({"error": "Ungültige Sammeländerung."}), 400
    normalized: list[dict] = []
    allowed_statuses = {"pending", "found", "missing", "wrong_color", "alternative"}
    for item in items:
        if not isinstance(item, dict):
            return jsonify({"error": "Ungültige Sammeländerung."}), 400
        item_key = str(item.get("item_key") or "")
        found = item.get("found_quantity")
        required = item.get("required_quantity")
        status = item.get("status")
        if (
            not item_key
            or len(item_key) > 180
            or not isinstance(found, int)
            or isinstance(found, bool)
            or not isinstance(required, int)
            or isinstance(required, bool)
            or required < 0
            or required > 100_000
            or found < 0
            or found > required
            or status not in allowed_statuses
        ):
            return jsonify({"error": "Ungültige Sammeländerung."}), 400
        normalized.append(
            {
                "item_key": item_key,
                "found": found,
                "required": required,
                "status": status,
            }
        )
    keys = [item["item_key"] for item in normalized]
    existing = {
        progress.item_key: progress
        for progress in db.session.scalars(
            db.select(SetPartProgress).where(
                SetPartProgress.user_id == current_user.id,
                SetPartProgress.set_number == set_number,
                SetPartProgress.item_key.in_(keys),
            )
        )
    }
    for item in normalized:
        progress = existing.get(item["item_key"])
        if progress is None:
            progress = SetPartProgress(
                user_id=current_user.id,
                set_number=set_number,
                item_key=item["item_key"],
            )
            db.session.add(progress)
        progress.found_quantity = item["found"]
        progress.required_quantity = item["required"]
        progress.is_checked = item["required"] > 0 and item["found"] >= item["required"]
        progress.status = item["status"]
    db.session.commit()
    return jsonify({"saved": True, "count": len(normalized)})


def _missing_parts(set_number: str) -> list[dict]:
    api_key = current_user.rebrickable_api_key or current_app.config.get(
        "REBRICKABLE_API_KEY", ""
    )
    if not api_key:
        raise RebrickableAPIError("Für die Teileliste wird ein Rebrickable-API-Key benötigt.")
    parts = RebrickableService(api_key).get_set_parts(set_number)
    _enrich_parts_with_progress(parts, set_number)
    return [entry for entry in parts if entry["missing_quantity"] > 0]


def _ensure_inventory_cache(set_numbers: list[str], refresh: bool = False) -> list[str]:
    cached_sets = set(
        db.session.scalars(
            db.select(CachedInventoryPart.set_number)
            .where(CachedInventoryPart.set_number.in_(set_numbers))
            .distinct()
        )
    )
    to_load = set_numbers if refresh else [number for number in set_numbers if number not in cached_sets]
    if not to_load:
        return []
    api_key = current_user.rebrickable_api_key or current_app.config.get(
        "REBRICKABLE_API_KEY", ""
    )
    if not api_key:
        raise RebrickableAPIError("Für die Fehlteilezentrale wird ein Rebrickable-API-Key benötigt.")
    failed: list[str] = []
    service = RebrickableService(api_key)
    for index, set_number in enumerate(to_load):
        if index:
            time.sleep(1.05)
        try:
            parts = service.get_set_parts(set_number)
            _enrich_parts_with_progress(parts, set_number)
        except RebrickableAPIError:
            current_app.logger.warning(
                "Inventar für die globale Fehlteileliste konnte nicht geladen werden: %s",
                set_number,
            )
            failed.append(set_number)
    return failed


def _all_missing_parts(*, refresh: bool = False) -> list[dict]:
    set_numbers = list(
        db.session.scalars(
            db.select(SetPartProgress.set_number)
            .where(SetPartProgress.user_id == current_user.id)
            .distinct()
            .order_by(SetPartProgress.set_number)
        )
    )
    if not set_numbers:
        return []
    failed = _ensure_inventory_cache(set_numbers, refresh=refresh)
    if failed:
        flash(
            "Einige Inventare konnten momentan nicht aktualisiert werden: "
            + ", ".join(failed),
            "warning",
        )
    cached_parts = list(
        db.session.scalars(
            db.select(CachedInventoryPart).where(
                CachedInventoryPart.set_number.in_(set_numbers)
            )
        )
    )
    progress_by_key = {
        (progress.set_number, progress.item_key): progress
        for progress in db.session.scalars(
            db.select(SetPartProgress).where(
                SetPartProgress.user_id == current_user.id,
                SetPartProgress.set_number.in_(set_numbers),
            )
        )
    }
    aggregated: dict[tuple[str, str, bool], dict] = {}
    for cached in cached_parts:
        progress = progress_by_key.get((cached.set_number, cached.item_key))
        found = 0
        status = "pending"
        note = ""
        if progress:
            found = (
                cached.required_quantity
                if progress.is_checked and progress.found_quantity == 0
                else min(max(progress.found_quantity, 0), cached.required_quantity)
            )
            status = progress.status
            note = progress.part_note or ""
        missing = max(cached.required_quantity - found, 0)
        if missing == 0:
            continue
        aggregate_key = (cached.part_number, cached.color_name, cached.is_spare)
        aggregate = aggregated.setdefault(
            aggregate_key,
            {
                "part_number": cached.part_number,
                "part_name": cached.part_name,
                "color_name": cached.color_name,
                "image_url": cached.image_url,
                "type_group": cached.type_group,
                "is_spare": cached.is_spare,
                "missing_quantity": 0,
                "sets": [],
            },
        )
        aggregate["missing_quantity"] += missing
        aggregate["sets"].append(
            {
                "set_number": cached.set_number,
                "missing_quantity": missing,
                "status": status,
                "note": note,
            }
        )
    return list(aggregated.values())


def _sort_aggregated_missing(parts: list[dict], ordering: str) -> None:
    sorters = {
        "missing_desc": lambda item: (-item["missing_quantity"], item["part_name"]),
        "missing_asc": lambda item: (item["missing_quantity"], item["part_name"]),
        "part": lambda item: item["part_number"],
        "name": lambda item: item["part_name"].lower(),
        "color": lambda item: (item["color_name"].lower(), item["part_name"].lower()),
        "sets": lambda item: (-len(item["sets"]), item["part_name"].lower()),
    }
    parts.sort(key=sorters.get(ordering, sorters["missing_desc"]))


@bp.get("/missing")
@login_required
def all_missing_parts():
    grouping = request.args.get("group", "type")
    ordering = request.args.get("sort", "missing_desc")
    if grouping not in {"none", "type", "color"}:
        grouping = "type"
    try:
        parts = _all_missing_parts(refresh=request.args.get("refresh") == "1")
    except RebrickableAPIError as exc:
        flash(str(exc), "danger")
        parts = []
    _sort_aggregated_missing(parts, ordering)
    if grouping == "type":
        parts.sort(key=lambda item: item["type_group"].lower())
    elif grouping == "color":
        parts.sort(key=lambda item: item["color_name"].lower())
    return render_template(
        "sets/all_missing_parts.html",
        parts=parts,
        grouping=grouping,
        ordering=ordering,
    )


@bp.get("/missing.csv")
@login_required
def all_missing_parts_csv():
    ordering = request.args.get("sort", "missing_desc")
    try:
        parts = _all_missing_parts()
    except RebrickableAPIError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("sets.all_missing_parts"))
    _sort_aggregated_missing(parts, ordering)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(
        [
            "Teilenummer",
            "Bezeichnung",
            "Farbe",
            "Gesamt fehlt",
            "Sets",
            "Teileart",
            "Ersatzteil",
            "Bild-URL",
        ]
    )
    for part in parts:
        set_breakdown = ", ".join(
            f"{entry['set_number']}: {entry['missing_quantity']}"
            for entry in part["sets"]
        )
        writer.writerow(
            [
                _safe_csv_value(part["part_number"]),
                _safe_csv_value(part["part_name"]),
                _safe_csv_value(part["color_name"]),
                part["missing_quantity"],
                _safe_csv_value(set_breakdown),
                _safe_csv_value(part["type_group"]),
                "Ja" if part["is_spare"] else "Nein",
                _safe_csv_value(part["image_url"]),
            ]
        )
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="brickshelf-alle-fehlteile.csv"'},
    )


def _set_inventory(set_number: str) -> tuple[dict, list[dict]]:
    api_key = current_user.rebrickable_api_key or current_app.config.get(
        "REBRICKABLE_API_KEY", ""
    )
    if not api_key:
        raise RebrickableAPIError("Für den Sortiermodus wird ein Rebrickable-API-Key benötigt.")
    service = RebrickableService(api_key)
    set_data = service.get_set_details(set_number)
    parts = service.get_set_parts(set_number)
    _enrich_parts_with_progress(parts, set_number)
    return set_data, parts


@bp.get("/sets/<path:set_number>/sort")
@login_required
def sort_assistant(set_number: str):
    try:
        set_data, parts = _set_inventory(set_number)
    except RebrickableAPIError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("sets.set_detail", set_number=set_number))
    note = db.session.scalar(
        db.select(SetNote).where(
            SetNote.user_id == current_user.id, SetNote.set_number == set_number
        )
    )
    start_index = 0
    if note and note.last_sort_item_key:
        start_index = next(
            (
                index
                for index, entry in enumerate(parts)
                if entry["progress_key"] == note.last_sort_item_key
            ),
            0,
        )
    return render_template(
        "sets/sort_assistant.html",
        set_number=set_number,
        set_data=set_data,
        parts=parts,
        start_index=start_index,
    )


@bp.post("/sets/<path:set_number>/sort-position")
@login_required
def save_sort_position(set_number: str):
    payload = request.get_json(silent=True) or {}
    item_key = str(payload.get("item_key") or "")
    if not item_key or len(item_key) > 180:
        return jsonify({"error": "Ungültige Sortierposition."}), 400
    note = db.session.scalar(
        db.select(SetNote).where(
            SetNote.user_id == current_user.id, SetNote.set_number == set_number
        )
    )
    if note is None:
        note = SetNote(user_id=current_user.id, set_number=set_number)
        db.session.add(note)
    note.last_sort_item_key = item_key
    db.session.commit()
    return jsonify({"saved": True})


@bp.get("/sets/<path:set_number>/sorting-sheet")
@login_required
def sorting_sheet(set_number: str):
    group_by = request.args.get("group", "color")
    if group_by not in {"color", "type", "status"}:
        group_by = "color"
    try:
        set_data, parts = _set_inventory(set_number)
    except RebrickableAPIError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("sets.set_detail", set_number=set_number))
    if group_by == "color":
        parts.sort(
            key=lambda entry: (
                (entry.get("color") or {}).get("name") or "",
                (entry.get("part") or {}).get("name") or "",
            )
        )
    elif group_by == "type":
        parts.sort(
            key=lambda entry: (
                entry["type_group"],
                (entry.get("part") or {}).get("name") or "",
            )
        )
    else:
        parts.sort(
            key=lambda entry: (
                entry["progress_status"],
                (entry.get("part") or {}).get("name") or "",
            )
        )
    return render_template(
        "sets/sorting_sheet.html",
        set_number=set_number,
        set_data=set_data,
        parts=parts,
        group_by=group_by,
    )


@bp.get("/sets/<path:set_number>/missing")
@login_required
def missing_parts(set_number: str):
    try:
        parts = _missing_parts(set_number)
    except RebrickableAPIError as exc:
        flash(str(exc), "danger")
        parts = []
    return render_template(
        "sets/missing_parts.html", set_number=set_number, parts=parts
    )


def _safe_csv_value(value: object) -> str:
    rendered = str(value or "")
    return f"'{rendered}" if rendered.startswith(("=", "+", "-", "@")) else rendered


@bp.get("/sets/<path:set_number>/missing.csv")
@login_required
def missing_parts_csv(set_number: str):
    try:
        parts = _missing_parts(set_number)
    except RebrickableAPIError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("sets.set_detail", set_number=set_number))

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(
        [
            "Set",
            "Teilenummer",
            "Bezeichnung",
            "Farbe",
            "Benötigt",
            "Vorhanden",
            "Fehlt",
            "Zustand",
            "Notiz",
            "Ersatzteil",
            "Bild-URL",
        ]
    )
    for entry in parts:
        part = entry.get("part") or {}
        color = entry.get("color") or {}
        writer.writerow(
            [
                _safe_csv_value(set_number),
                _safe_csv_value(part.get("part_num")),
                _safe_csv_value(part.get("name")),
                _safe_csv_value(color.get("name")),
                entry.get("quantity", 0),
                entry["found_quantity"],
                entry["missing_quantity"],
                entry["progress_status"],
                _safe_csv_value(entry["part_note"]),
                "Ja" if entry.get("is_spare") else "Nein",
                _safe_csv_value(part.get("part_img_url")),
            ]
        )
    csv_data = "\ufeff" + output.getvalue()
    return Response(
        csv_data,
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="brickshelf-{set_number}-fehlteile.csv"'
        },
    )
