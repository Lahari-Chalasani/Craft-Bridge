"""
CraftBridge - Single-file Flask marketplace demo

Install:
    pip install Flask Pillow

Optional AI background removal:
    pip install rembg

Run:
    python app.py

Open:
    http://127.0.0.1:5000

Demo seller:
    seller@craftbridge.com / seller123

Sellers and customers can register and sign in using separate pages.
Password reset codes are printed in the server terminal for this local demo.
Data and uploaded images are stored in ./craftbridge_data.
"""

from flask import (
    Flask, request, redirect, url_for, session, flash,
    render_template_string, send_from_directory, abort, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image, ImageEnhance
from pathlib import Path
from functools import wraps
from uuid import uuid4
import json
import os
import io
import secrets
import time

app = Flask(__name__)
app.secret_key = os.environ.get("CRAFTBRIDGE_SECRET", "change-this-secret-key")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "craftbridge_data"
UPLOAD_DIR = DATA_DIR / "uploads"
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

USERS_FILE = DATA_DIR / "users.json"
PRODUCTS_FILE = DATA_DIR / "products.json"
ORDERS_FILE = DATA_DIR / "orders.json"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

# Temporary, server-side password reset codes for the local demo.
# Codes expire after five minutes and are never stored in the browser session.
PASSWORD_RESET_CODES = {}


# -------------------- DATA HELPERS --------------------

def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, data):
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def users():
    data = read_json(USERS_FILE, {})
    if "seller@craftbridge.com" not in data:
        data["seller@craftbridge.com"] = {
            "name": "CraftBridge Demo Seller",
            "password": generate_password_hash("seller123"),
            "role": "seller"
        }
        write_json(USERS_FILE, data)
    return data


def products():
    return read_json(PRODUCTS_FILE, [])


def orders():
    return read_json(ORDERS_FILE, [])


def current_user():
    email = session.get("email")
    if not email:
        return None
    return users().get(email)


def login_required(role=None):
    def decorator(view_function):
        @wraps(view_function)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                flash("Please log in to continue.", "error")
                return redirect(url_for("choose_login"))
            if role and user.get("role") != role:
                flash("You do not have permission to open that page.", "error")
                return redirect(url_for("home"))
            return view_function(*args, **kwargs)
        return wrapper
    return decorator


def image_allowed(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def improve_product_image(source_path, output_path, use_ai=True):
    """Remove background when rembg is available, otherwise enhance the image."""
    try:
        original = Image.open(source_path).convert("RGBA")
        result = None

        if use_ai:
            try:
                from rembg import remove
                removed = remove(original)
                if isinstance(removed, Image.Image):
                    result = removed.convert("RGBA")
                else:
                    result = Image.open(io.BytesIO(removed)).convert("RGBA")
            except Exception as error:
                print("AI background removal unavailable:", error)

        if result is None:
            result = ImageEnhance.Contrast(original).enhance(1.08)
            result = ImageEnhance.Color(result).enhance(1.06)
            result = ImageEnhance.Sharpness(result).enhance(1.12)

        result.thumbnail((1100, 1100), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (1200, 1200), "white")
        x = (1200 - result.width) // 2
        y = (1200 - result.height) // 2
        canvas.alpha_composite(result, (x, y))
        canvas.convert("RGB").save(output_path, "JPEG", quality=92)
        return True

    except Exception as error:
        print("Image processing error:", error)
        return False


# -------------------- SHARED PAGE TEMPLATE --------------------

SHELL = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} | CraftBridge</title>
<style>
:root {
    --nav: #131921;
    --nav2: #232f3e;
    --gold: #febd69;
    --ink: #17202a;
    --muted: #667085;
    --bg: #eaeded;
    --green: #087443;
}
* { box-sizing: border-box; }
body {
    margin: 0;
    font-family: Arial, Helvetica, sans-serif;
    background: var(--bg);
    color: var(--ink);
}
a { text-decoration: none; color: inherit; }
.top {
    background: var(--nav);
    color: white;
    padding: 12px 3%;
    display: flex;
    align-items: center;
    gap: 22px;
    flex-wrap: wrap;
}
.logo { font-size: 27px; font-weight: 800; letter-spacing: -1px; }
.logo span { color: var(--gold); }
.search { display: flex; flex: 1; min-width: 230px; position: relative; }
.search input { min-width: 0; }
.search-suggestions {
    display: none; position: absolute; top: calc(100% + 5px); left: 0;
    width: calc(100% - 55px); max-height: 360px; overflow-y: auto;
    background: #fff; color: #17202a; border: 1px solid #d5d9dd;
    border-radius: 6px; box-shadow: 0 5px 18px #00000020; z-index: 1000;
}
.search-suggestions.show { display: block; }
.search-suggestion {
    display: block; padding: 11px 14px; border-bottom: 1px solid #eee;
    font-size: 14px; cursor: pointer;
}
.search-suggestion:last-child { border-bottom: 0; }
.search-suggestion:hover, .search-suggestion:focus { background: #f3f5f7; outline: none; }
.search-empty { padding: 12px 14px; color: #667085; font-size: 13px; }
.search input {
    width: 100%;
    padding: 12px;
    border: 0;
    border-radius: 5px 0 0 5px;
    font-size: 15px;
}
.search button {
    border: 0;
    background: var(--gold);
    padding: 0 18px;
    border-radius: 0 5px 5px 0;
    font-size: 18px;
    cursor: pointer;
}
.toplink { font-size: 13px; line-height: 1.4; }
.toplink b { display: block; font-size: 15px; }
.nav {
    background: var(--nav2);
    color: white;
    padding: 11px 3%;
    display: flex;
    gap: 24px;
    flex-wrap: wrap;
    font-size: 14px;
}
.hero {
    margin: 14px auto;
    max-width: 1500px;
    min-height: 230px;
    padding: 34px 5%;
    background: linear-gradient(110deg, #ffdf9e, #fff2d5 55%, #f6b86c);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    border-radius: 8px;
}
.hero h1 { font-size: clamp(28px, 4vw, 48px); margin: 0 0 12px; }
.hero p { font-size: 18px; color: #394150; }
.hero-art { font-size: 90px; }
.wrap { max-width: 1450px; margin: 18px auto; padding: 0 18px; }
.section-title { font-size: 23px; margin: 22px 0 14px; }
.grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
    gap: 16px;
}
.card {
    background: white;
    border-radius: 7px;
    padding: 14px;
    box-shadow: 0 1px 4px #00000012;
}
.product-img {
    width: 100%;
    height: 190px;
    object-fit: contain;
    background: white;
    border-radius: 5px;
}
.card h3 { font-size: 16px; margin: 10px 0 6px; }
.price { font-size: 22px; font-weight: bold; color: #b12704; margin: 7px 0; }
.muted { color: var(--muted); font-size: 13px; }
.btn {
    display: inline-block;
    border: 0;
    border-radius: 20px;
    background: #ffd814;
    padding: 10px 18px;
    cursor: pointer;
    font-weight: 600;
    color: #111;
    margin: 5px 4px 2px 0;
}
.btn.dark { background: #232f3e; color: white; }
.btn.green { background: var(--green); color: white; }
.btn.outline { background: white; border: 1px solid #aab0b7; }
.panel {
    background: white;
    border-radius: 9px;
    padding: 22px;
    margin: 18px auto;
    max-width: 900px;
    box-shadow: 0 2px 9px #00000010;
}
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
label { font-weight: 600; font-size: 14px; display: block; margin: 10px 0 6px; }
input, textarea, select {
    width: 100%;
    padding: 12px;
    border: 1px solid #c8cdd3;
    border-radius: 6px;
    font: inherit;
    background: white;
}
textarea { min-height: 90px; resize: vertical; }
.full { grid-column: 1 / -1; }
.notice { padding: 12px 16px; border-radius: 6px; background: #e8f5ee; margin: 12px 0; }
.notice.error { background: #ffe8e8; }
.dashboard-head {
    background: white;
    padding: 20px;
    border-radius: 8px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
}
.empty { background: white; padding: 35px; text-align: center; border-radius: 8px; color: var(--muted); }
footer { background: #232f3e; color: white; text-align: center; padding: 25px; margin-top: 40px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.tag { display: inline-block; background: #e8f5ee; color: #087443; padding: 5px 9px; border-radius: 20px; font-size: 12px; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: 10px; border-bottom: 1px solid #eee; }
@media (max-width: 650px) {
    .form-grid { grid-template-columns: 1fr; }
    .hero-art { font-size: 55px; }
    .top { gap: 12px; }
    .search { order: 3; flex-basis: 100%; }
}
</style>
</head>
<body>
<header class="top">
    <a class="logo" href="{{ url_for('home') }}">Craft<span>Bridge</span></a>
    <div class="toplink">Delivering to<b>India</b></div>
    <form class="search" id="productSearchForm"
          action="{{ url_for('customer_home') if user and user.role == 'customer' else url_for('home') }}"
          method="get" autocomplete="off">
        <input id="productSearchInput" name="q" type="search"
               placeholder="Search CraftBridge products..."
               value="{{ request.args.get('q', '') }}"
               aria-label="Search products" aria-autocomplete="list"
               aria-controls="productSuggestions">
        <div id="productSuggestions" class="search-suggestions" role="listbox"></div>
        <button type="submit" aria-label="Search">⌕</button>
    </form>
    {% if user %}
        <div class="toplink">Hello, {{ user.name }}<b>{{ user.role|title }} Account</b></div>
        {% if user.role == 'customer' %}
            <a class="toplink" href="{{ url_for('cart') }}">🛒 Cart</a>
            <a class="toplink" href="{{ url_for('my_orders') }}">My Orders</a>
        {% endif %}
        <a class="toplink" href="{{ url_for('settings') }}">Account & Settings</a>
        <a class="toplink" href="{{ url_for('logout') }}">Sign out</a>
    {% else %}
        <a class="toplink" href="{{ url_for('choose_login') }}">Hello, sign in<b>Account & Lists</b></a>
        <a class="toplink" href="{{ url_for('choose_login') }}">Orders & Returns</a>
        <a class="toplink" href="{{ url_for('choose_login') }}">🛒 Cart</a>
    {% endif %}
</header>
<nav class="nav">
    <a href="{{ url_for('home') }}">Home</a>
    <!-- Help & Support is public; it must never redirect visitors to sign in. -->
    <a href="{{ url_for('help_support') }}">Help & Support</a>
</nav>
<main class="wrap">
    {% with messages = get_flashed_messages(with_categories=true) %}
        {% for category, message in messages %}
            <div class="notice {{ 'error' if category == 'error' else '' }}">{{ message }}</div>
        {% endfor %}
    {% endwith %}
    {{ content|safe }}
</main>
<footer>CraftBridge · Connecting local makers with customers · Demo marketplace</footer>
<script>
(function () {
    const imageInput = document.getElementById("imageInput");
    if (imageInput) {
        imageInput.addEventListener("change", function () {
            const file = this.files && this.files[0];
            const preview = document.getElementById("preview");
            if (file && preview) {
                preview.src = URL.createObjectURL(file);
                preview.style.display = "block";
            }
        });
    }
})();

// Live product-name autocomplete for the CraftBridge search bar.
(function () {
    const input = document.getElementById("productSearchInput");
    const dropdown = document.getElementById("productSuggestions");
    if (!input || !dropdown) return;

    let debounceTimer = null;
    let activeRequest = null;

    function closeSuggestions() {
        dropdown.classList.remove("show");
        dropdown.replaceChildren();
    }

    function showMessage(message) {
        dropdown.replaceChildren();
        const item = document.createElement("div");
        item.className = "search-empty";
        item.textContent = message;
        dropdown.appendChild(item);
        dropdown.classList.add("show");
    }

    input.addEventListener("input", function () {
        const query = input.value.trim();
        clearTimeout(debounceTimer);

        if (!query) {
            closeSuggestions();
            return;
        }

        debounceTimer = setTimeout(async function () {
            if (activeRequest) activeRequest.abort();
            activeRequest = new AbortController();

            try {
                const response = await fetch(
                    "/api/product-suggestions?q=" + encodeURIComponent(query),
                    { signal: activeRequest.signal }
                );
                if (!response.ok) throw new Error("Suggestion request failed");
                const data = await response.json();

                dropdown.replaceChildren();
                if (!data.length) {
                    showMessage("No matching products found.");
                    return;
                }

                data.forEach(function (product) {
                    const link = document.createElement("a");
                    link.className = "search-suggestion";
                    link.href = product.url;
                    link.setAttribute("role", "option");
                    link.textContent = product.name;
                    dropdown.appendChild(link);
                });
                dropdown.classList.add("show");
            } catch (error) {
                if (error.name !== "AbortError") {
                    showMessage("Could not load suggestions. Please try again.");
                }
            }
        }, 150);
    });

    input.addEventListener("keydown", function (event) {
        if (event.key === "Escape") closeSuggestions();
        if (event.key === "ArrowDown") {
            const first = dropdown.querySelector("a");
            if (first) {
                event.preventDefault();
                first.focus();
            }
        }
    });

    document.addEventListener("click", function (event) {
        if (!event.target.closest("#productSearchForm")) closeSuggestions();
    });

    input.addEventListener("focus", function () {
        if (input.value.trim() && dropdown.children.length) {
            dropdown.classList.add("show");
        }
    });
})();

function listenFor(fieldId) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const status = document.getElementById("voiceStatus");

    if (!SpeechRecognition) {
        if (status) status.textContent = "Voice input is not supported here. Please use Chrome or Edge, or type the details.";
        alert("Voice input works in supported Chrome or Edge browsers. Please allow microphone access.");
        return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "en-IN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    if (status) status.textContent = "Listening... Speak clearly in English.";

    recognition.onresult = function (event) {
        const spoken = event.results[0][0].transcript.trim();
        const target = document.getElementById(fieldId);

        if (target) {
            if (fieldId === "price") {
                const match = spoken.replace(/,/g, "").match(/[0-9]+(?:\.[0-9]+)?/);
                target.value = match ? match[0] : spoken;
            } else {
                target.value = spoken.charAt(0).toUpperCase() + spoken.slice(1);
            }
        }

        if (status) status.textContent = "Captured: " + spoken + " - please review before publishing.";
    };

    recognition.onerror = function (event) {
        if (status) status.textContent = "Voice input error: " + event.error + ". Check microphone permission and try again.";
    };

    recognition.onend = function () {
        if (status && status.textContent === "Listening... Speak clearly in English.") {
            status.textContent = "No speech captured. Please try again.";
        }
    };

    recognition.start();
}
</script>
</body>
</html>
"""


def page(title, content, **context):
    return render_template_string(
        SHELL,
        title=title,
        content=content,
        user=current_user(),
        **context
    )


# -------------------- PRODUCT SEARCH AND DETAILS --------------------

@app.route("/api/product-suggestions")
def product_suggestions():
    """Return matching product names for the live search dropdown."""
    query = request.args.get("q", "").strip().casefold()
    if not query:
        return jsonify([])

    all_products = products()
    # Prioritize names that start with the typed text, then include other
    # product names containing the text. Match product names only.
    starts_with = []
    contains = []
    for item in all_products:
        name = str(item.get("name", "")).strip()
        normalized_name = name.casefold()
        if normalized_name.startswith(query):
            starts_with.append(item)
        elif query in normalized_name:
            contains.append(item)

    matches = starts_with + contains
    return jsonify([
        {
            "id": item.get("id"),
            "name": item.get("name", ""),
            "url": url_for("product_detail", product_id=item.get("id"))
        }
        for item in matches
    ])


@app.route("/product/<product_id>")
def product_detail(product_id):
    """Show the full details page for one product."""
    item = next(
        (p for p in products() if str(p.get("id")) == str(product_id)),
        None
    )
    if item is None:
        abort(404)

    user = current_user()
    content = """
    <div class="panel" style="max-width:1100px">
        <div class="form-grid" style="align-items:start">
            <div>
                <img src="{{ url_for('uploaded_file', filename=item.image) }}"
                     alt="{{ item.name }}"
                     style="width:100%;max-height:480px;object-fit:contain;border:1px solid #eee;border-radius:8px">
            </div>
            <div>
                <span class="tag">{{ item.category }}</span>
                <h1>{{ item.name }}</h1>
                <div class="price">₹{{ '%.2f'|format(item.price) }}</div>
                <p><b>Seller:</b> {{ item.seller_name }}</p>
                <hr style="border:0;border-top:1px solid #eee;margin:18px 0">
                <h3>Product description</h3>
                <p style="white-space:pre-wrap">{{ item.description }}</p>
                {% if user and user.role == 'customer' %}
                    <form method="post" action="{{ url_for('add_cart', product_id=item.id) }}">
                        <button class="btn green" type="submit">Add to Cart</button>
                    </form>
                {% elif not user %}
                    <a class="btn" href="{{ url_for('login', role='customer') }}">Sign in to buy</a>
                    <a class="btn outline" href="{{ url_for('register', role='customer') }}">Create customer account</a>
                {% else %}
                    <p class="muted">Sign in with a customer account to purchase this product.</p>
                {% endif %}
                <p><a href="{{ url_for('home') }}">← Continue shopping</a></p>
            </div>
        </div>
    </div>
    """
    return page(
        item.get("name", "Product"),
        render_template_string(content, item=item, user=user)
    )


# -------------------- PUBLIC PAGES --------------------

@app.route("/")
def home():
    all_products = products()
    query = request.args.get("q", "").strip().lower()

    if query:
        all_products = [
            item for item in all_products
            if query in (
                item.get("name", "") + " " +
                item.get("description", "") + " " +
                item.get("category", "")
            ).lower()
        ]

    user = current_user()
    if user and user.get("role") == "seller":
        return redirect(url_for("seller_dashboard"))
    if user and user.get("role") == "customer":
        return redirect(url_for("customer_home"))

    content = """
    <section class="hero">
        <div>
            <h1>Discover something handmade.</h1>
            <p>Shop unique products from independent sellers on CraftBridge.</p>
            <a class="btn" href="#products">Explore products</a>
            <a class="btn dark" href="{{ url_for('choose_login') }}">Get started</a>
        </div>
        <div class="hero-art">🛍️🎁</div>
    </section>
    <h2 class="section-title" id="products">Featured products</h2>
    {% if items %}
        <div class="grid">
        {% for p in items %}
            <article class="card">
                <img class="product-img" src="{{ url_for('uploaded_file', filename=p.image) }}" alt="{{ p.name }}">
                <h3><a href="{{ url_for('product_detail', product_id=p.id) }}">{{ p.name }}</a></h3>
                <div class="muted">{{ p.category }} · Seller: {{ p.seller_name }}</div>
                <div class="price">₹{{ '%.2f'|format(p.price) }}</div>
                <p class="muted">{{ p.description }}</p>
                <a class="btn" href="{{ url_for('choose_login') }}">Login to buy</a>
            </article>
        {% endfor %}
        </div>
    {% else %}
        <div class="empty">Welcome to CraftBridge! Products uploaded by sellers will appear here.</div>
    {% endif %}
    """
    return page("Home", render_template_string(content, items=all_products))


@app.route("/choose-login")
def choose_login():
    content = """
    <div class="panel">
        <h1>Welcome to CraftBridge</h1>
        <p>Choose an account type. Sign In and Register are available on separate pages.</p>
        <div class="grid">
            <div class="card">
                <h2>🧑‍💼 Seller</h2>
                <p class="muted">Upload products, manage listings and view purchases.</p>
                <a class="btn dark" href="{{ url_for('login', role='seller') }}">Seller Sign In</a>
                <a class="btn outline" href="{{ url_for('register', role='seller') }}">Seller Register</a>
            </div>
            <div class="card">
                <h2>🛍️ Customer</h2>
                <p class="muted">Explore products, add to cart and place orders.</p>
                <a class="btn" href="{{ url_for('login', role='customer') }}">Customer Sign In</a>
                <a class="btn outline" href="{{ url_for('register', role='customer') }}">Customer Register</a>
            </div>
        </div>
    </div>
    """
    return page("Choose account", render_template_string(content))


# -------------------- SIGN IN, REGISTRATION AND PASSWORD RESET --------------------

@app.route("/login/<role>", methods=["GET", "POST"])
def login(role):
    if role not in ("seller", "customer"):
        return redirect(url_for("choose_login"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = users().get(email)

        if (user and user.get("role") == role
                and check_password_hash(user.get("password", ""), password)):
            session.clear()
            session["email"] = email
            session["cart"] = []
            destination = "seller_dashboard" if role == "seller" else "customer_home"
            return redirect(url_for(destination))

        flash("Invalid email or password, or incorrect account type.", "error")

    content = """
    <div class="panel" style="max-width:520px">
        <h1>{{ role|title }} Sign In</h1>
        {% if role == 'seller' %}
            <p class="muted">Demo seller: seller@craftbridge.com / seller123</p>
        {% endif %}
        <form method="post">
            <label for="signin-email">Email</label>
            <input id="signin-email" type="email" name="email" autocomplete="email" required>
            <label for="signin-password">Password</label>
            <input id="signin-password" type="password" name="password" autocomplete="current-password" required>
            <button class="btn" type="submit">Sign In</button>
        </form>
        <p style="margin-top:14px">
            <a href="{{ url_for('forgot_password', role=role) }}"><b>Forgot Password?</b></a>
        </p>
        <hr>
        <p>Don't have a {{ role }} account?
            <a href="{{ url_for('register', role=role) }}"><b>Register here</b></a>
        </p>
        <p class="muted"><a href="{{ url_for('choose_login') }}">Back to account selection</a></p>
    </div>
    """
    return page(role + " sign in", render_template_string(content, role=role))


@app.route("/register/<role>", methods=["GET", "POST"])
def register(role):
    if role not in ("seller", "customer"):
        return redirect(url_for("choose_login"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        data = users()

        if not name or not email or len(password) < 6:
            flash("Enter your name, a valid email and a password with at least 6 characters.", "error")
        elif password != confirm_password:
            flash("Password and confirm password do not match.", "error")
        elif email in data:
            flash("This email is already registered. Please sign in.", "error")
        else:
            data[email] = {
                "name": name,
                "password": generate_password_hash(password),
                "role": role
            }
            write_json(USERS_FILE, data)
            flash("Registration successful! Please sign in with your new account.", "success")
            return redirect(url_for("login", role=role))

    content = """
    <div class="panel" style="max-width:520px">
        <h1>{{ role|title }} Register</h1>
        <p class="muted">Create your {{ role }} account. Sign In is on a separate page.</p>
        <form method="post">
            <label for="register-name">Your name</label>
            <input id="register-name" name="name" autocomplete="name" required>
            <label for="register-email">Email</label>
            <input id="register-email" type="email" name="email" autocomplete="email" required>
            <label for="register-password">Password</label>
            <input id="register-password" type="password" name="password" minlength="6" autocomplete="new-password" required>
            <label for="confirm-password">Confirm password</label>
            <input id="confirm-password" type="password" name="confirm_password" minlength="6" autocomplete="new-password" required>
            <button class="btn green" type="submit">Create Account</button>
        </form>
        <hr>
        <p>Already registered? <a href="{{ url_for('login', role=role) }}"><b>Sign In</b></a></p>
        <p class="muted"><a href="{{ url_for('choose_login') }}">Back to account selection</a></p>
    </div>
    """
    return page(role + " register", render_template_string(content, role=role))


@app.route("/forgot-password/<role>", methods=["GET", "POST"])
def forgot_password(role):
    if role not in ("seller", "customer"):
        return redirect(url_for("choose_login"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = users().get(email)

        # Remove any previous reset request from this browser session.
        old_token = session.pop("password_reset_token", None)
        if old_token:
            PASSWORD_RESET_CODES.pop(old_token, None)

        if user and user.get("role") == role:
            token = secrets.token_urlsafe(24)
            code = f"{secrets.randbelow(1_000_000):06d}"
            PASSWORD_RESET_CODES[token] = {
                "email": email,
                "role": role,
                "code": code,
                "expires_at": time.time() + 300,
                "attempts": 0
            }
            session["password_reset_token"] = token
            print(f"\n[CraftBridge] Password reset code for {email}: {code} (valid for 5 minutes)\n")

        flash("If the account exists, a reset code has been generated. For this local demo, check the VS Code/server terminal.", "success")
        return redirect(url_for("reset_password", role=role))

    content = """
    <div class="panel" style="max-width:520px">
        <h1>Forgot {{ role|title }} Password</h1>
        <p class="muted">Enter the email address used for your account.</p>
        <form method="post">
            <label for="forgot-email">Email</label>
            <input id="forgot-email" type="email" name="email" autocomplete="email" required>
            <button class="btn" type="submit">Get Reset Code</button>
        </form>
        <p class="muted">For this single-file local demo, the reset code is printed in the terminal running Flask. It expires in 5 minutes.</p>
        <a href="{{ url_for('login', role=role) }}">Back to Sign In</a>
    </div>
    """
    return page("Forgot password", render_template_string(content, role=role))


@app.route("/reset-password/<role>", methods=["GET", "POST"])
def reset_password(role):
    if role not in ("seller", "customer"):
        return redirect(url_for("choose_login"))

    token = session.get("password_reset_token")
    reset_data = PASSWORD_RESET_CODES.get(token) if token else None
    if not reset_data or reset_data.get("role") != role:
        content = """
        <div class="panel" style="max-width:520px">
            <h1>Reset Password</h1>
            <p class="muted">There is no active reset request, or the code has expired. Please request a new code.</p>
            <a class="btn" href="{{ url_for('forgot_password', role=role) }}">Request New Code</a>
            <a class="btn outline" href="{{ url_for('login', role=role) }}">Back to Sign In</a>
        </div>
        """
        return page("Reset password", render_template_string(content, role=role))

    if time.time() > reset_data["expires_at"]:
        PASSWORD_RESET_CODES.pop(token, None)
        session.pop("password_reset_token", None)
        flash("The reset code expired. Please request a new one.", "error")
        return redirect(url_for("forgot_password", role=role))

    if request.method == "POST":
        entered_code = request.form.get("code", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        reset_data["attempts"] += 1

        if reset_data["attempts"] > 5:
            PASSWORD_RESET_CODES.pop(token, None)
            session.pop("password_reset_token", None)
            flash("Too many incorrect attempts. Please request a new reset code.", "error")
            return redirect(url_for("forgot_password", role=role))
        elif not secrets.compare_digest(entered_code, reset_data["code"]):
            flash("Invalid reset code. Please try again.", "error")
        elif len(password) < 6:
            flash("New password must contain at least 6 characters.", "error")
        elif password != confirm_password:
            flash("Password and confirm password do not match.", "error")
        else:
            data = users()
            account = data.get(reset_data["email"])
            if not account or account.get("role") != role:
                PASSWORD_RESET_CODES.pop(token, None)
                session.pop("password_reset_token", None)
                flash("Account not found. Please register again or contact support.", "error")
                return redirect(url_for("login", role=role))

            account["password"] = generate_password_hash(password)
            write_json(USERS_FILE, data)
            PASSWORD_RESET_CODES.pop(token, None)
            session.pop("password_reset_token", None)
            flash("Password changed successfully. Please sign in with your new password.", "success")
            return redirect(url_for("login", role=role))

    content = """
    <div class="panel" style="max-width:520px">
        <h1>Reset {{ role|title }} Password</h1>
        <p class="muted">Enter the 6-digit code printed in the VS Code/server terminal.</p>
        <form method="post">
            <label for="reset-code">Reset code</label>
            <input id="reset-code" name="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required>
            <label for="new-password">New password</label>
            <input id="new-password" type="password" name="password" minlength="6" autocomplete="new-password" required>
            <label for="confirm-new-password">Confirm new password</label>
            <input id="confirm-new-password" type="password" name="confirm_password" minlength="6" autocomplete="new-password" required>
            <button class="btn green" type="submit">Update Password</button>
        </form>
        <p class="muted">The reset code is valid for 5 minutes and allows up to 5 attempts.</p>
        <a href="{{ url_for('forgot_password', role=role) }}">Request another code</a>
    </div>
    """
    return page("Reset password", render_template_string(content, role=role))


# -------------------- SELLER PAGES --------------------

@app.route("/seller")
@login_required("seller")
def seller_dashboard():
    email = session["email"]
    mine = [p for p in products() if p.get("seller_email") == email]
    my_ids = {p["id"] for p in mine}
    bought = [o for o in orders() if o.get("product_id") in my_ids]

    content = """
    <div class="dashboard-head">
        <div>
            <span class="tag">SELLER WORKSPACE</span>
            <h1>Hello, {{ user.name }}</h1>
            <p class="muted">Manage your products and customer purchases.</p>
        </div>
        <a class="btn green" href="{{ url_for('new_product') }}">＋ New Product</a>
    </div>

    <h2 class="section-title">Your uploaded products ({{ mine|length }})</h2>
    {% if mine %}
        <div class="grid">
        {% for p in mine %}
            <div class="card">
                <img class="product-img" src="{{ url_for('uploaded_file', filename=p.image) }}" alt="{{ p.name }}">
                <h3>{{ p.name }}</h3>
                <div class="price">₹{{ '%.2f'|format(p.price) }}</div>
                <p class="muted">{{ p.description }}</p>
                <span class="tag">Visible to customers</span>
                <form method="post" action="{{ url_for('delete_product', product_id=p.id) }}"
                      onsubmit="return confirm('Are you sure you want to delete this product?');"
                      style="margin-top:12px">
                    <button class="btn" type="submit" style="background:#b42318">Delete Product</button>
                </form>
            </div>
        {% endfor %}
        </div>
    {% else %}
        <div class="empty">You have not uploaded any products yet. Select New Product to begin.</div>
    {% endif %}

    <h2 class="section-title">Customer purchases ({{ bought|length }})</h2>
    {% if bought %}
        <div class="card">
            <table>
                <tr><th>Product</th><th>Customer details</th><th>Delivery address</th><th>Payment</th><th>Status</th><th>Total</th></tr>
                {% for o in bought %}
                    <tr>
                        <td>{{ o.product_name }}</td>
                        <td>{{ o.customer_name }}<br>{{ o.customer_email }}<br>{{ o.phone or 'Not provided' }}</td>
                        <td>{{ o.address or 'Not provided' }}{% if o.city %}, {{ o.city }}{% endif %}{% if o.state %}, {{ o.state }}{% endif %} {{ o.pincode or '' }}</td>
                        <td>{{ o.payment_method or 'Cash on Delivery' }}<br>{{ o.payment_status or 'Pay on delivery' }}</td>
                        <td><b>{{ o.status or 'Pending' }}</b>
                            {% if o.status != 'Cancelled' %}
                            <form method="post" action="{{ url_for('seller_update_order', order_id=o.id) }}">
                                <select name="status">{% for st in ['Pending','Confirmed','Shipped','Delivered'] %}<option value="{{ st }}" {% if (o.status or 'Pending') == st %}selected{% endif %}>{{ st }}</option>{% endfor %}</select>
                                <button class="btn outline" type="submit">Update</button>
                            </form>{% endif %}
                        </td>
                        <td>₹{{ '%.2f'|format(o.total) }}</td>
                    </tr>
                {% endfor %}
            </table>
        </div>
    {% else %}
        <div class="empty">No customer purchases yet.</div>
    {% endif %}
    """
    return page(
        "Seller dashboard",
        render_template_string(
            content, user=current_user(), mine=mine, bought=bought
        )
    )


@app.route("/seller/delete/<product_id>", methods=["POST"])
@login_required("seller")
def delete_product(product_id):
    """Delete a product owned by the currently logged-in seller."""
    email = session["email"]
    all_products = products()
    target = next(
        (p for p in all_products
         if str(p.get("id")) == str(product_id)
         and p.get("seller_email") == email),
        None
    )

    if target is None:
        flash("Product not found or you do not have permission to delete it.", "error")
        return redirect(url_for("seller_dashboard"))

    remaining = [p for p in all_products if str(p.get("id")) != str(product_id)]
    write_json(PRODUCTS_FILE, remaining)

    # Remove the product image if it exists. Past order records are kept.
    image_name = target.get("image")
    if image_name:
        image_path = UPLOAD_DIR / Path(image_name).name
        try:
            if image_path.is_file():
                image_path.unlink()
        except OSError:
            app.logger.warning("Could not delete product image: %s", image_path)

    flash("Product deleted successfully.", "success")
    return redirect(url_for("seller_dashboard"))


@app.route("/seller/new", methods=["GET", "POST"])
@login_required("seller")
def new_product():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "Other").strip()

        try:
            price = float(request.form.get("price", "0"))
            if price <= 0:
                raise ValueError
        except ValueError:
            flash("Enter a valid product price greater than zero.", "error")
            return redirect(url_for("new_product"))

        uploaded = request.files.get("image")
        if (
            not name
            or not description
            or not uploaded
            or not uploaded.filename
            or not image_allowed(uploaded.filename)
        ):
            flash("Enter product details and upload a JPG, PNG or WEBP image.", "error")
            return redirect(url_for("new_product"))

        image_id = uuid4().hex
        safe_name = secure_filename(uploaded.filename)
        source_path = UPLOAD_DIR / f"{image_id}_source_{safe_name}"
        final_name = f"{image_id}.jpg"
        destination_path = UPLOAD_DIR / final_name

        uploaded.save(source_path)
        use_ai = request.form.get("ai_background") == "yes"
        success = improve_product_image(
            source_path, destination_path, use_ai=use_ai
        )

        if not success:
            try:
                # If processing fails, keep the original upload with its safe name.
                source_path.replace(destination_path)
                final_name = destination_path.name
            except OSError:
                flash("Could not save the uploaded image. Please try again.", "error")
                return redirect(url_for("new_product"))
        else:
            try:
                source_path.unlink()
            except OSError:
                pass

        item = {
            "id": image_id,
            "name": name,
            "description": description,
            "category": category,
            "price": price,
            "image": final_name,
            "seller_email": session["email"],
            "seller_name": current_user()["name"]
        }

        data = products()
        data.insert(0, item)
        write_json(PRODUCTS_FILE, data)

        flash("Product published! It is now visible in the customer marketplace.", "success")
        return redirect(url_for("seller_dashboard"))

    content = """
    <div class="panel">
        <h1>＋ Add a new product</h1>
        <p class="muted">Upload a product photo. You can speak the details or type them manually.</p>

        <form method="post" enctype="multipart/form-data" id="productForm">
            <div class="form-grid">
                <div class="full">
                    <label>Product photo</label>
                    <input type="file" name="image" id="imageInput" accept="image/*" capture="environment" required>
                    <div class="actions">
                        <button type="button" class="btn outline" onclick="document.getElementById('imageInput').click()">📷 Camera / Choose image</button>
                    </div>
                    <img id="preview" style="display:none;max-width:260px;max-height:220px;object-fit:contain;margin-top:12px;border:1px solid #ddd;border-radius:8px" alt="Image preview">
                </div>

                <div>
                    <label>Product name</label>
                    <div class="actions">
                        <input id="name" name="name" required placeholder="e.g. Handmade clay pot">
                        <button class="btn outline" type="button" onclick="listenFor('name')">🎙 Speak</button>
                    </div>
                </div>

                <div>
                    <label>Price (₹)</label>
                    <div class="actions">
                        <input id="price" name="price" type="number" min="1" step="0.01" required placeholder="e.g. 350">
                        <button class="btn outline" type="button" onclick="listenFor('price')">🎙 Speak</button>
                    </div>
                </div>

                <div>
                    <label>Category</label>
                    <select name="category">
                        <option>Handmade</option>
                        <option>Home & Kitchen</option>
                        <option>Fashion</option>
                        <option>Art & Decor</option>
                        <option>Food</option>
                        <option>Other</option>
                    </select>
                </div>

                <div class="full">
                    <label>Description</label>
                    <textarea id="description" name="description" required placeholder="Describe the product, size, material and other details..."></textarea>
                    <button class="btn outline" type="button" onclick="listenFor('description')">🎙 Speak description</button>
                </div>

                <div class="full">
                    <label>
                        <input type="checkbox" name="ai_background" value="yes" checked style="width:auto">
                        Try AI background removal (requires optional rembg package)
                    </label>
                    <p class="muted">If rembg is unavailable, the app applies light image enhancement and a clean white background.</p>
                </div>
            </div>

            <div class="actions">
                <button class="btn green" type="submit">Publish Product</button>
                <a class="btn outline" href="{{ url_for('seller_dashboard') }}">Cancel</a>
            </div>
        </form>
        <p id="voiceStatus" class="muted"></p>
    </div>
    """
    return page("New product", render_template_string(content))


# -------------------- CUSTOMER PAGES --------------------

@app.route("/customer")
@login_required("customer")
def customer_home():
    all_products = products()
    query = request.args.get("q", "").strip().lower()

    if query:
        all_products = [
            item for item in all_products
            if query in (
                item.get("name", "") + " " +
                item.get("description", "") + " " +
                item.get("category", "")
            ).lower()
        ]

    content = """
    <section class="hero">
        <div>
            <h1>Welcome, {{ user.name }}!</h1>
            <p>Find products made and shared by CraftBridge sellers.</p>
            <a class="btn" href="#products">Shop now</a>
        </div>
        <div class="hero-art">🛒</div>
    </section>

    <h2 class="section-title" id="products">All products</h2>
    {% if items %}
        <div class="grid">
        {% for p in items %}
            <article class="card">
                <img class="product-img" src="{{ url_for('uploaded_file', filename=p.image) }}" alt="{{ p.name }}">
                <h3><a href="{{ url_for('product_detail', product_id=p.id) }}">{{ p.name }}</a></h3>
                <div class="muted">{{ p.category }} · {{ p.seller_name }}</div>
                <div class="price">₹{{ '%.2f'|format(p.price) }}</div>
                <p class="muted">{{ p.description }}</p>
                <a class="btn outline" href="{{ url_for('product_detail', product_id=p.id) }}">View Product</a>
                <form method="post" action="{{ url_for('add_cart', product_id=p.id) }}">
                    <button class="btn" type="submit">Add to Cart</button>
                </form>
            </article>
        {% endfor %}
        </div>
    {% else %}
        <div class="empty">No products are available yet. Please check again later.</div>
    {% endif %}
    """
    return page(
        "Customer home",
        render_template_string(content, user=current_user(), items=all_products)
    )


@app.route("/cart")
@login_required("customer")
def cart():
    cart_ids = session.get("cart", [])
    all_products = products()
    items = []

    for product_id in cart_ids:
        item = next((p for p in all_products if p["id"] == product_id), None)
        if item:
            items.append(item)

    total = sum(float(item["price"]) for item in items)

    content = """
    <div class="panel">
        <h1>Your Cart ({{ items|length }})</h1>
        {% if items %}
            {% for p in items %}
                <div style="display:flex;gap:18px;align-items:center;border-bottom:1px solid #eee;padding:12px 0">
                    <img src="{{ url_for('uploaded_file', filename=p.image) }}" style="width:100px;height:90px;object-fit:contain" alt="{{ p.name }}">
                    <div style="flex:1">
                        <b>{{ p.name }}</b>
                        <p class="price">₹{{ '%.2f'|format(p.price) }}</p>
                    </div>
                    <form method="post" action="{{ url_for('remove_cart', product_id=p.id) }}">
                        <button class="btn outline" type="submit">Remove</button>
                    </form>
                </div>
            {% endfor %}
            <h2>Total: ₹{{ '%.2f'|format(total) }}</h2>
            <form method="post" action="{{ url_for('checkout') }}">
                <h3>Delivery details</h3>
                <label>Customer name</label><input name="customer_name" value="{{ customer.name }}" required>
                <label>Mobile number</label><input name="phone" type="tel" required>
                <label>Full delivery address</label><textarea name="address" rows="3" required placeholder="House / street / area"></textarea>
                <label>City</label><input name="city" required>
                <label>State</label><input name="state" required>
                <label>PIN code</label><input name="pincode" inputmode="numeric" pattern="[0-9]{6}" required>
                <label>Payment method</label>
                <select name="payment_method" required><option value="Cash on Delivery">Cash on Delivery (COD)</option></select>
                <p class="muted">Pay in cash when your order is delivered. No online payment is collected in this demo.</p>
                <button class="btn green" type="submit">Confirm Order</button>
            </form>
        {% else %}
            <div class="empty">Your cart is empty. <a href="{{ url_for('customer_home') }}">Continue shopping</a></div>
        {% endif %}
    </div>
    """
    return page("Cart", render_template_string(content, items=items, total=total, customer=current_user()))


@app.route("/cart/add/<product_id>", methods=["POST"])
@login_required("customer")
def add_cart(product_id):
    if not any(p["id"] == product_id for p in products()):
        flash("Product not found.", "error")
    else:
        cart_items = session.get("cart", [])
        cart_items.append(product_id)
        session["cart"] = cart_items
        flash("Added to cart.", "success")
    return redirect(url_for("customer_home"))


@app.route("/cart/remove/<product_id>", methods=["POST"])
@login_required("customer")
def remove_cart(product_id):
    cart_items = session.get("cart", [])
    try:
        cart_items.remove(product_id)
    except ValueError:
        pass
    session["cart"] = cart_items
    return redirect(url_for("cart"))


@app.route("/checkout", methods=["POST"])
@login_required("customer")
def checkout():
    all_products = products()
    order_data = orders()
    customer = current_user()
    customer_name = request.form.get("customer_name", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    city = request.form.get("city", "").strip()
    state = request.form.get("state", "").strip()
    pincode = request.form.get("pincode", "").strip()
    payment_method = request.form.get("payment_method", "Cash on Delivery")

    if not all([customer_name, phone, address, city, state, pincode]):
        flash("Please complete all delivery details.", "error")
        return redirect(url_for("cart"))
    if not pincode.isdigit() or len(pincode) != 6:
        flash("Please enter a valid 6-digit PIN code.", "error")
        return redirect(url_for("cart"))
    if payment_method != "Cash on Delivery":
        flash("Only Cash on Delivery is available in this demo.", "error")
        return redirect(url_for("cart"))

    cart_items = session.get("cart", [])
    if not cart_items:
        flash("Your cart is empty.", "error")
        return redirect(url_for("cart"))
    for product_id in cart_items:
        item = next((p for p in all_products if p["id"] == product_id), None)
        if item:
            order_data.append({
                "id": uuid4().hex, "product_id": item["id"],
                "product_name": item["name"], "seller_email": item["seller_email"],
                "customer_email": session["email"], "customer_name": customer_name,
                "phone": phone, "address": address, "city": city, "state": state,
                "pincode": pincode, "quantity": 1, "total": item["price"],
                "payment_method": "Cash on Delivery", "payment_status": "Pay on delivery",
                "status": "Pending"
            })
    write_json(ORDERS_FILE, order_data)
    session["cart"] = []
    flash("Order placed. Pay in cash when the order is delivered.", "success")
    return redirect(url_for("my_orders"))


@app.route("/orders/cancel/<order_id>", methods=["POST"])
@login_required("customer")
def cancel_order(order_id):
    data = orders()
    target = next((o for o in data if str(o.get("id")) == str(order_id)
                   and o.get("customer_email") == session["email"]), None)
    if not target:
        flash("Order not found.", "error")
    elif target.get("status", "Pending") not in ("Pending", "Confirmed"):
        flash("This order can no longer be cancelled. Please contact the seller.", "error")
    else:
        target["status"] = "Cancelled"
        target["payment_status"] = "Not paid - order cancelled"
        write_json(ORDERS_FILE, data)
        flash("Your order has been cancelled.", "success")
    return redirect(url_for("help_support"))


@app.route("/orders/update/<order_id>", methods=["POST"])
@login_required("customer")
def update_order_details(order_id):
    """Update phone and delivery address for the signed-in customer's order."""
    data = orders()
    target = next(
        (o for o in data
         if str(o.get("id")) == str(order_id)
         and o.get("customer_email") == session.get("email")),
        None
    )

    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    city = request.form.get("city", "").strip()
    state = request.form.get("state", "").strip()
    pincode = request.form.get("pincode", "").strip()
    phone_digits = "".join(ch for ch in phone if ch.isdigit())

    if not target:
        flash("Order not found.", "error")
    elif target.get("status", "Pending") not in ("Pending", "Confirmed"):
        flash("Order details cannot be changed after the order is shipped.", "error")
    elif not all([phone, address, city, state, pincode]):
        flash("Please complete all phone and delivery address fields.", "error")
    elif not (10 <= len(phone_digits) <= 15):
        flash("Enter a valid phone number with 10 to 15 digits.", "error")
    elif not (pincode.isdigit() and len(pincode) == 6):
        flash("Enter a valid 6-digit PIN code.", "error")
    else:
        target["phone"] = phone
        target["address"] = address
        target["city"] = city
        target["state"] = state
        target["pincode"] = pincode
        write_json(ORDERS_FILE, data)
        flash("Your order phone number and delivery address were updated successfully.", "success")

    return redirect(url_for("help_support"))


@app.route("/seller/order/<order_id>/status", methods=["POST"])
@login_required("seller")
def seller_update_order(order_id):
    data = orders()
    target = next((o for o in data if str(o.get("id")) == str(order_id)
                   and o.get("seller_email") == session["email"]), None)
    new_status = request.form.get("status", "")
    allowed = {"Pending", "Confirmed", "Shipped", "Delivered"}
    if not target:
        flash("Order not found.", "error")
    elif target.get("status") == "Cancelled":
        flash("Cancelled orders cannot be updated.", "error")
    elif new_status not in allowed:
        flash("Invalid order status.", "error")
    else:
        target["status"] = new_status
        if new_status == "Delivered" and target.get("payment_method") == "Cash on Delivery":
            target["payment_status"] = "Collected on delivery"
        write_json(ORDERS_FILE, data)
        flash("Order status updated.", "success")
    return redirect(url_for("seller_dashboard"))


@app.route("/orders")
@login_required("customer")
def my_orders():
    mine = [
        order for order in orders()
        if order.get("customer_email") == session["email"]
    ]

    content = """
    <div class="panel">
        <h1>My Orders</h1>
        {% if mine %}
            <table>
                <tr><th>Product</th><th>Delivery address</th><th>Payment</th><th>Status</th><th>Total</th><th>Action</th></tr>
                {% for o in mine %}
                    <tr>
                        <td>{{ o.product_name }}</td>
                        <td>{{ o.address or 'Address not saved' }}{% if o.city %}, {{ o.city }}{% endif %}{% if o.state %}, {{ o.state }}{% endif %} {{ o.pincode or '' }}<br>Phone: {{ o.phone or 'Not provided' }}</td>
                        <td>{{ o.payment_method or 'Cash on Delivery' }}<br>{{ o.payment_status or 'Pay on delivery' }}</td>
                        <td>{{ o.status or 'Pending' }}</td>
                        <td>₹{{ '%.2f'|format(o.total) }}</td>
                        <td>{% if (o.status or 'Pending') in ['Pending', 'Confirmed'] %}
                            <form method="post" action="{{ url_for('cancel_order', order_id=o.id) }}" onsubmit="return confirm('Cancel this order?');"><button class="btn" type="submit" style="background:#b42318">Cancel Order</button></form>
                            {% else %}Not available{% endif %}</td>
                    </tr>
                {% endfor %}
            </table>
        {% else %}
            <div class="empty">You have not placed any orders yet.</div>
        {% endif %}
    </div>
    """
    return page("My orders", render_template_string(content, mine=mine))


# -------------------- HELP & SUPPORT --------------------

@app.route("/help-support")
def help_support():
    """Public support page. Customer order details are shown only to that customer."""
    user = current_user()
    mine = []

    if user and user.get("role") == "customer":
        mine = [
            order for order in orders()
            if order.get("customer_email") == session.get("email")
        ]
        mine.reverse()  # Show the most recently placed order first.

    content = """
    <div class="panel">
        <h1>Help &amp; Support</h1>
        <p class="muted">Find answers about your CraftBridge orders and get help when you need it.</p>

        <div class="grid" style="margin:18px 0">
            <a class="card" href="#where-order">
                <h3>📦 Where is my order?</h3>
                <p class="muted">View your order status, payment and delivery details.</p>
            </a>
            <a class="card" href="#cancel-order">
                <h3>❌ Cancel order</h3>
                <p class="muted">See which orders can still be cancelled.</p>
            </a>
            <a class="card" href="#return-order">
                <h3>↩️ Return order</h3>
                <p class="muted">Request a return for an order marked as delivered.</p>
            </a>
        </div>

        {% if user and user.role == 'customer' %}
            <h2 class="section-title" id="where-order">Where is my order?</h2>
            {% if mine %}
                {% for o in mine %}
                    <div class="card" style="margin:14px 0">
                        <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center">
                            <h3 style="margin:4px 0">{{ o.product_name }}</h3>
                            <span class="tag">{{ o.status or 'Pending' }}</span>
                        </div>
                        <p class="muted"><b>Order ID:</b> {{ o.id }}</p>
                        <p><b>Order total:</b> ₹{{ '%.2f'|format(o.total) }}</p>
                        <p><b>Payment:</b> {{ o.payment_method or 'Cash on Delivery' }} — {{ o.payment_status or 'Pay on delivery' }}</p>
                        <p><b>Delivery address:</b> {{ o.address or 'Not provided' }}, {{ o.city or '' }}, {{ o.state or '' }} - {{ o.pincode or '' }}</p>
                        <p><b>Contact number:</b> {{ o.phone or 'Not provided' }}</p>

                        {% if (o.status or 'Pending') in ['Pending', 'Confirmed'] %}
                            <details style="margin:14px 0;padding:12px;border:1px solid #e5e7eb;border-radius:8px">
                                <summary style="cursor:pointer;font-weight:700">✏️ Update phone number / delivery address</summary>
                                <form method="post" action="{{ url_for('update_order_details', order_id=o.id) }}" style="margin-top:12px">
                                    <label for="phone-{{ o.id }}">Phone number</label>
                                    <input id="phone-{{ o.id }}" name="phone" type="tel" value="{{ o.phone or '' }}" required placeholder="10-digit mobile number">
                                    <label for="address-{{ o.id }}">Full delivery address</label>
                                    <textarea id="address-{{ o.id }}" name="address" required placeholder="House number, street, area">{{ o.address or '' }}</textarea>
                                    <label for="city-{{ o.id }}">City</label>
                                    <input id="city-{{ o.id }}" name="city" value="{{ o.city or '' }}" required>
                                    <label for="state-{{ o.id }}">State</label>
                                    <input id="state-{{ o.id }}" name="state" value="{{ o.state or '' }}" required>
                                    <label for="pincode-{{ o.id }}">PIN code</label>
                                    <input id="pincode-{{ o.id }}" name="pincode" value="{{ o.pincode or '' }}" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required>
                                    <button class="btn green" type="submit">Save Order Details</button>
                                </form>
                            </details>
                        {% else %}
                            <p class="muted">Phone number and delivery address can be changed only while the order is Pending or Confirmed.</p>
                        {% endif %}

                        <div id="cancel-order">
                            {% if (o.status or 'Pending') in ['Pending', 'Confirmed'] %}
                                <form method="post" action="{{ url_for('cancel_order', order_id=o.id) }}"
                                      onsubmit="return confirm('Are you sure you want to cancel this order?');">
                                    <button class="btn" type="submit" style="background:#f04438;color:white">Cancel Order</button>
                                </form>
                            {% elif (o.status or '') == 'Cancelled' %}
                                <p class="muted"><b>Cancellation:</b> This order has been cancelled.</p>
                            {% else %}
                                <p class="muted">This order can no longer be cancelled because it is {{ o.status|lower }}.</p>
                            {% endif %}
                        </div>

                        <div id="return-order" style="margin-top:12px">
                            {% if o.return_status %}
                                <p><b>Return request:</b> <span class="tag">{{ o.return_status }}</span></p>
                                <p class="muted"><b>Reason:</b> {{ o.return_reason or 'Not provided' }}</p>
                            {% elif (o.status or '') == 'Delivered' %}
                                <form method="post" action="{{ url_for('request_return', order_id=o.id) }}">
                                    <label for="reason-{{ o.id }}">Return reason</label>
                                    <select id="reason-{{ o.id }}" name="reason" required>
                                        <option value="">Select a reason</option>
                                        <option>Product damaged</option>
                                        <option>Wrong product received</option>
                                        <option>Product not as described</option>
                                        <option>Other</option>
                                    </select>
                                    <button class="btn dark" type="submit">Request Return</button>
                                </form>
                            {% else %}
                                <p class="muted">Return request will be available after this order is marked as delivered.</p>
                            {% endif %}
                        </div>
                    </div>
                {% endfor %}
            {% else %}
                <div class="empty">You have not placed any orders yet. Your order details will appear here after checkout.</div>
            {% endif %}
        {% elif user and user.role == 'seller' %}
            <h2 class="section-title" id="where-order">Order support</h2>
            <p class="muted">Customer order details are private. Open your Seller Dashboard to view orders for your products.</p>
            <a class="btn dark" href="{{ url_for('seller_dashboard') }}">Open Seller Dashboard</a>
        {% else %}
            <h2 class="section-title" id="where-order">Order information</h2>
            <p>Help &amp; Support is available to everyone. To protect customer privacy, order-specific details are shown only to the customer account that placed the order.</p>
        {% endif %}

        <hr style="border:0;border-top:1px solid #eee;margin:24px 0">
        <h2>Common questions</h2>
        <h3>How can I track my order?</h3>
        <p class="muted">Check the order status shown above. The seller updates the status to Pending, Confirmed, Shipped or Delivered.</p>
        <h3>When can I cancel an order?</h3>
        <p class="muted">You can cancel an order while its status is Pending or Confirmed. Once it is shipped or delivered, the cancel option is unavailable.</p>
        <h3>How can I return an order?</h3>
        <p class="muted">After an order is marked Delivered, select a return reason and submit a return request. The request status will be shown with that order.</p>
        <h3>Contact support</h3>
        <p class="muted">Email: <a href="mailto:support@craftbridge.example">support@craftbridge.example</a></p>
        <p class="muted">This demo records return requests in the local orders data file; it does not automatically arrange pickup or issue refunds.</p>
    </div>
    """
    return page(
        "Help & Support",
        render_template_string(content, user=user, mine=mine)
    )


@app.route("/orders/return/<order_id>", methods=["POST"])
@login_required("customer")
def request_return(order_id):
    """Save a return request for a delivered order owned by the signed-in customer."""
    data = orders()
    target = next(
        (o for o in data
         if str(o.get("id")) == str(order_id)
         and o.get("customer_email") == session.get("email")),
        None
    )
    reason = request.form.get("reason", "").strip()
    allowed_reasons = {
        "Product damaged",
        "Wrong product received",
        "Product not as described",
        "Other"
    }

    if not target:
        flash("Order not found.", "error")
    elif target.get("status") != "Delivered":
        flash("A return can be requested only after the order is delivered.", "error")
    elif target.get("return_status"):
        flash("A return request already exists for this order.", "error")
    elif reason not in allowed_reasons:
        flash("Please select a valid return reason.", "error")
    else:
        target["return_status"] = "Requested"
        target["return_reason"] = reason
        write_json(ORDERS_FILE, data)
        flash("Your return request has been submitted.", "success")

    return redirect(url_for("help_support"))


# -------------------- ACCOUNT AND FILE ROUTES --------------------

@app.route("/settings")
@login_required()
def settings():
    user = current_user()

    content = """
    <div class="panel">
        <h1>Account & Settings</h1>
        <p><b>Name:</b> {{ user.name }}</p>
        <p><b>Email:</b> {{ email }}</p>
        <p><b>Account type:</b> {{ user.role|title }}</p>

        {% if user.role == 'customer' %}
            <a class="btn" href="{{ url_for('cart') }}">My Cart</a>
            <a class="btn outline" href="{{ url_for('my_orders') }}">My Orders</a>
        {% else %}
            <a class="btn" href="{{ url_for('seller_dashboard') }}">Seller Dashboard</a>
        {% endif %}

        <h3>Help & Support</h3>
        <p class="muted">For this demo, contact support@craftbridge.example. Replace this with your real support email before deployment.</p>
        <a class="btn dark" href="{{ url_for('logout') }}">Sign out</a>
    </div>
    """
    return page(
        "Settings",
        render_template_string(content, user=user, email=session["email"])
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    # Only serve files from the application's upload directory.
    return send_from_directory(UPLOAD_DIR, filename)


@app.errorhandler(413)
def file_too_large(_error):
    flash("Image is too large. Please upload an image under 8 MB.", "error")
    return redirect(url_for("new_product"))


@app.errorhandler(404)
def page_not_found(_error):
    return page(
        "Page not found",
        '<div class="panel"><h1>Page not found</h1><p>The page you requested does not exist.</p><a class="btn" href="/">Go home</a></div>'
    )


# -------------------- START APPLICATION --------------------

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
