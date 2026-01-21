# admin_app.py - COMPLETE ADMIN ORDERS MANAGEMENT WEBSITE
import os
from datetime import datetime, timedelta
import json
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
import pytz
from functools import wraps
import logging
from logging.handlers import RotatingFileHandler

# ✅ CLOUDINARY IMPORTS
import cloudinary
import cloudinary.uploader
import cloudinary.api

# ✅ LOAD ENVIRONMENT VARIABLES
load_dotenv()

# ✅ TIMEZONE CONFIGURATION
IST_TIMEZONE = pytz.timezone('Asia/Kolkata')
UTC_TIMEZONE = pytz.utc

# ✅ TIMEZONE HELPER FUNCTIONS
def ist_now():
    """Returns current time in IST timezone"""
    utc_now = datetime.now(UTC_TIMEZONE)
    return utc_now.astimezone(IST_TIMEZONE)

def to_ist(datetime_obj):
    """Convert any datetime object to IST timezone safely"""
    if datetime_obj is None:
        return None
    if datetime_obj.tzinfo is not None:
        return datetime_obj.astimezone(IST_TIMEZONE)
    return UTC_TIMEZONE.localize(datetime_obj).astimezone(IST_TIMEZONE)

def format_ist_datetime(datetime_obj, format_str="%d %b %Y, %I:%M %p"):
    """Format datetime in IST"""
    ist_time = to_ist(datetime_obj)
    if ist_time:
        return ist_time.strftime(format_str)
    return ""

# ✅ LOGGING SETUP
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('AdminOrders')
handler = RotatingFileHandler('admin_orders.log', maxBytes=10000, backupCount=3)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# ✅ FLASK APP SETUP
app = Flask(__name__, 
    template_folder='templates',
    static_folder='static',
    static_url_path='/static'
)
app.secret_key = os.environ.get('ADMIN_SECRET_KEY', 'admin-secret-key-change-in-production')
app.config['SESSION_TYPE'] = 'filesystem'

# ✅ CLOUDINARY CONFIGURATION
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    secure=True
)

# ✅ GOOGLE MAPS CONFIG
GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY', 'AIzaSyBmZG2Xi5WNXsEbY1gj4MQ6PKnS0gu1S4s')

# ✅ DATABASE FUNCTIONS
def get_db_connection():
    """Establish database connection using DATABASE_URL from environment"""
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not set")
    
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    try:
        conn = psycopg.connect(database_url, row_factory=dict_row)
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise

def init_admin_tables():
    """Initialize admin-specific tables if they don't exist"""
    try:
        logger.info("🔗 Initializing admin tables...")
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # ✅ 1. ADMIN USERS TABLE
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'admin_users'
                    )
                """)
                admin_table_exists = cur.fetchone()['exists']
                
                if not admin_table_exists:
                    logger.info("📦 Creating admin_users table...")
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS admin_users (
                            id SERIAL PRIMARY KEY,
                            username VARCHAR(50) UNIQUE NOT NULL,
                            email VARCHAR(100) UNIQUE NOT NULL,
                            password VARCHAR(255) NOT NULL,
                            full_name VARCHAR(100),
                            role VARCHAR(20) DEFAULT 'admin',
                            is_active BOOLEAN DEFAULT TRUE,
                            last_login TIMESTAMP,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    
                    # ✅ 2. ORDER_STATUS_LOG TABLE
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS order_status_log (
                            log_id SERIAL PRIMARY KEY,
                            order_id INTEGER REFERENCES orders(order_id) ON DELETE CASCADE,
                            admin_id INTEGER REFERENCES admin_users(id),
                            old_status VARCHAR(20),
                            new_status VARCHAR(20),
                            notes TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    
                    # ✅ 3. PAYMENT_STATUS_LOG TABLE
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS payment_status_log (
                            log_id SERIAL PRIMARY KEY,
                            payment_id INTEGER REFERENCES payments(payment_id) ON DELETE CASCADE,
                            admin_id INTEGER REFERENCES admin_users(id),
                            old_status VARCHAR(20),
                            new_status VARCHAR(20),
                            notes TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    
                    # Create default admin user
                    default_password = generate_password_hash('admin123')
                    cur.execute("""
                        INSERT INTO admin_users (username, email, password, full_name, role)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (username) DO NOTHING
                    """, ('admin', 'admin@bitemebuddy.com', default_password, 'Administrator', 'superadmin'))
                    
                    conn.commit()
                    logger.info("✅ Admin tables created successfully!")
                else:
                    logger.info("✅ Admin tables already exist")
                    
    except Exception as e:
        logger.error(f"❌ Error initializing admin tables: {e}")
        raise

# ✅ INITIALIZE ON STARTUP
try:
    init_admin_tables()
    logger.info("✅ Admin database initialization completed!")
except Exception as e:
    logger.error(f"⚠️ Admin database initialization failed: {e}")

# ✅ ADMIN LOGIN REQUIRED DECORATOR
def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please login as admin to access this page', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# ✅ HELPER FUNCTIONS
def get_today_date_range():
    """Get today's date range in IST"""
    ist_now = datetime.now(IST_TIMEZONE)
    start_of_day = ist_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = ist_now.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Convert to UTC for database query
    start_utc = start_of_day.astimezone(UTC_TIMEZONE)
    end_utc = end_of_day.astimezone(UTC_TIMEZONE)
    
    return start_utc, end_utc

def get_week_date_range():
    """Get this week's date range"""
    ist_now = datetime.now(IST_TIMEZONE)
    start_of_week = ist_now - timedelta(days=ist_now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)
    
    start_utc = start_of_week.astimezone(UTC_TIMEZONE)
    end_utc = end_of_week.astimezone(UTC_TIMEZONE)
    
    return start_utc, end_utc

def get_month_date_range():
    """Get this month's date range"""
    ist_now = datetime.now(IST_TIMEZONE)
    start_of_month = ist_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    if ist_now.month == 12:
        end_of_month = ist_now.replace(year=ist_now.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end_of_month = ist_now.replace(month=ist_now.month + 1, day=1) - timedelta(days=1)
    
    end_of_month = end_of_month.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    start_utc = start_of_month.astimezone(UTC_TIMEZONE)
    end_utc = end_of_month.astimezone(UTC_TIMEZONE)
    
    return start_utc, end_utc

def generate_google_maps_link(latitude, longitude):
    """Generate Google Maps link from coordinates"""
    if latitude and longitude:
        return f"https://www.google.com/maps?q={latitude},{longitude}"
    return None

def get_cloudinary_image(item_type, item_id, item_name):
    """Get Cloudinary image for item"""
    try:
        folder = "services" if item_type == 'service' else "menu_items"
        search_name = item_name.lower().replace(' ', '_')
        
        search_result = cloudinary.Search()\
            .expression(f"folder:{folder} AND filename:{search_name}*")\
            .execute()
        
        if search_result['resources']:
            return search_result['resources'][0]['secure_url']
        
        # Fallback search
        words = item_name.lower().split()
        for word in words:
            if len(word) > 3:
                search_result = cloudinary.Search()\
                    .expression(f"folder:{folder} AND filename:*{word}*")\
                    .execute()
                
                if search_result['resources']:
                    return search_result['resources'][0]['secure_url']
        
    except Exception as e:
        logger.error(f"Cloudinary search error: {e}")
    
    # Default images
    if item_type == 'service':
        return "https://res.cloudinary.com/demo/image/upload/v1633427556/sample_service.jpg"
    else:
        return "https://res.cloudinary.com/demo/image/upload/v1633427556/sample_food.jpg"

# ============================================
# ✅ AUTHENTICATION ROUTES
# ============================================

@app.route('/admin')
def admin_home():
    if 'admin_id' in session:
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('admin_login'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            flash('Username and password are required', 'error')
            return render_template('admin_login.html')
        
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT * FROM admin_users 
                        WHERE username = %s AND is_active = TRUE
                    """, (username,))
                    admin = cur.fetchone()
                    
                    if admin and check_password_hash(admin['password'], password):
                        # Update last login
                        cur.execute("""
                            UPDATE admin_users 
                            SET last_login = CURRENT_TIMESTAMP 
                            WHERE id = %s
                        """, (admin['id'],))
                        
                        # Set session
                        session['admin_id'] = admin['id']
                        session['admin_username'] = admin['username']
                        session['admin_email'] = admin['email']
                        session['admin_name'] = admin['full_name']
                        session['admin_role'] = admin['role']
                        
                        conn.commit()
                        
                        logger.info(f"✅ Admin login: {username}")
                        flash('Login successful!', 'success')
                        return redirect(url_for('admin_dashboard'))
                    else:
                        flash('Invalid username or password', 'error')
                        return render_template('admin_login.html')
                        
        except Exception as e:
            logger.error(f"Admin login error: {e}")
            flash(f'Login failed: {str(e)}', 'error')
            return render_template('admin_login.html')
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('admin_login'))

# ============================================
# ✅ DASHBOARD ROUTES
# ============================================

@app.route('/admin/dashboard')
@admin_login_required
def admin_dashboard():
    """Admin dashboard with today's orders and statistics"""
    try:
        time_filter = request.args.get('filter', 'today')
        
        # Get date range based on filter
        if time_filter == 'today':
            start_date, end_date = get_today_date_range()
            date_label = "Today"
        elif time_filter == 'week':
            start_date, end_date = get_week_date_range()
            date_label = "This Week"
        elif time_filter == 'month':
            start_date, end_date = get_month_date_range()
            date_label = "This Month"
        else:  # all time
            start_date = None
            end_date = None
            date_label = "All Time"
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get today's orders
                if start_date and end_date:
                    cur.execute("""
                        SELECT 
                            o.order_id,
                            o.user_name,
                            o.total_amount,
                            o.status,
                            o.order_date,
                            o.payment_mode,
                            p.payment_status
                        FROM orders o
                        LEFT JOIN payments p ON o.order_id = p.order_id
                        WHERE o.order_date BETWEEN %s AND %s
                        ORDER BY o.order_date DESC
                        LIMIT 20
                    """, (start_date, end_date))
                else:
                    cur.execute("""
                        SELECT 
                            o.order_id,
                            o.user_name,
                            o.total_amount,
                            o.status,
                            o.order_date,
                            o.payment_mode,
                            p.payment_status
                        FROM orders o
                        LEFT JOIN payments p ON o.order_id = p.order_id
                        ORDER BY o.order_date DESC
                        LIMIT 20
                    """)
                
                todays_orders = cur.fetchall()
                
                # Format dates
                for order in todays_orders:
                    order['order_date_formatted'] = format_ist_datetime(order['order_date'])
                
                # Get statistics
                if start_date and end_date:
                    # Total orders count
                    cur.execute("""
                        SELECT COUNT(*) as total_orders,
                               SUM(total_amount) as total_revenue,
                               AVG(total_amount) as avg_order_value
                        FROM orders 
                        WHERE order_date BETWEEN %s AND %s
                    """, (start_date, end_date))
                else:
                    cur.execute("""
                        SELECT COUNT(*) as total_orders,
                               SUM(total_amount) as total_revenue,
                               AVG(total_amount) as avg_order_value
                        FROM orders
                    """)
                
                stats = cur.fetchone()
                
                # Get orders by status
                if start_date and end_date:
                    cur.execute("""
                        SELECT status, COUNT(*) as count
                        FROM orders
                        WHERE order_date BETWEEN %s AND %s
                        GROUP BY status
                    """, (start_date, end_date))
                else:
                    cur.execute("""
                        SELECT status, COUNT(*) as count
                        FROM orders
                        GROUP BY status
                    """)
                
                status_stats = cur.fetchall()
                
                # Get most ordered items
                if start_date and end_date:
                    cur.execute("""
                        SELECT 
                            oi.item_name,
                            oi.item_type,
                            SUM(oi.quantity) as total_quantity,
                            SUM(oi.total) as total_revenue
                        FROM order_items oi
                        JOIN orders o ON oi.order_id = o.order_id
                        WHERE o.order_date BETWEEN %s AND %s
                        GROUP BY oi.item_name, oi.item_type
                        ORDER BY total_quantity DESC
                        LIMIT 10
                    """, (start_date, end_date))
                else:
                    cur.execute("""
                        SELECT 
                            oi.item_name,
                            oi.item_type,
                            SUM(oi.quantity) as total_quantity,
                            SUM(oi.total) as total_revenue
                        FROM order_items oi
                        GROUP BY oi.item_name, oi.item_type
                        ORDER BY total_quantity DESC
                        LIMIT 10
                    """)
                
                top_items = cur.fetchall()
                
                # Get daily revenue for chart
                if start_date and end_date:
                    cur.execute("""
                        SELECT 
                            DATE(order_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata') as order_day,
                            SUM(total_amount) as daily_revenue,
                            COUNT(*) as order_count
                        FROM orders
                        WHERE order_date BETWEEN %s AND %s
                        GROUP BY order_day
                        ORDER BY order_day
                    """, (start_date, end_date))
                else:
                    cur.execute("""
                        SELECT 
                            DATE(order_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata') as order_day,
                            SUM(total_amount) as daily_revenue,
                            COUNT(*) as order_count
                        FROM orders
                        GROUP BY order_day
                        ORDER BY order_day
                        LIMIT 30
                    """)
                
                revenue_data = cur.fetchall()
                
        # Prepare chart data
        chart_labels = [row['order_day'].strftime('%d %b') for row in revenue_data]
        chart_revenue = [float(row['daily_revenue']) for row in revenue_data]
        chart_orders = [row['order_count'] for row in revenue_data]
        
        # Prepare status chart data
        status_labels = [row['status'] for row in status_stats]
        status_counts = [row['count'] for row in status_stats]
        
        # Prepare top items chart data
        item_names = [f"{row['item_name'][:15]}..." if len(row['item_name']) > 15 else row['item_name'] 
                     for row in top_items]
        item_quantities = [row['total_quantity'] for row in top_items]
        
        return render_template('admin_dashboard.html',
                             todays_orders=todays_orders,
                             stats=stats,
                             status_stats=status_stats,
                             top_items=top_items,
                             chart_labels=chart_labels,
                             chart_revenue=chart_revenue,
                             chart_orders=chart_orders,
                             status_labels=status_labels,
                             status_counts=status_counts,
                             item_names=item_names,
                             item_quantities=item_quantities,
                             time_filter=time_filter,
                             date_label=date_label,
                             google_maps_api_key=GOOGLE_MAPS_API_KEY)
        
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return render_template('admin_dashboard.html',
                             todays_orders=[],
                             stats={},
                             status_stats=[],
                             top_items=[],
                             chart_labels=[],
                             chart_revenue=[],
                             chart_orders=[],
                             status_labels=[],
                             status_counts=[],
                             item_names=[],
                             item_quantities=[],
                             time_filter='today',
                             date_label='Today')

# ============================================
# ✅ ORDERS MANAGEMENT ROUTES
# ============================================

@app.route('/admin/orders')
@admin_login_required
def admin_orders():
    """List all orders with pagination and filters"""
    try:
        page = int(request.args.get('page', 1))
        per_page = 20
        offset = (page - 1) * per_page
        
        status_filter = request.args.get('status', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        search = request.args.get('search', '')
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Build dynamic WHERE clause
                conditions = []
                params = []
                
                if status_filter:
                    conditions.append("o.status = %s")
                    params.append(status_filter)
                
                if date_from:
                    try:
                        date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                        date_from_utc = IST_TIMEZONE.localize(date_from_obj).astimezone(UTC_TIMEZONE)
                        conditions.append("o.order_date >= %s")
                        params.append(date_from_utc)
                    except ValueError:
                        pass
                
                if date_to:
                    try:
                        date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
                        date_to_obj = date_to_obj.replace(hour=23, minute=59, second=59)
                        date_to_utc = IST_TIMEZONE.localize(date_to_obj).astimezone(UTC_TIMEZONE)
                        conditions.append("o.order_date <= %s")
                        params.append(date_to_utc)
                    except ValueError:
                        pass
                
                if search:
                    conditions.append("""
                        (o.user_name ILIKE %s OR 
                         o.user_phone ILIKE %s OR 
                         o.order_id::TEXT LIKE %s)
                    """)
                    params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
                
                where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
                
                # Get total count
                count_query = f"""
                    SELECT COUNT(*) as total 
                    FROM orders o
                    {where_clause}
                """
                cur.execute(count_query, params)
                total_result = cur.fetchone()
                total_orders = total_result['total']
                total_pages = (total_orders + per_page - 1) // per_page
                
                # Get orders with pagination
                order_query = f"""
                    SELECT 
                        o.order_id,
                        o.user_id,
                        o.user_name,
                        o.user_email,
                        o.user_phone,
                        o.total_amount,
                        o.status,
                        o.order_date,
                        o.payment_mode,
                        o.delivery_location,
                        p.payment_status,
                        p.transaction_id
                    FROM orders o
                    LEFT JOIN payments p ON o.order_id = p.order_id
                    {where_clause}
                    ORDER BY o.order_date DESC
                    LIMIT %s OFFSET %s
                """
                
                params_with_pagination = params + [per_page, offset]
                cur.execute(order_query, params_with_pagination)
                orders = cur.fetchall()
                
                # Format dates
                for order in orders:
                    order['order_date_formatted'] = format_ist_datetime(order['order_date'])
                    order['total_amount_formatted'] = f"₹{order['total_amount']:,.2f}"
                
        return render_template('admin_orders.html',
                             orders=orders,
                             current_page=page,
                             total_pages=total_pages,
                             total_orders=total_orders,
                             status_filter=status_filter,
                             date_from=date_from,
                             date_to=date_to,
                             search=search)
        
    except Exception as e:
        logger.error(f"Orders list error: {e}")
        flash(f'Error loading orders: {str(e)}', 'error')
        return render_template('admin_orders.html',
                             orders=[],
                             current_page=1,
                             total_pages=0,
                             total_orders=0)

# ============================================
# ✅ ORDER DETAILS MODAL ROUTES
# ============================================

@app.route('/admin/api/order/<int:order_id>')
@admin_login_required
def get_order_details(order_id):
    """Get complete order details for modal"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get order basic info
                cur.execute("""
                    SELECT 
                        o.*,
                        p.payment_status,
                        p.transaction_id,
                        p.payment_date,
                        p.razorpay_order_id,
                        p.razorpay_payment_id,
                        p.razorpay_signature
                    FROM orders o
                    LEFT JOIN payments p ON o.order_id = p.order_id
                    WHERE o.order_id = %s
                """, (order_id,))
                
                order = cur.fetchone()
                
                if not order:
                    return jsonify({'success': False, 'message': 'Order not found'})
                
                # Format dates
                order['order_date_formatted'] = format_ist_datetime(order['order_date'])
                if order.get('delivery_date'):
                    order['delivery_date_formatted'] = format_ist_datetime(order['delivery_date'])
                if order.get('payment_date'):
                    order['payment_date_formatted'] = format_ist_datetime(order['payment_date'])
                
                # Get order items
                cur.execute("""
                    SELECT 
                        oi.*,
                        COALESCE(s.photo, m.photo) as db_photo
                    FROM order_items oi
                    LEFT JOIN services s ON oi.item_type = 'service' AND oi.item_id = s.id
                    LEFT JOIN menu m ON oi.item_type = 'menu' AND oi.item_id = m.id
                    WHERE oi.order_id = %s
                    ORDER BY oi.order_item_id
                """, (order_id,))
                
                order_items = cur.fetchall()
                
                # Get Cloudinary images for items
                for item in order_items:
                    if item['db_photo'] and item['db_photo'].startswith('http'):
                        item['photo'] = item['db_photo']
                    else:
                        item['photo'] = get_cloudinary_image(
                            item['item_type'], 
                            item['item_id'], 
                            item['item_name']
                        )
                    
                    item['item_total_formatted'] = f"₹{item['total']:,.2f}"
                    item['price_formatted'] = f"₹{item['price']:,.2f}"
                
                # Get status log
                cur.execute("""
                    SELECT 
                        l.*,
                        a.username as admin_username,
                        a.full_name as admin_name
                    FROM order_status_log l
                    LEFT JOIN admin_users a ON l.admin_id = a.id
                    WHERE l.order_id = %s
                    ORDER BY l.created_at DESC
                """, (order_id,))
                
                status_log = cur.fetchall()
                
                for log in status_log:
                    log['created_at_formatted'] = format_ist_datetime(log['created_at'])
                
                return jsonify({
                    'success': True,
                    'order': order,
                    'order_items': order_items,
                    'status_log': status_log
                })
                
    except Exception as e:
        logger.error(f"Order details error: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/api/payment/<int:order_id>')
@admin_login_required
def get_payment_details(order_id):
    """Get payment details for modal"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get payment info
                cur.execute("""
                    SELECT 
                        p.*,
                        o.total_amount,
                        o.user_name,
                        o.user_email,
                        o.user_phone
                    FROM payments p
                    JOIN orders o ON p.order_id = o.order_id
                    WHERE p.order_id = %s
                """, (order_id,))
                
                payment = cur.fetchone()
                
                if not payment:
                    return jsonify({'success': False, 'message': 'Payment not found'})
                
                # Format dates
                if payment.get('payment_date'):
                    payment['payment_date_formatted'] = format_ist_datetime(payment['payment_date'])
                
                # Get payment status log
                cur.execute("""
                    SELECT 
                        l.*,
                        a.username as admin_username,
                        a.full_name as admin_name
                    FROM payment_status_log l
                    LEFT JOIN admin_users a ON l.admin_id = a.id
                    WHERE l.payment_id = %s
                    ORDER BY l.created_at DESC
                """, (payment['payment_id'],))
                
                payment_log = cur.fetchall()
                
                for log in payment_log:
                    log['created_at_formatted'] = format_ist_datetime(log['created_at'])
                
                return jsonify({
                    'success': True,
                    'payment': payment,
                    'payment_log': payment_log
                })
                
    except Exception as e:
        logger.error(f"Payment details error: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/api/customer/<int:user_id>')
@admin_login_required
def get_customer_details(user_id):
    """Get customer details for modal"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get user info
                cur.execute("""
                    SELECT 
                        u.*,
                        COUNT(o.order_id) as total_orders,
                        SUM(o.total_amount) as total_spent,
                        MAX(o.order_date) as last_order_date
                    FROM users u
                    LEFT JOIN orders o ON u.id = o.user_id
                    WHERE u.id = %s
                    GROUP BY u.id
                """, (user_id,))
                
                customer = cur.fetchone()
                
                if not customer:
                    return jsonify({'success': False, 'message': 'Customer not found'})
                
                # Format dates
                if customer.get('created_at'):
                    customer['created_at_formatted'] = format_ist_datetime(customer['created_at'])
                if customer.get('last_login'):
                    customer['last_login_formatted'] = format_ist_datetime(customer['last_login'])
                if customer.get('last_order_date'):
                    customer['last_order_date_formatted'] = format_ist_datetime(customer['last_order_date'])
                
                # Get addresses
                cur.execute("""
                    SELECT * FROM addresses 
                    WHERE user_id = %s 
                    ORDER BY is_default DESC, created_at DESC
                """, (user_id,))
                
                addresses = cur.fetchall()
                
                # Add Google Maps links
                for address in addresses:
                    if address.get('latitude') and address.get('longitude'):
                        address['maps_link'] = generate_google_maps_link(
                            address['latitude'], 
                            address['longitude']
                        )
                
                # Get recent orders
                cur.execute("""
                    SELECT 
                        order_id,
                        total_amount,
                        status,
                        order_date,
                        payment_mode
                    FROM orders 
                    WHERE user_id = %s 
                    ORDER BY order_date DESC 
                    LIMIT 5
                """, (user_id,))
                
                recent_orders = cur.fetchall()
                
                for order in recent_orders:
                    order['order_date_formatted'] = format_ist_datetime(order['order_date'])
                    order['total_amount_formatted'] = f"₹{order['total_amount']:,.2f}"
                
                return jsonify({
                    'success': True,
                    'customer': customer,
                    'addresses': addresses,
                    'recent_orders': recent_orders
                })
                
    except Exception as e:
        logger.error(f"Customer details error: {e}")
        return jsonify({'success': False, 'message': str(e)})

# ============================================
# ✅ ORDER UPDATE ROUTES
# ============================================

@app.route('/admin/api/update-order-status', methods=['POST'])
@admin_login_required
def update_order_status():
    """Update order status and log the change"""
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        new_status = data.get('status')
        notes = data.get('notes', '')
        
        if not order_id or not new_status:
            return jsonify({'success': False, 'message': 'Missing required fields'})
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get current status
                cur.execute("""
                    SELECT status FROM orders WHERE order_id = %s
                """, (order_id,))
                
                order = cur.fetchone()
                if not order:
                    return jsonify({'success': False, 'message': 'Order not found'})
                
                old_status = order['status']
                
                # Update order status
                cur.execute("""
                    UPDATE orders 
                    SET status = %s 
                    WHERE order_id = %s
                """, (new_status, order_id))
                
                # Log status change
                cur.execute("""
                    INSERT INTO order_status_log 
                    (order_id, admin_id, old_status, new_status, notes)
                    VALUES (%s, %s, %s, %s, %s)
                """, (order_id, session['admin_id'], old_status, new_status, notes))
                
                conn.commit()
                
                logger.info(f"Order #{order_id} status updated: {old_status} → {new_status} by admin {session['admin_username']}")
                
                return jsonify({
                    'success': True,
                    'message': 'Order status updated successfully'
                })
                
    except Exception as e:
        logger.error(f"Update order status error: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/api/update-payment-status', methods=['POST'])
@admin_login_required
def update_payment_status():
    """Update payment status and log the change"""
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        payment_status = data.get('payment_status')
        transaction_id = data.get('transaction_id', '')
        notes = data.get('notes', '')
        
        if not order_id or not payment_status:
            return jsonify({'success': False, 'message': 'Missing required fields'})
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get current payment status
                cur.execute("""
                    SELECT payment_id, payment_status 
                    FROM payments 
                    WHERE order_id = %s
                """, (order_id,))
                
                payment = cur.fetchone()
                if not payment:
                    return jsonify({'success': False, 'message': 'Payment not found'})
                
                old_status = payment['payment_status']
                
                # Update payment
                update_data = {
                    'payment_status': payment_status,
                    'payment_id': payment['payment_id']
                }
                
                update_fields = ["payment_status = %(payment_status)s"]
                
                if transaction_id:
                    update_fields.append("transaction_id = %(transaction_id)s")
                    update_data['transaction_id'] = transaction_id
                
                update_query = f"""
                    UPDATE payments 
                    SET {', '.join(update_fields)}
                    WHERE payment_id = %(payment_id)s
                """
                
                cur.execute(update_query, update_data)
                
                # Log status change
                cur.execute("""
                    INSERT INTO payment_status_log 
                    (payment_id, admin_id, old_status, new_status, notes)
                    VALUES (%s, %s, %s, %s, %s)
                """, (payment['payment_id'], session['admin_id'], old_status, payment_status, notes))
                
                conn.commit()
                
                logger.info(f"Payment for order #{order_id} status updated: {old_status} → {payment_status} by admin {session['admin_username']}")
                
                return jsonify({
                    'success': True,
                    'message': 'Payment status updated successfully'
                })
                
    except Exception as e:
        logger.error(f"Update payment status error: {e}")
        return jsonify({'success': False, 'message': str(e)})

# ============================================
# ✅ STATISTICS ROUTES
# ============================================

@app.route('/admin/statistics')
@admin_login_required
def admin_statistics():
    """Advanced statistics page with charts"""
    try:
        chart_type = request.args.get('chart', 'revenue')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Build date filter
                conditions = []
                params = []
                
                if date_from:
                    try:
                        date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                        date_from_utc = IST_TIMEZONE.localize(date_from_obj).astimezone(UTC_TIMEZONE)
                        conditions.append("o.order_date >= %s")
                        params.append(date_from_utc)
                    except ValueError:
                        pass
                
                if date_to:
                    try:
                        date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
                        date_to_obj = date_to_obj.replace(hour=23, minute=59, second=59)
                        date_to_utc = IST_TIMEZONE.localize(date_to_obj).astimezone(UTC_TIMEZONE)
                        conditions.append("o.order_date <= %s")
                        params.append(date_to_utc)
                    except ValueError:
                        pass
                
                where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
                
                # Revenue by day
                revenue_query = f"""
                    SELECT 
                        DATE(o.order_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata') as order_day,
                        SUM(o.total_amount) as daily_revenue,
                        COUNT(*) as order_count,
                        AVG(o.total_amount) as avg_order_value
                    FROM orders o
                    {where_clause}
                    GROUP BY order_day
                    ORDER BY order_day
                """
                
                cur.execute(revenue_query, params)
                revenue_data = cur.fetchall()
                
                # Revenue by hour
                hour_query = f"""
                    SELECT 
                        EXTRACT(HOUR FROM o.order_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata') as order_hour,
                        SUM(o.total_amount) as hourly_revenue,
                        COUNT(*) as order_count
                    FROM orders o
                    {where_clause}
                    GROUP BY order_hour
                    ORDER BY order_hour
                """
                
                cur.execute(hour_query, params)
                hourly_data = cur.fetchall()
                
                # Top customers
                top_customers_query = f"""
                    SELECT 
                        o.user_id,
                        o.user_name,
                        o.user_email,
                        COUNT(o.order_id) as order_count,
                        SUM(o.total_amount) as total_spent,
                        AVG(o.total_amount) as avg_order_value
                    FROM orders o
                    {where_clause}
                    GROUP BY o.user_id, o.user_name, o.user_email
                    ORDER BY total_spent DESC
                    LIMIT 10
                """
                
                cur.execute(top_customers_query, params)
                top_customers = cur.fetchall()
                
                # Top items
                top_items_query = f"""
                    SELECT 
                        oi.item_name,
                        oi.item_type,
                        SUM(oi.quantity) as total_quantity,
                        SUM(oi.total) as total_revenue,
                        COUNT(DISTINCT oi.order_id) as order_count
                    FROM order_items oi
                    JOIN orders o ON oi.order_id = o.order_id
                    {where_clause}
                    GROUP BY oi.item_name, oi.item_type
                    ORDER BY total_quantity DESC
                    LIMIT 15
                """
                
                cur.execute(top_items_query, params)
                top_items = cur.fetchall()
                
                # Payment methods
                payment_methods_query = f"""
                    SELECT 
                        o.payment_mode,
                        COUNT(*) as order_count,
                        SUM(o.total_amount) as total_amount
                    FROM orders o
                    {where_clause}
                    GROUP BY o.payment_mode
                    ORDER BY total_amount DESC
                """
                
                cur.execute(payment_methods_query, params)
                payment_methods = cur.fetchall()
                
        # Prepare chart data
        revenue_labels = [row['order_day'].strftime('%d %b') for row in revenue_data]
        revenue_values = [float(row['daily_revenue']) for row in revenue_data]
        order_counts = [row['order_count'] for row in revenue_data]
        
        # Hourly data
        hourly_labels = [f"{int(row['order_hour']):02d}:00" for row in hourly_data]
        hourly_values = [float(row['hourly_revenue']) for row in hourly_data]
        
        # Top customers data
        customer_names = [row['user_name'] for row in top_customers]
        customer_spent = [float(row['total_spent']) for row in top_customers]
        
        # Top items data
        item_names = [f"{row['item_name'][:20]}..." if len(row['item_name']) > 20 else row['item_name'] 
                     for row in top_items]
        item_quantities = [row['total_quantity'] for row in top_items]
        item_revenue = [float(row['total_revenue']) for row in top_items]
        
        # Payment methods data
        payment_labels = [row['payment_mode'] for row in payment_methods]
        payment_amounts = [float(row['total_amount']) for row in payment_methods]
        payment_counts = [row['order_count'] for row in payment_methods]
        
        return render_template('admin_statistics.html',
                             chart_type=chart_type,
                             date_from=date_from,
                             date_to=date_to,
                             revenue_labels=revenue_labels,
                             revenue_values=revenue_values,
                             order_counts=order_counts,
                             hourly_labels=hourly_labels,
                             hourly_values=hourly_values,
                             customer_names=customer_names,
                             customer_spent=customer_spent,
                             item_names=item_names,
                             item_quantities=item_quantities,
                             item_revenue=item_revenue,
                             payment_labels=payment_labels,
                             payment_amounts=payment_amounts,
                             payment_counts=payment_counts,
                             top_customers=top_customers,
                             top_items=top_items,
                             payment_methods=payment_methods,
                             revenue_data=revenue_data)
        
    except Exception as e:
        logger.error(f"Statistics error: {e}")
        flash(f'Error loading statistics: {str(e)}', 'error')
        return render_template('admin_statistics.html',
                             chart_type='revenue',
                             date_from='',
                             date_to='',
                             revenue_labels=[],
                             revenue_values=[],
                             order_counts=[],
                             hourly_labels=[],
                             hourly_values=[],
                             customer_names=[],
                             customer_spent=[],
                             item_names=[],
                             item_quantities=[],
                             item_revenue=[],
                             payment_labels=[],
                             payment_amounts=[],
                             payment_counts=[],
                             top_customers=[],
                             top_items=[],
                             payment_methods=[],
                             revenue_data=[])

# ============================================
# ✅ CUSTOMERS MANAGEMENT ROUTES
# ============================================

@app.route('/admin/customers')
@admin_login_required
def admin_customers():
    """List all customers"""
    try:
        page = int(request.args.get('page', 1))
        per_page = 20
        offset = (page - 1) * per_page
        
        search = request.args.get('search', '')
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Build search conditions
                conditions = ["u.is_active = TRUE"]
                params = []
                
                if search:
                    conditions.append("""
                        (u.full_name ILIKE %s OR 
                         u.phone ILIKE %s OR 
                         u.email ILIKE %s)
                    """)
                    params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
                
                where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
                
                # Get total count
                count_query = f"""
                    SELECT COUNT(*) as total 
                    FROM users u
                    {where_clause}
                """
                cur.execute(count_query, params)
                total_result = cur.fetchone()
                total_customers = total_result['total']
                total_pages = (total_customers + per_page - 1) // per_page
                
                # Get customers with stats
                customers_query = f"""
                    SELECT 
                        u.*,
                        COUNT(o.order_id) as total_orders,
                        COALESCE(SUM(o.total_amount), 0) as total_spent,
                        MAX(o.order_date) as last_order_date
                    FROM users u
                    LEFT JOIN orders o ON u.id = o.user_id
                    {where_clause}
                    GROUP BY u.id
                    ORDER BY u.created_at DESC
                    LIMIT %s OFFSET %s
                """
                
                params_with_pagination = params + [per_page, offset]
                cur.execute(customers_query, params_with_pagination)
                customers = cur.fetchall()
                
                # Format dates and amounts
                for customer in customers:
                    if customer.get('created_at'):
                        customer['created_at_formatted'] = format_ist_datetime(customer['created_at'])
                    if customer.get('last_login'):
                        customer['last_login_formatted'] = format_ist_datetime(customer['last_login'])
                    if customer.get('last_order_date'):
                        customer['last_order_date_formatted'] = format_ist_datetime(customer['last_order_date'])
                    
                    customer['total_spent_formatted'] = f"₹{customer['total_spent']:,.2f}"
                
        return render_template('admin_customers.html',
                             customers=customers,
                             current_page=page,
                             total_pages=total_pages,
                             total_customers=total_customers,
                             search=search)
        
    except Exception as e:
        logger.error(f"Customers list error: {e}")
        flash(f'Error loading customers: {str(e)}', 'error')
        return render_template('admin_customers.html',
                             customers=[],
                             current_page=1,
                             total_pages=0,
                             total_customers=0)

# ============================================
# ✅ SEARCH API ROUTES
# ============================================

@app.route('/admin/api/search')
@admin_login_required
def search_api():
    """Search API for orders, customers, and items"""
    try:
        query = request.args.get('q', '')
        search_type = request.args.get('type', 'all')
        
        if not query or len(query) < 2:
            return jsonify({'success': True, 'results': []})
        
        results = []
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if search_type in ['all', 'orders']:
                    # Search orders
                    cur.execute("""
                        SELECT 
                            'order' as type,
                            order_id as id,
                            CONCAT('Order #', order_id) as title,
                            CONCAT('₹', total_amount, ' • ', status) as description,
                            user_name as subtitle,
                            order_date as date
                        FROM orders 
                        WHERE order_id::TEXT LIKE %s 
                           OR user_name ILIKE %s 
                           OR user_phone LIKE %s
                        ORDER BY order_date DESC 
                        LIMIT 5
                    """, [f"%{query}%", f"%{query}%", f"%{query}%"])
                    
                    order_results = cur.fetchall()
                    for result in order_results:
                        result['date_formatted'] = format_ist_datetime(result['date'])
                        result['url'] = f"/admin/orders?search={result['id']}"
                        results.append(result)
                
                if search_type in ['all', 'customers']:
                    # Search customers
                    cur.execute("""
                        SELECT 
                            'customer' as type,
                            id,
                            full_name as title,
                            CONCAT(phone, ' • ', email) as description,
                            location as subtitle,
                            created_at as date
                        FROM users 
                        WHERE full_name ILIKE %s 
                           OR phone LIKE %s 
                           OR email ILIKE %s
                        ORDER BY created_at DESC 
                        LIMIT 5
                    """, [f"%{query}%", f"%{query}%", f"%{query}%"])
                    
                    customer_results = cur.fetchall()
                    for result in customer_results:
                        result['date_formatted'] = format_ist_datetime(result['date'])
                        result['url'] = f"/admin/customers?search={result['id']}"
                        results.append(result)
                
                if search_type in ['all', 'items']:
                    # Search items
                    cur.execute("""
                        SELECT 
                            'service' as type,
                            id,
                            name as title,
                            CONCAT('₹', final_price) as description,
                            category as subtitle,
                            created_at as date
                        FROM services 
                        WHERE name ILIKE %s 
                           OR description ILIKE %s
                        UNION ALL
                        SELECT 
                            'menu' as type,
                            id,
                            name as title,
                            CONCAT('₹', final_price) as description,
                            category as subtitle,
                            created_at as date
                        FROM menu 
                        WHERE name ILIKE %s 
                           OR description ILIKE %s
                        ORDER BY date DESC 
                        LIMIT 5
                    """, [f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"])
                    
                    item_results = cur.fetchall()
                    for result in item_results:
                        result['date_formatted'] = format_ist_datetime(result['date'])
                        result['url'] = f"/admin/services" if result['type'] == 'service' else f"/admin/menu"
                        results.append(result)
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({'success': False, 'message': str(e)})

# ============================================
# ✅ EXPORT ROUTES
# ============================================

@app.route('/admin/export/orders/csv')
@admin_login_required
def export_orders_csv():
    """Export orders to CSV"""
    try:
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Build date filter
                conditions = []
                params = []
                
                if date_from:
                    try:
                        date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                        date_from_utc = IST_TIMEZONE.localize(date_from_obj).astimezone(UTC_TIMEZONE)
                        conditions.append("o.order_date >= %s")
                        params.append(date_from_utc)
                    except ValueError:
                        pass
                
                if date_to:
                    try:
                        date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
                        date_to_obj = date_to_obj.replace(hour=23, minute=59, second=59)
                        date_to_utc = IST_TIMEZONE.localize(date_to_obj).astimezone(UTC_TIMEZONE)
                        conditions.append("o.order_date <= %s")
                        params.append(date_to_utc)
                    except ValueError:
                        pass
                
                where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
                
                # Get orders for export
                query = f"""
                    SELECT 
                        o.order_id,
                        o.user_name,
                        o.user_email,
                        o.user_phone,
                        o.user_address,
                        o.total_amount,
                        o.status,
                        o.payment_mode,
                        o.order_date,
                        o.delivery_location,
                        p.payment_status,
                        p.transaction_id
                    FROM orders o
                    LEFT JOIN payments p ON o.order_id = p.order_id
                    {where_clause}
                    ORDER BY o.order_date DESC
                """
                
                cur.execute(query, params)
                orders = cur.fetchall()
                
                # Create CSV
                import csv
                import io
                
                output = io.StringIO()
                writer = csv.writer(output)
                
                # Write header
                writer.writerow([
                    'Order ID', 'Customer Name', 'Email', 'Phone', 'Address',
                    'Total Amount', 'Status', 'Payment Mode', 'Order Date',
                    'Delivery Location', 'Payment Status', 'Transaction ID'
                ])
                
                # Write data
                for order in orders:
                    writer.writerow([
                        order['order_id'],
                        order['user_name'] or '',
                        order['user_email'] or '',
                        order['user_phone'] or '',
                        order['user_address'] or '',
                        order['total_amount'] or 0,
                        order['status'] or '',
                        order['payment_mode'] or '',
                        format_ist_datetime(order['order_date'], "%Y-%m-%d %H:%M:%S"),
                        order['delivery_location'] or '',
                        order['payment_status'] or '',
                        order['transaction_id'] or ''
                    ])
                
                output.seek(0)
                
                # Create response
                from flask import Response
                filename = f"orders_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                
                return Response(
                    output,
                    mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment;filename={filename}"}
                )
                
    except Exception as e:
        logger.error(f"Export CSV error: {e}")
        flash(f'Error exporting CSV: {str(e)}', 'error')
        return redirect(url_for('admin_orders'))

# ============================================
# ✅ HEALTH CHECK
# ============================================

@app.route('/admin/health')
def admin_health_check():
    """Health check endpoint"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        
        # Check Cloudinary
        try:
            cloudinary.api.ping()
            cloudinary_status = 'connected'
        except:
            cloudinary_status = 'disconnected'
        
        return jsonify({
            'status': 'healthy',
            'service': 'Bite Me Buddy Admin',
            'database': 'connected',
            'cloudinary': cloudinary_status,
            'timestamp': ist_now().isoformat(),
            'timezone': 'Asia/Kolkata',
            'admin_user': session.get('admin_username', 'not logged in')
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': ist_now().isoformat(),
            'timezone': 'Asia/Kolkata'
        }), 500

# ============================================
# ✅ CONTEXT PROCESSOR
# ============================================

@app.context_processor
def utility_processor():
    def format_currency(amount):
        """Format amount as currency"""
        if amount is None:
            return "₹0.00"
        return f"₹{float(amount):,.2f}"
    
    def get_status_badge(status):
        """Get Bootstrap badge class for status"""
        badge_classes = {
            'pending': 'bg-warning',
            'confirmed': 'bg-info',
            'processing': 'bg-primary',
            'shipped': 'bg-secondary',
            'delivered': 'bg-success',
            'cancelled': 'bg-danger',
            'refunded': 'bg-dark'
        }
        return badge_classes.get(status, 'bg-secondary')
    
    def get_payment_status_badge(status):
        """Get Bootstrap badge class for payment status"""
        badge_classes = {
            'pending': 'bg-warning',
            'completed': 'bg-success',
            'failed': 'bg-danger',
            'refunded': 'bg-dark'
        }
        return badge_classes.get(status, 'bg-secondary')
    
    return dict(
        format_currency=format_currency,
        get_status_badge=get_status_badge,
        get_payment_status_badge=get_payment_status_badge,
        ist_now=ist_now,
        format_ist_datetime=format_ist_datetime
    )

# ============================================
# ✅ APPLICATION STARTUP
# ============================================

if __name__ == '__main__':
    is_render = os.environ.get('RENDER') is not None
    
    if not is_render:
        print("🚀 Admin Application starting in LOCAL DEVELOPMENT mode")
        print(f"⏰ Current IST time: {ist_now().strftime('%d %b %Y, %I:%M %p')}")
        print(f"📊 Database URL: {os.environ.get('DATABASE_URL', 'Not set')[:50]}...")
        print(f"☁️ Cloudinary: {os.environ.get('CLOUDINARY_CLOUD_NAME', 'Not set')}")
        
        app.run(debug=True, host='0.0.0.0', port=5001)
    else:
        print("🚀 Admin Application starting in RENDER PRODUCTION mode")
        print(f"⏰ Current IST time: {ist_now().strftime('%d %b %Y, %I:%M %p')}")
        print("✅ Admin application ready for gunicorn")