from flask_wtf import FlaskForm
from wtforms import HiddenField, SubmitField
from wtforms.validators import DataRequired


class AdminUserActionForm(FlaskForm):
    user_id = HiddenField(validators=[DataRequired()])
    submit = SubmitField("Ausführen")

