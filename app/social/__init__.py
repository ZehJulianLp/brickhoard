from flask import Blueprint

bp = Blueprint("social", __name__)

from app.social import routes  # noqa: E402, F401
