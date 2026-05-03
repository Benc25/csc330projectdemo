from flask import render_template, request, redirect, url_for, session, flash, jsonify, Response
import types, os, uuid, csv, random, secrets, string
from io import StringIO
from functools import wraps
from datetime import datetime, timedelta

from sqlalchemy import or_, func
from flask_mail import Message

from app import app, db, mail
# Imported ForgotPasswordForm and ResetPasswordForm for password reset workflow
from app.forms import CreateRecipeForm, LoginForm, RegisterForm, ProfileSettingsForm, ForgotPasswordForm, ResetPasswordForm
from app.models import (
    Recipe, Ingredient, RecipeCategory, RecipeDietaryTag, RecipeAllergen,
    Category, DietaryTag, Allergen, MeasurementUnit, Rating, Comment, User,
    Notification, Group, GroupMember, GroupMessage, GroupRecipe, SavedRecipe,
    QuickTip
)


# =============================================================================
# Utility Helpers
# =============================================================================

def save_upload(file_field):
    """Save an uploaded image file to the uploads folder and return the stored filename."""
    if not file_field or not file_field.filename:
        return None
    ext = file_field.filename.rsplit('.', 1)[-1].lower()
    if ext not in app.config['ALLOWED_EXTENSIONS']:
        return None
    filename = f"{uuid.uuid4().hex}.{ext}"
    file_field.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return filename


def login_required(f):
    """Decorator that redirects unauthenticated users to the login page."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def get_current_user():
    """Return the logged-in User object, or None if no session exists."""
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None


def current_user_id():
    """Return the logged-in user's ID from the session, or None."""
    return session.get('user_id')


def _get_avg_rating(recipe_id):
    """Return (avg_stars, rating_count) for a given recipe."""
    result = (
        db.session.query(func.avg(Rating.stars), func.count(Rating.id))
        .filter_by(recipeID=recipe_id)
        .one()
    )
    avg = round(result[0], 1) if result[0] else None
    return avg, result[1]


def _recipe_card_data(recipe):
    """Build a dict of display data for a recipe card."""
    category_links = RecipeCategory.query.filter_by(recipeID=recipe.id).all()
    return {
        'recipe': recipe,
        'ingredient_count': Ingredient.query.filter_by(recipeID=recipe.id).count(),
        'category_names': [rc.category.name for rc in category_links if rc.category],
        'avg_rating': _get_avg_rating(recipe.id)[0],
        'rating_count': _get_avg_rating(recipe.id)[1],
    }


def _comment_author(comment):
    """Return a display name for a comment's author (e.g. 'Jane D.')."""
    user = User.query.get(comment.userID)
    return f"{user.firstName} {user.lastName[0]}." if user else "Anonymous"


def _get_notifications():
    """Return all notifications for the currently logged-in user."""
    uid = current_user_id()
    if uid is None:
        return []
    return Notification.query.filter_by(userID=uid).order_by(Notification.dateCreated.desc()).all()


# =============================================================================
# Context Processors
# =============================================================================

@app.context_processor
def inject_current_user():
    return {'current_user': get_current_user()}


@app.context_processor
def inject_notifications():
    notifications = _get_notifications()
    has_unread = any(not n.isRead for n in notifications)
    return dict(notifications=notifications, has_unread=has_unread)


@app.before_request
def update_last_seen():
    """Keep the user's lastSeen timestamp fresh on every request."""
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            user.lastSeen = datetime.now()
            db.session.commit()


# =============================================================================
# Email
# =============================================================================

def send_welcome_email(user):
    """Send a welcome email to a newly registered user."""
    try:
        msg = Message(
            subject='Welcome to The Open Kitchen!',
            recipients=[user.email],
            html=f"""
            <h2>Welcome to The Open Kitchen, {user.firstName}!</h2>
            <p>Your account has been successfully created.</p>
            <p>Start creating and forking recipes today to build your personal kitchen knowledge.</p>
            <p>Happy cooking!</p>
            """
        )
        mail.send(msg)
    except Exception as e:
        print(f"Failed to send welcome email: {e}")


def send_password_reset_email(user, reset_url):
    """
    Send a password reset email to the user.
    
    ENHANCEMENT: Sends secure password reset link valid for 1 hour.
    
    Args:
        user: User object to send reset email to
        reset_url: Full URL containing the secure reset token for password recovery
    """
    try:
        msg = Message(
            subject='Password Reset Request - The Open Kitchen',
            recipients=[user.email],
            html=f"""
            <h2>Password Reset Request</h2>
            <p>Hi {user.firstName},</p>
            <p>You requested to reset your password. Click the link below to create a new password:</p>
            <p><a href="{reset_url}" style="background-color: #3c66b3; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">Reset Password</a></p>
            <p>This link will expire in 1 hour.</p>
            <p>If you didn't request this reset, please ignore this email.</p>
            <p>The Open Kitchen Team</p>
            """
        )
        mail.send(msg)
    except Exception as e:
        print(f"Failed to send password reset email: {e}")


# =============================================================================
# Auth Routes
# =============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if get_current_user():
        return redirect(url_for('dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            session['user_id'] = user.id
            # If "Remember me" checkbox is checked, set session to persist for 30 days
            if form.remember.data:
                session.permanent = True
                app.permanent_session_lifetime = timedelta(days=30)
            flash(f'Welcome back, {user.firstName}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'error')

    return render_template('login.html', form=form)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if get_current_user():
        return redirect(url_for('dashboard'))

    form = RegisterForm()
    if form.validate_on_submit():
        user = User(
            firstName=form.firstName.data.strip(),
            lastName=form.lastName.data.strip(),
            email=form.email.data.strip()
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        send_welcome_email(user)
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html', form=form)


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('dashboard'))


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """
    Handle password reset requests - generates secure token and sends email
    
    ENHANCEMENT: Database schema updated with password_reset_token and password_reset_token_expiry columns
    to support this functionality. Migration applied: 0ba9ef8aa21c_add_password_reset_fields_to_user.py
    """
    if get_current_user():
        return redirect(url_for('dashboard'))
    
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            # Generate a secure reset token using secrets module (cryptographically strong)
            reset_token = secrets.token_urlsafe(32)
            user.password_reset_token = reset_token
            # Token expires after 1 hour for security
            user.password_reset_token_expiry = datetime.now() + timedelta(hours=1)
            db.session.commit()
            
            # Send password reset email with clickable reset link
            reset_url = url_for('reset_password', token=reset_token, _external=True)
            send_password_reset_email(user, reset_url)
            flash('If an account exists with that email, a password reset link has been sent.', 'info')
        else:
            # Security best practice: don't reveal if email exists in system
            flash('If an account exists with that email, a password reset link has been sent.', 'info')
        
        return redirect(url_for('login'))
    
    return render_template('forgot_password.html', form=form)


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Handle password reset - validates token and allows user to set new password"""
    if get_current_user():
        return redirect(url_for('dashboard'))
    
    # Find user with matching reset token
    user = User.query.filter_by(password_reset_token=token).first()
    
    # Check if token exists and hasn't expired
    if not user or (user.password_reset_token_expiry and user.password_reset_token_expiry < datetime.now()):
        flash('The password reset link is invalid or has expired.', 'error')
        return redirect(url_for('login'))
    
    form = ResetPasswordForm()
    if form.validate_on_submit():
        # Set new password using secure hashing
        user.set_password(form.password.data)
        # Clear reset token to prevent reuse
        user.password_reset_token = None
        user.password_reset_token_expiry = None
        db.session.commit()
        flash('Your password has been reset successfully. Please log in with your new password.', 'success')
        return redirect(url_for('login'))
    
    return render_template('reset_password.html', form=form, token=token)


# =============================================================================
# Dashboard
# =============================================================================

@app.route('/')
def dashboard():
    user = get_current_user()

    # Curators get their own dashboard view
    if user and user.role == 'curator':
        return redirect(url_for('curator_dashboard'))

    # Subquery for average rating and count per recipe
    rated_subq = (
        db.session.query(
            Rating.recipeID,
            func.avg(Rating.stars).label('avg'),
            func.count(Rating.id).label('cnt')
        )
        .group_by(Rating.recipeID)
        .subquery()
    )

    # Single highest-rated recipe for the hero card
    top_recipe_obj = (
        db.session.query(Recipe)
        .join(rated_subq, Recipe.id == rated_subq.c.recipeID)
        .order_by(rated_subq.c.avg.desc(), rated_subq.c.cnt.desc())
        .first()
    )
    top_recipe = _recipe_card_data(top_recipe_obj) if top_recipe_obj else None

    # Top 3 recipes by rating for the Popular section
    popular_recipes = (
        db.session.query(Recipe)
        .join(rated_subq, Recipe.id == rated_subq.c.recipeID)
        .order_by(rated_subq.c.avg.desc(), rated_subq.c.cnt.desc())
        .limit(3)
        .all()
    )
    popular = [_recipe_card_data(r) for r in popular_recipes]

    # Random selection for the Discover section
    all_recipes = Recipe.query.all()
    random_recipes = [_recipe_card_data(r) for r in random.sample(all_recipes, min(6, len(all_recipes)))]

    # 6 most recently created recipes
    newest = [_recipe_card_data(r) for r in Recipe.query.order_by(Recipe.dateCreated.desc()).limit(6).all()]

    # Recipes the logged-in user has saved
    saved_recipes = []
    if user:
        saved_query = (
            db.session.query(Recipe)
            .join(SavedRecipe, Recipe.id == SavedRecipe.recipeID)
            .filter(SavedRecipe.userID == user.id)
            .all()
        )
        saved_recipes = [_recipe_card_data(r) for r in saved_query]

    stats = {
        'recipes': Recipe.query.count(),
        'categories': Category.query.count(),
        'tags': DietaryTag.query.count(),
        'allergens': Allergen.query.count(),
    }

    return render_template('dashboard.html',
                           user=user,
                           top_recipe=top_recipe,
                           popular=popular,
                           random_recipes=random_recipes,
                           newest=newest,
                           saved_recipes=saved_recipes,
                           stats=stats)


# =============================================================================
# Profile
# =============================================================================

@app.route('/profile/settings', methods=['GET', 'POST'])
@login_required
def profile_settings():
    user = get_current_user()
    form = ProfileSettingsForm()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'avatar' and form.validate_on_submit():
            new_avatar = save_upload(form.avatar.data)
            if new_avatar:
                user.avatar = new_avatar
                db.session.commit()
                flash('Profile picture updated!', 'success')
            else:
                flash('Please choose a valid image file.', 'error')

        elif action == 'preferences':
            user.preferMetric = request.form.get('preferMetric') == 'on'
            user.disableNotifications = request.form.get('disableNotifications') == 'on'
            db.session.commit()

        return redirect(url_for('profile_settings'))

    return render_template('profile_settings.html', form=form, user=user)


@app.route('/profile/toggle-dnd', methods=['POST'])
@login_required
def toggle_dnd():
    """Toggle the Do Not Disturb status for the current user."""
    user = get_current_user()
    user.doNotDisturb = not user.doNotDisturb
    db.session.commit()
    return jsonify({'doNotDisturb': user.doNotDisturb})


# =============================================================================
# Recipe CRUD
# =============================================================================

def _populate_recipe_form(form):
    """Fill in the dropdown choices for the recipe create/edit form."""
    form.category_id.choices = (
        [(0, '-- Select Category --')] +
        [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]
    )
    form.dietary_tags.choices = [(t.id, t.name) for t in DietaryTag.query.order_by(DietaryTag.name).all()]
    form.allergens.choices = [(a.id, a.name) for a in Allergen.query.order_by(Allergen.name).all()]


def _parse_ingredients(ing_names, ing_qtys, ing_units):
    """
    Parse parallel ingredient lists from form data.
    Returns (parsed_ingredients, errors) where parsed_ingredients is a list of
    (name, quantity, unit_id) tuples.
    """
    parsed, errors = [], []
    for idx, (name, qty, unit_id) in enumerate(zip(ing_names, ing_qtys, ing_units), start=1):
        name = (name or '').strip()
        qty = (qty or '').strip()
        unit_id = (unit_id or '').strip()

        # Skip completely empty rows
        if not name and not qty and not unit_id:
            continue
        if not name:
            errors.append(f'Ingredient row {idx} is missing a name.')
            continue
        try:
            quantity = float(qty) if qty else 0.0
        except ValueError:
            errors.append(f'Ingredient row {idx} has an invalid quantity.')
            continue
        try:
            parsed_unit_id = int(unit_id) if unit_id else 1
        except ValueError:
            parsed_unit_id = 1

        parsed.append((name, quantity, parsed_unit_id))
    return parsed, errors


@app.route('/recipe/create', methods=['GET', 'POST'])
@login_required
def create_recipe():
    uid = current_user_id()
    form = CreateRecipeForm()
    _populate_recipe_form(form)
    units = MeasurementUnit.query.filter_by(isActive=True).order_by(MeasurementUnit.name).all()

    if form.dietary_tags.data is None:
        form.dietary_tags.data = []
    if form.allergens.data is None:
        form.allergens.data = []

    errors = []

    if form.validate_on_submit():
        ing_names = request.form.getlist('ing_name')
        ing_qtys = request.form.getlist('ing_quantity')
        ing_units = request.form.getlist('ing_unit')

        parsed_ingredients, parse_errors = _parse_ingredients(ing_names, ing_qtys, ing_units)
        errors.extend(parse_errors)

        if not any((n or '').strip() for n in ing_names):
            errors.append('At least one ingredient is required.')
        if Recipe.query.filter_by(authorID=uid, title=form.title.data.strip()).first():
            errors.append('You already have a recipe with this name.')

        if not errors:
            new_recipe = Recipe(
                authorID=uid,
                title=form.title.data.strip(),
                description=(form.description.data or '').strip() or None,
                instructions=form.instructions.data.strip(),
                baseServings=form.baseServings.data,
                prepTime=form.prepTime.data or None,
                cookTime=form.cookTime.data or None,
                image=save_upload(form.image.data),
            )
            db.session.add(new_recipe)
            db.session.flush()

            for name, quantity, unit_id in parsed_ingredients:
                db.session.add(Ingredient(recipeID=new_recipe.id, unitID=unit_id, name=name, quantity=quantity))

            if form.category_id.data and form.category_id.data != 0:
                db.session.add(RecipeCategory(recipeID=new_recipe.id, categoryID=form.category_id.data))

            for tag_id in form.dietary_tags.data:
                db.session.add(RecipeDietaryTag(recipeID=new_recipe.id, dietaryTagID=tag_id))

            for allergen_id in form.allergens.data:
                db.session.add(RecipeAllergen(recipeID=new_recipe.id, allergenID=allergen_id))

            db.session.commit()
            return redirect(url_for('view_recipe', recipe_id=new_recipe.id))

    errors.extend(msg for msgs in form.errors.values() for msg in msgs)
    return render_template('recipe_form.html', form=form, units=units, errors=errors,
                           is_edit=False, existing_ingredients=[], recipe=None)


@app.route('/recipe/<int:recipe_id>')
def view_recipe(recipe_id):
    uid = current_user_id()
    user = get_current_user()
    recipe = Recipe.query.get_or_404(recipe_id)

    ingredients = Ingredient.query.filter_by(recipeID=recipe_id).all()
    categories = RecipeCategory.query.filter_by(recipeID=recipe_id).all()
    dietary_tags = RecipeDietaryTag.query.filter_by(recipeID=recipe_id).all()
    allergens = RecipeAllergen.query.filter_by(recipeID=recipe_id).all()

    avg_rating, rating_count = _get_avg_rating(recipe_id)
    user_rating = Rating.query.filter_by(recipeID=recipe_id, userID=uid).first() if uid else None
    is_saved = bool(SavedRecipe.query.filter_by(userID=uid, recipeID=recipe_id).first()) if uid else False

    # Comments sorted by newest or oldest
    sort = request.args.get('sort', 'newest')
    order = Comment.dateCreated.asc() if sort == 'oldest' else Comment.dateCreated.desc()
    comments = Comment.query.filter_by(recipeID=recipe_id).order_by(order).all()
    for c in comments:
        c.author_name = _comment_author(c)

    # Consume a one-time toast notification stored in the session
    toast_notif = None
    toast_id = session.pop('toast_notification_id', None)
    if toast_id:
        toast_notif = Notification.query.get(toast_id)

    memberships = GroupMember.query.filter_by(userID=uid).all() if uid else []

    quick_tips = QuickTip.query.filter_by(recipeID=recipe_id).order_by(QuickTip.dateCreated.desc()).all()
    for t in quick_tips:
        tip_user = User.query.get(t.userID)
        t.author_name = f"{tip_user.firstName} {tip_user.lastName[0]}." if tip_user else "Anonymous"

    return render_template(
        'view_recipe.html',
        recipe=recipe,
        current_user=user,
        ingredients=ingredients,
        categories=categories,
        dietary_tags=dietary_tags,
        allergens=allergens,
        avg_rating=avg_rating,
        rating_count=rating_count,
        user_rating=user_rating,
        is_saved=is_saved,
        comments=comments,
        sort=sort,
        toast_notif=toast_notif,
        memberships=memberships,
        quick_tips=quick_tips,
    )


@app.route('/recipe/<int:recipe_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_recipe(recipe_id):
    current_user = get_current_user()
    recipe = Recipe.query.get_or_404(recipe_id)

    if recipe.authorID != current_user.id:
        flash('You do not have permission to edit this recipe.', 'error')
        return redirect(url_for('view_recipe', recipe_id=recipe_id))

    form = CreateRecipeForm()
    _populate_recipe_form(form)
    units = MeasurementUnit.query.filter_by(isActive=True).order_by(MeasurementUnit.name).all()
    errors = []
    existing_ingredients = Ingredient.query.filter_by(recipeID=recipe_id).all()

    if form.validate_on_submit():
        ing_names = request.form.getlist('ing_name')
        ing_qtys = request.form.getlist('ing_quantity')
        ing_units = request.form.getlist('ing_unit')

        parsed_ingredients, parse_errors = _parse_ingredients(ing_names, ing_qtys, ing_units)
        errors.extend(parse_errors)

        if not any((n or '').strip() for n in ing_names):
            errors.append('At least one ingredient is required.')

        new_title = form.title.data.strip()
        if new_title != recipe.title:
            if Recipe.query.filter_by(authorID=current_user.id, title=new_title).first():
                errors.append('You already have a recipe with this name.')

        if not errors:
            recipe.title = new_title
            recipe.description = (form.description.data or '').strip() or None
            recipe.instructions = form.instructions.data.strip()
            recipe.baseServings = form.baseServings.data
            recipe.prepTime = form.prepTime.data or None
            recipe.cookTime = form.cookTime.data or None
            new_image = save_upload(form.image.data)
            if new_image:
                recipe.image = new_image

            # Replace all relational data with the updated values
            Ingredient.query.filter_by(recipeID=recipe_id).delete()
            for name, quantity, unit_id in parsed_ingredients:
                db.session.add(Ingredient(recipeID=recipe_id, unitID=unit_id, name=name, quantity=quantity))

            RecipeCategory.query.filter_by(recipeID=recipe_id).delete()
            if form.category_id.data and form.category_id.data != 0:
                db.session.add(RecipeCategory(recipeID=recipe_id, categoryID=form.category_id.data))

            RecipeDietaryTag.query.filter_by(recipeID=recipe_id).delete()
            for tag_id in form.dietary_tags.data:
                db.session.add(RecipeDietaryTag(recipeID=recipe_id, dietaryTagID=tag_id))

            RecipeAllergen.query.filter_by(recipeID=recipe_id).delete()
            for allergen_id in form.allergens.data:
                db.session.add(RecipeAllergen(recipeID=recipe_id, allergenID=allergen_id))

            db.session.commit()
            flash('Recipe updated successfully!', 'success')
            return redirect(url_for('view_recipe', recipe_id=recipe_id))

        # Re-populate existing_ingredients from submitted form data on validation failure
        existing_ingredients = []
        for name, qty, unit_id in zip(ing_names, ing_qtys, ing_units):
            name = (name or '').strip()
            if not name:
                continue

            class _FakeIng:
                pass

            fi = _FakeIng()
            fi.name = name
            fi.quantity = float(qty) if qty else 0.0
            try:
                fi.unitID = int(unit_id) if unit_id else 1
            except ValueError:
                fi.unitID = 1
            existing_ingredients.append(fi)

    elif request.method == 'GET':
        # Pre-fill the form with the existing recipe data
        form.title.data = recipe.title
        form.description.data = recipe.description
        form.instructions.data = recipe.instructions
        form.baseServings.data = recipe.baseServings
        form.prepTime.data = recipe.prepTime
        form.cookTime.data = recipe.cookTime

        category_link = RecipeCategory.query.filter_by(recipeID=recipe_id).first()
        form.category_id.data = category_link.categoryID if category_link else 0

        form.dietary_tags.data = [dt.dietaryTagID for dt in RecipeDietaryTag.query.filter_by(recipeID=recipe_id).all()]
        form.allergens.data = [a.allergenID for a in RecipeAllergen.query.filter_by(recipeID=recipe_id).all()]

    errors.extend(msg for msgs in form.errors.values() for msg in msgs)
    return render_template('recipe_form.html', form=form, units=units, errors=errors, recipe=recipe,
                           current_user=current_user, is_edit=True,
                           existing_ingredients=existing_ingredients)


@app.route('/recipe/<int:recipe_id>/delete', methods=['POST'])
@login_required
def delete_recipe(recipe_id):
    """Delete a recipe and all its associated ratings, comments, and notifications."""
    Recipe.query.get_or_404(recipe_id)
    Rating.query.filter_by(recipeID=recipe_id).delete()
    Comment.query.filter_by(recipeID=recipe_id).delete()
    Notification.query.filter_by(recipeID=recipe_id).delete()
    db.session.delete(Recipe.query.get(recipe_id))
    db.session.commit()
    return redirect(url_for('dashboard'))


@app.route('/recipe/<int:recipe_id>/fork', methods=['POST'])
@login_required
def fork_recipe(recipe_id):
    """Create a copy of an existing recipe under the current user's account."""
    original_recipe = Recipe.query.get_or_404(recipe_id)
    current_user = get_current_user()

    forked_recipe = original_recipe.fork(current_user.id)
    db.session.add(forked_recipe)
    db.session.flush()

    # Copy all ingredients, categories, tags, and allergens to the forked recipe
    for ing in Ingredient.query.filter_by(recipeID=recipe_id).all():
        db.session.add(Ingredient(recipeID=forked_recipe.id, unitID=ing.unitID, name=ing.name, quantity=ing.quantity))

    for cat in RecipeCategory.query.filter_by(recipeID=recipe_id).all():
        db.session.add(RecipeCategory(recipeID=forked_recipe.id, categoryID=cat.categoryID))

    for tag in RecipeDietaryTag.query.filter_by(recipeID=recipe_id).all():
        db.session.add(RecipeDietaryTag(recipeID=forked_recipe.id, dietaryTagID=tag.dietaryTagID))

    for allergen in RecipeAllergen.query.filter_by(recipeID=recipe_id).all():
        db.session.add(RecipeAllergen(recipeID=forked_recipe.id, allergenID=allergen.allergenID))

    db.session.commit()
    flash(f'Recipe "{original_recipe.title}" forked to your account!', 'success')
    return redirect(url_for('view_recipe', recipe_id=forked_recipe.id))


@app.route('/recipe/<int:recipe_id>/save', methods=['POST'])
@login_required
def save_recipe(recipe_id):
    """Toggle a recipe as saved/unsaved for the current user."""
    current_user = get_current_user()
    Recipe.query.get_or_404(recipe_id)

    existing = SavedRecipe.query.filter_by(userID=current_user.id, recipeID=recipe_id).first()
    if existing:
        db.session.delete(existing)
        flash('Recipe removed from saved.', 'info')
    else:
        db.session.add(SavedRecipe(userID=current_user.id, recipeID=recipe_id))
        flash('Recipe saved!', 'success')

    db.session.commit()
    return redirect(request.referrer or url_for('view_recipe', recipe_id=recipe_id))


@app.route('/recipe/<int:recipe_id>/is-saved')
@login_required
def is_recipe_saved(recipe_id):
    current_user = get_current_user()
    saved = SavedRecipe.query.filter_by(userID=current_user.id, recipeID=recipe_id).first()
    return {'is_saved': bool(saved)}


# =============================================================================
# Comments and Tips
# =============================================================================

@app.route('/recipe/<int:recipe_id>/comments', methods=['POST'])
@login_required
def post_comment(recipe_id):
    uid = current_user_id()
    recipe = Recipe.query.get_or_404(recipe_id)

    # Save a star rating if one was submitted alongside the comment
    try:
        stars = int(request.form.get('stars', 0))
    except (ValueError, TypeError):
        stars = 0

    if 1 <= stars <= 5:
        existing = Rating.query.filter_by(recipeID=recipe_id, userID=uid).first()
        if existing:
            existing.stars = stars
        else:
            db.session.add(Rating(recipeID=recipe_id, userID=uid, stars=stars))

    content = request.form.get('content', '').strip()
    if content:
        new_comment = Comment(recipeID=recipe_id, userID=uid, content=content)
        db.session.add(new_comment)
        db.session.flush()

        # Create a notification and store its ID in the session for a toast popup
        author = _comment_author(new_comment)
        new_notif = Notification(
            userID=uid,
            title='New Comment',
            message=f'{author} commented on "{recipe.title}"',
            recipeID=recipe_id,
            isRead=False,
        )
        db.session.add(new_notif)
        db.session.flush()
        session['toast_notification_id'] = new_notif.id

    db.session.commit()
    return redirect(url_for('view_recipe', recipe_id=recipe_id))


@app.route('/recipe/<int:recipe_id>/tips', methods=['POST'])
@login_required
def post_tip(recipe_id):
    uid = current_user_id()
    Recipe.query.get_or_404(recipe_id)

    title = request.form.get('tip_title', '').strip()
    content = request.form.get('tip_content', '').strip()

    if title and content:
        db.session.add(QuickTip(recipeID=recipe_id, userID=uid, title=title, content=content))
        db.session.commit()

    return redirect(url_for('view_recipe', recipe_id=recipe_id))


@app.route('/recipe/<int:recipe_id>/rate', methods=['POST'])
@login_required
def rate_recipe(recipe_id):
    uid = current_user_id()
    Recipe.query.get_or_404(recipe_id)

    try:
        stars = int(request.form.get('stars', 0))
    except (ValueError, TypeError):
        stars = 0

    if not (1 <= stars <= 5):
        return redirect(url_for('view_recipe', recipe_id=recipe_id))

    existing = Rating.query.filter_by(recipeID=recipe_id, userID=uid).first()
    if existing:
        existing.stars = stars
    else:
        db.session.add(Rating(recipeID=recipe_id, userID=uid, stars=stars))

    db.session.commit()
    return redirect(url_for('view_recipe', recipe_id=recipe_id))


# =============================================================================
# Notifications
# =============================================================================

@app.route('/notifications/<int:notification_id>/delete', methods=['POST'])
@login_required
def delete_notification(notification_id):
    notif = Notification.query.get_or_404(notification_id)
    db.session.delete(notif)
    db.session.commit()
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/notifications/mark-read', methods=['POST'])
@login_required
def mark_notifications_read():
    Notification.query.filter_by(userID=current_user_id(), isRead=False).update({'isRead': True})
    db.session.commit()
    return redirect(request.referrer or url_for('dashboard'))


# =============================================================================
# Search
# =============================================================================

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    results = []

    if query:
        # Search across title, description, ingredients, dietary tags, and allergens
        title_matches = Recipe.query.filter(Recipe.title.ilike(f'%{query}%')).all()
        desc_matches = Recipe.query.filter(Recipe.description.ilike(f'%{query}%')).all()
        ingredient_matches = db.session.query(Recipe).join(Ingredient).filter(Ingredient.name.ilike(f'%{query}%')).all()
        tag_matches = db.session.query(Recipe).join(RecipeDietaryTag).join(DietaryTag).filter(DietaryTag.name.ilike(f'%{query}%')).all()
        allergen_matches = db.session.query(Recipe).join(RecipeAllergen).join(Allergen).filter(Allergen.name.ilike(f'%{query}%')).all()

        # Deduplicate while preserving order
        seen = set()
        for recipe in title_matches + desc_matches + ingredient_matches + tag_matches + allergen_matches:
            if recipe.id not in seen:
                seen.add(recipe.id)
                results.append(_recipe_card_data(recipe))

    return render_template('search.html', query=query, results=results)


# =============================================================================
# Groups
# =============================================================================

@app.route('/groups')
@login_required
def my_groups():
    user = get_current_user()

    user_groups = (
        db.session.query(Group)
        .join(GroupMember, Group.id == GroupMember.groupID)
        .filter(GroupMember.userID == user.id)
        .all()
    )

    user_recipes = Recipe.query.filter_by(authorID=user.id).order_by(Recipe.dateCreated.desc()).all()

    saved_query = (
        db.session.query(Recipe)
        .join(SavedRecipe, Recipe.id == SavedRecipe.recipeID)
        .filter(SavedRecipe.userID == user.id)
        .all()
    )

    avg_rating = (
        db.session.query(func.avg(Rating.stars))
        .join(Recipe, Rating.recipeID == Recipe.id)
        .filter(Recipe.authorID == user.id)
        .scalar()
    )

    return render_template('groups/index.html',
                           user=user,
                           groups=user_groups,
                           recipe_data=[_recipe_card_data(r) for r in user_recipes],
                           saved_recipes=[_recipe_card_data(r) for r in saved_query],
                           message_count=GroupMessage.query.filter_by(senderID=user.id).count(),
                           avg_rating=round(avg_rating, 1) if avg_rating else None)


@app.route('/groups/create', methods=['GET', 'POST'])
@login_required
def create_group():
    uid = current_user_id()
    if request.method == 'POST':
        new_group = Group(
            leaderID=uid,
            name=request.form.get('name'),
            description=request.form.get('description'),
            dateCreated=datetime.utcnow()
        )
        db.session.add(new_group)
        db.session.flush()

        db.session.add(GroupMember(groupID=new_group.id, userID=uid, dateJoined=datetime.utcnow()))
        db.session.commit()
        return redirect(url_for('view_group', group_id=new_group.id))

    return render_template('groups/create.html')


@app.route('/groups/<int:group_id>')
def view_group(group_id):
    group = Group.query.get_or_404(group_id)
    return render_template('groups/view.html',
                           group=group,
                           messages=GroupMessage.query.filter_by(groupID=group_id).order_by(GroupMessage.dateSent).all(),
                           shared_recipes=GroupRecipe.query.filter_by(groupID=group_id).all(),
                           members=GroupMember.query.filter_by(groupID=group_id).all())


@app.route('/groups/<int:group_id>/message', methods=['POST'])
@login_required
def send_message(group_id):
    db.session.add(GroupMessage(
        groupID=group_id,
        senderID=current_user_id(),
        content=request.form.get('content'),
        dateSent=datetime.utcnow()
    ))
    db.session.commit()
    return redirect(url_for('view_group', group_id=group_id))


@app.route('/groups/<int:group_id>/share/<int:recipe_id>', methods=['POST'])
@login_required
def share_recipe(group_id, recipe_id):
    db.session.add(GroupRecipe(
        groupID=group_id,
        recipeID=recipe_id,
        sharedByID=current_user_id(),
        dateSaved=datetime.utcnow()
    ))
    db.session.commit()
    return redirect(url_for('view_group', group_id=group_id))


@app.route('/groups/<int:group_id>/add_member', methods=['POST'])
@login_required
def add_member(group_id):
    Group.query.get_or_404(group_id)
    user = User.query.filter_by(email=request.form.get('email')).first()
    if user and not GroupMember.query.filter_by(groupID=group_id, userID=user.id).first():
        db.session.add(GroupMember(groupID=group_id, userID=user.id, dateJoined=datetime.utcnow()))
        db.session.commit()
    return redirect(url_for('view_group', group_id=group_id))


# =============================================================================
# Curator Dashboard
# =============================================================================

def _curator_required(f):
    """Decorator that redirects non-curators away from curator-only pages."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or user.role != 'curator':
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


@app.route('/curator')
@login_required
@_curator_required
def curator_dashboard():
    # User search
    search_query = request.args.get('q', '').strip()
    if search_query:
        users = User.query.filter(
            or_(
                User.firstName.ilike(f'%{search_query}%'),
                User.lastName.ilike(f'%{search_query}%'),
                User.email.ilike(f'%{search_query}%')
            )
        ).all()
    else:
        users = User.query.all()

    # Group search
    group_query = request.args.get('gq', '').strip()
    if group_query:
        groups = Group.query.filter(Group.name.ilike(f'%{group_query}%')).all()
    else:
        groups = Group.query.order_by(Group.dateCreated.desc()).all()

    stats = {
        'recipes': Recipe.query.count(),
        'users': User.query.count(),
        'groups': Group.query.count(),
        'messages': GroupMessage.query.count(),
    }

    return render_template('curator/dashboard.html',
                           users=users,
                           search_query=search_query,
                           groups=groups,
                           group_query=group_query,
                           stats=stats)


@app.route('/curator/reports')
@login_required
@_curator_required
def curator_reports():
    online_cutoff = datetime.now() - timedelta(minutes=5)
    stats = {
        'active_users': User.query.filter_by(isActive=True).count(),
        'online_users': User.query.filter(User.lastSeen >= online_cutoff).count(),
        'total_recipes': Recipe.query.count(),
        'total_messages': GroupMessage.query.count(),
    }
    return render_template('curator/reports.html', stats=stats)


@app.route('/curator/reports/user-activity')
@login_required
@_curator_required
def curator_user_activity():
    online_cutoff = datetime.now() - timedelta(minutes=5)
    search_query = request.args.get('q', '').strip()

    base_q = User.query.filter_by(isActive=True)
    if search_query:
        base_q = base_q.filter(
            or_(
                User.firstName.ilike(f'%{search_query}%'),
                User.lastName.ilike(f'%{search_query}%'),
                User.email.ilike(f'%{search_query}%'),
                User.role.ilike(f'%{search_query}%'),
            )
        )

    return render_template('curator/user_activity.html',
                           active_users=base_q.all(),
                           online_users=User.query.filter(User.lastSeen >= online_cutoff).all(),
                           online_cutoff=online_cutoff,
                           search_query=search_query)


@app.route('/curator/reports/recipes')
@login_required
@_curator_required
def curator_recipe_stats():
    now = datetime.now()
    periods = {
        '24h': now - timedelta(hours=24),
        '7d':  now - timedelta(days=7),
        '28d': now - timedelta(days=28),
        '1y':  now - timedelta(days=365),
        'all': None,
    }

    def top_recipes(since):
        q = (
            db.session.query(
                Recipe,
                func.avg(Rating.stars).label('avg_rating'),
                func.count(Rating.id).label('rating_count'),
                User.firstName,
                User.lastName,
            )
            .join(Rating, Rating.recipeID == Recipe.id)
            .join(User, User.id == Recipe.authorID)
        )
        if since:
            q = q.filter(Recipe.dateCreated >= since)
        q = q.group_by(Recipe.id).order_by(func.avg(Rating.stars).desc(), func.count(Rating.id).desc()).limit(10)
        return [
            {
                'id': r.Recipe.id,
                'title': r.Recipe.title,
                'author': f'{r.firstName} {r.lastName}',
                'avg_rating': round(r.avg_rating, 2),
                'rating_count': r.rating_count,
                'date_created': r.Recipe.dateCreated.strftime('%b %d, %Y'),
            }
            for r in q.all()
        ]

    return render_template('curator/recipe_stats.html',
                           recipe_data={key: top_recipes(since) for key, since in periods.items()})


@app.route('/curator/reports/recipes/export')
@login_required
@_curator_required
def curator_recipe_stats_export():
    period = request.args.get('period', 'all')
    try:
        count = max(1, int(request.args.get('count', 10)))
    except (ValueError, TypeError):
        count = 10

    now = datetime.now()
    period_map = {
        '24h': now - timedelta(hours=24),
        '7d':  now - timedelta(days=7),
        '28d': now - timedelta(days=28),
        '1y':  now - timedelta(days=365),
        'all': None,
    }
    since = period_map.get(period)

    q = (
        db.session.query(
            Recipe,
            func.avg(Rating.stars).label('avg_rating'),
            func.count(Rating.id).label('rating_count'),
            User.firstName,
            User.lastName,
        )
        .join(Rating, Rating.recipeID == Recipe.id)
        .join(User, User.id == Recipe.authorID)
    )
    if since:
        q = q.filter(Recipe.dateCreated >= since)
    q = q.group_by(Recipe.id).order_by(func.avg(Rating.stars).desc(), func.count(Rating.id).desc()).limit(count)

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Rank', 'Title', 'Author', 'Avg Rating', 'Rating Count', 'Date Created'])
    for i, r in enumerate(q.all(), start=1):
        writer.writerow([i, r.Recipe.title, f'{r.firstName} {r.lastName}',
                         round(r.avg_rating, 2), r.rating_count,
                         r.Recipe.dateCreated.strftime('%Y-%m-%d')])

    period_labels = {'24h': 'last_24h', '7d': 'last_7_days', '28d': 'last_28_days', '1y': 'last_year', 'all': 'all_time'}
    filename = f'top_{count}_recipes_{period_labels.get(period, period)}.csv'

    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@app.route('/curator/reports/messages')
@login_required
@_curator_required
def curator_message_stats():
    import re
    from collections import Counter, defaultdict

    # Common words excluded from word-frequency analysis
    STOP_WORDS = {
        'the','a','an','and','or','but','in','on','at','to','for','of','with',
        'is','it','its','was','are','be','been','being','have','has','had',
        'do','did','does','will','would','could','should','may','might','shall',
        'not','no','so','as','by','from','that','this','these','those','then',
        'than','if','i','you','he','she','we','they','me','him','her','us','them',
        'my','your','his','our','their','what','which','who','how','when','where',
        'just','up','out','about','into','more','also','can','all','there','here',
        'get','got','like','well','one','some','any','over','now','only','very',
        'too','use','s','t','re','ve','ll','d','m',
    }

    now = datetime.now()

    def make_buckets(bucket_type, since):
        """Build time-bucket keys and display labels for a given period."""
        keys, labels = [], []
        if bucket_type == 'hour':
            for i in range(23, -1, -1):
                t = (now - timedelta(hours=i)).replace(minute=0, second=0, microsecond=0)
                keys.append(t.strftime('%Y-%m-%d-%H'))
                labels.append(t.strftime('%b %d %H:00'))
        elif bucket_type == 'day':
            total_days = (now.date() - since.date()).days + 1
            for i in range(total_days - 1, -1, -1):
                t = now.date() - timedelta(days=i)
                keys.append(t.strftime('%Y-%m-%d'))
                labels.append(t.strftime('%b %d'))
        else:  # month
            if since:
                start = since.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                earliest = GroupMessage.query.order_by(GroupMessage.dateSent.asc()).first()
                start = earliest.dateSent.replace(day=1, hour=0, minute=0, second=0, microsecond=0) if earliest else now.replace(day=1)
            cur = start
            end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            while cur <= end:
                keys.append(cur.strftime('%Y-%m'))
                labels.append(cur.strftime('%b %Y'))
                cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        return keys, labels

    def compute_period(bucket_type, since):
        """Count word frequencies per time bucket for the given period."""
        keys, labels = make_buckets(bucket_type, since)
        q = GroupMessage.query
        if since:
            q = q.filter(GroupMessage.dateSent >= since)
        messages = q.with_entities(GroupMessage.content, GroupMessage.dateSent).all()

        counter = Counter()
        bucket_counts = defaultdict(Counter)

        for content, sent in messages:
            key = sent.strftime('%Y-%m-%d-%H' if bucket_type == 'hour' else '%Y-%m-%d' if bucket_type == 'day' else '%Y-%m')
            for w in re.findall(r"[a-zA-Z']+", content.lower()):
                w = w.strip("'")
                if len(w) > 1 and w not in STOP_WORDS:
                    counter[w] += 1
                    bucket_counts[key][w] += 1

        top_words = counter.most_common(25)
        return {
            'words': [[w, c] for w, c in top_words],
            'labels': labels,
            'series': {word: [bucket_counts[k][word] for k in keys] for word, _ in top_words},
        }

    period_configs = [
        ('24h', 'hour',  now - timedelta(hours=24)),
        ('7d',  'day',   now - timedelta(days=7)),
        ('28d', 'day',   now - timedelta(days=28)),
        ('1y',  'month', now - timedelta(days=365)),
        ('all', 'month', None),
    ]

    return render_template('curator/message_stats.html',
                           word_data={key: compute_period(bt, since) for key, bt, since in period_configs})


@app.route('/curator/user/<int:user_id>')
@login_required
@_curator_required
def curator_user_profile(user_id):
    _profile = User.query.get_or_404(user_id)
    profile = types.SimpleNamespace(
        id=_profile.id,
        firstName=_profile.firstName,
        lastName=_profile.lastName,
        email=_profile.email,
        role=_profile.role,
        dateCreated=_profile.dateCreated,
        avatar=_profile.avatar,
        preferMetric=_profile.preferMetric,
        disableNotifications=_profile.disableNotifications,
    )
    return render_template('curator/user_profile.html',
                           profile=profile,
                           recipes=[_recipe_card_data(r) for r in Recipe.query.filter_by(authorID=user_id).order_by(Recipe.dateCreated.desc()).all()],
                           memberships=GroupMember.query.filter_by(userID=user_id).all(),
                           messages=GroupMessage.query.filter_by(senderID=user_id).order_by(GroupMessage.dateSent.desc()).all())


# =============================================================================
# Curator Data Exports (CSV)
# =============================================================================

def _csv_response(rows, headers, filename):
    """Build a CSV download response from a list of row tuples."""
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@app.route('/curator/export/recipes')
@login_required
@_curator_required
def export_recipes():
    rows = [
        [r.id, r.title, f"{r.author.firstName} {r.author.lastName}",
         r.description, r.baseServings, r.prepTime, r.cookTime, r.dateCreated]
        for r in Recipe.query.all()
    ]
    return _csv_response(rows, ['ID', 'Title', 'Author', 'Description', 'Base Servings', 'Prep Time', 'Cook Time', 'Date Created'], 'recipes.csv')


@app.route('/curator/export/users')
@login_required
@_curator_required
def export_users():
    rows = [
        [u.id, u.firstName, u.lastName, u.email, u.role, u.isActive, u.dateCreated]
        for u in User.query.all()
    ]
    return _csv_response(rows, ['ID', 'First Name', 'Last Name', 'Email', 'Role', 'Active', 'Date Created'], 'users.csv')


@app.route('/curator/export/groups')
@login_required
@_curator_required
def export_groups():
    rows = []
    for g in Group.query.all():
        leader = User.query.get(g.leaderID)
        rows.append([g.id, g.name, g.description,
                     f"{leader.firstName} {leader.lastName}" if leader else 'N/A',
                     len(g.members), g.dateCreated])
    return _csv_response(rows, ['ID', 'Name', 'Description', 'Leader', 'Member Count', 'Date Created'], 'groups.csv')


@app.route('/curator/export/messages')
@login_required
@_curator_required
def export_messages():
    rows = [
        [m.id, f"{m.sender.firstName} {m.sender.lastName}", m.group.name, m.content, m.dateSent]
        for m in GroupMessage.query.all()
    ]
    return _csv_response(rows, ['ID', 'Sender', 'Group', 'Content', 'Date Sent'], 'messages.csv')


# =============================================================================
# Curator Delete Actions
# =============================================================================

@app.route('/curator/user/<int:user_id>/delete', methods=['POST'])
@login_required
@_curator_required
def curator_delete_user(user_id):
    target = User.query.get_or_404(user_id)

    # Remove all content owned by this user before deleting the account
    for recipe in Recipe.query.filter_by(authorID=user_id).all():
        Rating.query.filter_by(recipeID=recipe.id).delete()
        Comment.query.filter_by(recipeID=recipe.id).delete()
        Notification.query.filter_by(recipeID=recipe.id).delete()
        GroupRecipe.query.filter_by(recipeID=recipe.id).delete()
        SavedRecipe.query.filter_by(recipeID=recipe.id).delete()
        db.session.delete(recipe)

    GroupMember.query.filter_by(userID=user_id).delete()
    GroupMessage.query.filter_by(senderID=user_id).delete()
    Rating.query.filter_by(userID=user_id).delete()
    Comment.query.filter_by(userID=user_id).delete()
    Notification.query.filter_by(userID=user_id).delete()
    SavedRecipe.query.filter_by(userID=user_id).delete()

    db.session.delete(target)
    db.session.commit()
    flash(f'User "{target.firstName} {target.lastName}" has been deleted.', 'success')
    return redirect(url_for('curator_dashboard'))


@app.route('/curator/group/<int:group_id>/delete', methods=['POST'])
@login_required
@_curator_required
def curator_delete_group(group_id):
    group = Group.query.get_or_404(group_id)
    GroupMember.query.filter_by(groupID=group_id).delete()
    GroupMessage.query.filter_by(groupID=group_id).delete()
    GroupRecipe.query.filter_by(groupID=group_id).delete()
    db.session.delete(group)
    db.session.commit()
    flash(f'Group "{group.name}" has been deleted.', 'success')
    return redirect(url_for('curator_dashboard'))


@app.route('/curator/recipe/<int:recipe_id>/delete', methods=['POST'])
@login_required
@_curator_required
def curator_delete_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    Rating.query.filter_by(recipeID=recipe_id).delete()
    Comment.query.filter_by(recipeID=recipe_id).delete()
    Notification.query.filter_by(recipeID=recipe_id).delete()
    GroupRecipe.query.filter_by(recipeID=recipe_id).delete()
    SavedRecipe.query.filter_by(recipeID=recipe_id).delete()
    db.session.delete(recipe)
    db.session.commit()
    flash(f'Recipe "{recipe.title}" has been deleted.', 'success')
    return redirect(url_for('curator_dashboard'))


# =============================================================================
# The Pot — Drag-and-Drop Recipe Builder Page
# =============================================================================

@app.route('/pot')
def recipe_pot():
    """Full-page drag-and-drop ingredient picker with a local recipe generation engine."""
    return render_template('recipe_pot.html')


# =============================================================================
# The Pot — AI Recipe Generation (Anthropic API)
# =============================================================================

@app.route('/api/generate-recipe', methods=['POST'])
def generate_recipe_api():
    """
    Generate a recipe from a list of ingredients using the Anthropic API.
    Accepts JSON: { ingredients: ["Chicken", "Garlic", ...] }
    Returns JSON: { recipe: "<markdown string>" }
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key or api_key == 'your-api-key-here':
        return jsonify({'error': 'ANTHROPIC_API_KEY is not configured. Add it to your .flaskenv file.'}), 500

    data = request.get_json(silent=True) or {}
    ingredients = data.get('ingredients', [])

    if not ingredients:
        return jsonify({'error': 'No ingredients provided.'}), 400

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        ingredient_list = '\n'.join(f'- {ing}' for ing in ingredients)

        # The prompt instructs the model to use only the provided ingredients
        # and to follow a strict markdown structure for easy parsing on publish.
        prompt = f"""You are a creative and knowledgeable chef. A user has collected the following ingredients and wants you to create a unique, delicious recipe just for them.

Ingredients available:
{ingredient_list}

Create a complete, creative recipe using ONLY the ingredients listed above. Do not add any other ingredients — not oil, salt, water, or any pantry staples unless they are explicitly in the list. Every ingredient used in the recipe must come from the list provided. Be imaginative with the name and technique. Structure your response exactly like this:

# [Creative Recipe Name]

**Cuisine style:** [e.g. Italian, Asian-fusion, Mediterranean]
**Prep time:** [X min] | **Cook time:** [X min] | **Serves:** [X]

## What You'll Need
[List only the provided ingredients with realistic quantities. Do not add anything else.]

## Instructions
[Clear numbered steps using only the listed ingredients. Be specific about temperatures, times, and techniques. Make it feel like a real chef is guiding them.]

Keep the tone warm and encouraging. Make this recipe feel special."""

        message = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=1500,
            messages=[{'role': 'user', 'content': prompt}]
        )

        return jsonify({'recipe': message.content[0].text})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/publish-recipe', methods=['POST'])
def publish_recipe_api():
    """
    Save an AI-generated recipe to the database.
    The frontend parses the markdown from generate-recipe and sends structured data here.
    Accepts JSON: { title, instructions, description, ingredients, servings, prepTime, cookTime }
    Returns JSON: { recipe_id, url }
    """
    uid = current_user_id()
    if not uid:
        return jsonify({'error': 'You must be logged in to publish a recipe.'}), 401

    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()[:150]
    instructions = (data.get('instructions') or '').strip()
    description = (data.get('description') or '').strip() or None
    ingredients = data.get('ingredients', [])
    servings = data.get('servings', 2)
    prep_time = data.get('prepTime')
    cook_time = data.get('cookTime')

    if not title:
        return jsonify({'error': "Could not determine a recipe title from The Pot's output."}), 400
    if not ingredients:
        return jsonify({'error': 'No ingredients to publish.'}), 400

    # Return a 409 if the user already has a recipe with this title
    duplicate = Recipe.query.filter_by(authorID=uid, title=title).first()
    if duplicate:
        return jsonify({
            'error': f'You already have a recipe called "{title}". '
                     'Try tweaking your ingredients and cooking again.',
            'recipe_id': duplicate.id,
            'url': url_for('view_recipe', recipe_id=duplicate.id)
        }), 409

    try:
        new_recipe = Recipe(
            authorID=uid,
            title=title,
            description=description,
            instructions=instructions,
            baseServings=max(1, int(servings)) if servings else 2,
            prepTime=int(prep_time) if prep_time else None,
            cookTime=int(cook_time) if cook_time else None,
            isAIGenerated=True,
        )
        db.session.add(new_recipe)
        db.session.flush()

        for ing in ingredients:
            name = (ing.get('name') or '').strip()[:32]
            if not name:
                continue
            db.session.add(Ingredient(
                recipeID=new_recipe.id,
                unitID=int(ing.get('unitID') or 1),
                name=name,
                quantity=float(ing.get('quantity') or 1.0),
            ))

        db.session.commit()
        return jsonify({'recipe_id': new_recipe.id, 'url': url_for('view_recipe', recipe_id=new_recipe.id)})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
