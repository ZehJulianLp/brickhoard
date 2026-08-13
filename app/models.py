from __future__ import annotations

import base64
import hashlib
from datetime import date, datetime, timezone
from decimal import Decimal

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fernet() -> Fernet:
    configured = current_app.config.get("CREDENTIAL_ENCRYPTION_KEY", "")
    if configured:
        key = configured.encode()
    else:
        digest = hashlib.sha256(current_app.config["SECRET_KEY"].encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str | None) -> str | None:
    return _fernet().encrypt(value.encode()).decode() if value else None


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        current_app.logger.error("Gespeicherte Zugangsdaten konnten nicht entschlüsselt werden.")
        return None


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_enabled = db.Column(db.Boolean, default=True, nullable=False)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)
    onboarding_pending = db.Column(db.Boolean, default=False, nullable=False)
    profile_picture = db.Column(db.LargeBinary)
    profile_picture_updated_at = db.Column(db.DateTime(timezone=True))
    email_verified_at = db.Column(db.DateTime(timezone=True), nullable=True)
    confirmation_sent_at = db.Column(db.DateTime(timezone=True))
    password_reset_sent_at = db.Column(db.DateTime(timezone=True))
    rebrickable_username = db.Column(db.String(120))
    _rebrickable_api_key = db.Column("rebrickable_api_key", db.Text)
    _rebrickable_user_token = db.Column("rebrickable_user_token", db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    notes = db.relationship(
        "SetNote", back_populates="user", cascade="all, delete-orphan", lazy="dynamic"
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self) -> bool:
        return bool(self.is_enabled)

    @property
    def rebrickable_api_key(self) -> str | None:
        return decrypt_secret(self._rebrickable_api_key)

    @rebrickable_api_key.setter
    def rebrickable_api_key(self, value: str | None) -> None:
        self._rebrickable_api_key = encrypt_secret(value)

    @property
    def rebrickable_user_token(self) -> str | None:
        return decrypt_secret(self._rebrickable_user_token)

    @rebrickable_user_token.setter
    def rebrickable_user_token(self, value: str | None) -> None:
        self._rebrickable_user_token = encrypt_secret(value)

    @property
    def has_rebrickable_credentials(self) -> bool:
        api_key = self.rebrickable_api_key or current_app.config.get("REBRICKABLE_API_KEY")
        return bool(api_key and self.rebrickable_user_token)


class SetNote(db.Model):
    __table_args__ = (UniqueConstraint("user_id", "set_number"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    set_number = db.Column(db.String(40), nullable=False, index=True)
    note = db.Column(db.Text)
    storage_location = db.Column(db.String(255))
    purchase_date = db.Column(db.Date)
    purchase_price = db.Column(db.Numeric(10, 2))
    is_complete = db.Column(db.Boolean, default=False, nullable=False)
    is_built = db.Column(db.Boolean, default=False, nullable=False)
    last_sort_item_key = db.Column(db.String(180))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    user = db.relationship("User", back_populates="notes")

    purchase_date: date | None
    purchase_price: Decimal | None


class SetPartProgress(db.Model):
    __table_args__ = (UniqueConstraint("user_id", "set_number", "item_key"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    set_number = db.Column(db.String(40), nullable=False, index=True)
    item_key = db.Column(db.String(180), nullable=False)
    is_checked = db.Column(db.Boolean, default=False, nullable=False)
    found_quantity = db.Column(db.Integer, default=0, nullable=False)
    required_quantity = db.Column(db.Integer, default=1, nullable=False)
    status = db.Column(db.String(24), default="pending", nullable=False)
    part_note = db.Column(db.String(500))
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class CachedInventoryPart(db.Model):
    __table_args__ = (UniqueConstraint("set_number", "item_key"),)

    id = db.Column(db.Integer, primary_key=True)
    set_number = db.Column(db.String(40), nullable=False, index=True)
    item_key = db.Column(db.String(180), nullable=False)
    part_number = db.Column(db.String(120), nullable=False, index=True)
    part_name = db.Column(db.String(500), nullable=False)
    color_name = db.Column(db.String(120), nullable=False)
    image_url = db.Column(db.Text)
    required_quantity = db.Column(db.Integer, nullable=False)
    is_spare = db.Column(db.Boolean, default=False, nullable=False)
    type_group = db.Column(db.String(80), nullable=False)
    cached_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    return db.session.get(User, int(user_id))
