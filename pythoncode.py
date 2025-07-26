from flask import Flask, request, render_template, redirect, url_for, session, flash, g
import sqlite3
import requests
import numpy as np
from scipy.optimize import linear_sum_assignment
import os
import requests.exceptions

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Database connection management
def get_db():
    if 'db' not in g:
        db_path = os.path.join(os.path.dirname(__file__), 'delivery.db')
        g.db = sqlite3.connect(db_path, timeout=30)  # Increased timeout
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# Initialize database
def init_db():
    db_path = os.path.join(os.path.dirname(__file__), 'delivery.db')
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"Old database dropped: {db_path}")
        
        with sqlite3.connect(db_path) as conn:
            c = conn.cursor()
            c.execute('PRAGMA journal_mode=WAL;')  # Enable WAL mode
            c.execute('''CREATE TABLE IF NOT EXISTS users 
                         (id INTEGER PRIMARY KEY, username TEXT, password TEXT, role TEXT, phone TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS orders 
                         (id INTEGER PRIMARY KEY, customer_id INTEGER, rest_name TEXT, 
                          rest_lat REAL, rest_lon REAL, food_lat REAL, food_lon REAL, 
                          item TEXT, status TEXT, rider_id INTEGER, type TEXT)''')
            conn.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    print(f"Database initialized: {db_path}")

init_db()

# Get restaurants from OSM or fallback
def get_osm_restaurants(lat=17.3850, lon=78.4867):  # Default Hyderabad coords
    try:
        query = f"[out:json];node['amenity'='restaurant'](around:5000,{lat},{lon});out body;"
        response = requests.post("http://overpass-api.de/api/interpreter", data={'data': query}, timeout=10).json()
        restaurants = [(node.get('tags', {}).get('name', f"Rest_{node['id']}"), node['lat'], node['lon']) 
                       for node in response['elements']][:10]
        if not restaurants:
            print("DEBUG: OSM returned empty list, using fallback")
            return [("Paradise Biryani", 17.3850, 78.4867), ("Bawarchi", 17.4012, 78.4778), ("Jewel of Nizam", 17.4167, 78.4381)]
        return restaurants
    except requests.exceptions.RequestException as e:
        print(f"OSM API error: {e}")
        return [("Paradise Biryani", 17.3850, 78.4867), ("Bawarchi", 17.4012, 78.4778), ("Jewel of Nizam", 17.4167, 78.4381)]

# Get coordinates for an address
def get_coordinates(address):
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={address}&format=json"
        response = requests.get(url, headers={'User-Agent': 'FoodieRide'}, timeout=10).json()
        if response:
            return float(response[0]['lat']), float(response[0]['lon'])
        print(f"DEBUG: No coordinates found for {address}, using default")
        return 17.3850, 78.4867  # Default Hyderabad
    except requests.exceptions.RequestException as e:
        print(f"Nominatim API error: {e}, using default coordinates")
        return 17.3850, 78.4867

@app.route('/')
def root():
    return redirect(url_for('index'))

@app.route('/index')
def index():
    session.clear()
    print("DEBUG: Session cleared on index")
    return render_template('index.html')

@app.route('/home')
def home():
    if 'user_id' not in session:
        print("DEBUG: Home route - Not logged in, redirecting to login with role=customer")
        return redirect(url_for('login', next='home'))
    if session.get('role') != 'customer':
        session.pop('role', None)
        return redirect(url_for('login', next='home'))
    is_logged_in = True
    username = None
    try:
        db = get_db()
        cursor = db.execute("SELECT username FROM users WHERE id=?", (session['user_id'],))
        user = cursor.fetchone()
        if user:
            username = user['username']
    except sqlite3.Error as e:
        print(f"Database error in home: {e}")
        flash("Error loading user data", "error")
    restaurants = get_osm_restaurants()
    print(f"DEBUG: Home route - is_logged_in={is_logged_in}, username={username}, restaurants={restaurants}")
    return render_template('home.html', is_logged_in=is_logged_in, username=username, restaurants=restaurants)

@app.route('/ride')
def ride():
    if 'user_id' not in session:
        print("DEBUG: Ride route - Not logged in, redirecting to login with role=rider")
        return redirect(url_for('login', next='ride'))
    if session.get('role') != 'rider':
        session.pop('role', None)
        return redirect(url_for('login', next='ride'))
    return render_template('ride.html')

@app.route('/captain')
def captain():
    if 'user_id' not in session:
        print("DEBUG: Captain route - Not logged in, redirecting to login with role=captain")
        return redirect(url_for('login', next='captain'))
    if session.get('role') != 'captain':
        session.pop('role', None)
        return redirect(url_for('login', next='captain'))
    
    try:
        db = get_db()
        cursor = db.execute("SELECT id, rest_name, rest_lat, rest_lon, food_lat, food_lon, item FROM orders WHERE status='pending' AND type='food'")
        pending_orders = cursor.fetchall()
        pending_tasks = [{
            'food_id': order['id'],
            'rest_name': order['rest_name'],
            'rest_lat': order['rest_lat'],
            'rest_lon': order['rest_lon'],
            'food_lat': order['food_lat'],
            'food_lon': order['food_lon'],
            'item': order['item']
        } for order in pending_orders]
        print("DEBUG: Captain route - Loaded with pending tasks:", pending_tasks)
        return render_template('captain.html', pending_tasks=pending_tasks)
    except sqlite3.Error as e:
        print(f"Database error in captain: {e}")
        flash("Error loading tasks", "error")
        return render_template('captain.html', pending_tasks=[])

@app.route('/login', methods=['GET', 'POST'])
def login():
    next_page = request.args.get('next', 'index')
    if request.method == 'POST':
        email_or_phone = request.form.get('email') or request.form.get('phone')
        password = request.form.get('password')
        
        if not email_or_phone or not password:
            return "Please provide email/phone and password!", 400
        
        try:
            db = get_db()
            cursor = db.execute("SELECT * FROM users WHERE username=? AND password=?", (email_or_phone, password))
            user = cursor.fetchone()
            
            if user:
                session['user_id'] = user['id']
                session['role'] = user['role']
                print(f"DEBUG: Login successful - user_id={user['id']}, role={user['role']}")
            else:
                name = request.form.get('name')
                email = request.form.get('email')
                phone = request.form.get('phone')
                if name or email or phone:
                    username = name if name else (email or phone)
                    role = 'customer' if next_page == 'home' else 'rider' if next_page == 'ride' else 'captain'
                    with db:
                        db.execute("INSERT INTO users (username, password, role, phone) VALUES (?, ?, ?, ?)", 
                                   (username, password, role, phone))
                    session['user_id'] = db.execute("SELECT last_insert_rowid()").fetchone()[0]
                    session['role'] = role
                    print(f"DEBUG: New user created - user_id={session['user_id']}, role={role}")
                else:
                    return "Invalid signup details! Provide name, email, or phone.", 400
        except sqlite3.Error as e:
            print(f"Database error in login: {e}")
            flash("Error during login/signup", "error")
            return render_template('login.html', next=next_page)
        
        if next_page == 'home':
            return redirect(url_for('home'))
        elif next_page == 'ride':
            return redirect(url_for('ride'))
        elif next_page == 'captain':
            return redirect(url_for('captain'))
        return redirect(url_for('index'))
    
    return render_template('login.html', next=next_page)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
    print("DEBUG: Logged out, redirecting to index")
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session or session.get('role') != 'customer':
        return redirect(url_for('login', next='home'))
    try:
        restaurants = get_osm_restaurants()
        db = get_db()
        cursor = db.execute("SELECT o.id, o.rest_name, o.food_lat, o.food_lon, o.item, o.status, u.username, u.phone FROM orders o LEFT JOIN users u ON o.rider_id = u.id WHERE o.customer_id=? AND o.type='food'", (session['user_id'],))
        orders = cursor.fetchall()
        print("DEBUG: Dashboard loaded for customer, orders:", orders)
        return render_template('customer_dashboard.html', restaurants=restaurants, orders=orders)
    except sqlite3.Error as e:
        print(f"Database error in dashboard: {e}")
        flash("Error loading dashboard", "error")
        return render_template('customer_dashboard.html', restaurants=[], orders=[])
    except Exception as e:
        print(f"Unexpected error in dashboard: {e}")
        flash("Error loading dashboard", "error")
        return render_template('customer_dashboard.html', restaurants=[], orders=[])

@app.route('/book', methods=['GET', 'POST'])
def book():
    if 'user_id' not in session or session.get('role') != 'customer':
        return redirect(url_for('login', next='home'))
    
    restaurants = get_osm_restaurants()
    print(f"DEBUG: Book route - Available restaurants: {restaurants}")
    
    if request.method == 'POST':
        order_type = request.form.get('order_type')
        print(f"DEBUG: Booking - order_type={order_type}")
        
        if order_type == 'food':
            rest_name = request.form.get('restaurant', '').strip()
            food_address = request.form.get('food_address', 'Hyderabad').strip()
            item = request.form.get('item', '').strip()
            
            if not rest_name:
                print("DEBUG: No restaurant name provided")
                flash("Please select a restaurant!", "error")
                return render_template('book.html', restaurants=restaurants)
            
            if not item:
                print("DEBUG: No item provided")
                flash("Please specify an item!", "error")
                return render_template('book.html', restaurants=restaurants)
            
            # Case-insensitive restaurant matching
            rest = next((r for r in restaurants if r[0].lower() == rest_name.lower()), None)
            if not rest:
                print(f"DEBUG: Restaurant '{rest_name}' not found in {[(r[0]) for r in restaurants]}")
                flash(f"Restaurant '{rest_name}' not found!", "error")
                return render_template('book.html', restaurants=restaurants)
            
            food_lat, food_lon = get_coordinates(food_address)
            rest_lat, rest_lon = rest[1], rest[2]
            rest_name = rest[0]  # Use the exact name from the restaurants list
            print(f"DEBUG: Food order - rest_name={rest_name}, food_address={food_address}, item={item}, coords=({food_lat}, {food_lon})")
        
            try:
                db = get_db()
                with db:
                    db.execute("INSERT INTO orders (customer_id, rest_name, rest_lat, rest_lon, food_lat, food_lon, item, status, type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (session['user_id'], rest_name, rest_lat, rest_lon, food_lat, food_lon, item, 'pending', order_type))
                print("DEBUG: Order booked successfully, redirecting to dashboard")
                flash("Order placed successfully!", "success")
                return redirect(url_for('dashboard'))
            except sqlite3.Error as e:
                print(f"Database error in book: {e}")
                flash("Error booking order", "error")
                return render_template('book.html', restaurants=restaurants)
    
    return render_template('book.html', restaurants=restaurants)

@app.route('/accept', methods=['POST'])
def accept():
    if 'user_id' not in session or session.get('role') != 'captain':
        return redirect(url_for('login', next='captain'))
    
    food_id = request.form.get('food_id')
    try:
        db = get_db()
        with db:
            cursor = db.execute("SELECT customer_id FROM orders WHERE id=?", (food_id,))
            food_customer = cursor.fetchone()
            if food_customer:
                db.execute("UPDATE orders SET status='accepted', rider_id=? WHERE id=?", (session['user_id'], food_id))
                flash(f"Captain assigned to your food order (ID: {food_id})!", category=f"food_{food_customer['customer_id']}")
                print(f"DEBUG: Food order accepted - food_id={food_id}, food_customer={food_customer['customer_id']}")
            else:
                flash("Order not found", "error")
                print(f"DEBUG: Food order not found - food_id={food_id}")
        return redirect(url_for('captain'))
    except sqlite3.Error as e:
        print(f"Database error in accept: {e}")
        flash("Error accepting order", "error")
        return redirect(url_for('captain'))

if __name__ == '__main__':
    app.run(debug=True, threaded=False)  # Single-threaded for development