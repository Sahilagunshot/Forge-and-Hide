from flask import Flask, render_template, redirect, url_for, request, flash, session
from werkzeug.utils import secure_filename
import uuid
import os
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

db.init_app(app)

migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.login_view = "admin_login"
login_manager.init_app(app)
from functools import wraps


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

@app.context_processor
def inject_cart_count():

    cart_count = 0

    if current_user.is_authenticated:

        cart_items = Cart.query.filter_by(
            customer_id=current_user.id
        ).all()

        for item in cart_items:
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
        is_featured=True
    ).limit(8).all()

    latest_products = Product.query.order_by(
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
                category_id=category.id
            ).order_by(
                Product.id.desc()
            ).all()
        else:
            products = []
    else:
        products = Product.query.order_by(
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
        slug=slug
    ).first_or_404()

    return render_template(
        "product_detail.html",
        product=product
    )

@app.route("/add-to-cart/<int:product_id>")
@login_required
def add_to_cart(product_id):

    product = Product.query.get_or_404(product_id)

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
        customer_id=current_user.id,
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
            customer_id=current_user.id,
            product_id=product_id,
            quantity=1
        )

        db.session.add(cart)


    db.session.commit()

    flash("Product Added To Cart")

    return redirect(url_for("cart"))


@app.route("/cart")
@login_required
def cart():

    cart_items = Cart.query.filter_by(
        customer_id=current_user.id
    ).all()
    print("CURRENT USER IN CART:", current_user.id)
    print("CART ITEMS LOADED:", cart_items)

    total = 0

    for item in cart_items:
        total += item.product.price * item.quantity

    return render_template(
        "cart.html",
        cart_items=cart_items,
        total=total
    )

@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():

    cart_items = Cart.query.filter_by(
        customer_id=current_user.id
    ).all()

    if not cart_items:
        flash("Your cart is empty")
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

        # =========================
        # CREATE ORDER
        # =========================

        order = Order(
            customer_id=current_user.id,
            total_amount=total,
            status="Pending",
            payment_status="Pending",
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

@app.route("/order-confirmation/<int:order_id>")
@login_required
def order_confirmation(order_id):

    order = Order.query.get_or_404(order_id)

    if order.customer_id != current_user.id:
        return redirect(url_for("shop"))

    return render_template(
        "order_confirmation.html",
        order=order
    )

@app.route("/my-orders")
@login_required
def my_orders():

    orders = Order.query.filter_by(
        customer_id=current_user.id
    ).order_by(
        Order.created_at.desc()
    ).all()

    return render_template(
        "my_orders.html",
        orders=orders
    )

@app.route("/my-orders/<int:order_id>")
@login_required
def order_details(order_id):

    order = Order.query.get_or_404(order_id)

    if order.customer_id != current_user.id:
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
    # UPDATE ORDER STATUS
    # =========================

    if status in allowed_statuses:
        order.status = status

    if payment_status in allowed_payment_statuses:
        order.payment_status = payment_status

    # =========================
    # RESTORE STOCK
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

    if restore_stock and not order.stock_restored:

        for item in order.items:

            if item.product:
                item.product.stock += item.quantity

        order.stock_restored = True

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
@login_required
def increase_quantity(id):

    item = Cart.query.get_or_404(id)

    if item.customer_id != current_user.id:
        return redirect(url_for("cart"))

    item.quantity += 1

    db.session.commit()

    return redirect(url_for("cart"))

@app.route("/cart/decrease/<int:id>")
@login_required
def decrease_quantity(id):

    item = Cart.query.get_or_404(id)

    if item.customer_id != current_user.id:
        return redirect(url_for("cart"))

    if item.quantity > 1:
        item.quantity -= 1
        db.session.commit()

    return redirect(url_for("cart"))

@app.route("/cart/remove/<int:id>")
@login_required
def remove_cart_item(id):

    item = Cart.query.get_or_404(id)

    if item.customer_id != current_user.id:
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

@app.route("/admin/orders")
@admin_required
def admin_orders():

    if not isinstance(current_user, Admin):
        return redirect(url_for("home"))

    orders = Order.query.order_by(
        Order.created_at.desc()
    ).all()

    return render_template(
        "admin_orders.html",
        orders=orders
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

    if product.image:

        image_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            product.image
        )

        if os.path.exists(image_path):
            os.remove(image_path)

    db.session.delete(product)
    db.session.commit()

    flash("Product Deleted Successfully")

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
if __name__ == "__main__":
    app.run(debug=True)