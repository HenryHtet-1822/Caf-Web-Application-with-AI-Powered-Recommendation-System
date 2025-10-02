from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from datetime import datetime
from flask_login import login_required, current_user
from functools import wraps
from extensions import db, bcrypt
from models import User, Event, MenuItem, Category
from sqlalchemy.orm import joinedload
from models import OrderItemNew, User, MenuItem, Event, Category
from sqlalchemy import func, extract, cast, Date
from extensions import bcrypt  # using your bcrypt instance
from app1 import db

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# -----------------------
# Admin-only decorator
# -----------------------
def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            flash("You are not authorized to access this page.", "danger")
            # Make sure 'home_page' exists in your main app
            return redirect(url_for("home_page"))
        return func(*args, **kwargs)

    return wrapper


@admin_bp.route("/dashboard")
@login_required
@admin_required
def dashboard():
    # Just render the admin dashboard without Stripe API calls
    return render_template("admin/adminDashboard.html")


# Manage Events Page
@admin_bp.route("/events", methods=["GET"])
@login_required
@admin_required
def manage_events():
    events = Event.query.order_by(Event.start_datetime.asc()).all()
    return render_template("admin/createEvent.html", events=events)


# Create Event
@admin_bp.route("/events/create", methods=["GET", "POST"])
@login_required
@admin_required
def create_event():
    if request.method == "GET":
        return redirect(url_for("admin.manage_events"))

    try:
        event_title = request.form["event_title"]
        start_datetime = datetime.fromisoformat(request.form["start_datetime"])
        end_datetime = datetime.fromisoformat(request.form["end_datetime"])
        event_type = request.form.get("event_type")
        ticket_sales = request.form.get("ticket_sales") == "on"
        ticket_price = float(request.form.get("ticket_price") or 0)
        img_src = request.form.get("img_src")

        new_event = Event(
            event_title=event_title,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            event_type=event_type,
            ticket_sales=ticket_sales,
            ticket_price=ticket_price,
            img_src=img_src
        )
        db.session.add(new_event)
        db.session.commit()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({
                "success": True,
                "event": {
                    "id": new_event.event_id,
                    "title": new_event.event_title,
                    "start": new_event.start_datetime.strftime('%Y-%m-%d %H:%M'),
                    "end": new_event.end_datetime.strftime('%Y-%m-%d %H:%M'),
                    "type": new_event.event_type,
                    "tickets": "Yes" if new_event.ticket_sales else "No",
                    "price": new_event.ticket_price
                }
            })

        flash("Event created successfully!", "success")
        return redirect(url_for("admin.manage_events"))

    except Exception as e:
        print(e)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"success": False, "message": "Failed to create event."})
        flash("Failed to create event.", "danger")
        return redirect(url_for("admin.manage_events"))


# Delete Event
@admin_bp.route("/events/delete/<int:event_id>", methods=["POST"])
@login_required
@admin_required
def delete_event(event_id):
    event = Event.query.get_or_404(event_id)
    try:
        db.session.delete(event)
        db.session.commit()
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"success": True})
        flash("Event deleted successfully!", "success")
    except Exception as e:
        print(e)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"success": False})
        flash("Failed to delete event.", "danger")
    return redirect(url_for("admin.manage_events"))


# Update/Edit Event
@admin_bp.route("/events/edit/<int:event_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_event(event_id):
    event = Event.query.get_or_404(event_id)

    if request.method == "POST":
        try:
            event.event_title = request.form["event_title"]
            event.start_datetime = datetime.fromisoformat(request.form["start_datetime"])
            event.end_datetime = datetime.fromisoformat(request.form["end_datetime"])
            event.event_type = request.form.get("event_type")
            event.ticket_sales = request.form.get("ticket_sales") == "on"
            event.ticket_price = float(request.form.get("ticket_price") or 0)
            event.img_src = request.form.get("img_src")

            db.session.commit()

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"success": True, "message": "Event updated successfully!"})

            flash("Event updated successfully!", "success")
            return redirect(url_for("admin.manage_events"))

        except Exception as e:
            print(e)
            db.session.rollback()
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"success": False, "message": "Failed to update event."})
            flash("Failed to update event.", "danger")
            return redirect(url_for("admin.manage_events"))

    # If GET request, render edit form
    return render_template("admin/createEvent.html", event=event)


@admin_bp.route("/users", methods=["GET", "POST"])
@login_required
@admin_required
def manage_users():
    from models import User

    users = User.query.order_by(User.user_id.asc()).all()
    user_to_edit = None

    # Handle create user
    if request.method == "POST" and request.form.get("action") == "create":
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        phone_number = request.form.get('phone_number')
        address = request.form.get('address')
        role = request.form['role']
        password = request.form['password']

        # Check for duplicate email
        if User.query.filter_by(email=email).first():
            flash("Email already exists!", "danger")
            return render_template("admin/manageUsers.html", users=users, user=None)

        password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

        new_user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password_hash=password_hash,
            phone_number=phone_number,
            address=address,
            role=role
        )
        db.session.add(new_user)
        db.session.commit()
        flash("User created successfully!", "success")
        return redirect(url_for("admin.manage_users"))

    # Handle edit user
    if request.method == "POST" and request.form.get("action") == "edit":
        user_id = int(request.form['user_id'])
        user_to_edit = User.query.get_or_404(user_id)

        # Update fields
        user_to_edit.first_name = request.form['first_name']
        user_to_edit.last_name = request.form['last_name']
        user_to_edit.email = request.form['email']
        user_to_edit.phone_number = request.form.get('phone_number')
        user_to_edit.address = request.form.get('address')
        user_to_edit.role = request.form['role']

        db.session.commit()
        flash("User updated successfully!", "success")
        return redirect(url_for("admin.manage_users"))

    return render_template("admin/manageUsers.html", users=users, user=user_to_edit)


# Edit user
@admin_bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    users = User.query.order_by(User.user_id.asc()).all()

    if request.method == 'POST':
        user.first_name = request.form['first_name']
        user.last_name = request.form['last_name']
        user.email = request.form['email']
        user.phone_number = request.form.get('phone_number')
        user.address = request.form.get('address')
        user.role = request.form['role']
        db.session.commit()
        flash('User updated successfully!', 'success')
        return redirect(url_for('admin.manage_users'))

    # Render same template with "user" for edit form
    return render_template('admin/manageUsers.html', users=users, user=user)


# Delete user
@admin_bp.route("/users/delete/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def delete_users(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash("User deleted successfully!", "success")
    return redirect(url_for("admin.manage_users"))


# Menu Item Management

@admin_bp.route("/menu_items", methods=["GET", "POST"])
@login_required
@admin_required
def manage_menu_items():
    items = MenuItem.query.options(joinedload(MenuItem.category)).all()
    categories = Category.query.all()
    return render_template("admin/manageMenu_item.html", items=items, categories=categories)


@admin_bp.route("/menu_items/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_menu_item():
    categories = Category.query.order_by(Category.category_id.asc()).all()
    if request.method == "POST":
        recipe_name = request.form['recipe_name']
        prep_time = request.form.get('prep_time')
        cook_time = request.form.get('cook_time')
        total_time = request.form.get('total_time')
        ingredients = request.form.get('ingredients')
        rating = request.form.get('rating', type=float)
        cuisine_path = request.form.get('cuisine_path')
        nutrition = request.form.get('nutrition')
        img_src = request.form.get('img_src')
        is_ready_to_serve = bool(request.form.get('is_ready_to_serve'))
        cleaned_ingredients = request.form.get('cleaned_ingredients')
        category_id = request.form.get('category_id', type=int)
        price = request.form.get('price', type=float)

        new_item = MenuItem(
            recipe_name=recipe_name,
            prep_time=prep_time,
            cook_time=cook_time,
            total_time=total_time,
            ingredients=ingredients,
            rating=rating,
            cuisine_path=cuisine_path,
            nutrition=nutrition,
            img_src=img_src,
            is_ready_to_serve=is_ready_to_serve,
            cleaned_ingredients=cleaned_ingredients,
            category_id=category_id,
            price=price
        )
        db.session.add(new_item)
        db.session.commit()
        flash("Menu item added successfully!", "success")
        return redirect(url_for("admin.manage_menu_items"))

    return render_template("admin/manageMenu_item.html", categories=categories)


@admin_bp.route("/menu_items/edit/<int:item_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_menu_item(item_id):
    item = MenuItem.query.get_or_404(item_id)
    categories = Category.query.order_by(Category.category_id.asc()).all()

    if request.method == "POST":
        item.recipe_name = request.form['recipe_name']
        item.prep_time = request.form.get('prep_time')
        item.cook_time = request.form.get('cook_time')
        item.total_time = request.form.get('total_time')
        item.ingredients = request.form.get('ingredients')
        item.rating = request.form.get('rating', type=float)
        item.cuisine_path = request.form.get('cuisine_path')
        item.nutrition = request.form.get('nutrition')
        item.img_src = request.form.get('img_src')
        item.is_ready_to_serve = bool(request.form.get('is_ready_to_serve'))
        item.cleaned_ingredients = request.form.get('cleaned_ingredients')
        item.category_id = request.form.get('category_id', type=int)
        item.price = request.form.get('price', type=float)

        db.session.commit()
        flash("Menu item updated successfully!", "success")
        return redirect(url_for("admin.manage_menu_items"))

    return render_template("admin/manageMenu_item.html", item=item, categories=categories)


@admin_bp.route("/menu_items/delete/<int:item_id>", methods=["POST"])
@login_required
@admin_required
def delete_menu_item(item_id):
    item = MenuItem.query.get_or_404(item_id)
    try:
        db.session.delete(item)
        db.session.commit()
        flash(f"Menu item '{item.recipe_name}' deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting item: {str(e)}", "danger")
    return redirect(url_for("admin.manage_menu_items"))


@admin_bp.route("/orders", methods=["GET"])
@login_required
def manage_orders_view():
    # Eager-load user and menu_item relationships to avoid multiple queries
    orders = OrderItemNew.query.options(
        joinedload(OrderItemNew.user),
        joinedload(OrderItemNew.menu_item)
    ).order_by(OrderItemNew.order_date.desc()).all()

    return render_template("admin/manageOrders.html", orders=orders)


@admin_bp.route("/orders")
@login_required
def manage_orders():
    orders = OrderItemNew.query.order_by(OrderItemNew.order_date.desc()).all()
    return render_template("admin/manage_orders.html", orders=orders)


@admin_bp.route("/orders/update_status/<int:order_id>", methods=["POST"])
@login_required
def update_order_status(order_id):
    order = OrderItemNew.query.get_or_404(order_id)

    # Get form values
    status = request.form.get("status")
    quantity = request.form.get("quantity", type=int)
    price = request.form.get("price", type=float)

    if status not in ["processing", "closed", "cancelled"]:
        flash("Invalid status selected.", "danger")
        return redirect(url_for("admin.manage_orders"))

    try:
        order.status = status
        order.quantity = quantity
        order.price = price
        db.session.commit()
        flash(f"Order {order.order_id} updated successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to update order: {str(e)}", "danger")

    return redirect(url_for("admin.manage_orders"))


# --- Summary KPIs ---

@admin_bp.route("/api/summary")
@login_required
@admin_required
def summary():
    total_users = db.session.query(func.count(User.user_id)).scalar()
    total_orders = db.session.query(func.count(OrderItemNew.id)).scalar()
    total_revenue = db.session.query(func.sum(OrderItemNew.price * OrderItemNew.quantity)).scalar() or 0
    total_events = db.session.query(func.count(Event.event_id)).scalar()

    return jsonify({
        "total_users": total_users,
        "total_orders": total_orders,
        "total_revenue": float(total_revenue),
        "total_events": total_events
    })


# --- User Roles Chart ---
@admin_bp.route("/api/user_roles")
@login_required
@admin_required
def user_roles():
    roles = db.session.query(User.role, func.count(User.user_id)).group_by(User.role).all()
    return jsonify([{"role": r, "count": c} for r, c in roles])


# --- Orders by Status Chart ---
@admin_bp.route("/api/orders_status")
@login_required
@admin_required
def orders_status():
    statuses = db.session.query(OrderItemNew.status, func.count(OrderItemNew.id)) \
        .group_by(OrderItemNew.status).all()
    return jsonify([{"status": s, "count": c} for s, c in statuses])


# --- Revenue by Menu Item Chart ---
@admin_bp.route("/api/orders_revenue")
@login_required
@admin_required
def orders_revenue():
    revenues = db.session.query(
        MenuItem.recipe_name,
        func.sum(OrderItemNew.price * OrderItemNew.quantity)
    ).join(MenuItem, OrderItemNew.menu_item_id == MenuItem.menu_items_id) \
        .group_by(MenuItem.recipe_name).all()

    return jsonify([{"menu_item": m, "revenue": float(r)} for m, r in revenues])


@admin_bp.route("/api/events_month")
@login_required
@admin_required
def api_events_month():
    try:
        # Group events by month
        results = (
            db.session.query(
                extract('month', Event.start_datetime).label('month'),
                db.func.count(Event.event_id).label('count')
            )
            .group_by('month')
            .order_by('month')
            .all()
        )
        # Convert numeric month to readable format (Jan, Feb, ...)
        import calendar
        data = [{"month": calendar.month_abbr[int(r.month)], "count": r.count} for r in results]
        return jsonify(data)
    except Exception as e:
        print("Error in /api/events_month:", e)
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/api/orders_revenue_over_time")
@login_required
@admin_required
def api_orders_revenue_over_time():
    try:
        # Sum revenue per day
        results = (
            db.session.query(
                cast(OrderItemNew.order_date, Date).label("date"),
                func.sum(OrderItemNew.price * OrderItemNew.quantity).label("revenue")
            )
            .group_by("date")
            .order_by("date")
            .all()
        )

        data = [{"date": r.date.strftime("%b %d, %Y"), "revenue": float(r.revenue)} for r in results]

        return jsonify(data)

    except Exception as e:
        print("Error in /api/orders_revenue_over_time:", e)
        return jsonify({"error": str(e)}), 500


# Admin profile
@admin_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    from models import User

    if request.method == "POST":
        try:
            # Safely get form values
            current_user.first_name = request.form.get('first_name') or current_user.first_name
            current_user.last_name = request.form.get('last_name') or current_user.last_name
            current_user.email = request.form.get('email') or current_user.email
            current_user.dob = request.form.get('dob') or current_user.dob
            current_user.gender = request.form.get('gender') or current_user.gender
            current_user.phone_number = request.form.get('phone_number') or current_user.phone_number
            current_user.address = request.form.get('address') or current_user.address
            current_user.role = request.form.get('role') or current_user.role

            # Update password only if a new one is provided
            new_password = request.form.get('password')
            if new_password:
                current_user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')

            db.session.commit()
            flash("Profile updated successfully!", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating profile: {str(e)}", "danger")

        return redirect(url_for("admin.profile"))

    return render_template("admin/adminProfile.html", user=current_user)
