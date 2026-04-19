from flask import render_template, request, redirect, url_for, session, flash
from sqlalchemy import or_, func
from app import app, db, mail
from app.forms import CreateRecipeForm, LoginForm, RegisterForm
from app.models import (
    Recipe, Ingredient, RecipeCategory, RecipeDietaryTag, RecipeAllergen,
    Category, DietaryTag, Allergen, MeasurementUnit, Rating, Comment, User,
    Notification, SavedRecipe
)
from flask_mail import Message
from functools import wraps


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

def send_welcome_email(user):
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
        print(f"Failed to send email: {e}")

def _get_avg_rating(recipe_id):
    result = db.session.query(func.avg(Rating.stars), func.count(Rating.id)).filter_by(recipeID=recipe_id).one()
    avg = round(result[0], 1) if result[0] else None
    count = result[1]
    return avg, count


def _recipe_card_data(recipe):
    ingredient_count = Ingredient.query.filter_by(recipeID=recipe.id).count()
    category_links = RecipeCategory.query.filter_by(recipeID=recipe.id).all()
    category_names = [rc.category.name for rc in category_links if rc.category]
    avg_rating, rating_count = _get_avg_rating(recipe.id)
    return {
        'recipe': recipe,
        'ingredient_count': ingredient_count,
        'category_names': category_names,
        'avg_rating': avg_rating,
        'rating_count': rating_count,
    }


def _comment_author(comment):
    user = User.query.get(comment.userID)
    return f"{user.firstName} {user.lastName[0]}." if user else "Anonymous"


def _get_notifications(user_id=None):
    if user_id is None:
        user = get_current_user()
        if not user:
            return []
        user_id = user.id
    return Notification.query.filter_by(userID=user_id).order_by(Notification.dateCreated.desc()).all()


# ==================== AUTH ROUTES ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if get_current_user():
        return redirect(url_for('dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()

        if user and user.check_password(form.password.data):
            session['user_id'] = user.id
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


# ==================== RECIPE ROUTES ====================

@app.route('/')
def dashboard():
    recipes = Recipe.query.order_by(Recipe.dateCreated.desc()).all()
    featured = [_recipe_card_data(r) for r in recipes[:6]]

    rated_subq = (
        db.session.query(Rating.recipeID, func.avg(Rating.stars).label('avg'), func.count(Rating.id).label('cnt'))
        .group_by(Rating.recipeID)
        .subquery()
    )
    popular_recipes = (
        db.session.query(Recipe)
        .join(rated_subq, Recipe.id == rated_subq.c.recipeID)
        .order_by(rated_subq.c.avg.desc(), rated_subq.c.cnt.desc())
        .limit(3)
        .all()
    )
    popular = [_recipe_card_data(r) for r in popular_recipes]

    stats = {
        'recipes': Recipe.query.count(),
        'categories': Category.query.count(),
        'tags': DietaryTag.query.count(),
        'allergens': Allergen.query.count(),
    }

    current_user = get_current_user()
    notifications = _get_notifications(current_user.id) if current_user else []
    has_unread = any(not n.isRead for n in notifications)

    return render_template('dashboard.html', featured=featured, stats=stats, popular=popular,
                           notifications=notifications, has_unread=has_unread, current_user=current_user)


@app.route('/recipe/<int:recipe_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_recipe(recipe_id):
    current_user = get_current_user()
    recipe = Recipe.query.get_or_404(recipe_id)

    # Only allow the author to edit
    if recipe.authorID != current_user.id:
        flash('You do not have permission to edit this recipe.', 'error')
        return redirect(url_for('view_recipe', recipe_id=recipe_id))

    form = CreateRecipeForm()
    form.category_id.choices = [(0, '-- Select Category --')] + [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]
    form.dietary_tags.choices = [(t.id, t.name) for t in DietaryTag.query.order_by(DietaryTag.name).all()]
    form.allergens.choices = [(a.id, a.name) for a in Allergen.query.order_by(Allergen.name).all()]
    units = MeasurementUnit.query.filter_by(isActive=True).order_by(MeasurementUnit.name).all()

    errors = []

    if form.validate_on_submit():
        ing_names = request.form.getlist('ing_name')
        ing_qtys = request.form.getlist('ing_quantity')
        ing_units = request.form.getlist('ing_unit')

        has_ingredient = any((n or '').strip() for n in ing_names)

        if not has_ingredient:
            errors.append('At least one ingredient is required.')

        parsed_ingredients = []
        for idx, (name, qty, unit_id) in enumerate(zip(ing_names, ing_qtys, ing_units), start=1):
            name = (name or '').strip()
            qty = (qty or '').strip()
            unit_id = (unit_id or '').strip()
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
            parsed_ingredients.append((name, quantity, parsed_unit_id))

        if not errors:
            # Update recipe
            recipe.title = form.title.data.strip()
            recipe.description = (form.description.data or '').strip() or None
            recipe.instructions = form.instructions.data.strip()
            recipe.baseServings = form.baseServings.data
            recipe.prepTime = form.prepTime.data or None
            recipe.cookTime = form.cookTime.data or None

            # Delete and recreate ingredients
            Ingredient.query.filter_by(recipeID=recipe_id).delete()
            for name, quantity, unit_id in parsed_ingredients:
                db.session.add(Ingredient(recipeID=recipe_id, unitID=unit_id, name=name, quantity=quantity))

            # Update categories
            RecipeCategory.query.filter_by(recipeID=recipe_id).delete()
            if form.category_id.data and form.category_id.data != 0:
                db.session.add(RecipeCategory(recipeID=recipe_id, categoryID=form.category_id.data))

            # Update dietary tags
            RecipeDietaryTag.query.filter_by(recipeID=recipe_id).delete()
            for tag_id in form.dietary_tags.data:
                db.session.add(RecipeDietaryTag(recipeID=recipe_id, dietaryTagID=tag_id))

            # Update allergens
            RecipeAllergen.query.filter_by(recipeID=recipe_id).delete()
            for allergen_id in form.allergens.data:
                db.session.add(RecipeAllergen(recipeID=recipe_id, allergenID=allergen_id))

            db.session.commit()
            flash('Recipe updated successfully!', 'success')
            return redirect(url_for('view_recipe', recipe_id=recipe_id))

    elif request.method == 'GET':
        # Populate form with existing data
        form.title.data = recipe.title
        form.description.data = recipe.description
        form.instructions.data = recipe.instructions
        form.baseServings.data = recipe.baseServings
        form.prepTime.data = recipe.prepTime
        form.cookTime.data = recipe.cookTime

        # Set category
        category_link = RecipeCategory.query.filter_by(recipeID=recipe_id).first()
        form.category_id.data = category_link.categoryID if category_link else 0

        # Set dietary tags
        diet_tags = RecipeDietaryTag.query.filter_by(recipeID=recipe_id).all()
        form.dietary_tags.data = [dt.dietaryTagID for dt in diet_tags]

        # Set allergens
        allergen_links = RecipeAllergen.query.filter_by(recipeID=recipe_id).all()
        form.allergens.data = [a.allergenID for a in allergen_links]

    if form.errors:
        for _, messages in form.errors.items():
            errors.extend(messages)

    notifications = _get_notifications(current_user.id)
    has_unread = any(not n.isRead for n in notifications)
    return render_template('recipe_form.html', form=form, units=units, errors=errors, recipe=recipe,
                           notifications=notifications, has_unread=has_unread, current_user=current_user, is_edit=True)


@app.route('/recipe/create', methods=['GET', 'POST'])
@login_required
def create_recipe():
    current_user = get_current_user()
    form = CreateRecipeForm()
    form.category_id.choices = [(0, '-- Select Category --')] + [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]
    form.dietary_tags.choices = [(t.id, t.name) for t in DietaryTag.query.order_by(DietaryTag.name).all()]
    form.allergens.choices = [(a.id, a.name) for a in Allergen.query.order_by(Allergen.name).all()]
    units = MeasurementUnit.query.filter_by(isActive=True).order_by(MeasurementUnit.name).all()

    errors = []

    if form.validate_on_submit():
        ing_names = request.form.getlist('ing_name')
        ing_qtys = request.form.getlist('ing_quantity')
        ing_units = request.form.getlist('ing_unit')

        has_ingredient = any((n or '').strip() for n in ing_names)
        duplicate = Recipe.query.filter_by(authorID=current_user.id, title=form.title.data.strip()).first()

        if not has_ingredient:
            errors.append('At least one ingredient is required.')
        if duplicate:
            errors.append('You already have a recipe with this name.')

        parsed_ingredients = []
        for idx, (name, qty, unit_id) in enumerate(zip(ing_names, ing_qtys, ing_units), start=1):
            name = (name or '').strip()
            qty = (qty or '').strip()
            unit_id = (unit_id or '').strip()
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
            parsed_ingredients.append((name, quantity, parsed_unit_id))

        if not errors:
            new_recipe = Recipe(
                authorID=current_user.id,
                title=form.title.data.strip(),
                description=(form.description.data or '').strip() or None,
                instructions=form.instructions.data.strip(),
                forkedFrom=None,
                baseServings=form.baseServings.data,
                prepTime=form.prepTime.data or None,
                cookTime=form.cookTime.data or None,
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
            flash('Recipe created successfully!', 'success')
            return redirect(url_for('view_recipe', recipe_id=new_recipe.id))

    if form.errors:
        for _, messages in form.errors.items():
            errors.extend(messages)

    notifications = _get_notifications(current_user.id)
    has_unread = any(not n.isRead for n in notifications)
    return render_template('recipe_form.html', form=form, units=units, errors=errors,
                           notifications=notifications, has_unread=has_unread, current_user=current_user, is_edit=False)


@app.route('/recipe/<int:recipe_id>')
def view_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    ingredients = Ingredient.query.filter_by(recipeID=recipe_id).all()
    categories = RecipeCategory.query.filter_by(recipeID=recipe_id).all()
    dietary_tags = RecipeDietaryTag.query.filter_by(recipeID=recipe_id).all()
    allergens = RecipeAllergen.query.filter_by(recipeID=recipe_id).all()
    avg_rating, rating_count = _get_avg_rating(recipe_id)

    current_user = get_current_user()
    user_rating = None
    is_saved = False
    if current_user:
        user_rating = Rating.query.filter_by(recipeID=recipe_id, userID=current_user.id).first()
        is_saved = SavedRecipe.query.filter_by(userID=current_user.id, recipeID=recipe_id).first() is not None

    sort = request.args.get('sort', 'newest')
    order = Comment.dateCreated.asc() if sort == 'oldest' else Comment.dateCreated.desc()
    comments = Comment.query.filter_by(recipeID=recipe_id).order_by(order).all()
    for c in comments:
        c.author_name = _comment_author(c)

    notifications = _get_notifications(current_user.id) if current_user else []
    has_unread = any(not n.isRead for n in notifications)

    # Pick up any notification that should trigger a toast (set by post_comment)
    toast_notif = None
    toast_id = session.pop('toast_notification_id', None)
    if toast_id:
        toast_notif = Notification.query.get(toast_id)

    return render_template(
        'view_recipe.html',
        recipe=recipe,
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
        notifications=notifications,
        has_unread=has_unread,
        toast_notif=toast_notif,
        current_user=current_user,
    )


@app.route('/recipe/<int:recipe_id>/fork', methods=['POST'])
@login_required
def fork_recipe(recipe_id):
    original_recipe = Recipe.query.get_or_404(recipe_id)
    current_user = get_current_user()

    forked_recipe = original_recipe.fork(current_user.id)
    db.session.add(forked_recipe)
    db.session.flush()

    # Copy ingredients
    ingredients = Ingredient.query.filter_by(recipeID=recipe_id).all()
    for ing in ingredients:
        new_ing = Ingredient(
            recipeID=forked_recipe.id,
            unitID=ing.unitID,
            name=ing.name,
            quantity=ing.quantity
        )
        db.session.add(new_ing)

    # Copy categories
    categories = RecipeCategory.query.filter_by(recipeID=recipe_id).all()
    for cat in categories:
        new_cat = RecipeCategory(recipeID=forked_recipe.id, categoryID=cat.categoryID)
        db.session.add(new_cat)

    # Copy dietary tags
    dietary_tags = RecipeDietaryTag.query.filter_by(recipeID=recipe_id).all()
    for tag in dietary_tags:
        new_tag = RecipeDietaryTag(recipeID=forked_recipe.id, dietaryTagID=tag.dietaryTagID)
        db.session.add(new_tag)

    # Copy allergens
    allergens = RecipeAllergen.query.filter_by(recipeID=recipe_id).all()
    for allergen in allergens:
        new_allergen = RecipeAllergen(recipeID=forked_recipe.id, allergenID=allergen.allergenID)
        db.session.add(new_allergen)

    db.session.commit()
    flash(f'Recipe "{original_recipe.title}" forked to your account!', 'success')
    return redirect(url_for('view_recipe', recipe_id=forked_recipe.id))


@app.route('/recipe/<int:recipe_id>/comments', methods=['POST'])
def post_comment(recipe_id):
    if not get_current_user():
        flash('Please log in to comment.', 'warning')
        return redirect(url_for('login'))

    current_user = get_current_user()
    recipe = Recipe.query.get_or_404(recipe_id)

    # Save star rating if provided
    try:
        stars = int(request.form.get('stars', 0))
    except (ValueError, TypeError):
        stars = 0
    if 1 <= stars <= 5:
        existing = Rating.query.filter_by(recipeID=recipe_id, userID=current_user.id).first()
        if existing:
            existing.stars = stars
        else:
            db.session.add(Rating(recipeID=recipe_id, userID=current_user.id, stars=stars))

    # Save comment and create notification
    content = request.form.get('content', '').strip()
    if content:
        new_comment = Comment(recipeID=recipe_id, userID=current_user.id, content=content)
        db.session.add(new_comment)
        db.session.flush()

        author = _comment_author(new_comment)
        new_notif = Notification(
            userID=current_user.id,
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


@app.route('/recipe/<int:recipe_id>/rate', methods=['POST'])
def rate_recipe(recipe_id):
    if not get_current_user():
        flash('Please log in to rate.', 'warning')
        return redirect(url_for('login'))

    current_user = get_current_user()
    Recipe.query.get_or_404(recipe_id)
    try:
        stars = int(request.form.get('stars', 0))
    except (ValueError, TypeError):
        stars = 0

    if stars < 1 or stars > 5:
        return redirect(url_for('view_recipe', recipe_id=recipe_id))

    existing = Rating.query.filter_by(recipeID=recipe_id, userID=current_user.id).first()
    if existing:
        existing.stars = stars
    else:
        db.session.add(Rating(recipeID=recipe_id, userID=current_user.id, stars=stars))
    db.session.commit()
    return redirect(url_for('view_recipe', recipe_id=recipe_id))


@app.route('/recipe/<int:recipe_id>/delete', methods=['POST'])
@login_required
def delete_recipe(recipe_id):
    current_user = get_current_user()
    recipe = Recipe.query.get_or_404(recipe_id)

    # Only allow user to delete their own recipes
    if recipe.authorID != current_user.id:
        flash('You do not have permission to delete this recipe.', 'error')
        return redirect(url_for('view_recipe', recipe_id=recipe_id))

    Rating.query.filter_by(recipeID=recipe_id).delete()
    Comment.query.filter_by(recipeID=recipe_id).delete()
    Notification.query.filter_by(recipeID=recipe_id).delete()
    db.session.delete(recipe)
    db.session.commit()
    flash('Recipe deleted successfully.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/notifications/<int:notification_id>/delete', methods=['POST'])
def delete_notification(notification_id):
    current_user = get_current_user()
    if not current_user:
        return redirect(url_for('login'))

    notif = Notification.query.get_or_404(notification_id)

    # Only allow user to delete their own notifications
    if notif.userID != current_user.id:
        flash('You do not have permission to delete this notification.', 'error')
        return redirect(request.referrer or url_for('dashboard'))

    db.session.delete(notif)
    db.session.commit()
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/notifications/mark-read', methods=['POST'])
def mark_notifications_read():
    current_user = get_current_user()
    if not current_user:
        return redirect(url_for('login'))

    Notification.query.filter_by(userID=current_user.id, isRead=False).update({'isRead': True})
    db.session.commit()
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/search')
def search():
    current_user = get_current_user()
    query = request.args.get('q', '').strip()
    results = []

    if query:
        title_matches = Recipe.query.filter(Recipe.title.ilike(f'%{query}%')).all()
        desc_matches = Recipe.query.filter(Recipe.description.ilike(f'%{query}%')).all()
        ingredient_matches = db.session.query(Recipe).join(Ingredient).filter(Ingredient.name.ilike(f'%{query}%')).all()
        tag_matches = db.session.query(Recipe).join(RecipeDietaryTag).join(DietaryTag).filter(DietaryTag.name.ilike(f'%{query}%')).all()
        allergen_matches = db.session.query(Recipe).join(RecipeAllergen).join(Allergen).filter(Allergen.name.ilike(f'%{query}%')).all()

        seen = set()
        combined = title_matches + desc_matches + ingredient_matches + tag_matches + allergen_matches
        for recipe in combined:
            if recipe.id not in seen:
                seen.add(recipe.id)
                results.append(_recipe_card_data(recipe))

    notifications = _get_notifications(current_user.id) if current_user else []
    has_unread = any(not n.isRead for n in notifications)
    return render_template('search.html', query=query, results=results,
                           notifications=notifications, has_unread=has_unread, current_user=current_user)


@app.route('/profile')
@login_required
def profile():
    current_user = get_current_user()

    # Fetch created recipes (original recipes, not forked)
    created_recipes_data = Recipe.query.filter_by(authorID=current_user.id).filter(Recipe.forkedFrom.is_(None)).order_by(Recipe.dateCreated.desc()).all()
    created_recipes = [_recipe_card_data(r) for r in created_recipes_data]

    # Fetch saved recipes
    saved_recipes_data = db.session.query(SavedRecipe).filter_by(userID=current_user.id).order_by(SavedRecipe.dateCreated.desc()).all()
    saved_recipes = [_recipe_card_data(sr.recipe) for sr in saved_recipes_data]

    # Fetch forked recipes
    forked_recipes_data = Recipe.query.filter_by(authorID=current_user.id).filter(Recipe.forkedFrom.isnot(None)).order_by(Recipe.dateCreated.desc()).all()
    forked_recipes = [_recipe_card_data(r) for r in forked_recipes_data]

    notifications = _get_notifications(current_user.id)
    has_unread = any(not n.isRead for n in notifications)

    return render_template('profile.html', created_recipes=created_recipes, saved_recipes=saved_recipes, forked_recipes=forked_recipes,
                           notifications=notifications, has_unread=has_unread, current_user=current_user)


@app.route('/recipe/<int:recipe_id>/save', methods=['POST'])
@login_required
def save_recipe(recipe_id):
    current_user = get_current_user()
    recipe = Recipe.query.get_or_404(recipe_id)

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

