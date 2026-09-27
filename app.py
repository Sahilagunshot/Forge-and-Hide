from flask import Flask, render_template, redirect, url_for, request, flash, session
from werkzeug.utils import secure_filename
import uuid
import os
import hmac
import hashlib
import razorpay
from dotenv import load_dotenv
from flask_migrate import Migrate
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
load_dotenv()

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

login_manager = LoginManager()
login_manager.login_view = "admin_login"
login_manager.init_app(app)
from functools import wraps



def admin_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):
        print(
    "ADMIN CHECK:",
    current_user.is_authenticated,
    type(current_user).__name__,
    session.get("customer_id")
)

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
        "cart_count": cart_count
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

    return render_template(
    "index.html",
    featured_products=featured_products,
    latest_products=latest_products,
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

    print(
        "CURRENT CUSTOMER IN CART:",
        customer_id
    )

    print(
        "CART ITEMS LOADED:",
        cart_items
    )

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
                        "amount": int(round(total * 100)),
                        "currency": "INR",
                        "receipt": f"fh_order_{order.id}"
                    }
                )

            except Exception:

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

    old_status = order.status
    old_payment_status = order.payment_status

    status = request.form.get("status")
    payment_status = request.form.get("payment_status")

    allowed_statuses = [
        "Pending",
        "Processing",
        "Shipped",
        "Delivered",
        "Cancelled"
    ]

    allowed_payment_statuses = [
        "Pending",
        "Paid",
        "Failed"
    ]

    # =========================
    # VALIDATE INPUT
    # =========================

    if status not in allowed_statuses:
        flash("Invalid order status.")
        return redirect(
            url_for(
                "admin_order_details",
                order_id=order.id
            )
        )

    if payment_status not in allowed_payment_statuses:
        flash("Invalid payment status.")
        return redirect(
            url_for(
                "admin_order_details",
                order_id=order.id
            )
        )

    # =========================
    # UPDATE ORDER STATUS
    # =========================

    order.status = status
    order.payment_status = payment_status

    # =========================
    # DETERMINE STOCK ACTION
    # =========================

    restore_stock = (
        (
            status == "Cancelled"
            and old_status != "Cancelled"
        )
        or
        (
            payment_status == "Failed"
            and old_payment_status != "Failed"
        )
    )

    restore_was_reversed = (
        order.stock_restored
        and status != "Cancelled"
        and payment_status != "Failed"
    )

    # =========================
    # RESTORE STOCK
    # =========================

    if restore_stock and not order.stock_restored:

        for item in order.items:

            if item.product:

                item.product.stock += item.quantity

        order.stock_restored = True

    # =========================
    # RE-DEDUCT STOCK
    # =========================

    elif restore_was_reversed:

        # Check stock for ALL items first

        stock_available = True

        for item in order.items:

            if item.product:

                if item.product.stock < item.quantity:

                    stock_available = False
                    break

        if not stock_available:

            db.session.rollback()

            flash(
                "Order status changed back, "
                "but there is not enough stock to restore "
                "this order."
            )

            return redirect(
                url_for(
                    "admin_order_details",
                    order_id=order.id
                )
            )

        # Deduct stock only after ALL items pass

        for item in order.items:

            if item.product:

                item.product.stock -= item.quantity

        order.stock_restored = False

    # =========================
    # SAVE
    # =========================

    db.session.commit()

    flash("Order Updated Successfully")

    return redirect(
        url_for(
            "admin_order_details",
            order_id=order.id
        )
    )

@app.route("/cart/increase/<int:id>")
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


@app.route("/cart/decrease/<int:id>")
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


@app.route("/cart/remove/<int:id>")
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


@app.route("/admin/products/add", methods=["GET", "POST"])
@admin_required
def add_product():

    categories = Category.query.all()

    if request.method == "POST":

        name = request.form.get("name")
        description = request.form.get("description")
        price = float(request.form.get("price"))
        stock = int(request.form.get("stock"))
        category_id = request.form.get("category")
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
            slug=name.lower().replace(" ", "-"),
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
        product.price = float(request.form.get("price"))
        product.stock = int(request.form.get("stock"))
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


@app.route("/admin/products/delete/<int:id>")
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

@app.route("/admin/products/archive/<int:id>")
@admin_required
def archive_product(id):

    product = Product.query.get_or_404(id)

    product.is_active = False

    db.session.commit()

    flash("Product Archived Successfully")

    return redirect(url_for("products"))


@app.route("/admin/products/unarchive/<int:id>")
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
            slug=name.lower().replace(" ", "-")
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
        category.slug = category.name.lower().replace(" ", "-")

        db.session.commit()

        flash("Category Updated Successfully")

        return redirect(url_for("categories"))

    return render_template(
        "admin/edit_category.html",
        category=category
    )


@app.route("/admin/categories/delete/<int:id>")
@admin_required
def delete_category(id):

    category = Category.query.get_or_404(id)

    db.session.delete(category)
    db.session.commit()

    flash("Category Deleted Successfully")

    return redirect(url_for("categories"))

@app.route("/razorpay-test-order")
@customer_required
def razorpay_test_order():

    amount = 100

    razorpay_order = razorpay_client.order.create(
        {
            "amount": amount,
            "currency": "INR",
            "payment_capture": 1
        }
    )

    return {
        "success": True,
        "razorpay_order_id": razorpay_order["id"],
        "amount": razorpay_order["amount"],
        "currency": razorpay_order["currency"]
    }




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

    # CHECK REQUIRED PAYMENT DETAILS
    if not all([
        razorpay_payment_id,
        razorpay_order_id,
        razorpay_signature
    ]):

        return {
            "success": False,
            "message": "Missing payment details."
        }, 400

    # FIND OUR ORDER
    order = Order.query.filter_by(
        razorpay_order_id=razorpay_order_id
    ).first()

    if not order:

        return {
            "success": False,
            "message": "Order not found."
        }, 404

    # =========================
    # CHECK CUSTOMER OWNERSHIP
    # =========================

    if order.customer_id != session.get(
        "customer_id"
    ):

        return {
            "success": False,
            "message": "Unauthorized order."
        }, 403


    # =========================
    # CHECK ORDER STATUS
    # =========================

    if order.status == "Cancelled":

        return {
            "success": False,
            "message": "This order has been cancelled."
        }, 400


    # =========================
    # DUPLICATE VERIFICATION
    # =========================

    if order.payment_status == "Paid":

        if order.razorpay_payment_id == razorpay_payment_id:

            return {
                "success": True
            }

        return {
            "success": False,
            "message": "Order has already been paid."
        }, 400

    # CHECK WHETHER THIS PAYMENT ID
    # WAS ALREADY USED FOR ANOTHER ORDER
    existing_payment = Order.query.filter_by(
        razorpay_payment_id=razorpay_payment_id
    ).first()

    if existing_payment:

        return {
            "success": False,
            "message": "Payment has already been used."
        }, 400

    # VERIFY RAZORPAY SIGNATURE
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
            "message": "Payment verification failed."
        }, 400

    # FINAL STOCK CHECK
    for item in order.items:

        product = Product.query.get(
            item.product_id
        )

        if not product:

            return {
                "success": False,
                "message": "Product no longer exists."
            }, 400

        if product.stock < item.quantity:

            return {
                "success": False,
                "message":
                    f"Not enough stock for {product.name}."
            }, 400

    # REDUCE STOCK
    for item in order.items:

        product = Product.query.get(
            item.product_id
        )

        product.stock -= item.quantity

    # =========================
    # CLEAR ONLY ITEMS
    # BELONGING TO THIS ORDER
    # =========================

    ordered_product_ids = {
        item.product_id
        for item in order.items
    }

    cart_items = Cart.query.filter(
        Cart.customer_id == session.get("customer_id"),
        Cart.product_id.in_(ordered_product_ids)
    ).all()

    for cart_item in cart_items:

        db.session.delete(cart_item)

    # SAVE PAYMENT INFORMATION
    order.razorpay_payment_id = (
        razorpay_payment_id
    )

    order.payment_status = "Paid"

    db.session.commit()

    return {
        "success": True
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
    razorpay_order = razorpay_client.order.create(
        {
            "amount": int(
                round(order.total_amount * 100)
            ),
            "currency": "INR",
            "receipt": f"fh_order_{order.id}_retry"
        }
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
    # WEBHOOK VERIFIED
    # =========================

    return {
        "success": True,
        "message": "Webhook verified."
    }, 200
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)