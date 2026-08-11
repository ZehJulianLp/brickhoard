from flask import Blueprint

bp = Blueprint("sets", __name__)

from app.sets import routes  # noqa: E402, F401

