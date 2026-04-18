from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv
from os import environ
import os

load_dotenv('.flaskenv')

DB_NAME = environ.get('SQLITE_DB', 'recipe.db')
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'open-kitchen-demo'
app.config['WTF_CSRF_ENABLED'] = False
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, DB_NAME)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
Migrate(app, db) 

from app import models, routes
