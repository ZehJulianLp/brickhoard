from __future__ import annotations

import hashlib
import hmac
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Any

from flask import current_app, render_template
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


class MailServiceError(Exception):
    """A safe, user-facing mail delivery error."""


class AccountTokenError(Exception):
    """An invalid or expired account action token."""


class MailService:
    CONFIRM_SALT = "brickshelf-email-confirmation-v1"
    RESET_SALT = "brickshelf-password-reset-v1"

    def __init__(self) -> None:
        self._serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])

    @staticmethod
    def _password_fingerprint(password_hash: str) -> str:
        return hashlib.sha256(password_hash.encode()).hexdigest()

    def create_confirmation_token(self, user: Any) -> str:
        return self._serializer.dumps(
            {"user_id": user.id, "email": user.email}, salt=self.CONFIRM_SALT
        )

    def read_confirmation_token(self, token: str) -> dict[str, Any]:
        return self._read_token(
            token,
            salt=self.CONFIRM_SALT,
            max_age=current_app.config["EMAIL_CONFIRM_TOKEN_MAX_AGE"],
        )

    def create_password_reset_token(self, user: Any) -> str:
        return self._serializer.dumps(
            {
                "user_id": user.id,
                "email": user.email,
                "password": self._password_fingerprint(user.password_hash),
            },
            salt=self.RESET_SALT,
        )

    def read_password_reset_token(self, token: str) -> dict[str, Any]:
        return self._read_token(
            token,
            salt=self.RESET_SALT,
            max_age=current_app.config["PASSWORD_RESET_TOKEN_MAX_AGE"],
        )

    def password_reset_token_matches(self, payload: dict[str, Any], user: Any) -> bool:
        expected = self._password_fingerprint(user.password_hash)
        supplied = str(payload.get("password", ""))
        return (
            payload.get("user_id") == user.id
            and payload.get("email") == user.email
            and hmac.compare_digest(supplied, expected)
        )

    def _read_token(self, token: str, *, salt: str, max_age: int) -> dict[str, Any]:
        try:
            payload = self._serializer.loads(token, salt=salt, max_age=max_age)
        except SignatureExpired as error:
            raise AccountTokenError("Der Link ist abgelaufen.") from error
        except BadSignature as error:
            raise AccountTokenError("Der Link ist ungültig.") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("user_id"), int):
            raise AccountTokenError("Der Link ist ungültig.")
        return payload

    def send_confirmation(self, user: Any, confirmation_path: str) -> None:
        links = self._absolute_links(confirmation_path)
        self.send_template(
            recipient=user.email,
            subject="E-Mail-Adresse für BrickHoard bestätigen",
            template="email/confirm_email",
            username=user.username,
            confirmation_links=links,
            expires_hours=current_app.config["EMAIL_CONFIRM_TOKEN_MAX_AGE"] // 3600,
        )

    def send_password_reset(self, user: Any, reset_path: str) -> None:
        links = self._absolute_links(reset_path)
        self.send_template(
            recipient=user.email,
            subject="BrickHoard-Passwort zurücksetzen",
            template="email/reset_password",
            username=user.username,
            reset_links=links,
            expires_minutes=current_app.config["PASSWORD_RESET_TOKEN_MAX_AGE"] // 60,
        )

    def send_friend_request(self, recipient: Any, requester: Any, social_path: str) -> None:
        self.send_template(
            recipient=recipient.email,
            subject=f"{requester.username} möchte dich auf BrickHoard hinzufügen",
            template="email/friend_request",
            username=recipient.username,
            requester=requester,
            social_links=self._absolute_links(social_path),
        )

    def send_project_share(
        self,
        recipient: Any,
        owner: Any,
        set_number: str,
        permission: str,
        project_path: str,
    ) -> None:
        self.send_template(
            recipient=recipient.email,
            subject=f"{owner.username} teilt LEGO-Set {set_number} mit dir",
            template="email/project_share",
            username=recipient.username,
            owner=owner,
            set_number=set_number,
            permission=permission,
            project_links=self._absolute_links(project_path),
        )

    def _absolute_links(self, path: str) -> list[str]:
        normalized_path = "/" + path.lstrip("/")
        return [f"{base_url}{normalized_path}" for base_url in current_app.config["EMAIL_LINK_BASE_URLS"]]

    def send_template(
        self, *, recipient: str, subject: str, template: str, **context: Any
    ) -> None:
        text_body = render_template(f"{template}.txt", **context)
        html_body = render_template(f"{template}.html", **context)
        self.send(
            recipient=recipient,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )

    def send(
        self, *, recipient: str, subject: str, text_body: str, html_body: str | None = None
    ) -> None:
        self._validate_header(recipient)
        self._validate_header(subject)
        sender = current_app.config["MAIL_DEFAULT_SENDER"]
        self._validate_header(sender)

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = recipient
        message.set_content(text_body)
        if html_body:
            message.add_alternative(html_body, subtype="html")

        if current_app.config["MAIL_SUPPRESS_SEND"]:
            current_app.extensions.setdefault("mail_outbox", []).append(message)
            return

        server = current_app.config["MAIL_SERVER"]
        port = current_app.config["MAIL_PORT"]
        username = current_app.config.get("MAIL_USERNAME")
        password = current_app.config.get("MAIL_PASSWORD")
        timeout = current_app.config["MAIL_TIMEOUT"]

        if not server or not parseaddr(sender)[1]:
            raise MailServiceError("Der E-Mail-Versand ist noch nicht vollständig eingerichtet.")
        if username and not password:
            raise MailServiceError("Der E-Mail-Versand ist noch nicht vollständig eingerichtet.")

        try:
            if current_app.config["MAIL_USE_SSL"]:
                with smtplib.SMTP_SSL(
                    server, port, timeout=timeout, context=ssl.create_default_context()
                ) as smtp:
                    self._authenticate_and_send(smtp, message, username, password)
            else:
                with smtplib.SMTP(server, port, timeout=timeout) as smtp:
                    if current_app.config["MAIL_USE_TLS"]:
                        smtp.starttls(context=ssl.create_default_context())
                    self._authenticate_and_send(smtp, message, username, password)
        except (OSError, smtplib.SMTPException) as error:
            current_app.logger.warning(
                "E-Mail-Versand fehlgeschlagen (%s).", type(error).__name__
            )
            raise MailServiceError(
                "Die E-Mail konnte momentan nicht versendet werden. Bitte versuche es später erneut."
            ) from error

    @staticmethod
    def _authenticate_and_send(
        smtp: smtplib.SMTP, message: EmailMessage, username: str | None, password: str | None
    ) -> None:
        if username:
            smtp.login(username, password or "")
        smtp.send_message(message)

    @staticmethod
    def _validate_header(value: str) -> None:
        if "\r" in value or "\n" in value:
            raise MailServiceError("Die E-Mail enthält ungültige Kopfdaten.")
