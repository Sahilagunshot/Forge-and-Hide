from flask import Flask, render_template, redirect, url_for, request, flash, session
from werkzeug.utils import secure_filename
import uuid
import os
import hmac
import re
import unicodedata
import hashlib
import razorpay
from dotenv import load_dotenv
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_login import (
    LoginManager,
    login_required,
    login_user,
    logout_user,
    current_user
)

from config import Config
from models import (
    db,
    Category,
    Product,
    ProductImage,
    Admin,
    Customer,
    Cart,
    Order,
    OrderItem
)


app = Flask(__name__)
app.config.from_object(Config)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = os.getenv(
    "RAZORPAY_WEBHOOK_SECRET"
)

razorpay_client = razorpay.Client(
    auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
)


db.init_app(app)

migrate = Migrate(app, db)

# CSRF protection ON (token session tak valid, 1 ghante me expire nahi hoga)
app.config["WTF_CSRF_TIME_LIMIT"] = None
csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.login_view = "admin_login"
login_manager.init_app(app)
from functools import wraps



def admin_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):

        if not current_user.is_authenticated:
            return redirect(url_for("admin_login"))

        if not isinstance(current_user, Admin):
            return redirect(url_for("home"))

        return f(*args, **kwargs)

    return decorated_function



def customer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):

        if not session.get("customer_id"):
            return redirect(url_for("login"))

        return f(*args, **kwargs)

    return decorated_function

@app.context_processor
def inject_cart_count():

    cart_count = 0

    customer_id = session.get("customer_id")

    if customer_id:

        cart_items = Cart.query.filter_by(
            customer_id=customer_id
        ).all()

        for item in cart_items:

            if item.product and item.product.is_active:

                cart_count += item.quantity

    return {
        "cart_count": cart_count,
        "business": BUSINESS
    }

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Admin, int(user_id))


@app.route("/")
def home():

    featured_products = Product.query.filter_by(
        is_featured=True,
        is_active=True
    ).limit(8).all()

    latest_products = Product.query.filter_by(
        is_active=True
    ).order_by(
        Product.id.desc()
    ).limit(8).all()

    if not featured_products:
        featured_products = latest_products[:4]

    categories = Category.query.order_by(
        Category.id.asc()
    ).all()

    # =========================
    # HOME PAGE DATA
    # =========================

    uploads = app.config["UPLOAD_FOLDER"]

    # Hero: static/video/hero.mp4 ho to video, warna photo
    hero_video = os.path.exists(
        os.path.join(app.root_path, "static", "video", "hero.mp4")
    )

    hero_image = None

    for file_name in ["hero.jpg", "hero.png", "green-duffle-side-1.jpg"]:

        if os.path.exists(os.path.join(uploads, file_name)):

            hero_image = file_name
            break

    if not hero_image:

        for product in latest_products:

            if product.image:

                hero_image = product.image
                break

    # Category tiles: har category ka ek cover photo
    categories = Category.query.order_by(
        Category.id.asc()
    ).all()

    category_tiles = []

    for category in categories:

        cover = Product.query.filter(
            Product.category_id == category.id,
            Product.is_active == True,
            Product.image.isnot(None),
            Product.image != ""
        ).order_by(
            Product.id.desc()
        ).first()

        category_tiles.append({
            "category": category,
            "image": cover.image if cover else None
        })

    return render_template(
        "index.html",
        hero_video=hero_video,
        hero_image=hero_image,
        collection_products=latest_products,
        category_tiles=category_tiles,
        customer_name=session.get("customer_name")
    )

@app.route("/shop")
def shop():
    category_slug = request.args.get("category")

    categories = Category.query.order_by(
        Category.id.asc()
    ).all()

    if category_slug:
        category = Category.query.filter_by(
            slug=category_slug
        ).first()

        if category:
            products = Product.query.filter_by(
              category_id=category.id,
              is_active=True
            ).order_by(
              Product.id.desc()
            ).all()
        else:
            products = []
    else:
            products = Product.query.filter_by(
              is_active=True
            ).order_by(
              Product.id.desc()
            ).all()

    return render_template(
        "shop.html",
        products=products,
        categories=categories,
        selected_category=category_slug
    )

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if password != confirm_password:

            flash("Passwords do not match.")

            return redirect(url_for("register"))

        existing_customer = Customer.query.filter_by(
            email=email
        ).first()

        if existing_customer:

            flash("Email already registered.")

            return redirect(url_for("register"))

        customer = Customer(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone
        )

        customer.set_password(password)

        db.session.add(customer)
        db.session.commit()

        flash("Account created successfully. Please login.")

        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        customer = Customer.query.filter_by(
            email=email
        ).first()

        if customer and customer.check_password(password):

            session["customer_id"] = customer.id
            session["customer_name"] = customer.first_name

            flash("Login Successful!")

            return redirect(url_for("home"))

        flash("Invalid Email or Password.")

    return render_template("login.html")


@app.route("/customer/logout")
def customer_logout():

    session.pop("customer_id", None)
    session.pop("customer_name", None)

    flash("Logged out successfully.")

    return redirect(url_for("home"))


@app.route("/product/<slug>")
def product_detail(slug):

    product = Product.query.filter_by(
        slug=slug,
        is_active=True
    ).first_or_404()

    return render_template(
        "product_detail.html",
        product=product
    )

@app.route("/add-to-cart/<int:product_id>")
@customer_required
def add_to_cart(product_id):

    product = Product.query.filter_by(
    id=product_id,
    is_active=True
).first_or_404()
    if not product.is_active:

          flash("This product is no longer available.")

          return redirect(url_for("shop"))

    # =========================
    # CHECK PRODUCT STOCK
    # =========================

    if product.stock <= 0:

        flash("This product is out of stock.")

        return redirect(
            url_for(
                "product_detail",
                slug=product.slug
            )
        )


    # =========================
    # FIND EXISTING CART ITEM
    # =========================

    existing = Cart.query.filter_by(
    customer_id=session.get("customer_id"),
    product_id=product_id
).first()


    # =========================
    # CHECK CART QUANTITY
    # =========================

    if existing:

        if existing.quantity >= product.stock:

            flash(
                f"Only {product.stock} item(s) available in stock."
            )

            return redirect(
                url_for(
                    "product_detail",
                    slug=product.slug
                )
            )

        existing.quantity += 1


    else:

        cart = Cart(
            customer_id=session.get("customer_id"),
            product_id=product_id,
            quantity=1
        )

        db.session.add(cart)


    db.session.commit()

    flash("Product Added To Cart")

    return redirect(url_for("cart"))


@app.route("/cart")
@customer_required
def cart():

    customer_id = session.get("customer_id")

    cart_items = Cart.query.filter_by(
        customer_id=customer_id
    ).all()

    # =========================
    # REMOVE ARCHIVED PRODUCTS
    # =========================

    active_cart_items = []

    for item in cart_items:

        if item.product and item.product.is_active:

            active_cart_items.append(item)

        else:

            db.session.delete(item)

    db.session.commit()

    # =========================
    # CALCULATE TOTAL
    # =========================

    total = 0

    for item in active_cart_items:

        total += (
            item.product.price *
            item.quantity
        )

    return render_template(
        "cart.html",
        cart_items=active_cart_items,
        total=total
    )

@app.route("/checkout", methods=["GET", "POST"])
@customer_required
def checkout():

    cart_items = Cart.query.filter_by(
        customer_id=session.get("customer_id")
    ).all()

    if not cart_items:

        flash("Your cart is empty.")
        return redirect(url_for("cart"))

    # =========================
    # REMOVE ARCHIVED PRODUCTS
    # =========================

    active_cart_items = []

    for item in cart_items:

        if item.product and item.product.is_active:
            active_cart_items.append(item)

        else:
            db.session.delete(item)

    db.session.commit()

    cart_items = active_cart_items

    if not cart_items:

        flash("Your cart is empty.")
        return redirect(url_for("cart"))

    # =========================
    # CHECK PRODUCT EXISTS
    # =========================

    for item in cart_items:

        if not item.product:
            db.session.delete(item)

    db.session.commit()

    cart_items = [
        item for item in cart_items
        if item.product
    ]

    if not cart_items:

        flash("Your cart is empty.")
        return redirect(url_for("cart"))

    # =========================
    # CHECK STOCK BEFORE CHECKOUT
    # =========================

    for item in cart_items:

        product = item.product

        if item.quantity > product.stock:

            flash(
                f"Only {product.stock} item(s) of "
                f"{product.name} are available in stock."
            )

            return redirect(url_for("cart"))

    # =========================
    # CALCULATE TOTAL
    # =========================

    total = 0

    for item in cart_items:
        total += item.product.price * item.quantity

    # =========================
    # PROCESS ORDER ONLY ON POST
    # =========================

    if request.method == "POST":

        # =========================
        # FINAL STOCK CHECK
        # =========================

        for item in cart_items:

            product = item.product

            if product.stock < item.quantity:

                flash(
                    f"Not enough stock for {product.name}. "
                    f"Only {product.stock} item(s) available."
                )

                return redirect(url_for("cart"))

        # =========================
        # SHIPPING DETAILS
        # =========================

        shipping_name = request.form.get("shipping_name")
        shipping_phone = request.form.get("shipping_phone")
        shipping_address = request.form.get("shipping_address")
        city = request.form.get("city")
        state = request.form.get("state")
        pincode = request.form.get("pincode")
        payment_method = request.form.get("payment_method")

        if payment_method == "COD":

            payment_status = "Pending"

        elif payment_method == "ONLINE":

            payment_status = "Pending"

        # =========================
        # VALIDATE PAYMENT METHOD
        # =========================

        if payment_method not in ["COD", "ONLINE"]:

            flash("Please select a valid payment method.")

            return redirect(url_for("checkout"))

        # =========================
        # VALIDATE SHIPPING DETAILS
        # =========================

        if not all([
            shipping_name,
            shipping_phone,
            shipping_address,
            city,
            state,
            pincode
        ]):

            flash("Please fill all shipping details.")

            return redirect(url_for("checkout"))

        # =========================
        # ONLINE PAYMENT
        # =========================

        if payment_method == "ONLINE":

            

            # =========================
            # CREATE NEW LOCAL ORDER
            # =========================

            order = Order(
                customer_id=session.get("customer_id"),
                total_amount=total,
                status="Pending",
                payment_status="Pending",
                payment_method="ONLINE",
                shipping_name=shipping_name,
                shipping_phone=shipping_phone,
                shipping_address=shipping_address,
                city=city,
                state=state,
                pincode=pincode
            )

            db.session.add(order)

            db.session.flush()

            # =========================
            # CREATE RAZORPAY ORDER
            # =========================

            try:

                razorpay_order = razorpay_client.order.create(
                    {
                        "amount": int(round(total * 100  )),
                        "currency": "INR",
                        "receipt": f"fh_order_{order.id}"
                    }
                )

            except Exception as e:

                print(f"RAZORPAY ERROR: {type(e).__name__}: {e}")

                db.session.rollback()

                flash(
                    "Didn't connect to Payment Gateway. "
                    "Please Try Again."
                )

                return redirect(
                    url_for("checkout")
                )

            order.razorpay_order_id = (
                razorpay_order["id"]
            )

            # =========================
            # CREATE ORDER ITEMS
            # DO NOT REDUCE STOCK YET
            # =========================

            for item in cart_items:

                order_item = OrderItem(
                    order_id=order.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    price=item.product.price
                )

                db.session.add(order_item)

            # =========================
            # SAVE PENDING ORDER
            # =========================

            db.session.commit()

            # =========================
            # OPEN PAYMENT PAGE
            # =========================

            return redirect(
                url_for(
                    "online_payment",
                    order_id=order.id
                )
            )

        # =========================
        # COD ORDER
        # =========================

        order = Order(
            customer_id=session.get("customer_id"),
            total_amount=total,
            status="Pending",
            payment_status=payment_status,
            payment_method=payment_method,
            shipping_name=shipping_name,
            shipping_phone=shipping_phone,
            shipping_address=shipping_address,
            city=city,
            state=state,
            pincode=pincode
        )

        db.session.add(order)

        db.session.flush()

        # =========================
        # CREATE ORDER ITEMS
        # + REDUCE STOCK
        # =========================

        for item in cart_items:

            order_item = OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                quantity=item.quantity,
                price=item.product.price
            )

            db.session.add(order_item)

            item.product.stock -= item.quantity

        # =========================
        # CLEAR CART
        # =========================

        for item in cart_items:

            db.session.delete(item)

        # =========================
        # SAVE ORDER
        # =========================

        db.session.commit()

        flash("Order Placed Successfully")

        return redirect(
            url_for(
                "order_confirmation",
                order_id=order.id
            )
        )

    # =========================
    # SHOW CHECKOUT PAGE
    # =========================

    return render_template(
        "checkout.html",
        cart_items=cart_items,
        total=total
    )


@app.route("/online-payment-demo", methods=["POST"])
@customer_required
def online_payment_demo():

    return render_template(
        "online_payment_demo.html"
    )

@app.route("/order-confirmation/<int:order_id>")
@customer_required
def order_confirmation(order_id):

    order = Order.query.get_or_404(order_id)

    if order.customer_id != session.get("customer_id"):
        return redirect(url_for("shop"))

    return render_template(
        "order_confirmation.html",
        order=order
    )

@app.route("/my-orders")
@customer_required
def my_orders():

    customer_id = session.get("customer_id")

    if not customer_id:
        return redirect(url_for("login"))

    orders = Order.query.filter_by(
        customer_id=customer_id
    ).order_by(
        Order.created_at.desc()
    ).all()

    return render_template(
        "my_orders.html",
        orders=orders
    )

@app.route("/my-orders/<int:order_id>")
@customer_required
def order_details(order_id):

    customer_id = session.get("customer_id")

    if not customer_id:
        return redirect(url_for("login"))

    order = Order.query.get_or_404(order_id)

    if order.customer_id != customer_id:
        flash("You are not authorized to view this order.")
        return redirect(url_for("my_orders"))

    return render_template(
        "order_details.html",
        order=order
    )

@app.route("/admin/orders/<int:order_id>")
@admin_required
def admin_order_details(order_id):

    # Only Admin can access this page
    if not isinstance(current_user, Admin):
        return redirect(url_for("home"))

    order = Order.query.get_or_404(order_id)

    return render_template(
        "admin_order_details.html",
        order=order
    )

@app.after_request
def add_no_cache_headers(response):

    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response

@app.route(
    "/admin/orders/<int:order_id>/update",
    methods=["POST"]
)
@admin_required
def admin_update_order(order_id):

    order = Order.query.get_or_404(order_id)

    details_url = url_for(
        "admin_order_details",
        order_id=order.id
    )

    old_status = order.status
    old_payment_status = order.payment_status

    new_status = request.form.get("status")
    new_payment_status = request.form.get("payment_status")

    # =========================
    # WHICH STATUS CAN MOVE TO WHICH
    # =========================

    order_flow = {
        "Pending": ["Pending", "Processing", "Cancelled"],
        "Processing": ["Processing", "Shipped", "Cancelled"],
        "Shipped": ["Shipped", "Delivered", "Cancelled"],
        "Delivered": ["Delivered"],
        "Cancelled": ["Cancelled"]
    }

    allowed_payment_statuses = [
        "Pending",
        "Paid",
        "Failed"
    ]

    # =========================
    # VALIDATE INPUT
    # =========================

    if new_status not in order_flow:

        flash("Invalid order status.")
        return redirect(details_url)

    if new_payment_status not in allowed_payment_statuses:

        flash("Invalid payment status.")
        return redirect(details_url)

    if new_status not in order_flow.get(old_status, [old_status]):

        flash(
            f"An order cannot move from "
            f"{old_status} to {new_status}."
        )
        return redirect(details_url)

    # =========================
    # PAYMENT STATUS RULES
    # =========================

    if (
        order.payment_method == "ONLINE"
        and new_payment_status != old_payment_status
    ):

        flash(
            "Online payment status is set automatically "
            "by Razorpay and cannot be changed here."
        )
        return redirect(details_url)

    if (
        old_status == "Cancelled"
        and new_payment_status != old_payment_status
    ):

        flash("A cancelled order cannot be changed.")
        return redirect(details_url)

    # =========================
    # WAS STOCK REDUCED FOR THIS ORDER?
    # COD: reduced when order was placed.
    # ONLINE: reduced only after payment.
    # =========================

    stock_held = (
        not order.stock_restored
        and (
            order.payment_method == "COD"
            or (
                order.payment_method == "ONLINE"
                and old_payment_status == "Paid"
            )
        )
    )

    cancelling = (
        new_status == "Cancelled"
        and old_status != "Cancelled"
    )

    # =========================
    # SAVE
    # =========================

    try:

        order.status = new_status
        order.payment_status = new_payment_status

        if cancelling and stock_held:

            for item in order.items:

                Product.query.filter(
                    Product.id == item.product_id
                ).update(
                    {"stock": Product.stock + item.quantity},
                    synchronize_session=False
                )

            order.stock_restored = True

        db.session.commit()

    except Exception:

        db.session.rollback()

        flash("Order could not be updated. Please try again.")
        return redirect(details_url)

    if (
        cancelling
        and order.payment_method == "ONLINE"
        and old_payment_status == "Paid"
    ):

        flash(
            "Order cancelled. The customer already paid online, "
            "so please refund the amount from the Razorpay dashboard."
        )

    else:

        flash("Order Updated Successfully")

    return redirect(details_url)

@app.route("/cart/increase/<int:id>", methods=["POST"])
@customer_required
def increase_quantity(id):

    item = Cart.query.get_or_404(id)

    customer_id = session.get("customer_id")

    # Make sure this cart item belongs to the logged-in customer
    if item.customer_id != customer_id:
        return redirect(url_for("cart"))

    item.quantity += 1

    db.session.commit()

    return redirect(url_for("cart"))


@app.route("/cart/decrease/<int:id>", methods=["POST"])
@customer_required
def decrease_quantity(id):

    item = Cart.query.get_or_404(id)

    customer_id = session.get("customer_id")

    # Make sure this cart item belongs to the logged-in customer
    if item.customer_id != customer_id:
        return redirect(url_for("cart"))

    if item.quantity > 1:
        item.quantity -= 1
        db.session.commit()

    return redirect(url_for("cart"))


@app.route("/cart/remove/<int:id>", methods=["POST"])
@customer_required
def remove_cart_item(id):

    item = Cart.query.get_or_404(id)

    customer_id = session.get("customer_id")

    # Make sure this cart item belongs to the logged-in customer
    if item.customer_id != customer_id:
        return redirect(url_for("cart"))

    db.session.delete(item)

    db.session.commit()

    flash("Item Removed")

    return redirect(url_for("cart"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if current_user.is_authenticated and isinstance(current_user, Admin):
        return redirect(url_for("admin_dashboard"))


    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        admin = Admin.query.filter_by(
            username=username
        ).first()

        if admin and admin.check_password(password):

            login_user(admin)

            return redirect(url_for("admin_dashboard"))

        flash("Invalid Username or Password")

    return render_template("admin/login.html")

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():

    total_orders = Order.query.count()

    pending_orders = Order.query.filter_by(
        status="Pending"
    ).count()

    total_products = Product.query.count()

    low_stock_products = Product.query.filter(
        Product.stock <= 5
    ).count()

    total_categories = Category.query.count()

    total_customers = Customer.query.count()

    recent_orders = Order.query.order_by(
        Order.created_at.desc()
    ).limit(5).all()

    return render_template(
        "admin/dashboard.html",
        total_orders=total_orders,
        pending_orders=pending_orders,
        total_products=total_products,
        low_stock_products=low_stock_products,
        total_categories=total_categories,
        total_customers=total_customers,
        recent_orders=recent_orders
    )

@app.route("/admin/inventory")
@admin_required
def admin_inventory():

    products = Product.query.order_by(
        Product.name.asc()
    ).all()

    return render_template(
        "admin_inventory.html",
        products=products
    )

@app.route("/admin/customers")
@admin_required
def admin_customers():

    customers = Customer.query.order_by(
        Customer.id.desc()
    ).all()

    return render_template(
        "admin_customers.html",
        customers=customers
    )


@app.route("/admin/orders")
@admin_required
def admin_orders():

    if not isinstance(current_user, Admin):
        return redirect(url_for("home"))

    status_filter = request.args.get("status")
    payment_filter = request.args.get("payment_status")

    query = Order.query

    # =========================
    # ORDER STATUS FILTER
    # =========================

    if status_filter in [
        "Pending",
        "Processing",
        "Shipped",
        "Delivered",
        "Cancelled"
    ]:

        query = query.filter(
            Order.status == status_filter
        )

    # =========================
    # PAYMENT STATUS FILTER
    # =========================

    if payment_filter in [
        "Pending",
        "Paid",
        "Failed"
    ]:

        query = query.filter(
            Order.payment_status == payment_filter
        )

    # =========================
    # LOAD ORDERS
    # =========================

    orders = query.order_by(
        Order.created_at.desc()
    ).all()

    return render_template(
        "admin_orders.html",
        orders=orders,
        status_filter=status_filter,
        payment_filter=payment_filter
    )

@app.route("/logout")
@admin_required
def logout():

    logout_user()

    return redirect(url_for("admin_login"))

def slugify(text):

    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()

    return text or "item"


def is_clean_slug(slug):

    return bool(
        slug
        and re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug)
    )


def unique_slug(name, exclude_id=None):

    base = slugify(name)
    slug = base
    counter = 2

    while Product.query.filter(
        Product.slug == slug,
        Product.id != (exclude_id or 0)
    ).first():

        slug = f"{base}-{counter}"
        counter += 1

    return slug


def unique_category_slug(name, exclude_id=None):

    base = slugify(name)
    slug = base
    counter = 2

    while Category.query.filter(
        Category.slug == slug,
        Category.id != (exclude_id or 0)
    ).first():

        slug = f"{base}-{counter}"
        counter += 1

    return slug


@app.cli.command("fix-slugs")
def fix_slugs():
    """Purane ganday slugs ko saaf URL me badalta hai."""

    def show(text):
        return str(text).encode("ascii", "backslashreplace").decode()

    changed = 0

    for category in Category.query.order_by(Category.id).all():

        if is_clean_slug(category.slug):
            continue

        new_slug = unique_category_slug(
            category.name,
            exclude_id=category.id
        )

        print(f"Category: {show(category.slug)}  ->  {new_slug}")

        category.slug = new_slug
        db.session.flush()
        changed += 1

    for product in Product.query.order_by(Product.id).all():

        if is_clean_slug(product.slug):
            continue

        new_slug = unique_slug(
            product.name,
            exclude_id=product.id
        )

        print(f"Product: {show(product.slug)}  ->  {new_slug}")

        product.slug = new_slug
        db.session.flush()
        changed += 1

    db.session.commit()

    print(f"Done. {changed} slug(s) updated.")

@app.route("/admin/products/add", methods=["GET", "POST"])
@admin_required
def add_product():

    categories = Category.query.all()

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = request.form.get("description")
        category_id = request.form.get("category")

        try:
            price = float(request.form.get("price"))
            stock = int(request.form.get("stock"))
        except (TypeError, ValueError):
            flash("Please enter a valid price and stock.")
            return redirect(url_for("add_product"))

        if not name or price <= 0 or stock < 0:
            flash(
                "Name is required, price must be above 0 "
                "and stock cannot be negative."
            )
            return redirect(url_for("add_product"))
        short_description = request.form.get("short_description")
        long_description = request.form.get("long_description")
        leather_type = request.form.get("leather_type")
        hardware = request.form.get("hardware")
        lining = request.form.get("lining")
        dimensions = request.form.get("dimensions")
        weight = request.form.get("weight")
        made_in = request.form.get("made_in")
        warranty = request.form.get("warranty")
        care = request.form.get("care")

        image = request.files.get("image")

        filename = ""

        if image and image.filename != "":
            filename = secure_filename(image.filename)

            image.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )

        product = Product(
            name=name,
            slug= unique_slug(name),
            description=description,
            short_description=short_description,
            long_description=long_description,
            leather_type=leather_type,
            hardware=hardware,
            lining=lining,
            dimensions=dimensions,
            weight=weight,
            made_in=made_in,
            warranty=warranty,
            care=care,
            is_bestseller=True if request.form.get("is_bestseller") else False,
            price=price,
            stock=stock,
            image=filename,
            category_id=category_id if category_id else None
    )

        db.session.add(product)
        db.session.commit()

        flash("Product Added Successfully")

        return redirect(url_for("products"))

    return render_template(
        "admin/add_product.html",
        categories=categories
    )


@app.route("/admin/products")
@admin_required
def products():

    products = Product.query.order_by(Product.id.desc()).all()

    return render_template(
        "admin/products.html",
        products=products
    )



@app.route("/admin/products/edit/<int:id>", methods=["GET", "POST"])
@admin_required
def edit_product(id):

    product = Product.query.get_or_404(id)

    categories = Category.query.all()

    if request.method == "POST":

        product.name = request.form.get("name")
        product.description = request.form.get("description")
        try:
            new_price = float(request.form.get("price"))
            new_stock = int(request.form.get("stock"))
        except (TypeError, ValueError):
            flash("Please enter a valid price and stock.")
            return redirect(url_for("products"))

        if new_price <= 0 or new_stock < 0:
            flash(
                "Price must be above 0 and stock cannot be negative."
            )
            return redirect(url_for("products"))

        product.price = new_price
        product.stock = new_stock
        product.short_description = request.form.get("short_description")
        product.long_description = request.form.get("long_description")
        product.leather_type = request.form.get("leather_type")
        product.hardware = request.form.get("hardware")
        product.lining = request.form.get("lining")
        product.dimensions = request.form.get("dimensions")
        product.weight = request.form.get("weight")
        product.made_in = request.form.get("made_in")
        product.warranty = request.form.get("warranty")
        product.care = request.form.get("care")
        product.is_bestseller = True if request.form.get("is_bestseller") else False

        category = request.form.get("category")
        image = request.files.get("image")

        if image and image.filename != "":

            

            filename = secure_filename(image.filename)
            image.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )
            product.image = filename

        product.category_id = category if category else None

        db.session.commit()


        flash("Product Updated Successfully")

        return redirect(url_for("products"))

    return render_template(
        "admin/edit_product.html",
        product=product,
        categories=categories
    )


@app.route("/admin/products/delete/<int:id>", methods=["POST"])
@admin_required
def delete_product(id):

    product = Product.query.get_or_404(id)

    # =========================
    # CHECK EXISTING ORDERS
    # =========================

    order_item = OrderItem.query.filter_by(
        product_id=product.id
    ).first()

    if order_item:
        flash(
            "This product cannot be deleted because it exists in an order."
        )

        return redirect(url_for("products"))

    # =========================
    # CHECK ACTIVE CARTS
    # =========================

    cart_item = Cart.query.filter_by(
        product_id=product.id
    ).first()

    if cart_item:
        flash(
            "This product cannot be deleted because it is in a customer cart."
        )

        return redirect(url_for("products"))

    # =========================
    # SAVE MAIN PRODUCT IMAGE
    # =========================

    main_image_path = None

    if product.image:

        main_image_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            product.image
        )

    # =========================
    # SAVE GALLERY IMAGE PATHS
    # =========================

    gallery_images = ProductImage.query.filter_by(
        product_id=product.id
    ).all()

    gallery_image_paths = []

    for gallery_image in gallery_images:

        if gallery_image.image:

            gallery_image_paths.append(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    gallery_image.image
                )
            )

    # =========================
    # DELETE GALLERY DATABASE RECORDS
    # =========================

    for gallery_image in gallery_images:

        db.session.delete(gallery_image)

    # =========================
    # DELETE PRODUCT
    # =========================

    db.session.delete(product)

    db.session.commit()

    # =========================
    # DELETE MAIN IMAGE FILE
    # =========================

    if (
        main_image_path
        and os.path.exists(main_image_path)
    ):
        os.remove(main_image_path)

    # =========================
    # DELETE GALLERY IMAGE FILES
    # =========================

    for image_path in gallery_image_paths:

        if os.path.exists(image_path):

            os.remove(image_path)

    flash("Product Deleted Successfully")

    return redirect(url_for("products"))

@app.route("/admin/products/archive/<int:id>", methods=["POST"])
@admin_required
def archive_product(id):

    product = Product.query.get_or_404(id)

    product.is_active = False

    db.session.commit()

    flash("Product Archived Successfully")

    return redirect(url_for("products"))


@app.route("/admin/products/unarchive/<int:id>", methods=["POST"])
@admin_required
def unarchive_product(id):

    product = Product.query.get_or_404(id)

    product.is_active = True

    db.session.commit()

    flash("Product Restored Successfully")

    return redirect(url_for("products"))

@app.route("/admin/products/<int:id>/gallery")
@admin_required
def product_gallery(id):

    product = Product.query.get_or_404(id)

    images = ProductImage.query.filter_by(
        product_id=id
    ).order_by(ProductImage.sort_order).all()

    return render_template(
        "admin/product_gallery.html",
        product=product,
        images=images
    )

@app.route(
    "/admin/products/<int:id>/gallery/add",
    methods=["POST"]
)
@admin_required
def add_product_gallery_image(id):

    product = Product.query.get_or_404(id)

    image = request.files.get("image")

    if not image or image.filename == "":
        flash("Please select an image.")

        return redirect(
            url_for(
                "product_gallery",
                id=product.id
            )
        )

    filename = secure_filename(image.filename)

    # Make filename unique
    filename = f"{uuid.uuid4().hex}_{filename}"

    image.save(
        os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename
        )
    )

    last_image = ProductImage.query.filter_by(
        product_id=product.id
    ).order_by(
        ProductImage.sort_order.desc()
    ).first()

    if last_image:
        next_sort_order = last_image.sort_order + 1
    else:
        next_sort_order = 0

    gallery_image = ProductImage(
        product_id=product.id,
        image=filename,
        sort_order=next_sort_order
    )

    db.session.add(gallery_image)
    db.session.commit()

    flash("Image Added To Gallery")

    return redirect(
        url_for(
            "product_gallery",
            id=product.id
        )
    )

@app.route(
    "/admin/products/gallery/image/<int:image_id>/delete",
    methods=["POST"]
)
@admin_required
def delete_product_gallery_image(image_id):

    gallery_image = ProductImage.query.get_or_404(
        image_id
    )

    product_id = gallery_image.product_id

    image_path = None

    if gallery_image.image:

        image_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            gallery_image.image
        )

    db.session.delete(gallery_image)
    db.session.commit()

    if image_path and os.path.exists(image_path):
        os.remove(image_path)

    flash("Gallery Image Deleted")

    return redirect(
        url_for(
            "product_gallery",
            id=product_id
        )
    )


@app.route("/admin/categories")
@admin_required
def categories():

    categories = Category.query.order_by(Category.id.desc()).all()

    return render_template(
        "admin/categories.html",
        categories=categories
    )


@app.route("/admin/categories/add", methods=["GET", "POST"])
@admin_required
def add_category():

    if request.method == "POST":

        name = request.form.get("name")

        category = Category(
            name=name,
            slug=unique_category_slug(name)
        )

        db.session.add(category)
        db.session.commit()

        flash("Category Added Successfully")

        return redirect(url_for("categories"))

    return render_template("admin/add_category.html")

@app.route("/admin/categories/edit/<int:id>", methods=["GET", "POST"])
@admin_required
def edit_category(id):

    category = Category.query.get_or_404(id)

    if request.method == "POST":

        category.name = request.form.get("name")
        category.slug = unique_category_slug(
            category.name,
            exclude_id=category.id
        )

        db.session.commit()

        flash("Category Updated Successfully")

        return redirect(url_for("categories"))

    return render_template(
        "admin/edit_category.html",
        category=category
    )

@app.route("/admin/categories/delete/<int:id>", methods=["POST"])
@admin_required
def delete_category(id):

    category = Category.query.get_or_404(id)

    product_count = Product.query.filter_by(
        category_id=category.id
    ).count()

    if product_count > 0:

        flash(
            f"This category has {product_count} product(s). "
            "Move or delete them first."
        )

        return redirect(url_for("categories"))

    db.session.delete(category)
    db.session.commit()

    flash("Category Deleted Successfully")

    return redirect(url_for("categories"))


# =========================
# FINALIZE A PAID ORDER
# =========================

def finalize_paid_order(
    order,
    razorpay_payment_id
):

    # =========================
    # CANCELLED ORDER
    # =========================

    if order.status == "Cancelled":

        return {
            "success": False,
            "message": "This order has been cancelled."
        }

    # =========================
    # ALREADY PAID
    # =========================

    if order.payment_status == "Paid":

        if order.razorpay_payment_id == razorpay_payment_id:

            return {
                "success": True,
                "message": "Payment already processed."
            }

        return {
            "success": False,
            "message":
                "Order has already been paid "
                "with another payment."
        }

    # =========================
    # PAYMENT ID BELONGS TO ANOTHER ORDER?
    # =========================

    other_order = Order.query.filter(
        Order.razorpay_payment_id == razorpay_payment_id,
        Order.id != order.id
    ).first()

    if other_order:

        return {
            "success": False,
            "message":
                "This payment ID belongs to another order."
        }

    # =========================
    # COPY ORDER DETAILS
    # =========================

    order_id = order.id
    customer_id = order.customer_id

    items = [
        (item.product_id, item.quantity)
        for item in order.items
    ]

    try:

        # =========================
        # CLAIM THE ORDER (ONLY ONE PROCESS WINS)
        # =========================

        claimed = Order.query.filter(
            Order.id == order_id,
            Order.payment_status != "Paid",
            Order.status != "Cancelled"
        ).update(
            {
                "payment_status": "Paid",
                "razorpay_payment_id": razorpay_payment_id,
                "stock_restored": False
            },
            synchronize_session=False
        )

        if claimed == 0:

            db.session.rollback()

            fresh_order = db.session.get(Order, order_id)

            if (
                fresh_order
                and fresh_order.payment_status == "Paid"
                and fresh_order.razorpay_payment_id
                    == razorpay_payment_id
            ):

                return {
                    "success": True,
                    "message": "Payment already processed."
                }

            return {
                "success": False,
                "message": "Order could not be processed."
            }

        # =========================
        # REDUCE STOCK SAFELY (NO OVERSELL)
        # =========================

        for product_id, quantity in items:

            updated = Product.query.filter(
                Product.id == product_id,
                Product.stock >= quantity
            ).update(
                {"stock": Product.stock - quantity},
                synchronize_session=False
            )

            if updated == 0:

                db.session.rollback()

                product = db.session.get(Product, product_id)

                product_name = (
                    product.name if product
                    else "a product"
                )

                return {
                    "success": False,
                    "message":
                        f"Not enough stock for {product_name}."
                }

        # =========================
        # REMOVE ORDERED PRODUCTS FROM CART
        # =========================

        product_ids = [
            product_id for product_id, quantity in items
        ]

        Cart.query.filter(
            Cart.customer_id == customer_id,
            Cart.product_id.in_(product_ids)
        ).delete(synchronize_session=False)

        # =========================
        # SAVE EVERYTHING TOGETHER
        # =========================

        db.session.commit()

    except Exception:

        db.session.rollback()

        return {
            "success": False,
            "message": "Payment update failed."
        }

    return {
        "success": True,
        "message": "Payment processed successfully."
    }


# =========================
# VERIFY RAZORPAY PAYMENT
# =========================

@app.route(
    "/verify-razorpay-payment",
    methods=["POST"]
)
@customer_required
def verify_razorpay_payment():

    data = request.get_json()

    razorpay_payment_id = data.get(
        "razorpay_payment_id"
    )

    razorpay_order_id = data.get(
        "razorpay_order_id"
    )

    razorpay_signature = data.get(
        "razorpay_signature"
    )


    # =========================
    # CHECK REQUIRED DETAILS
    # =========================

    if not all([
        razorpay_payment_id,
        razorpay_order_id,
        razorpay_signature
    ]):

        return {
            "success": False,
            "message":
                "Missing payment details."
        }, 400


    # =========================
    # FIND OUR ORDER
    # =========================

    order = Order.query.filter_by(
        razorpay_order_id=razorpay_order_id
    ).first()


    if not order:

        return {
            "success": False,
            "message":
                "Order not found."
        }, 404


    # =========================
    # CHECK CUSTOMER OWNERSHIP
    # =========================

    if order.customer_id != session.get(
        "customer_id"
    ):

        return {
            "success": False,
            "message":
                "Unauthorized order."
        }, 403


    # =========================
    # VERIFY RAZORPAY SIGNATURE
    # =========================

    try:

        razorpay_client.utility.verify_payment_signature(
            {
                "razorpay_order_id":
                    order.razorpay_order_id,

                "razorpay_payment_id":
                    razorpay_payment_id,

                "razorpay_signature":
                    razorpay_signature
            }
        )

    except Exception:

        return {
            "success": False,
            "message":
                "Payment verification failed."
        }, 400


    # =========================
    # FINALIZE PAYMENT
    # =========================

    result = finalize_paid_order(
        order,
        razorpay_payment_id
    )


    if not result["success"]:

        return result, 400


    return {
        "success": True,
        "message":
            result["message"]
    }

@app.route("/online-payment/<int:order_id>", methods=["GET"])
@customer_required
def online_payment(order_id):

    order = Order.query.get_or_404(order_id)

    if order.customer_id != session.get("customer_id"):
        flash("Unauthorized order.")
        return redirect(url_for("my_orders"))

    return render_template(
        "online_payment.html",
        total=order.total_amount,
        payment_method="ONLINE",
        order_id=order.id,
        razorpay_order_id=order.razorpay_order_id,
        razorpay_key_id=RAZORPAY_KEY_ID
    )



@app.route(
    "/retry-payment/<int:order_id>",
    methods=["GET"]
)
@customer_required
def retry_payment(order_id):

    # FIND ORDER
    order = Order.query.get_or_404(order_id)

    # CHECK CUSTOMER OWNERSHIP
    if order.customer_id != session.get(
        "customer_id"
    ):
        flash("Unauthorized order.")
        return redirect(url_for("my_orders"))

    # =========================
    # ALREADY PAID
    # =========================

    if order.payment_status == "Paid":

        flash("This order has already been paid.")
        return redirect(
                url_for(
                "order_confirmation",
                order_id=order.id
        )
    )


    # =========================
    # CANCELLED ORDER
    # =========================

    if order.status == "Cancelled":

        flash(
            "This order has been cancelled "
            "and payment cannot be completed."
    )

        return redirect(
            url_for(
            "my_orders"
        )
    )


    # =========================
    # ONLY ONLINE ORDERS
    # CAN BE RETRIED
    # =========================

    if order.payment_method != "ONLINE":

        flash("This order does not use online payment.")

        return redirect(
            url_for(
            "my_orders"
            )
        )
    # CREATE A NEW RAZORPAY ORDER
    # FOR THE SAME LOCAL ORDER
    # (2 attempts: stale connection ho to dusra attempt naye connection par chalega)

    razorpay_order = None

    for attempt in range(2):

        try:

            razorpay_order = razorpay_client.order.create(
                {
                    "amount": int(
                        round(order.total_amount * 100 )
                    ),
                    "currency": "INR",
                    "receipt": f"fh_order_{order.id}_retry"
                }
            )

            break

        except Exception as e:

            print("RAZORPAY RETRY ERROR:", repr(e))

    if not razorpay_order:

        flash(
            "Didn't connect to Payment Gateway. "
            "Please Try Again."
        )

        return redirect(
            url_for(
                "my_orders"
            )
        )

    # UPDATE RAZORPAY ORDER ID
    order.razorpay_order_id = (
        razorpay_order["id"]
    )

    # RESET PAYMENT STATUS
    order.payment_status = "Pending"

    db.session.commit()

    # OPEN PAYMENT PAGE AGAIN
    return render_template(
        "online_payment.html",
        total=order.total_amount,
        payment_method="ONLINE",
        order_id=order.id,
        razorpay_order_id=razorpay_order["id"],
        razorpay_key_id=RAZORPAY_KEY_ID
    )

@app.route(
    "/razorpay-webhook",
    methods=["POST"]
)
@csrf.exempt
def razorpay_webhook():

    # =========================
    # RECEIVE WEBHOOK
    # =========================

    payload = request.get_data()

    webhook_signature = request.headers.get(
        "X-Razorpay-Signature"
    )

    if not webhook_signature:

        return {
            "success": False,
            "message": "Missing webhook signature."
        }, 400


    # =========================
    # CHECK WEBHOOK SECRET
    # =========================

    if not RAZORPAY_WEBHOOK_SECRET:

        return {
            "success": False,
            "message": "Webhook secret is not configured."
        }, 500


    # =========================
    # GENERATE EXPECTED SIGNATURE
    # =========================

    expected_signature = hmac.new(
        RAZORPAY_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()


    # =========================
    # VERIFY SIGNATURE
    # =========================

    if not hmac.compare_digest(
        expected_signature,
        webhook_signature
    ):

        return {
            "success": False,
            "message": "Invalid webhook signature."
        }, 400


    # =========================
    # PARSE WEBHOOK PAYLOAD
    # =========================

    try:

        webhook_data = request.get_json()

    except Exception:

        return {
            "success": False,
            "message": "Invalid webhook payload."
        }, 400


    if not webhook_data:

        return {
            "success": False,
            "message": "Empty webhook payload."
        }, 400


        # =========================
    # IDENTIFY EVENT
    # =========================

    event = webhook_data.get(
        "event"
    )


    # =========================
    # EXTRACT PAYMENT DATA
    # =========================

    payment_entity = (
        webhook_data
        .get("payload", {})
        .get("payment", {})
        .get("entity", {})
    )

    razorpay_payment_id = payment_entity.get(
        "id"
    )

    razorpay_order_id = payment_entity.get(
        "order_id"
    )


    # =========================
    # HANDLE PAYMENT EVENT
    # =========================
    if event == "payment.captured":

        if not razorpay_payment_id:

            return {
                "success": False,
                "message":
                    "Payment ID missing from webhook."
            }, 400


        if not razorpay_order_id:

            return {
                "success": False,
                "message":
                    "Razorpay order ID missing from webhook."
            }, 400


        # =========================
        # FIND LOCAL ORDER
        # =========================

        order = Order.query.filter_by(
            razorpay_order_id=razorpay_order_id
        ).first()


        if not order:

            return {
                "success": False,
                "message":
                    "Local order not found."
            }, 404


        # =========================
        # FINALIZE PAYMENT
        # =========================

        result = finalize_paid_order(
            order,
            razorpay_payment_id
        )


        if not result["success"]:

            return result, 400


        return {
            "success": True,
            "message":
                result["message"],
            "event": event,
            "razorpay_payment_id":
                razorpay_payment_id,
            "razorpay_order_id":
                razorpay_order_id
        }, 200

    # =========================
    # OTHER WEBHOOK EVENTS
    # =========================

    return {
        "success": True,
        "message":
            "Webhook received.",
        "event": event
    }, 200

# =========================
# BUSINESS DETAILS
# (apna asli data yahan likho, baaki pages khud badal jayenge)
# =========================

BUSINESS = {
    "name": "Forge & Hide",
    "legal_name": "R.S. Leather Work",
    "address": "7, Ground floor, Block no 7, Transit camp, Mahatama gandhi road, Road no 2, Rajiv Gandhi Nagar, Dharavi, Mumbai, Maharashtra 400017 India",
    "phone": "+91 89283 52221",
    "email": "ansarisahil987654@gmail.com",
    "production_time": "4 to 8 weeks",
    "delivery_time": "5 to 8 business days",
    "return_window": "7 days",
}


def build_info_pages():

    n = BUSINESS["name"].replace("&", "&amp;")
    legal = BUSINESS["legal_name"]
    address = BUSINESS["address"]
    phone = BUSINESS["phone"]
    email = BUSINESS["email"]
    prod = BUSINESS["production_time"]
    deliv = BUSINESS["delivery_time"]
    window = BUSINESS["return_window"]

    return {

        "about": ("About Us", f"""
<p>{n} is a handcrafted leather brand by {legal}. Every bag, trolley and jacket
is made by experienced artisans in India using carefully selected premium
leather and quality hardware.</p>
<p>We do not chase trends. We build leather goods that age beautifully and
last for years.</p>
<p>Many of our pieces are made to order, so your product is built specifically
for you. For custom requests, write to us at {email}.</p>
"""),

        "contact": ("Contact Us", f"""
<p>We are happy to help with orders, custom requests and product questions.</p>
<p><strong>Business:</strong> {legal}</p>
<p><strong>Address:</strong> {address}</p>
<p><strong>Phone:</strong> {phone}</p>
<p><strong>Email:</strong> {email}</p>
<p>We usually reply within 1 to 2 business days.</p>
"""),

        "privacy-policy": ("Privacy Policy", f"""
<p>{n} respects your privacy. This page explains what information we collect
and how we use it.</p>
<h2>Information we collect</h2>
<p>When you create an account or place an order, we collect your name, email
address, phone number, shipping address and order details.</p>
<h2>How we use it</h2>
<p>We use this information only to process and deliver your orders, send order
updates, provide support and improve our store.</p>
<h2>Payments</h2>
<p>Online payments are processed securely by Razorpay. We do not store your
card, UPI or net banking details on our servers.</p>
<h2>Cookies</h2>
<p>We use a session cookie to keep you logged in and to remember your cart.</p>
<h2>Sharing</h2>
<p>We do not sell your personal information. We share it only with payment
and delivery partners as needed to complete your order.</p>
<h2>Your choices</h2>
<p>To view, correct or delete your information, write to us at {email}.</p>
"""),

        "terms-and-conditions": ("Terms and Conditions", f"""
<p>By using this website and placing an order with {n}, you agree to these
terms.</p>
<h2>Products and pricing</h2>
<p>All prices are in Indian Rupees (INR). Leather is a natural material, so
colour, grain and finish may vary slightly from the photos.</p>
<h2>Orders</h2>
<p>An order is confirmed once it is placed successfully. For online payments,
the order is confirmed after payment is received. We may cancel an order if a
product cannot be made or delivered, and any amount paid will be refunded.</p>
<h2>Made-to-order items</h2>
<p>Many products are made to order and take around {prod} to prepare before
shipping.</p>
<h2>Payments</h2>
<p>We accept Cash on Delivery and online payments through Razorpay.</p>
<h2>Liability</h2>
<p>Our liability for any order is limited to the amount paid for that order.</p>
<h2>Contact</h2>
<p>Questions about these terms: {email}.</p>
"""),

        "refund-policy": ("Refund and Cancellation Policy", f"""
<h2>Cancellation</h2>
<p>You can cancel an order before we start making it. Write to us at {email}
or call {phone} with your order number.</p>
<h2>Made-to-order and customised items</h2>
<p>Customised products are made specially for you and cannot be returned or
exchanged unless they arrive damaged or defective.</p>
<h2>Damaged or defective items</h2>
<p>If your item arrives damaged or defective, tell us within {window} of
delivery with your order number and clear photos (please also keep the unboxing
video if you have one). We will repair, replace or refund it after checking.</p>
<h2>Refunds</h2>
<p>Approved refunds are returned to the original payment method within 5 to 7
business days. For Cash on Delivery orders, we refund by bank transfer.</p>
"""),

        "shipping-policy": ("Shipping Policy", f"""
<h2>Where we ship</h2>
<p>We currently ship across India. For international orders, please contact
us at {email}.</p>
<h2>Processing time</h2>
<p>Made-to-order products take around {prod} to prepare. You will be informed
when your order is shipped.</p>
<h2>Delivery time</h2>
<p>After shipping, delivery usually takes {deliv}.</p>
<h2>Shipping charges</h2>
<p>Shipping is currently free within India.</p>
<h2>Questions</h2>
<p>For help with your delivery, write to {email} or call {phone}.</p>
"""),
    }


INFO_PAGES = build_info_pages()


def make_info_view(slug):

    def view():

        title, content = INFO_PAGES[slug]

        return render_template(
            "info_page.html",
            title=title,
            content=content
        )

    return view


for _slug in INFO_PAGES:

    app.add_url_rule(
        "/" + _slug,
        endpoint="info_" + _slug.replace("-", "_"),
        view_func=make_info_view(_slug)
    )
@app.errorhandler(CSRFError)
def csrf_error(error):

    return render_template(
        "error.html",
        code=400,
        title="Session Expired",
        message="Your session expired. Please go back, refresh the page and try again."
    ), 400


@app.errorhandler(403)
def forbidden_error(error):

    return render_template(
        "error.html",
        code=403,
        title="Access Denied",
        message="You do not have permission to open this page."
    ), 403


@app.errorhandler(404)
def not_found_error(error):

    return render_template(
        "error.html",
        code=404,
        title="Page Not Found",
        message="The page you are looking for does not exist."
    ), 404


@app.errorhandler(500)
def server_error(error):

    db.session.rollback()

    return render_template(
        "error.html",
        code=500,
        title="Something Went Wrong",
        message="Please try again in a moment."
    ), 500


@app.route(
    "/my-orders/<int:order_id>/cancel",
    methods=["POST"]
)
@customer_required
def cancel_order(order_id):

    order = Order.query.get_or_404(order_id)

    if order.customer_id != session.get("customer_id"):

        flash("You are not authorized to cancel this order.")

        return redirect(url_for("my_orders"))

    order_pk = order.id
    payment_method = order.payment_method

    items = [
        (item.product_id, item.quantity)
        for item in order.items
    ]

    try:

        cancelled = Order.query.filter(
            Order.id == order_pk,
            Order.status == "Pending",
            Order.payment_status != "Paid"
        ).update(
            {"status": "Cancelled"},
            synchronize_session=False
        )

        if cancelled == 0:

            db.session.rollback()

            flash(
                "This order can no longer be cancelled online. "
                "Please contact us."
            )

            return redirect(
                url_for("order_details", order_id=order_pk)
            )

        if payment_method == "COD":

            for product_id, quantity in items:

                Product.query.filter(
                    Product.id == product_id
                ).update(
                    {"stock": Product.stock + quantity},
                    synchronize_session=False
                )

            Order.query.filter(
                Order.id == order_pk
            ).update(
                {"stock_restored": True},
                synchronize_session=False
            )

        db.session.commit()

    except Exception:

        db.session.rollback()

        flash("Could not cancel the order. Please try again.")

        return redirect(
            url_for("order_details", order_id=order_pk)
        )

    flash("Your order has been cancelled.")

    return redirect(
        url_for("order_details", order_id=order_pk)
    )
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)