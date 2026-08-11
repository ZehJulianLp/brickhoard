from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

import click
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from dotenv import load_dotenv
from sqlalchemy import func, inspect, or_, text
from werkzeug.middleware.proxy_fix import ProxyFix

from app.extensions import csrf, db, login_manager


def create_app(test_config: dict | None = None) -> Flask:
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-only-change-me"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///brickshelf.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        REBRICKABLE_API_KEY=os.getenv("REBRICKABLE_API_KEY", ""),
        CREDENTIAL_ENCRYPTION_KEY=os.getenv("CREDENTIAL_ENCRYPTION_KEY", ""),
        MAIL_SERVER=os.getenv("MAIL_SERVER", "mail.julianverse.de"),
        MAIL_PORT=int(os.getenv("MAIL_PORT", "465")),
        MAIL_USE_SSL=os.getenv("MAIL_USE_SSL", "true").lower() in {"1", "true", "yes"},
        MAIL_USE_TLS=os.getenv("MAIL_USE_TLS", "false").lower() in {"1", "true", "yes"},
        MAIL_USERNAME=os.getenv("MAIL_USERNAME", "brickhoard@julianverse.de"),
        MAIL_PASSWORD=os.getenv("MAIL_PASSWORD", ""),
        MAIL_DEFAULT_SENDER=os.getenv(
            "MAIL_DEFAULT_SENDER", "BrickHoard <brickhoard@julianverse.de>"
        ),
        EMAIL_LINK_BASE_URLS=tuple(
            url.strip().rstrip("/")
            for url in os.getenv(
                "EMAIL_LINK_BASE_URLS",
                "http://localhost:5000,https://brickhoard.julianverse.de",
            ).split(",")
            if url.strip()
        ),
        MAIL_TIMEOUT=int(os.getenv("MAIL_TIMEOUT", "10")),
        MAIL_SUPPRESS_SEND=os.getenv("MAIL_SUPPRESS_SEND", "false").lower()
        in {"1", "true", "yes"},
        EMAIL_CONFIRM_TOKEN_MAX_AGE=int(
            os.getenv("EMAIL_CONFIRM_TOKEN_MAX_AGE", "86400")
        ),
        PASSWORD_RESET_TOKEN_MAX_AGE=int(
            os.getenv("PASSWORD_RESET_TOKEN_MAX_AGE", "3600")
        ),
        MAIL_RESEND_COOLDOWN=int(os.getenv("MAIL_RESEND_COOLDOWN", "60")),
        PUBLIC_BASE_URL=os.getenv(
            "PUBLIC_BASE_URL", "https://brickhoard.julianverse.de"
        ).rstrip("/"),
        LEGAL_OPERATOR_NAME=os.getenv("LEGAL_OPERATOR_NAME", "Julian"),
        LEGAL_POSTAL_ADDRESS=tuple(
            line.strip()
            for line in os.getenv("LEGAL_POSTAL_ADDRESS", "").split("|")
            if line.strip()
        ),
        LEGAL_CONTACT_EMAIL=os.getenv(
            "LEGAL_CONTACT_EMAIL", "brickhoard@julianverse.de"
        ),
        PRIVACY_LAST_UPDATED=os.getenv(
            "PRIVACY_LAST_UPDATED", "11. August 2026"
        ),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("FLASK_ENV") == "production",
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=os.getenv("FLASK_ENV") == "production",
    )
    if test_config:
        app.config.update(test_config)
        if "MAIL_SUPPRESS_SEND" not in test_config:
            app.config["MAIL_SUPPRESS_SEND"] = True

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Bitte melde dich an, um diese Seite aufzurufen."
    login_manager.login_message_category = "warning"

    from app.auth import bp as auth_bp
    from app.account import bp as account_bp
    from app.admin import bp as admin_bp
    from app.main import bp as main_bp
    from app.sets import bp as sets_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(sets_bp)

    register_cli(app)
    register_error_handlers(app)
    configure_logging(app)

    indexable_endpoints = {
        "main.index",
        "main.contact",
        "main.privacy",
        "main.imprint",
    }

    @app.context_processor
    def inject_seo_metadata():
        endpoint = request.endpoint or ""
        is_indexable = endpoint in indexable_endpoints
        public_base_url = app.config["PUBLIC_BASE_URL"]
        canonical_url = (
            f"{public_base_url}{url_for(endpoint)}" if is_indexable else None
        )
        structured_data = None
        if endpoint == "main.index":
            structured_data = [
                {
                    "@context": "https://schema.org",
                    "@type": "WebSite",
                    "name": "BrickHoard",
                    "url": f"{public_base_url}/",
                    "inLanguage": "de-DE",
                },
                {
                    "@context": "https://schema.org",
                    "@type": "WebApplication",
                    "name": "BrickHoard",
                    "url": f"{public_base_url}/",
                    "applicationCategory": "LifestyleApplication",
                    "operatingSystem": "Web",
                    "inLanguage": "de-DE",
                    "description": (
                        "Private Web-App zum Verwalten von LEGO-Setlisten, "
                        "Sortierfortschritten und Fehlteilen mit Rebrickable."
                    ),
                    "offers": {
                        "@type": "Offer",
                        "price": "0",
                        "priceCurrency": "EUR",
                    },
                    "featureList": [
                        "LEGO-Setlisten verwalten",
                        "Teile sortieren und Fortschritt speichern",
                        "Fehlteile erkennen und exportieren",
                        "Rebrickable-Sammlungen anbinden",
                    ],
                },
            ]
        return {
            "seo_canonical_url": canonical_url,
            "seo_is_indexable": is_indexable,
            "seo_public_base_url": public_base_url,
            "seo_social_image_url": (
                f"{public_base_url}{url_for('static', filename='img/icon-512.png')}"
            ),
            "seo_structured_data": structured_data,
        }

    @app.after_request
    def add_search_engine_headers(response):
        endpoint = request.endpoint or ""
        if endpoint not in indexable_endpoints and endpoint not in {
            "main.robots_txt",
            "main.sitemap_xml",
            "main.service_worker",
            "static",
        }:
            response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        return response

    @app.before_request
    def require_forced_password_change():
        allowed = {
            "account.account_settings",
            "account.change_password",
            "auth.logout",
            "main.service_worker",
            "static",
        }
        if (
            current_user.is_authenticated
            and current_user.must_change_password
            and request.endpoint not in allowed
        ):
            flash("Bitte ändere zuerst dein temporäres Passwort.", "warning")
            return redirect(url_for("account.account_settings"))

        verification_allowed = {
            "account.account_settings",
            "account.change_password",
            "auth.confirm_email",
            "auth.logout",
            "auth.resend_confirmation",
            "auth.verification_required",
            "main.service_worker",
            "static",
        }
        if (
            current_user.is_authenticated
            and current_user.email_verified_at is None
            and request.endpoint not in verification_allowed
        ):
            flash("Bitte bestätige zuerst deine E-Mail-Adresse.", "warning")
            return redirect(url_for("auth.verification_required"))

    return app


def register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Create all database tables."""
        db.create_all()
        columns = {
            column["name"]
            for column in inspect(db.engine).get_columns("set_part_progress")
        }
        additions = {
            "found_quantity": "INTEGER NOT NULL DEFAULT 0",
            "required_quantity": "INTEGER NOT NULL DEFAULT 1",
            "status": "VARCHAR(24) NOT NULL DEFAULT 'pending'",
            "part_note": "VARCHAR(500)",
        }
        for name, definition in additions.items():
            if name not in columns:
                db.session.execute(
                    text(f"ALTER TABLE set_part_progress ADD COLUMN {name} {definition}")
                )
        if any(name not in columns for name in additions):
            db.session.commit()
        note_columns = {
            column["name"] for column in inspect(db.engine).get_columns("set_note")
        }
        if "last_sort_item_key" not in note_columns:
            db.session.execute(
                text("ALTER TABLE set_note ADD COLUMN last_sort_item_key VARCHAR(180)")
            )
            db.session.commit()
        user_columns = {
            column["name"] for column in inspect(db.engine).get_columns("user")
        }
        user_additions = {
            "is_admin": "BOOLEAN NOT NULL DEFAULT 0",
            "is_enabled": "BOOLEAN NOT NULL DEFAULT 1",
            "must_change_password": "BOOLEAN NOT NULL DEFAULT 0",
            "onboarding_pending": "BOOLEAN NOT NULL DEFAULT 0",
            "email_verified_at": "DATETIME",
            "confirmation_sent_at": "DATETIME",
            "password_reset_sent_at": "DATETIME",
        }
        for name, definition in user_additions.items():
            if name not in user_columns:
                db.session.execute(text(f'ALTER TABLE "user" ADD COLUMN {name} {definition}'))
        if any(name not in user_columns for name in user_additions):
            db.session.commit()
        if "email_verified_at" not in user_columns:
            db.session.execute(
                text('UPDATE "user" SET email_verified_at = CURRENT_TIMESTAMP')
            )
            db.session.commit()
        from app.models import User

        if db.session.scalar(db.select(func.count(User.id))) and not db.session.scalar(
            db.select(User).where(User.is_admin.is_(True))
        ):
            first_user = db.session.scalar(db.select(User).order_by(User.id))
            first_user.is_admin = True
            db.session.commit()
        click.echo("Die BrickHoard-Datenbank wurde initialisiert.")

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    @click.option("--email", prompt=True)
    @click.password_option()
    def create_admin_command(username: str, email: str, password: str) -> None:
        """Create a local BrickHoard administrator."""
        from app.models import User, utcnow

        email = email.strip().lower()
        if db.session.scalar(
            db.select(User).where(
                or_(User.email == email, User.username == username.strip())
            )
        ):
            raise click.ClickException("Benutzername oder E-Mail existiert bereits.")
        user = User(
            username=username.strip(),
            email=email,
            is_admin=True,
            is_enabled=True,
            email_verified_at=utcnow(),
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo("Administrator wurde erstellt.")


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(_error):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    @app.errorhandler(CSRFError)
    def csrf_error(error: CSRFError):
        return render_template("errors/csrf.html", reason=error.description), 400


def configure_logging(app: Flask) -> None:
    if app.testing:
        return
    handler = RotatingFileHandler(
        Path(app.instance_path) / "brickshelf.log", maxBytes=1_000_000, backupCount=3
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
