from werkzeug.utils import secure_filename
import os
import requests
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from datetime import datetime, timedelta
import pytz
# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Configure database path to be inside your project folder
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'services.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
CATEGORY_UPLOAD_FOLDER = os.path.join(basedir, 'static', 'categories')
app.config['CATEGORY_UPLOAD_FOLDER'] = CATEGORY_UPLOAD_FOLDER

os.makedirs(app.config['CATEGORY_UPLOAD_FOLDER'], exist_ok=True)

# Image upload configuration
UPLOAD_FOLDER = os.path.join(basedir, 'static', 'services')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize database
db = SQLAlchemy(app)

# Database Models
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    image_filename = db.Column(db.String(100), nullable=True)
    subcategories = db.relationship('Subcategory', backref='category', lazy=True, cascade="all, delete-orphan")

class Subcategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    services = db.relationship('Service', backref='subcategory', lazy=True, cascade="all, delete-orphan")

# In your app.py, modify the Service model and initialization code:
# Add new Variant model
class Variant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # e.g. "30g", "100g"
    price = db.Column(db.Integer, nullable=False)
    unit = db.Column(db.String(50), nullable=False, default="per service")  # Add this line
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=False)
    available = db.Column(db.Boolean, default=True)

# Modify Service model (remove price and unit fields)
class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    available = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text, nullable=True)
    subcategory_id = db.Column(db.Integer, db.ForeignKey('subcategory.id'), nullable=False)
    image_filename = db.Column(db.String(100), nullable=True)
    variants = db.relationship('Variant', backref='service', lazy=True, cascade="all, delete-orphan")

class ShopStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    is_open = db.Column(db.Boolean, default=True)
    message = db.Column(db.String(200), default="We're currently closed. Please come back during our business hours.")
# Then in your initialization code
with app.app_context():
    db.create_all()

    # Initialize shop status if not exists
    if not ShopStatus.query.first():
        db.session.add(ShopStatus(is_open=True))
        db.session.commit()

    if not Category.query.first():
        # Create test categories
        categories = [
            Category(name="Cleaning Services", image_filename="clean.jpg"),
            Category(name="Repair Services", image_filename="repair.jpg"),
            Category(name="Beauty Services", image_filename="beauty.jpg")
        ]
        db.session.add_all(categories)

        # Create test subcategories
        subcategories = [
            Subcategory(name="Home Cleaning", category=categories[0]),
            Subcategory(name="Office Cleaning", category=categories[0]),
            Subcategory(name="Appliance Repair", category=categories[1]),
            Subcategory(name="Salon Services", category=categories[2])
        ]
        db.session.add_all(subcategories)

        # Create test services
        services = [
            Service(name="Basic Cleaning", description="Basic cleaning includes dusting, vacuuming, and bathroom cleaning", subcategory=subcategories[0], image_filename=None),
            Service(name="Deep Cleaning", description="Deep cleaning includes all basic cleaning plus kitchen deep clean", subcategory=subcategories[0], image_filename=None)
        ]
        db.session.add_all(services)

        # Create test variants
        variants = [
            Variant(name="1 Bedroom", price=1500, available=True, service=services[0]),
            Variant(name="2 Bedroom", price=2500, available=True, service=services[0]),
            Variant(name="Standard", price=3000, available=True, service=services[1]),
            Variant(name="Premium", price=4000, available=True, service=services[1])
        ]
        db.session.add_all(variants)
        db.session.commit()

# Helper functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_services_data():
    # Clear any existing SQLAlchemy session to ensure fresh data
    #db.session.expire_all()

    # Force reload all relationships
    categories = Category.query.options(
        db.joinedload(Category.subcategories)
        .joinedload(Subcategory.services)
        .joinedload(Service.variants)
    ).all()

    services_data = {"categories": []}

    for category in categories:
        cat_dict = {
            "id": category.id,
            "name": category.name,
            "image_filename": category.image_filename,
            "subcategories": []
        }

        for subcategory in category.subcategories:
            sub_dict = {
                "id": subcategory.id,
                "name": subcategory.name,
                "services": []
            }

            for service in subcategory.services:
                service_dict = {
                    "id": service.id,
                    "name": service.name,
                    "available": service.available,  # Make sure this is included
                    "description": service.description,
                    "image_filename": service.image_filename,
                    "variants": []
                }

                for variant in service.variants:
                    service_dict["variants"].append({
                        "id": variant.id,
                        "name": variant.name,
                        "price": variant.price,
                        "unit": variant.unit,
                        "available": variant.available  # Make sure this is included
                    })

                sub_dict["services"].append(service_dict)

            cat_dict["subcategories"].append(sub_dict)

        services_data["categories"].append(cat_dict)

    return services_data

# Admin credentials
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "mani7301"

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    shop_status = ShopStatus.query.first()
    if not shop_status or shop_status.is_open:
        services_data = get_services_data()
        return render_template('index.html', services_data=services_data, show_whatsapp=False)
    else:
        return render_template('closed.html', message=shop_status.message)

@app.route('/submit_order', methods=['POST'])
def submit_order():
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    address = request.form.get('address', '').strip()

    if not name or not phone or not address:
        return redirect(url_for('index'))

    services_data = get_services_data()
    selected_services = []
    subtotal = 0

    # Collect all form data
    form_data = request.form.to_dict(flat=False)

    # First collect all selected service-variant combinations with quantities
    selected_items = {}
    for key, values in form_data.items():
        if key.startswith('service_'):
            try:
                parts = key.split('_')
                if len(parts) == 3:  # format: service_<service_id>_<variant_id>
                    service_id = int(parts[1])
                    variant_id = int(parts[2])
                    quantity = int(values[0]) if values else 0
                    if quantity > 0:
                        selected_items[(service_id, variant_id)] = quantity
            except (ValueError, IndexError):
                continue

    # Now find all selected services in our database structure
    for category in services_data["categories"]:
        for subcategory in category["subcategories"]:
            for service in subcategory["services"]:
                for variant in service["variants"]:
                    key = (service["id"], variant["id"])
                    if key in selected_items:
                        quantity = selected_items[key]
                        selected_services.append({
                            'name': service['name'],
                            'variant': variant['name'],
                            'quantity': quantity,
                            'price': variant['price'],
                            'unit': variant['unit'],
                            'subtotal': quantity * variant['price'],
                            'category': category['name'],
                            'subcategory': subcategory['name']
                        })
                        subtotal += quantity * variant['price']

    if not selected_services:
        return redirect(url_for('index'))

    # Total is now just the subtotal
    grand_total = subtotal

    indian_timezone = pytz.timezone("Asia/Kolkata")
    current_time = datetime.now(indian_timezone).strftime("%d-%m-%Y %I:%M %p")

    message_parts = [
        "📌 *Mess Ranchi* 📌",
        f"📅 *Date*: {current_time}",
        "",
        "👤 *Customer Details*:",
        f"• *Name*: {name}",
        f"• *Phone*: {phone}",
        f"• *Address*: {address}",
        "",
        "🛒 *Ordered Items*:"
    ]

    # Group items by category for better organization
    categories = {}
    for service in selected_services:
        if service['category'] not in categories:
            categories[service['category']] = []
        categories[service['category']].append(service)

    # Add items to message grouped by category
    for category_name, items in categories.items():
        message_parts.append(f"\n*{category_name}*")
        for item in items:
            message_parts.append(
                f"➡️ {item['name']} ({item['variant']}) - "
                f"Qty: {item['quantity']} {item['unit']} × ₹{item['price']} = ₹{item['subtotal']}"
            )
            message_parts.append("")
        message_parts.append("")
    message_parts.extend([
        "",
        "💵 *Payment Summary*:",
        f"• *Subtotal*: ₹{subtotal}",
        f"• *Total Amount*: ₹{grand_total}",
        f"• *Payment Mode*: {request.form.get('payment_mode', 'Online')}",
        "",
        "🛑 *Please Share Your current location link for fast delivery* 🛑",
    ])

    full_message = "\n".join(message_parts)
    whatsapp_url = f"https://wa.me/+918969161759?text={requests.utils.quote(full_message)}"

    return redirect(whatsapp_url)
# Admin routes
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin_panel'))
        else:
            return render_template('admin.html', error="Invalid credentials", login_page=True)

    return render_template('admin.html', login_page=True)

@app.route('/admin/logout')
def admin_logout():
    session.pop('logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/admin/panel')
@login_required
def admin_panel():
    services_data = get_services_data()
    shop_status = ShopStatus.query.first()
    if not shop_status:
        shop_status = ShopStatus(is_open=True)
        db.session.add(shop_status)
        db.session.commit()

    return render_template(
        'admin.html',
        services_data=services_data,
        shop_status=shop_status,
        login_page=False
    )
# Category operations

@app.route('/admin/add_category', methods=['POST'])
@login_required
def add_category():
    name = request.form.get('name', '').strip()
    if name:
        new_category = Category(name=name)
        db.session.add(new_category)
        db.session.commit()

        # Handle image upload
        if 'image' in request.files:
            file = request.files['image']
            if file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(f"category_{new_category.id}.jpg")
                filepath = os.path.join(app.config['CATEGORY_UPLOAD_FOLDER'], filename)
                file.save(filepath)
                new_category.image_filename = filename
                db.session.commit()


        return redirect(url_for('admin_panel'))
    return redirect(url_for('admin_panel'))

# Update your update_category route
@app.route('/admin/update_category/<int:category_id>', methods=['POST'])
@login_required
def update_category(category_id):
    name = request.form.get('name', '').strip()
    category = Category.query.get_or_404(category_id)
    if name:
        category.name = name

        # Handle image upload
        if 'image' in request.files:
            file = request.files['image']
            if file.filename != '' and allowed_file(file.filename):
                # Delete old image if exists
                if category.image_filename:
                    old_filepath = os.path.join(app.config['CATEGORY_UPLOAD_FOLDER'], category.image_filename)
                    if os.path.exists(old_filepath):
                        os.remove(old_filepath)

                # Save new image
                filename = secure_filename(f"category_{category.id}.jpg")
                filepath = os.path.join(app.config['CATEGORY_UPLOAD_FOLDER'], filename)
                file.save(filepath)
                category.image_filename = filename

        db.session.commit()
        return redirect(url_for('admin_panel', _anchor=f'category-{category_id}'))



@app.route('/admin/update_subcategory/<int:category_id>/<int:subcategory_id>', methods=['POST'])
@login_required
def update_subcategory(category_id, subcategory_id):
    name = request.form.get('name', '').strip()
    subcategory = Subcategory.query.get_or_404(subcategory_id)
    if name:
        subcategory.name = name
        db.session.commit()
        return redirect(url_for('admin_panel', _anchor=f'subcat-{subcategory_id}'))



@app.route('/admin/update_service/<int:category_id>/<int:subcategory_id>/<int:service_id>', methods=['POST'])
@login_required
def update_service(category_id, subcategory_id, service_id):
    name = request.form.get('name', '').strip()
    available = request.form.get('available') == 'on'
    description = request.form.get('description', '').strip()

    service = Service.query.get_or_404(service_id)
    if name:
        service.name = name
        service.available = available
        service.description = description
        db.session.commit()
        return redirect(url_for('admin_panel', _anchor=f'service-{service_id}'))



@app.route('/admin/upload_service_image/<int:service_id>', methods=['POST'])
@login_required
def upload_service_image(service_id):
    if 'file' not in request.files:
        return "No file part", 400
    file = request.files['file']
    if file.filename == '':
        return "No selected file", 400

    if file and allowed_file(file.filename):
        # Get the service
        service = Service.query.get_or_404(service_id)

        # Delete old image if exists
        if service.image_filename:
            old_filepath = os.path.join(app.config['UPLOAD_FOLDER'], service.image_filename)
            if os.path.exists(old_filepath):
                os.remove(old_filepath)

        # Generate filename (use service ID to ensure uniqueness)
        filename = secure_filename(f"service_{service_id}.jpg")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        # Save the file
        file.save(filepath)

        # Update the service with the image filename
        service.image_filename = filename
        db.session.commit()

        return redirect(url_for('admin_panel', _anchor=f'service-{service_id}'))

    return "Invalid file type", 400


@app.route('/admin/delete_category/<int:category_id>')
@login_required
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    db.session.delete(category)
    db.session.commit()
    return redirect(url_for('admin_panel'))


@app.route('/admin/delete_subcategory/<int:category_id>/<int:subcategory_id>')
@login_required
def delete_subcategory(category_id, subcategory_id):
    subcategory = Subcategory.query.get_or_404(subcategory_id)
    db.session.delete(subcategory)
    db.session.commit()
    return redirect(url_for('admin_panel', _anchor=f'category-{category_id}'))


@app.route('/admin/delete_service/<int:category_id>/<int:subcategory_id>/<int:service_id>')
@login_required
def delete_service(category_id, subcategory_id, service_id):
    service = Service.query.get_or_404(service_id)
    db.session.delete(service)
    db.session.commit()
    return redirect(url_for('admin_panel', _anchor=f'subcat-{subcategory_id}'))




# Update add routes to redirect to the new item
@app.route('/admin/add_subcategory/<int:category_id>', methods=['POST'])
@login_required
def add_subcategory(category_id):
    name = request.form.get('name', '').strip()
    category = Category.query.get_or_404(category_id)
    if name:
        new_subcategory = Subcategory(name=name, category_id=category_id)
        db.session.add(new_subcategory)
        db.session.commit()
        return redirect(url_for('admin_panel', _anchor=f'subcat-{new_subcategory.id}'))
    return redirect(url_for('admin_panel'))

@app.route('/admin/add_service/<int:category_id>/<int:subcategory_id>', methods=['POST'])
@login_required
def add_service(category_id, subcategory_id):
    name = request.form.get('name', '').strip()
    available = request.form.get('available') == 'on'
    description = request.form.get('description', '').strip()

    subcategory = Subcategory.query.get_or_404(subcategory_id)
    if name:
        new_service = Service(
            name=name,
            available=available,
            description=description,
            subcategory_id=subcategory_id
        )
        db.session.add(new_service)
        db.session.commit()
        return redirect(url_for('admin_panel', _anchor=f'service-{new_service.id}'))
    return redirect(url_for('admin_panel'))

# Variant operations
@app.route('/admin/add_variant/<int:service_id>', methods=['POST'])
@login_required
def add_variant(service_id):
    name = request.form.get('name', '').strip()
    price = request.form.get('price', '0')
    unit = request.form.get('unit','').strip()
    available = request.form.get('available') == 'on'

    try:
        price = int(price)
    except ValueError:
        price = 0

    service = Service.query.get_or_404(service_id)
    if name:  # Changed from 'name and price > 0' to just 'name'
        new_variant = Variant(
            name=name,
            price=price,
            unit=unit,
            available=available,
            service_id=service_id
        )
        db.session.add(new_variant)
        db.session.commit()
        return redirect(url_for('admin_panel', _anchor=f'variant-{new_variant.id}'))
    return redirect(url_for('admin_panel', _anchor=f'service-{service_id}'))

@app.route('/admin/update_variant/<int:variant_id>', methods=['POST'])
@login_required
def update_variant(variant_id):
    variant = Variant.query.get_or_404(variant_id)

    # Get all form data with proper defaults
    name = request.form.get('name', variant.name).strip()
    price_str = request.form.get('price', str(variant.price)).strip()
    unit = request.form.get('unit', variant.unit).strip()
    available = request.form.get('available') == 'on'

    # Validate price
    try:
        price = int(price_str)
        if price < 0:
            price = variant.price  # Keep original if invalid
    except ValueError:
        price = variant.price  # Keep original if invalid

    # Update all fields
    variant.name = name
    variant.price = price
    variant.unit = unit
    variant.available = available

    db.session.commit()
    return redirect(url_for('admin_panel', _anchor=f'variant-{variant_id}'))

@app.route('/admin/delete_variant/<int:variant_id>')
@login_required
def delete_variant(variant_id):
    variant = Variant.query.get_or_404(variant_id)
    service_id = variant.service_id
    db.session.delete(variant)
    db.session.commit()
    return redirect(url_for('admin_panel', _anchor=f'service-{service_id}'))
@app.route('/admin/toggle_shop_status', methods=['POST'])
@login_required
def toggle_shop_status():
    status = ShopStatus.query.first()
    if not status:
        status = ShopStatus(is_open=True)
        db.session.add(status)

    status.is_open = not status.is_open
    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/update_closed_message', methods=['POST'])
@login_required
def update_closed_message():
    new_message = request.form.get('message', '').strip()
    if new_message:
        status = ShopStatus.query.first()
        if not status:
            status = ShopStatus(is_open=False, message=new_message)
            db.session.add(status)
        else:
            status.message = new_message
        db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/menu')
def menu():
    return render_template('menu.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    # Create necessary directories if they don't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Print database location for verification
    print(f"Database will be created at: {os.path.join(basedir, 'services.db')}")
    print(f"Upload folder is at: {app.config['UPLOAD_FOLDER']}")

    app.run(debug=True)