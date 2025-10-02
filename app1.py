from flask import Flask, render_template, redirect, url_for, jsonify, flash, request, session, current_app, Blueprint
import os
from config import Config
from extensions import db, bcrypt, login_manager
from models import User, Category, MenuItem, Event, OrderItemNew, EventRegistration
from auth.routes import auth
from test import stripe_bp
from menu_recommender import recommend_menu_with_weather
from flask import url_for
from admin import admin_bp
from datetime import datetime
from flask_login import login_required, current_user, AnonymousUserMixin
from werkzeug.utils import secure_filename


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Stripe API keys
    app.config[
        'STRIPE_PUBLIC_KEY'] = 'pk_test_12345'
    app.config[
        'STRIPE_SECRET_KEY'] = 'sk_test_12345'

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)

    # Create DB tables
    with app.app_context():
        db.create_all()

    # Register Blueprints
    app.register_blueprint(auth)
    app.register_blueprint(stripe_bp)
    app.register_blueprint(admin_bp)

    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.template_filter('datetimeformat')
    def datetimeformat(value, format='%Y-%m-%d %H:%M:%S'):

        if isinstance(value, int):
            return datetime.fromtimestamp(value).strftime(format)
        return value

    @app.route("/api/search")
    def api_search():
        query = request.args.get("q", "").strip()
        if not query:
            return jsonify([])

        # Example: search menu items
        results = MenuItem.query.filter(MenuItem.name.ilike(f"%{query}%")).limit(5).all()
        return jsonify([{"id": r.id, "name": r.name, "price": r.price} for r in results])

    @app.route('/profile')
    @login_required
    def profile():
        return render_template('Profile.html', user=current_user)

    UPLOAD_FOLDER = os.path.join("static", "images", "profile")
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

    def allowed_file(filename):
        return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

    @app.route('/update_profile', methods=['POST'])
    @login_required
    def update_profile():
        # Example: get form data
        phone_number = request.form.get("phone_number")
        address = request.form.get("address")

        # Update current user
        current_user.phone_number = phone_number
        current_user.address = address

        # Save changes
        db.session.commit()

        flash("Profile updated successfully!", "success")
        return redirect(url_for('profile'))

    @app.route('/upload_profile_image', methods=['POST'])
    @login_required
    def upload_profile_image():
        if 'profile_image' not in request.files:
            flash('No file part', 'danger')
            return redirect(url_for('profile'))

        file = request.files['profile_image']

        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(url_for('profile'))

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            upload_folder = os.path.join(current_app.root_path, "static", "images", "profile")

            # Make sure the folder exists
            os.makedirs(upload_folder, exist_ok=True)

            # Save file
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)

            # Save relative path to DB
            current_user.profile_image_url = f"images/profile/{filename}"
            db.session.commit()

            flash("Profile picture updated successfully!", "success")

        return redirect(url_for('profile'))

    @app.route('/change_password', methods=['POST'])
    @login_required
    def change_password():
        old_password = request.form.get("old_password")
        new_password = request.form.get("new_password")

        # Check old password
        if not bcrypt.check_password_hash(current_user.password_hash, old_password):
            flash("Old password is incorrect", "danger")
            return redirect(url_for("profile"))

        # Hash new password
        new_hash = bcrypt.generate_password_hash(new_password).decode("utf-8")

        # Update DB
        current_user.password_hash = new_hash
        db.session.commit()

        flash("Password changed successfully!", "success")
        return redirect(url_for("profile"))

    @app.route('/order-history')
    @login_required
    def order_history_page():
        # Fetch all orders for the current user
        user_orders = OrderItemNew.query.filter_by(user_id=current_user.user_id).all()

        # Group orders by restaurant
        orders_by_restaurant = {}
        for order in user_orders:
            restaurant_name = order.menu_item.category.category_name  # Example
            if restaurant_name not in orders_by_restaurant:
                orders_by_restaurant[restaurant_name] = {
                    "name": restaurant_name,
                    "total_orders": 0,
                    "order_list": []
                }

            # Use the rating directly from the order
            user_rating = order.rating

            # Add order details
            orders_by_restaurant[restaurant_name]["total_orders"] += 1
            orders_by_restaurant[restaurant_name]["order_list"].append({
                "id": order.id,
                "image_url": order.menu_item.img_src,
                "delivered_at": order.order_date.strftime("%d %b %Y"),
                "address": order.address,
                "items_summary": order.menu_item.recipe_name,  # Simplified summary
                "user_rating": user_rating
            })

        orders = list(orders_by_restaurant.values())

        return render_template('order_history.html', orders=orders)

    # Optional: AJAX route for inline rating update
    @app.route('/rate-order', methods=['POST'])
    @login_required
    def rate_order():
        data = request.get_json()
        order_id = data.get('order_id')
        rating = data.get('rating')

        if not order_id or rating is None:
            return jsonify({"success": False, "message": "Invalid data"}), 400

        order = OrderItemNew.query.get(order_id)
        if not order or order.user_id != current_user.user_id:
            return jsonify({"success": False, "message": "Order not found"}), 404

        # Update the rating
        order.rating = rating
        db.session.commit()

        return jsonify({"success": True, "message": "Rating saved"})

    @app.route('/order-receipt/<int:order_id>')
    @login_required
    def order_receipt(order_id):
        order = OrderItemNew.query.get_or_404(order_id)
        if order.user_id != current_user.user_id:
            abort(403)  # Prevent others from seeing it
        return render_template('order_receipt.html', order=order)

    @app.route('/set_language/<lang>')
    def set_language(lang):
        session['lang'] = lang
        return redirect(request.referrer or url_for('index'))

    @app.route('/settings')
    @login_required
    def settings():
        return render_template('Setting.html', user=current_user)

    @app.route('/order-history')
    @login_required
    def order_history():
        # Example: later you can query orders by current_user.user_id
        # orders = Order.query.filter_by(user_id=current_user.user_id).all()
        return render_template('order_history.html', user=current_user)

    @app.route("/add-to-cart", methods=["POST"])
    @login_required
    def add_to_cart():
        try:
            data = request.get_json() or {}
            item_id = data.get("item_id")  # <-- fixed to match cart.js
            quantity = int(data.get("quantity", 1))

            # Validate presence of an identifier
            if not item_id:
                return jsonify({"message": "No item identifier provided"}), 400

            # Ensure item_id is an integer
            try:
                item_id = int(item_id)
            except (ValueError, TypeError):
                return jsonify({"message": "Invalid item_id"}), 400

            # Lookup menu item by ID
            menu_item = MenuItem.query.get(item_id)
            if not menu_item:
                return jsonify({"message": "Item not found"}), 404

            # Store cart in session
            cart = session.get("cart", {})
            cart[str(item_id)] = cart.get(str(item_id), 0) + quantity
            session["cart"] = cart

            print(f"User {current_user.user_id} added {quantity} of {menu_item.recipe_name} to cart")

            return jsonify({
                "message": f"{menu_item.recipe_name} added to cart successfully!",
                "cart": cart
            }), 200

        except Exception as e:
            print("Error in /add-to-cart:", e)
            return jsonify({"message": str(e)}), 500

    # Public Routes
    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    @app.route('/home')
    def home_page():
        return render_template('Home.html')

    @app.route('/menu')
    def menu():
        categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
        return render_template('Menu.html', categories=categories, current_user=current_user)

    @app.route('/menu/<slug>')
    def menu_by_category(slug):
        return render_template('menu_item.html', filename='Menu Items', item_name='Menu Items')

    @app.route('/about_us')
    def about_us():
        return render_template('AboutUs.html', item_name='About Us')

    @app.route('/contact')
    def contact():
        return render_template('ContactUs.html', item_name='Contact Us')

    @app.route('/cart')
    @login_required
    def cart():
        return render_template('ShoppingCart.html', item_name='Shopping Cart')

    @app.route('/thanks')
    def thanks():
        return render_template('thanks.html')

    @app.route('/api/menu/<int:category_id>')
    def get_menu_items(category_id):
        items = MenuItem.query.filter_by(category_id=category_id).all()
        data = [
            {
                "id": item.menu_items_id,
                "recipe_name": item.recipe_name,  # matches JS
                "img_src": item.img_src,  # matches JS
                "price": float(item.price) if hasattr(item, 'price') else None,
                "ingredients": item.ingredients,  # matches JS
                "group": item.cuisine_path
            }
            for item in items
        ]
        return jsonify(data)

    @app.route('/menu-items/<slug>')
    def menu_items_by_category(slug):

        category = Category.query.filter_by(slug=slug).first_or_404()
        items = MenuItem.query.filter_by(category_id=category.category_id).all()
        categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()

        return render_template(
            'menu_item.html',
            categories=categories,
            category=category,
            items=items,
            category_id=category.category_id
        )

    @app.route('/menu/category/<int:category_id>')
    def menu_items(category_id):
        return render_template('menu_item.html', category_id=category_id, item_name='Menu Item')

    @app.route('/api/menu-item/<int:item_id>')
    def get_menu_item(item_id):
        item = MenuItem.query.get(item_id)
        if not item:
            return jsonify({"error": "Item not found"}), 404

        from sqlalchemy.sql.expression import func

        recommended_items = MenuItem.query.filter(
            MenuItem.category_id == item.category_id,
            MenuItem.menu_items_id != item.menu_items_id
        ).order_by(func.random()).limit(7).all()

        data = {
            "id": item.menu_items_id,
            "recipe_name": item.recipe_name,
            "img_src": item.img_src,
            "price": float(item.price),
            "ingredients": item.ingredients,
            "group": item.cuisine_path,
            "recommendations": [
                {
                    "id": rec.menu_items_id,
                    "recipe_name": rec.recipe_name,
                    "img_src": rec.img_src,
                    "price": float(rec.price),
                }
                for rec in recommended_items
            ]
        }
        return jsonify(data)

    @app.route('/event')
    def event():
        events = Event.query.order_by(Event.start_datetime.asc()).all()
        now = datetime.now()

        # Convert ticket_sales to boolean explicitly
        for e in events:
            e.ticket_sales = bool(e.ticket_sales)

        return render_template("Event.html", events=events, now=now)

    @app.route("/api/events")
    def api_events():
        events = Event.query.order_by(Event.start_datetime.asc()).all()
        return jsonify([
            {
                "event_id": e.event_id,
                "event_title": e.event_title or "Untitled Event",
                "start_datetime": e.start_datetime.strftime("%Y-%m-%d %H:%M") if e.start_datetime else None,
                "end_datetime": e.end_datetime.strftime("%Y-%m-%d %H:%M") if e.end_datetime else None,
                "event_type": e.event_type or "standard",
                "ticket_sales": e.ticket_sales,
                "ticket_price": float(e.ticket_price) if e.ticket_price else None,
                "img_src": e.img_src
            }
            for e in events
        ])

    # --- Event registration ---
    @app.route('/register_event/<int:event_id>', methods=['POST'])
    @login_required
    def register_event(event_id):
        event = Event.query.get_or_404(event_id)

        # Prevent duplicate registration
        existing = EventRegistration.query.filter_by(user_id=current_user.user_id, event_id=event_id).first()
        if existing:
            return jsonify({"success": False, "message": "You have already registered for this event."}), 400

        # Guests count
        guests = int(request.json.get("guests", 1))

        registration = EventRegistration(user_id=current_user.user_id, event_id=event_id)
        db.session.add(registration)
        db.session.commit()

        return jsonify(
            {"success": True, "message": f"Successfully registered for {event.event_title} with {guests} guest(s)."})

    # --- Menu Recommender API Routes ---

    @app.route("/recommendations_weather/<menu_item>")
    def get_recommendations_with_weather(menu_item):
        try:
            # Call your recommender
            result = recommend_menu_with_weather(menu_item)  # returns dict with DataFrames

            # Item-based recommendations
            item_based_raw = result["clicked_item_recommendation"]
            item_based = item_based_raw.to_dict(orient="records") if hasattr(item_based_raw, "to_dict") else []

            # Weather-based recommendations
            weather_based_raw = result["weather_based_recommendation"]
            if hasattr(weather_based_raw, "to_dict"):
                weather_based = weather_based_raw.copy()
                # Ensure img_src exists
                if "img_src" not in weather_based.columns:
                    weather_based["img_src"] = None
                weather_based["img_src"] = weather_based["img_src"].fillna("https://placehold.co/300x200")
                weather_based = weather_based[
                    ["recipe_name", "ingredients", "category_id", "category_name", "price", "img_src"]]
                weather_based = weather_based.to_dict(orient="records")
            else:
                weather_based = []

            # Return all required info
            return jsonify({
                "clicked_item_recommendation": item_based,
                "weather_based_recommendation": weather_based,
                "weather": result["weather"],
                "temperature": result["temperature"]
            })

        except Exception as e:
            print("Error in get_recommendations_with_weather:", e)
            return jsonify({"error": str(e)}), 500

    return app


# Run the app
if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
