from flask import Response, current_app, flash, redirect, render_template, send_from_directory, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.main import bp
from app.models import SetPartProgress
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
    for row in progress_rows:
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
