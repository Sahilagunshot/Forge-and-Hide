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
    Customer
)

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.login_view = "admin_login"
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))


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

    products = Product.query.order_by(
        Product.id.desc()
    ).all()

    return render_template(
        "shop.html",
        products=products
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


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if current_user.is_authenticated:
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        admin = Admin.query.filter_by(username=username).first()

        if admin and admin.check_password(password):

            login_user(admin)

            return redirect(url_for("admin_dashboard"))

        flash("Invalid Username or Password")

    return render_template("admin/login.html")


@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    return render_template("admin/dashboard.html")


@app.route("/logout")
@login_required
def logout():

    logout_user()

    return redirect(url_for("admin_login"))


@app.route("/admin/products/add", methods=["GET", "POST"])
@login_required
def add_product():

    categories = Category.query.all()

    if request.method == "POST":

        name = request.form.get("name")
        description = request.form.get("description")
        price = float(request.form.get("price"))
        stock = int(request.form.get("stock"))
        category_id = request.form.get("category")

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
@login_required
def products():

    products = Product.query.order_by(Product.id.desc()).all()

    return render_template(
        "admin/products.html",
        products=products
    )


@app.route("/admin/products/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_product(id):

    product = Product.query.get_or_404(id)

    categories = Category.query.all()

    if request.method == "POST":

        product.name = request.form.get("name")
        product.description = request.form.get("description")
        product.price = float(request.form.get("price"))
        product.stock = int(request.form.get("stock"))

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
@login_required
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
@login_required
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
@login_required
def categories():

    categories = Category.query.order_by(Category.id.desc()).all()

    return render_template(
        "admin/categories.html",
        categories=categories
    )


@app.route("/admin/categories/add", methods=["GET", "POST"])
@login_required
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
@login_required
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
@login_required
def delete_category(id):

    category = Category.query.get_or_404(id)

    db.session.delete(category)
    db.session.commit()

    flash("Category Deleted Successfully")

    return redirect(url_for("categories"))
if __name__ == "__main__":
    app.run(debug=True)