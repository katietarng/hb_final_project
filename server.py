import os
import json

from jinja2 import StrictUndefined
from flask import Flask, render_template, request, flash, redirect, session, jsonify
from flask_debugtoolbar import DebugToolbarExtension
from datetime import datetime
from generate_recipes import recipe_request, return_stored_recipes, recipe_info
from process_data import return_db_ingredients, add_bookmark, update_cooked_recipe
from flask.ext.bcrypt import Bcrypt
from model import *


app = Flask(__name__)
bcrypt = Bcrypt(app)

app.secret_key = os.environ['APP_KEY']

# Raises an error if there is an undefined variable
app.jinja_env.undefined = StrictUndefined


@app.route('/')
def index():
    """Homepage with login and sign-up functionality."""

    user_id = session.get('user_id', None)

    if user_id:
        user = User.query.get(user_id)
        avail_ingredients = Ingredient.query.filter_by(user_id=user.user_id).all()
        avail_ing = Ingredient.query.filter(Ingredient.user_id == user.user_id, Ingredient.amount > 0).all()
        avail_ing = return_db_ingredients(avail_ing)
        depleted_ing = db.session.query(Ingredient.name).filter_by(user_id=user.user_id, amount=0).all()
        name = user.fname
        date = datetime.now()
        date = date.strftime("%B %d, %Y")
        return render_template("profile.html",
                               name=name,
                               date=date,
                               avail_ing=avail_ing,
                               depleted_ing=depleted_ing
                               )

    return render_template("homepage.html")


@app.route('/register')
def register_form():
    """Show registration form for new user."""

    return render_template("registration.html")


@app.route('/register', methods=['POST'])
def process_new_user():
    """Process new user from registration form."""

    username = request.form.get("username")
    email = request.form.get("email")
    password = request.form.get("password")
    first_name = request.form.get("fname")
    last_name = request.form.get("lname")
    phone = request.form.get("phone")

    user = db.session.query(User).filter_by(username=username).first()
    password = bcrypt.generate_password_hash(password)

    if user:
        flash("This username is taken.")
        return render_template("registration.html")
    else:
        new_user = User(username=username,
                        email=email,
                        password=password,
                        fname=first_name,
                        lname=last_name,
                        phone=phone)

        db.session.add(new_user)
        db.session.commit()

        session["user_id"] = new_user.user_id

        flash("You have successfully signed up for an account!")
        return redirect('/profile/{}'.format(new_user.username))


@app.route('/login', methods=['POST'])
def process_login():
    """Process login form."""

    email = request.form.get("email")
    password = request.form.get("password")

    #Want to use .first() so that it can return None type object
    user = User.query.filter_by(email=email).first()

    if not user:
        flash("This email does not exist. Please sign up or try again.")
        return redirect("/")

    if not bcrypt.check_password_hash(user.password, password):
        flash("Your password is incorrect.")
        return redirect("/")

    session["user_id"] = user.user_id

    flash("You are now logged in.")
    return redirect("/profile/{}".format(user.username))


@app.route('/logout')
def logout():
    """Log out."""

    del session["user_id"]
    flash("You have successfully logged out.")
    return redirect("/")


@app.route('/profile/<username>')
def show_user_profile(username):
    """Show user profile."""

    user = db.session.query(User).filter_by(username=username).one()
    avail_ing = Ingredient.query.filter(Ingredient.user_id == user.user_id, Ingredient.amount > 0).all()
    avail_ing = return_db_ingredients(avail_ing)

    depleted_ing = db.session.query(Ingredient.name).filter_by(user_id=user.user_id, amount=0).all()

    name = user.fname
    date = datetime.now()
    date = date.strftime("%B %d, %Y")

    return render_template("profile.html",
                           name=name,
                           date=date,
                           avail_ing=avail_ing,
                           depleted_ing=depleted_ing
                           )


@app.route('/add-ingredients', methods=["POST"])
def add_new_ingredients():
    """Add new ingredients to database."""

    #Get user ID to query the users table - need the user object to get the username attribute
    user_id = session.get('user_id', None)
    user = User.query.get(user_id)

    # Get the ingredients, amounts, and units from the form in the profile html
    # Slice up to second to last item because of hidden form template
    ingredients = request.form.getlist("ingredient", None)[:-1]
    amounts = request.form.getlist("amount", None)[:-1]
    units = request.form.getlist("unit", None)[:-1]

    # Map function applies the int() function to the amounts list
    # which changes the amounts from a list of strings to a list of integers
    amounts = map(float, amounts)
    ingredients = zip(ingredients, amounts, units)

    if ingredients:
        input_date = datetime.utcnow()

        for ingredient in ingredients:
            name = ingredient[0]
            amount = ingredient[1]
            unit = ingredient[2]

            db_ingredient = db.session.query(Ingredient).filter_by(user_id=user_id, name=name).first()

            if db_ingredient:
                amount += db_ingredient.amount
                db.session.query(Ingredient).filter_by(user_id=user_id, name=name).update({Ingredient.amount: amount,
                                                                                           Ingredient.unit: unit})
            else:
                new_ingredient = Ingredient(user_id=user_id,
                                            name=ingredient[0],
                                            amount=ingredient[1],
                                            unit=ingredient[2],
                                            input_date=input_date)

                db.session.add(new_ingredient)

            db.session.commit()

        flash("You have successfully added the ingredients.")

    return redirect("/profile/{}".format(user.username))


@app.route('/recipes')
def suggest_recipes():
    """Show user a list of suggested recipes."""

    # Grab user_id from session
    user_id = session.get('user_id', None)

    avail_ingredients = db.session.query(Ingredient.name).filter(Ingredient.user_id == user_id, Ingredient.amount > 0).all()  # Returns a list of tuples
    avail_ingredients = ",".join([ingredient[0] for ingredient in avail_ingredients])  # Creating a comma separated string (required for API argument)

    suggested_recipes = recipe_request(avail_ingredients, user_id)  # API request returns a dictionary with: id, image_url, recipe name, source, only the used ingredients and the amount

    return render_template("recipes.html",
                           recipes=suggested_recipes)


@app.route('/bookmarks')
def show_bookmarks():
    """Show user their list of bookmarked recipes."""

    user_id = session.get('user_id', None)

    bookmarked = BookmarkedRecipe.query.filter_by(user_id=user_id).all()
    avail_ingredients = db.session.query(Ingredient.name).filter(Ingredient.user_id == user_id, Ingredient.amount > 0).all()
    bookmark = True

    bookmarked_recipes = return_stored_recipes(bookmarked, avail_ingredients, user_id, bookmark)
    return render_template("recipes.html",
                           recipes=bookmarked_recipes)


@app.route('/cooked-recipes')
def show_cooked_recipes():
    """Show user their list of cooked recipes."""

    user_id = session.get('user_id', None)

    cooked = UsedRecipe.query.filter_by(user_id=user_id).all()
    avail_ingredients = db.session.query(Ingredient.name).filter(Ingredient.user_id == user_id, Ingredient.amount > 0).all()

    cooked_recipes = return_stored_recipes(cooked, avail_ingredients, user_id)

    return render_template("recipes.html",
                           recipes=cooked_recipes)


@app.route('/add-recipe.json', methods=["GET"])
def add_used_recipe():
    """Add used or bookmarked recipes to database."""

    user_id = session.get('user_id', None)
    button = request.args.get("button", None)
    recipe_id = request.args.get("api_id", None)
    image = request.args.get("image", None)
    source = request.args.get("source", None)
    title = request.args.get("title", None)
    ingredients = request.args.get("ing", None)

    recipe_id = int(recipe_id)
    button = button.split()
    ingredients = json.loads(ingredients)

    # Check if recipe is stored in the database
    db_recipe = Recipe.query.filter_by(recipe_id=recipe_id, user_id=user_id).first()

    if db_recipe:
        pass
    else:
        recipe = Recipe(recipe_id=recipe_id,
                        user_id=user_id,
                        title=title,
                        image_url=image,
                        source_url=source)

        db.session.add(recipe)
        db.session.commit()

    if button[-1] == "cook":
        update_cooked_recipe(user_id, recipe_id, ingredients)
    elif button[-1] == "bookmarks":
        add_bookmark(user_id, recipe_id)

    return jsonify(id=recipe_id, button=button)


@app.route('/recipe-details.json', methods=["GET"])
def return_recipe_details():

    recipe_id = request.args.get("api_id", None)
    ingredients = request.args.get("ingredients", None)
    title = request.args.get("title", None)
    image = request.args.get("image", None)

    ingredients = json.loads(ingredients)

    if isinstance(ingredients["used_ings"][0], unicode):
        info = recipe_info(recipe_id, ingredients["used_ings"])

    if isinstance(ingredients["used_ings"][0], dict):
        info = recipe_info(recipe_id)
        info["ingredients"] = json.dumps(ingredients)

    return jsonify(info=info,
                   id=recipe_id,
                   image=image,
                   title=title)


@app.route('/groceries')
def show_grocery_list():
    """Show grocery list."""

    user_id = session.get('user_id', None)

    depleted_ing = db.session.query(Ingredient.name).filter_by(user_id=user_id, amount=0).all()

    return render_template("grocery_list.html", groceries=depleted_ing)


if __name__ == "__main__":
    # We have to set debug=True here, since it has to be True at the point
    # that we invoke the DebugToolbarExtension
    app.debug = True

    connect_to_db(app)

    # Use the DebugToolbar
    DebugToolbarExtension(app)

    app.run()
