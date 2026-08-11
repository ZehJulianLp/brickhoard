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
    resume_project = None
    if current_user.has_rebrickable_credentials:
        try:
            lists = service_for_current_user().get_user_set_lists()
            list_count = lists["count"]
            set_count = sum(int(item.get("num_sets") or 0) for item in lists["results"])
        except RebrickableAPIError as exc:
            flash(str(exc), "warning")
    latest_progress = db.session.scalar(
        db.select(SetPartProgress)
        .where(SetPartProgress.user_id == current_user.id)
        .order_by(SetPartProgress.updated_at.desc())
    )
    if latest_progress:
        project_rows = list(
            db.session.scalars(
                db.select(SetPartProgress).where(
                    SetPartProgress.user_id == current_user.id,
                    SetPartProgress.set_number == latest_progress.set_number,
                )
            )
        )
        required = sum(max(row.required_quantity, 0) for row in project_rows)
        found = sum(
            min(max(row.found_quantity, 0), max(row.required_quantity, 0))
            for row in project_rows
        )
        resume_project = {
            "set_number": latest_progress.set_number,
            "found": found,
            "required": required,
            "percent": round(found / required * 100) if required else 0,
        }
    return render_template(
        "main/dashboard.html",
        list_count=list_count,
        set_count=set_count,
        resume_project=resume_project,
    )


@bp.get("/service-worker.js")
def service_worker():
    response = send_from_directory(current_app.static_folder, "service-worker.js")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Service-Worker-Allowed"] = "/"
    return response
