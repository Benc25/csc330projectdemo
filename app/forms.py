from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SelectField, SelectMultipleField, TextAreaField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Optional, NumberRange

class CreateRecipeForm(FlaskForm):
    title = StringField('Recipe Name', validators=[DataRequired(message='Recipe name is required.')])
    instructions = TextAreaField('Recipe Directions', validators=[DataRequired(message='Recipe directions are required.')])
    baseServings = IntegerField('Base Servings', validators=[DataRequired(message='Base serving size is required.'), NumberRange(min=1, message='Servings must be at least 1.')])
    description = TextAreaField('Description', validators=[Optional()])
    prepTime = IntegerField('Prep Time', validators=[Optional(), NumberRange(min=0, message='Prep time must be 0 or more.')])
    cookTime = IntegerField('Cook Time', validators=[Optional(), NumberRange(min=0, message='Cook time must be 0 or more.')])
    category_id = SelectField('Category', coerce=int, validators=[Optional()], choices=[])
    dietary_tags = SelectMultipleField('Dietary Tags', coerce=int, validators=[Optional()], choices=[])
    allergens = SelectMultipleField('Allergens', coerce=int, validators=[Optional()], choices=[])
    isPublic = BooleanField('Make this recipe public', default=True)
    submit = SubmitField('Create Recipe')
