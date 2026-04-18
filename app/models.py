from app import db
from datetime import datetime

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    firstName = db.Column(db.String(50), nullable=False)
    lastName = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='contributor')
    isActive = db.Column(db.Boolean, default=True)
    dateCreated = db.Column(db.DateTime, nullable=False, default=datetime.now)

    recipes = db.relationship('Recipe', backref='author', lazy=True)

class MeasurementUnit(db.Model):
    __tablename__ = 'measurement_units'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True, nullable=False)
    abbreviation = db.Column(db.String(32), unique=True, nullable=False)
    system = db.Column(db.String(32), nullable=False)
    isActive = db.Column(db.Boolean, default=True)

    ingredients = db.relationship('Ingredient', backref='unit', lazy=True)
    
class Recipe(db.Model):
    __tablename__ = 'recipes'

    id = db.Column(db.Integer, primary_key=True)
    authorID = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    instructions = db.Column(db.Text, nullable=False)
    forkedFrom = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=True)
    baseServings = db.Column(db.Integer, nullable=False)
    prepTime = db.Column(db.Integer, nullable=True)
    cookTime = db.Column(db.Integer, nullable=True)
    dateCreated = db.Column(db.DateTime, nullable=False, default=datetime.now)

    ingredients = db.relationship('Ingredient', backref='recipe', lazy=True, cascade='all, delete-orphan')
    categories = db.relationship('RecipeCategory', backref='recipe', lazy=True, cascade='all, delete-orphan')
    dietary_tags = db.relationship('RecipeDietaryTag', backref='recipe', lazy=True, cascade='all, delete-orphan')
    allergens = db.relationship('RecipeAllergen', backref='recipe', lazy=True, cascade='all, delete-orphan')

class Ingredient(db.Model):
    __tablename__ = 'ingredients'

    id = db.Column(db.Integer, primary_key=True)
    recipeID = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False)
    unitID = db.Column(db.Integer, db.ForeignKey('measurement_units.id'), nullable=False)
    name = db.Column(db.String(32), nullable=False)
    quantity = db.Column(db.Float, nullable=False)

class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True, nullable=False)

class RecipeCategory(db.Model):
    __tablename__ = 'recipe_categories'

    id = db.Column(db.Integer, primary_key=True)
    recipeID = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False)
    categoryID = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)

    category = db.relationship('Category', backref='recipe_categories')

class Allergen(db.Model):
    __tablename__ = 'allergens'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True, nullable=False)

class DietaryTag(db.Model):
    __tablename__ = 'dietary_tags'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True, nullable=False)

class RecipeAllergen(db.Model):
    __tablename__ = 'recipe_allergens'

    id = db.Column(db.Integer, primary_key=True)
    recipeID = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False)
    allergenID = db.Column(db.Integer, db.ForeignKey('allergens.id'), nullable=False)

    allergen = db.relationship('Allergen', backref='recipe_allergens')

class RecipeDietaryTag(db.Model):
    __tablename__ = 'recipe_dietary_tags'

    id = db.Column(db.Integer, primary_key=True)
    recipeID = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False)
    dietaryTagID = db.Column(db.Integer, db.ForeignKey('dietary_tags.id'), nullable=False)

    dietaryTag = db.relationship('DietaryTag', backref='recipe_dietary_tags')

class Comment(db.Model):
    __tablename__ = 'comments'

    id = db.Column(db.Integer, primary_key=True)
    recipeID = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False)
    userID = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=True)
    dateCreated = db.Column(db.DateTime, nullable=False, default=datetime.now)

class Rating(db.Model):
    __tablename__ = 'ratings'

    id = db.Column(db.Integer, primary_key=True)
    recipeID = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False)
    userID = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    stars = db.Column(db.Integer, nullable=False)
    dateCreated = db.Column(db.DateTime, nullable=False, default=datetime.now)

class QuickTip(db.Model):
    __tablename__ = 'quick_tips'

    id = db.Column(db.Integer, primary_key=True)
    recipeID = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    userID = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    dateCreated = db.Column(db.DateTime, nullable=False, default=datetime.now)


class Notification(db.Model):
    __tablename__ = 'notification'

    id = db.Column(db.Integer, primary_key=True)
    userID = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    recipeID = db.Column(db.Integer, nullable=True)
    isRead = db.Column(db.Boolean, default=False)
    dateCreated = db.Column(db.DateTime, default=datetime.now)

class Group(db.Model):
    __tablename__ = 'groups'
    id = db.Column(db.Integer, primary_key=True)
    leaderID = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    dateCreated = db.Column(db.DateTime, nullable=False)

    members = db.relationship('GroupMember', backref='group', lazy=True)
    messages = db.relationship('GroupMessage', backref='group', lazy=True)


class GroupMember(db.Model):
    __tablename__ = 'group_members'
    id = db.Column(db.Integer, primary_key=True)
    groupID = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    userID = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    dateJoined = db.Column(db.DateTime, nullable=False)

    user = db.relationship('User', backref='memberships', lazy=True)


class GroupMessage(db.Model):
    __tablename__ = 'group_messages'
    id = db.Column(db.Integer, primary_key=True)
    groupID = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    senderID = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    dateSent = db.Column(db.DateTime, nullable=False)

    sender = db.relationship('User', foreign_keys=[senderID])


class GroupRecipe(db.Model):
    __tablename__ = 'group_recipes'
    id = db.Column(db.Integer, primary_key=True)
    groupID = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    recipeID = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False)
    sharedByID = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    dateSaved = db.Column(db.DateTime, nullable=False)

    recipe = db.relationship('Recipe', foreign_keys=[recipeID])
    sharedBy = db.relationship('User', foreign_keys=[sharedByID])