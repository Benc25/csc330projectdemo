from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from dotenv import load_dotenv
from os import environ
import os

load_dotenv('.flaskenv')

DB_NAME = environ.get('SQLITE_DB', 'recipe.db')
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = environ.get('SECRET_KEY', 'open-kitchen-demo')
app.config['WTF_CSRF_ENABLED'] = False
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, DB_NAME)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Email configuration
app.config['MAIL_SERVER'] = environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = environ.get('MAIL_USE_TLS', True)
app.config['MAIL_USERNAME'] = environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = environ.get('MAIL_DEFAULT_SENDER', 'noreply@openkitchen.com')

db = SQLAlchemy(app)
mail = Mail(app)

from app import models, routes

# Initialize database tables on app startup
with app.app_context():
    db.create_all()
