from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SelectField, SelectMultipleField, TextAreaField, BooleanField, SubmitField, PasswordField
from wtforms.validators import DataRequired, Optional, NumberRange, Email, Length, EqualTo, ValidationError
from app.models import User

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

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(message='Email is required.'), Email(message='Invalid email address.')])
    password = PasswordField('Password', validators=[DataRequired(message='Password is required.')])
    submit = SubmitField('Sign In')

class RegisterForm(FlaskForm):
    firstName = StringField('First Name', validators=[DataRequired(message='First name is required.'), Length(min=2, max=50)])
    lastName = StringField('Last Name', validators=[DataRequired(message='Last name is required.'), Length(min=2, max=50)])
    email = StringField('Email', validators=[DataRequired(message='Email is required.'), Email(message='Invalid email address.')])
    password = PasswordField('Password', validators=[DataRequired(message='Password is required.'), Length(min=8, message='Password must be at least 8 characters.')])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(message='Please confirm your password.'), EqualTo('password', message='Passwords do not match.')])
    submit = SubmitField('Create Account')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email is already registered. Please log in.')
