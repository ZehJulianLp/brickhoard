from flask_wtf import FlaskForm
from flask_babel import lazy_gettext as _l
from wtforms import HiddenField, SubmitField
from wtforms.validators import DataRequired


class AdminUserActionForm(FlaskForm):
    user_id = HiddenField(validators=[DataRequired()])
    submit = SubmitField(_l("Ausführen"))
