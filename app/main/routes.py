from flask import Response, abort, current_app, flash, redirect, render_template, request, send_from_directory, session, url_for
from flask_login import current_user, login_required
from flask_babel import gettext, refresh

from app.extensions import db
from app.main import bp
from app.models import CachedInventoryPart, SetPartProgress
from app.services.rebrickable import RebrickableAPIError, RebrickableService


def service_for_current_user() -> RebrickableService:
    api_key = current_user.rebrickable_api_key or current_app.config.get(
        "REBRICKABLE_API_KEY", ""
    )
    return RebrickableService(api_key, current_user.rebrickable_user_token)


@bp.get("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return render_template("main/index.html")


@bp.post("/language/<locale>")
def set_language(locale: str):
    if locale not in current_app.config["LANGUAGES"]:
        abort(404)
    session["locale"] = locale
    if current_user.is_authenticated:
        current_user.preferred_locale = locale
        db.session.commit()
    refresh()
    target = request.form.get("next") or url_for("main.index")
    if not target.startswith("/") or target.startswith("//"):
        target = url_for("main.index")
    return redirect(target)


@bp.get("/install/brickhoard.desktop")
def linux_desktop_launcher():
    public_url = current_app.config["PUBLIC_BASE_URL"]
    body = "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Version=1.0",
            "Name=BrickHoard",
            f"Comment={gettext('LEGO-Sets sortieren und Fehlteile verwalten')}",
            f"Exec=xdg-open {public_url}/",
            "Icon=applications-internet",
            "Terminal=false",
            "Categories=Utility;",
            "StartupNotify=true",
            "",
        ]
    )
    return Response(
        body,
        mimetype="application/x-desktop",
        headers={"Content-Disposition": 'attachment; filename="brickhoard.desktop"'},
    )


@bp.get("/kontakt")
def contact():
    return render_template("main/contact.html")


@bp.get("/datenschutz")
def privacy():
    return render_template("main/privacy.html")


@bp.get("/impressum")
def imprint():
    return render_template("main/imprint.html")


@bp.get("/robots.txt")
def robots_txt():
    public_base_url = current_app.config["PUBLIC_BASE_URL"]
    body = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /account/",
            "Disallow: /admin/",
            "Disallow: /dashboard",
            "Disallow: /lists",
            "Disallow: /search",
            "Disallow: /social",
            "Disallow: /sets/",
            "Disallow: /settings/",
            f"Sitemap: {public_base_url}/sitemap.xml",
            "",
        ]
    )
    return Response(body, mimetype="text/plain", headers={"Cache-Control": "public, max-age=3600"})


@bp.get("/sitemap.xml")
def sitemap_xml():
    public_base_url = current_app.config["PUBLIC_BASE_URL"]
    urls = [
        (f"{public_base_url}{url_for('main.index')}", "1.0"),
        (f"{public_base_url}{url_for('main.contact')}", "0.5"),
        (f"{public_base_url}{url_for('main.privacy')}", "0.3"),
        (f"{public_base_url}{url_for('main.imprint')}", "0.3"),
    ]
    xml = render_template("main/sitemap.xml", urls=urls)
    return Response(xml, mimetype="application/xml", headers={"Cache-Control": "public, max-age=3600"})


@bp.get("/dashboard")
@login_required
def dashboard():
    list_count = None
    set_count = None
    rebrickable_state = "missing"
    if current_user.has_rebrickable_credentials:
        rebrickable_state = "connected"
        try:
            lists = service_for_current_user().get_user_set_lists()
            list_count = lists["count"]
            set_count = sum(int(item.get("num_sets") or 0) for item in lists["results"])
        except RebrickableAPIError as exc:
            rebrickable_state = "error"
            flash(str(exc), "warning")

    progress_rows = list(
        db.session.scalars(
            db.select(SetPartProgress)
            .where(SetPartProgress.user_id == current_user.id)
            .order_by(SetPartProgress.updated_at.desc())
        )
    )
    projects_by_set: dict[str, dict] = {}
    progress_by_set_and_key: dict[tuple[str, str], SetPartProgress] = {}
    for row in progress_rows:
        progress_by_set_and_key[(row.set_number, row.item_key)] = row
        project = projects_by_set.setdefault(
            row.set_number,
            {
                "set_number": row.set_number,
                "found": 0,
                "required": 0,
                "missing": 0,
                "updated_at": row.updated_at,
            },
        )
        required = max(row.required_quantity, 0)
        found = min(max(row.found_quantity, 0), required)
        project["required"] += required
        project["found"] += found
        project["missing"] += max(required - found, 0)
        if row.updated_at and (
            project["updated_at"] is None or row.updated_at > project["updated_at"]
        ):
            project["updated_at"] = row.updated_at

    # Progress rows only exist after a part has been touched. Use the complete
    # cached inventory so untouched parts still count towards the project total.
    # The values accumulated above remain a fallback for older projects whose
    # inventory has not been cached yet.
    if projects_by_set:
        cached_by_set: dict[str, list[CachedInventoryPart]] = {}
        for cached in db.session.scalars(
            db.select(CachedInventoryPart).where(
                CachedInventoryPart.set_number.in_(projects_by_set)
            )
        ):
            cached_by_set.setdefault(cached.set_number, []).append(cached)
        for set_number, cached_parts in cached_by_set.items():
            project = projects_by_set[set_number]
            project["found"] = 0
            project["required"] = 0
            project["missing"] = 0
            for cached in cached_parts:
                required = max(cached.required_quantity, 0)
                progress = progress_by_set_and_key.get((set_number, cached.item_key))
                found = 0
                if progress:
                    found = (
                        required
                        if progress.is_checked and progress.found_quantity == 0
                        else min(max(progress.found_quantity, 0), required)
                    )
                project["required"] += required
                project["found"] += found
                project["missing"] += max(required - found, 0)

    projects = sorted(
        projects_by_set.values(),
        key=lambda project: project["updated_at"],
        reverse=True,
    )
    for project in projects:
        required = project["required"]
        project["percent"] = round(project["found"] / required * 100) if required else 0
        project["is_complete"] = required > 0 and project["found"] >= required

    total_required = sum(project["required"] for project in projects)
    total_found = sum(project["found"] for project in projects)
    total_missing = sum(project["missing"] for project in projects)
    collection_percent = (
        round(total_found / total_required * 100) if total_required else 0
    )
    completed_projects = sum(project["is_complete"] for project in projects)
    active_projects = len(projects) - completed_projects
    resume_project = projects[0] if projects else None

    return render_template(
        "main/dashboard.html",
        list_count=list_count,
        set_count=set_count,
        rebrickable_state=rebrickable_state,
        resume_project=resume_project,
        recent_projects=projects[:4],
        project_count=len(projects),
        active_projects=active_projects,
        completed_projects=completed_projects,
        total_required=total_required,
        total_found=total_found,
        total_missing=total_missing,
        collection_percent=collection_percent,
    )


@bp.get("/service-worker.js")
def service_worker():
    response = send_from_directory(current_app.static_folder, "service-worker.js")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Service-Worker-Allowed"] = "/"
    return response
