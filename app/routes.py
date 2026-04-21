from flask import render_template, request, redirect, url_for, session, flash
from sqlalchemy import or_, func
from app import app, db, mail
from datetime import datetime
from app.forms import CreateRecipeForm, LoginForm, RegisterForm
from app.models import (
    Recipe, Ingredient, RecipeCategory, RecipeDietaryTag, RecipeAllergen,
    Category, DietaryTag, Allergen, MeasurementUnit, Rating, Comment, User,
    Notification, Group, GroupMember, GroupMessage, GroupRecipe, SavedRecipe
)
import csv
from io import StringIO
from flask import Response
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

def current_user_id():
    return session.get('user_id')

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


def _get_notifications():
    uid = current_user_id()
    if uid is None:
        return []
    return Notification.query.filter_by(userID=uid).order_by(Notification.dateCreated.desc()).all()


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
    user = get_current_user()

    if user and user.role == 'curator':
        return redirect(url_for('curator_dashboard'))

    rated_subq = (
        db.session.query(Rating.recipeID, func.avg(Rating.stars).label('avg'), func.count(Rating.id).label('cnt'))
        .group_by(Rating.recipeID)
        .subquery()
    )

    top_recipe_obj = (
        db.session.query(Recipe)
        .join(rated_subq, Recipe.id == rated_subq.c.recipeID)
        .order_by(rated_subq.c.avg.desc(), rated_subq.c.cnt.desc())
        .first()
    )
    top_recipe = _recipe_card_data(top_recipe_obj) if top_recipe_obj else None

    popular_recipes = (
        db.session.query(Recipe)
        .join(rated_subq, Recipe.id == rated_subq.c.recipeID)
        .order_by(rated_subq.c.avg.desc(), rated_subq.c.cnt.desc())
        .limit(3)
        .all()
    )
    popular = [_recipe_card_data(r) for r in popular_recipes]

    all_recipes = Recipe.query.all()
    import random
    random_sample = random.sample(all_recipes, min(6, len(all_recipes)))
    random_recipes = [_recipe_card_data(r) for r in random_sample]

    newest_recipes = Recipe.query.order_by(Recipe.dateCreated.desc()).limit(6).all()
    newest = [_recipe_card_data(r) for r in newest_recipes]

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

    notifications = _get_notifications()
    has_unread = any(not n.isRead for n in notifications)

    return render_template('dashboard.html',
                           user=user,
                           top_recipe=top_recipe,
                           popular=popular,
                           random_recipes=random_recipes,
                           newest=newest,
                           saved_recipes=saved_recipes,
                           stats=stats,
                           notifications=notifications,
                           has_unread=has_unread)


@app.route('/recipe/create', methods=['GET', 'POST'])
@login_required
def create_recipe():
    uid = current_user_id()
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
        duplicate = Recipe.query.filter_by(authorID=uid, title=form.title.data.strip()).first()

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
                authorID=uid,
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
            return redirect(url_for('view_recipe', recipe_id=new_recipe.id))

    if form.errors:
        for _, messages in form.errors.items():
            errors.extend(messages)

    notifications = _get_notifications()
    has_unread = any(not n.isRead for n in notifications)
    return render_template('recipe_form.html', form=form, units=units, errors=errors,
                           notifications=notifications, has_unread=has_unread,
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
 
    is_saved = False
    if uid:
        is_saved = SavedRecipe.query.filter_by(userID=uid, recipeID=recipe_id).first() is not None
 
    sort = request.args.get('sort', 'newest')
    order = Comment.dateCreated.asc() if sort == 'oldest' else Comment.dateCreated.desc()
    comments = Comment.query.filter_by(recipeID=recipe_id).order_by(order).all()
    for c in comments:
        c.author_name = _comment_author(c)
 
    notifications = _get_notifications()
    has_unread = any(not n.isRead for n in notifications)
 
    toast_notif = None
    toast_id = session.pop('toast_notification_id', None)
    if toast_id:
        toast_notif = Notification.query.get(toast_id)
 
    memberships = GroupMember.query.filter_by(userID=uid).all() if uid else []
 
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
        notifications=notifications,
        has_unread=has_unread,
        toast_notif=toast_notif,
        memberships=memberships,
    )

@app.route('/recipe/<int:recipe_id>/comments', methods=['POST'])
@login_required
def post_comment(recipe_id):
    uid = current_user_id()
    recipe = Recipe.query.get_or_404(recipe_id)

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


@app.route('/recipe/<int:recipe_id>/rate', methods=['POST'])
@login_required
def rate_recipe(recipe_id):
    uid = current_user_id()
    Recipe.query.get_or_404(recipe_id)
    try:
        stars = int(request.form.get('stars', 0))
    except (ValueError, TypeError):
        stars = 0

    if stars < 1 or stars > 5:
        return redirect(url_for('view_recipe', recipe_id=recipe_id))

    existing = Rating.query.filter_by(recipeID=recipe_id, userID=uid).first()
    if existing:
        existing.stars = stars
    else:
        db.session.add(Rating(recipeID=recipe_id, userID=uid, stars=stars))
    db.session.commit()
    return redirect(url_for('view_recipe', recipe_id=recipe_id))


@app.route('/recipe/<int:recipe_id>/delete', methods=['POST'])
@login_required
def delete_recipe(recipe_id):
    Recipe.query.get_or_404(recipe_id)
    Rating.query.filter_by(recipeID=recipe_id).delete()
    Comment.query.filter_by(recipeID=recipe_id).delete()
    Notification.query.filter_by(recipeID=recipe_id).delete()
    recipe = Recipe.query.get(recipe_id)
    db.session.delete(recipe)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/recipe/<int:recipe_id>/fork', methods=['POST'])
@login_required
def fork_recipe(recipe_id):
    original_recipe = Recipe.query.get_or_404(recipe_id)
    current_user = get_current_user()

    forked_recipe = original_recipe.fork(current_user.id)
    db.session.add(forked_recipe)
    db.session.flush()

    ingredients = Ingredient.query.filter_by(recipeID=recipe_id).all()
    for ing in ingredients:
        new_ing = Ingredient(
            recipeID=forked_recipe.id,
            unitID=ing.unitID,
            name=ing.name,
            quantity=ing.quantity
        )
        db.session.add(new_ing)

    categories = RecipeCategory.query.filter_by(recipeID=recipe_id).all()
    for cat in categories:
        new_cat = RecipeCategory(recipeID=forked_recipe.id, categoryID=cat.categoryID)
        db.session.add(new_cat)

    dietary_tags = RecipeDietaryTag.query.filter_by(recipeID=recipe_id).all()
    for tag in dietary_tags:
        new_tag = RecipeDietaryTag(recipeID=forked_recipe.id, dietaryTagID=tag.dietaryTagID)
        db.session.add(new_tag)

    allergens = RecipeAllergen.query.filter_by(recipeID=recipe_id).all()
    for allergen in allergens:
        new_allergen = RecipeAllergen(recipeID=forked_recipe.id, allergenID=allergen.allergenID)
        db.session.add(new_allergen)

    db.session.commit()
    flash(f'Recipe "{original_recipe.title}" forked to your account!', 'success')
    return redirect(url_for('view_recipe', recipe_id=forked_recipe.id))

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

@app.route('/recipe/<int:recipe_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_recipe(recipe_id):
    current_user = get_current_user()
    recipe = Recipe.query.get_or_404(recipe_id)

    if recipe.authorID != current_user.id:
        flash('You do not have permission to edit this recipe.', 'error')
        return redirect(url_for('view_recipe', recipe_id=recipe_id))

    form = CreateRecipeForm()
    form.category_id.choices = [(0, '-- Select Category --')] + [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]
    form.dietary_tags.choices = [(t.id, t.name) for t in DietaryTag.query.order_by(DietaryTag.name).all()]
    form.allergens.choices = [(a.id, a.name) for a in Allergen.query.order_by(Allergen.name).all()]
    units = MeasurementUnit.query.filter_by(isActive=True).order_by(MeasurementUnit.name).all()

    errors = []
    # Always pre-load from DB; the GET branch uses this directly, POST failure overwrites it
    existing_ingredients = Ingredient.query.filter_by(recipeID=recipe_id).all()

    if form.validate_on_submit():
        ing_names = request.form.getlist('ing_name')
        ing_qtys = request.form.getlist('ing_quantity')
        ing_units = request.form.getlist('ing_unit')

        has_ingredient = any((n or '').strip() for n in ing_names)

        if not has_ingredient:
            errors.append('At least one ingredient is required.')

        # Only flag duplicate if the title changed AND another recipe already uses it
        new_title = form.title.data.strip()
        if new_title != recipe.title:
            duplicate = Recipe.query.filter_by(authorID=current_user.id, title=new_title).first()
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
            recipe.title = new_title
            recipe.description = (form.description.data or '').strip() or None
            recipe.instructions = form.instructions.data.strip()
            recipe.baseServings = form.baseServings.data
            recipe.prepTime = form.prepTime.data or None
            recipe.cookTime = form.cookTime.data or None

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

        # Validation failed — re-render with the ingredients the user just submitted
        # so they don't lose their edits
        existing_ingredients = []
        for name, qty, unit_id in zip(ing_names, ing_qtys, ing_units):
            name = (name or '').strip()
            if not name:
                continue
            try:
                quantity = float(qty) if qty else 0.0
            except ValueError:
                quantity = 0.0
            try:
                uid_int = int(unit_id) if unit_id else 1
            except ValueError:
                uid_int = 1

            class _FakeIng:
                pass
            fi = _FakeIng()
            fi.name = name
            fi.quantity = quantity
            fi.unitID = uid_int
            existing_ingredients.append(fi)

    elif request.method == 'GET':
        form.title.data = recipe.title
        form.description.data = recipe.description
        form.instructions.data = recipe.instructions
        form.baseServings.data = recipe.baseServings
        form.prepTime.data = recipe.prepTime
        form.cookTime.data = recipe.cookTime

        category_link = RecipeCategory.query.filter_by(recipeID=recipe_id).first()
        form.category_id.data = category_link.categoryID if category_link else 0

        diet_tags = RecipeDietaryTag.query.filter_by(recipeID=recipe_id).all()
        form.dietary_tags.data = [dt.dietaryTagID for dt in diet_tags]

        allergen_links = RecipeAllergen.query.filter_by(recipeID=recipe_id).all()
        form.allergens.data = [a.allergenID for a in allergen_links]

    if form.errors:
        for _, messages in form.errors.items():
            errors.extend(messages)

    notifications = _get_notifications()
    has_unread = any(not n.isRead for n in notifications)
    return render_template('recipe_form.html', form=form, units=units, errors=errors, recipe=recipe,
                           notifications=notifications, has_unread=has_unread,
                           current_user=current_user, is_edit=True,
                           existing_ingredients=existing_ingredients)


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
    uid = current_user_id()
    Notification.query.filter_by(userID=uid, isRead=False).update({'isRead': True})
    db.session.commit()
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/search')
def search():
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

    notifications = _get_notifications()
    has_unread = any(not n.isRead for n in notifications)
    return render_template('search.html', query=query, results=results,
                           notifications=notifications, has_unread=has_unread)


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
    recipe_data = [_recipe_card_data(r) for r in user_recipes]

    saved_query = (
        db.session.query(Recipe)
        .join(SavedRecipe, Recipe.id == SavedRecipe.recipeID)
        .filter(SavedRecipe.userID == user.id)
        .all()
    )
    saved_recipes = [_recipe_card_data(r) for r in saved_query]

    message_count = GroupMessage.query.filter_by(senderID=user.id).count()

    ratings = (
        db.session.query(func.avg(Rating.stars))
        .join(Recipe, Rating.recipeID == Recipe.id)
        .filter(Recipe.authorID == user.id)
        .scalar()
    )
    avg_rating = round(ratings, 1) if ratings else None

    return render_template('groups/index.html',
                           user=user,
                           groups=user_groups,
                           recipe_data=recipe_data,
                           saved_recipes=saved_recipes,
                           message_count=message_count,
                           avg_rating=avg_rating)


@app.route('/groups/create', methods=['GET', 'POST'])
@login_required
def create_group():
    uid = current_user_id()
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')

        new_group = Group(
            leaderID=uid,
            name=name,
            description=description,
            dateCreated=datetime.utcnow()
        )
        db.session.add(new_group)
        db.session.flush()

        membership = GroupMember(
            groupID=new_group.id,
            userID=uid,
            dateJoined=datetime.utcnow()
        )
        db.session.add(membership)
        db.session.commit()
        return redirect(url_for('view_group', group_id=new_group.id))

    notifications = _get_notifications()
    has_unread = any(not n.isRead for n in notifications)
    return render_template('groups/create.html',
                           notifications=notifications, has_unread=has_unread)


@app.route('/groups/<int:group_id>')
def view_group(group_id):
    group = Group.query.get_or_404(group_id)
    messages = GroupMessage.query.filter_by(groupID=group_id).order_by(GroupMessage.dateSent).all()
    shared_recipes = GroupRecipe.query.filter_by(groupID=group_id).all()
    members = GroupMember.query.filter_by(groupID=group_id).all()
    notifications = _get_notifications()
    has_unread = any(not n.isRead for n in notifications)
    return render_template('groups/view.html', group=group, messages=messages,
                           shared_recipes=shared_recipes, members=members,
                           notifications=notifications, has_unread=has_unread)


@app.route('/groups/<int:group_id>/message', methods=['POST'])
@login_required
def send_message(group_id):
    uid = current_user_id()
    content = request.form.get('content')
    msg = GroupMessage(
        groupID=group_id,
        senderID=uid,
        content=content,
        dateSent=datetime.utcnow()
    )
    db.session.add(msg)
    db.session.commit()
    return redirect(url_for('view_group', group_id=group_id))


@app.route('/groups/<int:group_id>/share/<int:recipe_id>', methods=['POST'])
@login_required
def share_recipe(group_id, recipe_id):
    uid = current_user_id()
    shared = GroupRecipe(
        groupID=group_id,
        recipeID=recipe_id,
        sharedByID=uid,
        dateSaved=datetime.utcnow()
    )
    db.session.add(shared)
    db.session.commit()
    return redirect(url_for('view_group', group_id=group_id))


@app.route('/groups/<int:group_id>/add_member', methods=['POST'])
@login_required
def add_member(group_id):
    Group.query.get_or_404(group_id)
    email = request.form.get('email')
    user = User.query.filter_by(email=email).first()
    if user:
        already_member = GroupMember.query.filter_by(groupID=group_id, userID=user.id).first()
        if not already_member:
            member = GroupMember(groupID=group_id, userID=user.id, dateJoined=datetime.utcnow())
            db.session.add(member)
            db.session.commit()
    return redirect(url_for('view_group', group_id=group_id))


@app.route('/curator')
@login_required
def curator_dashboard():
    user = get_current_user()
    if not user or user.role != 'curator':
        return redirect(url_for('dashboard'))

    newest = Recipe.query.order_by(Recipe.dateCreated.desc()).limit(6).all()

    rated_subq = (
        db.session.query(Rating.recipeID, func.avg(Rating.stars).label('avg'), func.count(Rating.id).label('cnt'))
        .group_by(Rating.recipeID)
        .subquery()
    )
    popular_recipes = (
        db.session.query(Recipe)
        .join(rated_subq, Recipe.id == rated_subq.c.recipeID)
        .order_by(rated_subq.c.avg.desc(), rated_subq.c.cnt.desc())
        .limit(6)
        .all()
    )

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

    stats = {
        'recipes': Recipe.query.count(),
        'users': User.query.count(),
        'groups': Group.query.count(),
        'messages': GroupMessage.query.count(),
    }

    notifications = _get_notifications()
    has_unread = any(not n.isRead for n in notifications)

    return render_template('curator/dashboard.html',
                           newest=[_recipe_card_data(r) for r in newest],
                           popular=[_recipe_card_data(r) for r in popular_recipes],
                           users=users,
                           search_query=search_query,
                           stats=stats,
                           notifications=notifications,
                           has_unread=has_unread)


@app.route('/curator/user/<int:user_id>')
@login_required
def curator_user_profile(user_id):
    user = get_current_user()
    if not user or user.role != 'curator':
        return redirect(url_for('dashboard'))

    profile = User.query.get_or_404(user_id)
    recipes = Recipe.query.filter_by(authorID=user_id).order_by(Recipe.dateCreated.desc()).all()
    memberships = GroupMember.query.filter_by(userID=user_id).all()
    messages = GroupMessage.query.filter_by(senderID=user_id).order_by(GroupMessage.dateSent.desc()).all()

    notifications = _get_notifications()
    has_unread = any(not n.isRead for n in notifications)

    return render_template('curator/user_profile.html',
                           profile=profile,
                           recipes=[_recipe_card_data(r) for r in recipes],
                           memberships=memberships,
                           messages=messages,
                           notifications=notifications,
                           has_unread=has_unread)


@app.route('/curator/export/recipes')
@login_required
def export_recipes():
    user = get_current_user()
    if not user or user.role != 'curator':
        return redirect(url_for('dashboard'))

    recipes = Recipe.query.all()
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['ID', 'Title', 'Author', 'Description', 'Base Servings', 'Prep Time', 'Cook Time', 'Date Created'])
    for r in recipes:
        writer.writerow([r.id, r.title, f"{r.author.firstName} {r.author.lastName}", r.description, r.baseServings, r.prepTime, r.cookTime, r.dateCreated])
    return Response(si.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=recipes.csv'})


@app.route('/curator/export/users')
@login_required
def export_users():
    user = get_current_user()
    if not user or user.role != 'curator':
        return redirect(url_for('dashboard'))

    users = User.query.all()
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['ID', 'First Name', 'Last Name', 'Email', 'Role', 'Active', 'Date Created'])
    for u in users:
        writer.writerow([u.id, u.firstName, u.lastName, u.email, u.role, u.isActive, u.dateCreated])
    return Response(si.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=users.csv'})


@app.route('/curator/export/groups')
@login_required
def export_groups():
    user = get_current_user()
    if not user or user.role != 'curator':
        return redirect(url_for('dashboard'))

    groups = Group.query.all()
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['ID', 'Name', 'Description', 'Leader', 'Member Count', 'Date Created'])
    for g in groups:
        leader = User.query.get(g.leaderID)
        writer.writerow([g.id, g.name, g.description, f"{leader.firstName} {leader.lastName}" if leader else 'N/A', len(g.members), g.dateCreated])
    return Response(si.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=groups.csv'})


@app.route('/curator/export/messages')
@login_required
def export_messages():
    user = get_current_user()
    if not user or user.role != 'curator':
        return redirect(url_for('dashboard'))

    messages = GroupMessage.query.all()
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['ID', 'Sender', 'Group', 'Content', 'Date Sent'])
    for m in messages:
        writer.writerow([m.id, f"{m.sender.firstName} {m.sender.lastName}", m.group.name, m.content, m.dateSent])
    return Response(si.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=messages.csv'})

@app.route('/curator/user/<int:user_id>/delete', methods=['POST'])
@login_required
def curator_delete_user(user_id):
    user = get_current_user()
    if not user or user.role != 'curator':
        return redirect(url_for('dashboard'))

    target = User.query.get_or_404(user_id)

    # Delete all user-related data
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
def curator_delete_group(group_id):
    user = get_current_user()
    if not user or user.role != 'curator':
        return redirect(url_for('dashboard'))

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
def curator_delete_recipe(recipe_id):
    user = get_current_user()
    if not user or user.role != 'curator':
        return redirect(url_for('dashboard'))

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