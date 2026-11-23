import os
import re
import sys
import csv
import shutil
import sqlite3
import hashlib
import hmac
import secrets
from datetime import datetime, date, timedelta

from i18n import raw

# App (exe ya script) kahan hai
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = APP_DIR  # purana naam

# Poora data (database, receipts, labels, backups) EK hi folder mein:
#   C:\Users\<aap ka naam>\SuperstorePOS_Data
# Exe kahin se bhi chalayen ya dobara banayen, data wahi rehta hai.
DATA_DIR = os.environ.get("SUPERSTORE_DATA_DIR") or os.path.join(
    os.path.expanduser("~"), "SuperstorePOS_Data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_NAME = os.path.join(DATA_DIR, "superstore.db")
MIGRATED_FROM = None  # purana data copy hua to wo folder yahan aata hai


def _db_score(path):
    """Database mein kitna data hai (products + sales + customers)."""
    try:
        c = sqlite3.connect(path)
        try:
            return sum(c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                       for t in ("products", "sales", "customers"))
        finally:
            c.close()
    except sqlite3.Error:
        return -1


def migrate_legacy_data():
    """Pehli dafa: purani jagah (exe/script ke saath wali) se data naye folder mein COPY karta hai.
    Agar kai purani databases hon to jis mein sab se zyada data ho wo uthata hai."""
    global MIGRATED_FROM
    if os.path.exists(DB_NAME):
        return
    best, best_score = None, -1
    for d in dict.fromkeys(os.path.abspath(x) for x in (APP_DIR, os.path.dirname(APP_DIR), os.getcwd())):
        p = os.path.join(d, "superstore.db")
        if os.path.exists(p) and os.path.abspath(p) != os.path.abspath(DB_NAME):
            score = _db_score(p)
            if score > best_score:
                best, best_score = d, score
    if best is None:
        return
    shutil.copy2(os.path.join(best, "superstore.db"), DB_NAME)
    for sub in ("receipts", "labels", "backups"):
        src, dst = os.path.join(best, sub), os.path.join(DATA_DIR, sub)
        if os.path.isdir(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)
    MIGRATED_FROM = best

DEFAULT_SETTINGS = {
    "store_name": "My Superstore",
    "address": "",
    "phone": "",
    "footer": "Thank you! Please visit again",
    "default_tax": "0",
    "backup_folder": "",         # doosra backup folder (USB / Google Drive folder), khali = band
    "language": "en",            # dukaan ki default zubaan: en / ru
    "receipt_language": "en",    # receipt ki zubaan: same / en / ru
    "ntn": "",
    "strn": "",
    "paper_width": "80",       # receipt paper: 80 ya 58 (mm)
    "auto_print": "0",         # 1 = bill save hote hi receipt print
    "drawer_printer": "",      # cash drawer wale printer ka naam (khali = band)
}


def get_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


PBKDF2_ITERATIONS = 200_000
FIRST_RUN_PASSWORD = None  # (purana) ab istemal nahi hota
NEEDS_SETUP = False        # True = koi user nahi: pehle setup screen dikhayen


def hash_password(password):
    """Salt ke saath PBKDF2-SHA256. Format: pbkdf2$iterations$salt$hash"""
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt}${h.hex()}"


def _is_legacy_hash(stored):
    return bool(stored) and not stored.startswith("pbkdf2$")


def verify_password(password, stored):
    """Naye (pbkdf2) aur purane (plain sha256) dono hash check karta hai."""
    if not stored:
        return False
    if _is_legacy_hash(stored):
        old = hashlib.sha256(password.encode()).hexdigest()
        return hmac.compare_digest(old, stored)
    try:
        _, iters, salt, h = stored.split("$")
        new = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(new.hex(), h)
    except (ValueError, TypeError):
        return False


def authenticate(username, password):
    """Sahi login par user row wapas karta hai warna None.
    Purana sha256 hash login par khud naye hash mein badal jata hai."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None or not verify_password(password, row["password_hash"]):
            return None
        if _is_legacy_hash(row["password_hash"]):
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                         (hash_password(password), row["id"]))
            conn.commit()
        return row
    finally:
        conn.close()


def _add_column(cur, table, col_def):
    """Purane database mein nayi column add karta hai (agar pehle se na ho)."""
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
    except sqlite3.OperationalError:
        pass


def init_db():
    migrate_legacy_data()
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('admin', 'manager', 'cashier'))
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        barcode TEXT UNIQUE,
        name TEXT NOT NULL,
        category TEXT,
        cost_price REAL NOT NULL DEFAULT 0,
        sale_price REAL NOT NULL,
        stock_qty INTEGER NOT NULL DEFAULT 0,
        low_stock_limit INTEGER NOT NULL DEFAULT 5,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_date TEXT DEFAULT CURRENT_TIMESTAMP,
        cashier_id INTEGER,
        subtotal REAL NOT NULL,
        discount REAL NOT NULL DEFAULT 0,
        tax REAL NOT NULL DEFAULT 0,
        total REAL NOT NULL,
        payment_method TEXT DEFAULT 'cash',
        FOREIGN KEY (cashier_id) REFERENCES users(id)
    )""")
    _add_column(cur, "sales", "customer_id INTEGER")
    _add_column(cur, "sales", "paid REAL")
    _add_column(cur, "products", "expiry_date TEXT")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sale_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        line_total REAL NOT NULL,
        FOREIGN KEY (sale_id) REFERENCES sales(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )""")

    # Customers aur udhaar khata
    cur.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        balance REAL NOT NULL DEFAULT 0
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS customer_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        pay_date TEXT DEFAULT CURRENT_TIMESTAMP,
        note TEXT,
        FOREIGN KEY (customer_id) REFERENCES customers(id)
    )""")

    # Returns (wapsi)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS returns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_id INTEGER NOT NULL,
        return_date TEXT DEFAULT CURRENT_TIMESTAMP,
        cashier_id INTEGER,
        refund_amount REAL NOT NULL,
        FOREIGN KEY (sale_id) REFERENCES sales(id)
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS return_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        return_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        line_total REAL NOT NULL,
        FOREIGN KEY (return_id) REFERENCES returns(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )""")

    _add_column(cur, "returns", "credit_offset REAL NOT NULL DEFAULT 0")

    # Suppliers aur purchase (maal aana)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        balance REAL NOT NULL DEFAULT 0
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS supplier_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        pay_date TEXT DEFAULT CURRENT_TIMESTAMP,
        note TEXT,
        FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_id INTEGER,
        purchase_date TEXT DEFAULT CURRENT_TIMESTAMP,
        user_id INTEGER,
        total REAL NOT NULL,
        paid REAL NOT NULL,
        note TEXT,
        FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS purchase_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        purchase_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        cost_price REAL NOT NULL,
        line_total REAL NOT NULL,
        FOREIGN KEY (purchase_id) REFERENCES purchases(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )""")

    # Dukaan ki settings
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    for k, v in DEFAULT_SETTINGS.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    cur.execute("UPDATE settings SET value = 'ru' WHERE key IN ('language', 'receipt_language') AND value IN ('ur', 'pa')")
    # purani Roman-Urdu default footer ko English default se badal dein
    cur.execute("UPDATE settings SET value = ? WHERE key = 'footer' AND value = ?",
                (DEFAULT_SETTINGS["footer"], "Shukriya! Dobara tashreef layein"))

    _add_column(cur, "users", "language TEXT")
    _add_column(cur, "users", "can_return INTEGER NOT NULL DEFAULT 1")
    _add_column(cur, "users", "can_discount INTEGER NOT NULL DEFAULT 1")
    _add_column(cur, "users", "perms TEXT")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT DEFAULT CURRENT_TIMESTAMP,
        user_id INTEGER,
        username TEXT,
        action TEXT NOT NULL,
        details TEXT
    )""")
    cur.execute("UPDATE users SET language = 'ru' WHERE language IN ('ur', 'pa')")   # Urdu/Punjabi hata di gayi
    global NEEDS_SETUP
    cur.execute("SELECT COUNT(*) FROM users")
    NEEDS_SETUP = cur.fetchone()[0] == 0

    conn.commit()
    conn.close()
    _migrate_user_roles()
    _backfill_perms()


# ---------- Roles aur ijazaten (Super Admin / Admin / Cashier) ----------
# Database mein 'admin' = Super Admin (malik, sab kuch kar sakta hai),
# 'manager' = Admin (limited, Super Admin jo ijazat de), 'cashier' = Cashier.
ROLE_LABELS = {"admin": "Super Admin", "manager": "Admin", "cashier": "Cashier"}
PERMISSIONS = [
    ("dashboard", "View the dashboard"),
    ("reports", "View sales reports"),
    ("closing", "Daily closing"),
    ("inventory", "Manage products and stock"),
    ("prices", "Change prices"),
    ("delete_products", "Delete products"),
    ("purchases", "Stock In (purchases)"),
    ("suppliers", "Suppliers"),
    ("returns", "Process returns"),
    ("discounts", "Give discounts"),
    ("backup", "Create backups"),
    ("audit", "View the audit log"),
    ("users", "Manage cashier accounts"),
    ("settings", "Change shop settings"),
]
PERM_KEYS = [k for k, _ in PERMISSIONS]
DEFAULT_PERMS = {
    "cashier": ["returns", "discounts"],
    "manager": ["dashboard", "reports", "closing", "inventory", "prices", "purchases", "suppliers",
                "returns", "discounts"],
}
MANAGER_GRANTABLE = ("returns", "discounts")   # jo ek Admin (manager) apne cashier ko de sakta hai


def _migrate_user_roles():
    """Purani users table mein 'manager' role ki ijazat nahi thi: table naye sire se banata hai (data wahi rehta hai)."""
    conn = sqlite3.connect(DB_NAME, isolation_level=None)
    try:
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
        if not row or "'manager'" in row[0]:
            return
        new_sql = re.sub(r"role\s+IN\s*\([^)]*\)", "role IN ('admin', 'manager', 'cashier')", row[0], count=1)
        new_sql = re.sub(r'CREATE TABLE\s+"?users"?', "CREATE TABLE users_new", new_sql, count=1)
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")
        try:
            conn.execute(new_sql)
            conn.execute("INSERT INTO users_new SELECT * FROM users")
            conn.execute("DROP TABLE users")
            conn.execute("ALTER TABLE users_new RENAME TO users")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()


def _backfill_perms():
    """Jin users ki ijazaten abhi tak likhi nahi gayi (purane users) unhein purani settings ke hisab se bharta hai."""
    conn = get_connection()
    for r in conn.execute("SELECT id, role, can_return, can_discount FROM users WHERE perms IS NULL").fetchall():
        if r["role"] == "admin":
            perms = ""
        elif r["role"] == "manager":
            perms = ",".join(DEFAULT_PERMS["manager"])
        else:
            perms = ",".join(k for k, on in (("returns", r["can_return"]), ("discounts", r["can_discount"])) if on)
        conn.execute("UPDATE users SET perms = ? WHERE id = ?", (perms, r["id"]))
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return row


def get_perms(user):
    """User ki ijazaten (set). Super Admin ke paas hamesha sab hoti hain."""
    if user is None:
        return set()
    if user["role"] == "admin":
        return set(PERM_KEYS)
    keys = user.keys()
    raw_perms = user["perms"] if "perms" in keys else None
    if raw_perms is None:        # abhi likhi nahi gayi: purani settings / role ke default se
        if user["role"] == "manager":
            return set(DEFAULT_PERMS["manager"])
        return {k for k, col in (("returns", "can_return"), ("discounts", "can_discount"))
                if col not in keys or user[col]}
    return {p for p in raw_perms.split(",") if p in PERM_KEYS}


def set_perms(user_id, perms):
    conn = get_connection()
    conn.execute("UPDATE users SET perms = ? WHERE id = ?",
                 (",".join(k for k in PERM_KEYS if k in set(perms)), user_id))
    conn.commit()
    conn.close()


def create_user(username, password, role, perms=None):
    if role not in ("manager", "cashier"):
        raise ValueError("role")
    perms = DEFAULT_PERMS[role] if perms is None else perms
    conn = get_connection()
    cur = conn.execute("INSERT INTO users (username, password_hash, role, perms) VALUES (?, ?, ?, ?)",
                       (username, hash_password(password), role, ",".join(perms)))
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return uid


def create_admin(username, password):
    """Setup screen se pehla admin account banata hai."""
    global NEEDS_SETUP
    conn = get_connection()
    conn.execute("INSERT INTO users (username, password_hash, role, perms) VALUES (?, ?, 'admin', '')",
                 (username, hash_password(password)))
    conn.commit()
    conn.close()
    NEEDS_SETUP = False


def set_user_permissions(user_id, can_return=None, can_discount=None):
    conn = get_connection()
    if can_return is not None:
        conn.execute("UPDATE users SET can_return = ? WHERE id = ?", (1 if can_return else 0, user_id))
    if can_discount is not None:
        conn.execute("UPDATE users SET can_discount = ? WHERE id = ?", (1 if can_discount else 0, user_id))
    conn.commit()
    conn.close()


# ---------- Audit log ----------
def log_action(user_id, username, action, details=""):
    """Kaun ne kya kiya: login, bill, return, price badalna wagaira. Kabhi masla nahi khara karta."""
    try:
        conn = get_connection()
        conn.execute("INSERT INTO audit_log (user_id, username, action, details) VALUES (?, ?, ?, ?)",
                     (user_id, username, action, details))
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass


def list_audit(limit=1000, day=None, username=None, text=None):
    sql = ("SELECT id, datetime(ts, 'localtime') AS t, COALESCE(username, '-') AS username, action, "
           "COALESCE(details, '') AS details FROM audit_log WHERE 1 = 1")
    args = []
    if day:
        sql += " AND date(ts, 'localtime') = ?"
        args.append(day)
    if username:
        sql += " AND username = ?"
        args.append(username)
    if text:
        sql += " AND (action LIKE ? OR details LIKE ?)"
        args += [f"%{text}%", f"%{text}%"]
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    conn = get_connection()
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return rows


# ---------- Logo ----------
def logo_path():
    for name in ("logo.png", "logo.gif"):
        p = os.path.join(DATA_DIR, name)
        if os.path.exists(p):
            return p
    return None


def set_logo(src):
    ext = os.path.splitext(src)[1].lower()
    if ext not in (".png", ".gif"):
        raise ValueError(raw("Please choose a PNG or GIF image"))
    remove_logo()
    shutil.copy2(src, os.path.join(DATA_DIR, "logo" + ext))


def remove_logo():
    for name in ("logo.png", "logo.gif"):
        p = os.path.join(DATA_DIR, name)
        if os.path.exists(p):
            os.remove(p)


def set_user_language(user_id, code):
    conn = get_connection()
    conn.execute("UPDATE users SET language = ? WHERE id = ?", (code, user_id))
    conn.commit()
    conn.close()


# ---------- Settings ----------
def get_settings():
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    s = dict(DEFAULT_SETTINGS)
    s.update({r["key"]: r["value"] for r in rows})
    return s


def set_setting(key, value):
    conn = get_connection()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


# ---------- Password recovery ----------
def set_recovery_code(code):
    set_setting("recovery_hash", hash_password("recovery:" + code))


def has_recovery_code():
    return bool(get_settings().get("recovery_hash"))


def check_recovery_code(code):
    stored = get_settings().get("recovery_hash")
    return bool(stored) and verify_password("recovery:" + code, stored)


def reset_password(username, new_password):
    conn = get_connection()
    cur = conn.execute("UPDATE users SET password_hash = ? WHERE username = ?",
                       (hash_password(new_password), username))
    if cur.rowcount == 0 and username == "admin":
        conn.execute("INSERT INTO users (username, password_hash, role) VALUES ('admin', ?, 'admin')",
                     (hash_password(new_password),))
    conn.commit()
    conn.close()


# ---------- Products ----------
def add_product(barcode, name, category, cost_price, sale_price, stock_qty,
                low_stock_limit=5, expiry_date=None):
    conn = get_connection()
    conn.execute(
        """INSERT INTO products
           (barcode, name, category, cost_price, sale_price, stock_qty, low_stock_limit, expiry_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (barcode, name, category, cost_price, sale_price, stock_qty, low_stock_limit, expiry_date),
    )
    conn.commit()
    conn.close()


def get_product_by_barcode(barcode):
    conn = get_connection()
    row = conn.execute("SELECT * FROM products WHERE barcode = ?", (barcode,)).fetchone()
    conn.close()
    return row


def search_products(text):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM products WHERE name LIKE ? OR barcode LIKE ?",
        (f"%{text}%", f"%{text}%"),
    ).fetchall()
    conn.close()
    return rows


def low_stock_products():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM products WHERE stock_qty <= low_stock_limit"
    ).fetchall()
    conn.close()
    return rows


def next_bill_no():
    conn = get_connection()
    n = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM sales").fetchone()[0]
    conn.close()
    return n


# ---------- Customers ----------
def add_customer(name, phone=""):
    conn = get_connection()
    cur = conn.execute("INSERT INTO customers (name, phone) VALUES (?, ?)", (name, phone))
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return cid


def list_customers(search=""):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM customers WHERE name LIKE ? OR phone LIKE ? ORDER BY name",
        (f"%{search}%", f"%{search}%"),
    ).fetchall()
    conn.close()
    return rows


def get_customer(customer_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    conn.close()
    return row


def receive_payment(customer_id, amount, note=""):
    amount = _r(amount)
    if amount <= 0:
        raise ValueError(raw("The amount must be greater than 0"))
    conn = get_connection()
    conn.execute("INSERT INTO customer_payments (customer_id, amount, note) VALUES (?, ?, ?)",
                 (customer_id, amount, note))
    conn.execute("UPDATE customers SET balance = balance - ? WHERE id = ?", (amount, customer_id))
    conn.commit()
    conn.close()


# ---------- Billing ----------
def _r(x):
    """Paison ko 2 decimal tak round karo taake float ka farq jama na ho."""
    return round(float(x) + 0.0, 2)


PAY_METHODS = ("cash", "card", "easypaisa", "jazzcash")


def save_sale(cashier_id, items, discount=0, tax_percent=0, customer_id=None, paid=None,
              payment_method="cash"):
    """items = [(product_id, quantity, unit_price), ...]
    paid = abhi diye gaye paise. Baqaya customer ke udhaar mein chala jata hai."""
    subtotal = _r(sum(q * p for _, q, p in items))
    discount = _r(min(discount, subtotal))
    tax = _r((subtotal - discount) * tax_percent / 100)
    total = _r(subtotal - discount + tax)
    if paid is None:
        paid = total
    paid = _r(max(0.0, min(paid, total)))
    credit = _r(total - paid)
    if credit < 0.02:
        credit = 0.0
        paid = total
    if credit > 0 and not customer_id:
        raise ValueError(raw("A customer must be selected for credit"))
    if payment_method not in PAY_METHODS:
        payment_method = "cash"
    if paid <= 0:
        payment_method = "udhaar"  # kuch bhi nahi diya, poora udhaar

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()
        for product_id, qty, _ in items:
            row = cur.execute("SELECT name, stock_qty FROM products WHERE id = ?",
                              (product_id,)).fetchone()
            if row is None or row["stock_qty"] < qty:
                raise ValueError(raw("Not enough stock: {name}", name=row['name'] if row else product_id))
        cur.execute(
            """INSERT INTO sales (cashier_id, subtotal, discount, tax, total,
                                  payment_method, customer_id, paid)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (cashier_id, subtotal, discount, tax, total,
             payment_method, customer_id, paid),
        )
        sale_id = cur.lastrowid
        for product_id, qty, price in items:
            cur.execute(
                """INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, line_total)
                   VALUES (?, ?, ?, ?, ?)""",
                (sale_id, product_id, qty, price, qty * price),
            )
            cur.execute("UPDATE products SET stock_qty = stock_qty - ? WHERE id = ?",
                        (qty, product_id))
        if credit > 0:
            cur.execute("UPDATE customers SET balance = balance + ? WHERE id = ?",
                        (credit, customer_id))
        conn.commit()
        return sale_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------- Returns ----------
def get_sale(sale_id):
    conn = get_connection()
    row = conn.execute(
        """SELECT s.*, c.name AS customer_name FROM sales s
           LEFT JOIN customers c ON c.id = s.customer_id WHERE s.id = ?""",
        (sale_id,)).fetchone()
    conn.close()
    return row


def get_returnable_items(sale_id):
    conn = get_connection()
    rows = conn.execute(
        """SELECT si.product_id, p.name, si.unit_price, si.quantity AS sold,
                  COALESCE((SELECT SUM(ri.quantity) FROM return_items ri
                            JOIN returns r ON r.id = ri.return_id
                            WHERE r.sale_id = si.sale_id AND ri.product_id = si.product_id), 0)
                  AS returned
           FROM sale_items si JOIN products p ON p.id = si.product_id
           WHERE si.sale_id = ?""", (sale_id,)).fetchall()
    conn.close()
    return rows


def process_return(sale_id, cashier_id, items):
    """items = [(product_id, qty), ...]
    Wapis hone wala saaman stock mein wapas aata hai. Refund bill ke discount/tax ke
    hisab se barabar hissa hota hai. Agar customer ka udhaar baqaya ho to pehle wahi kam hota hai.
    Returns (return_id, refund_amount, udhaar_se_kam)"""
    sale = get_sale(sale_id)
    if sale is None:
        raise ValueError(raw("Bill not found"))
    available = {r["product_id"]: r for r in get_returnable_items(sale_id)}
    factor = sale["total"] / sale["subtotal"] if sale["subtotal"] else 1

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()
        lines, refund = [], 0.0
        for pid, qty in items:
            r = available.get(pid)
            if r is None or qty < 1 or qty > r["sold"] - r["returned"]:
                raise ValueError(raw("The return quantity is wrong"))
            line = qty * r["unit_price"]
            lines.append((pid, qty, r["unit_price"], line))
            refund += line * factor
        refund = round(refund, 2)
        cur.execute("INSERT INTO returns (sale_id, cashier_id, refund_amount) VALUES (?, ?, ?)",
                    (sale_id, cashier_id, refund))
        return_id = cur.lastrowid
        for pid, qty, price, line in lines:
            cur.execute(
                """INSERT INTO return_items (return_id, product_id, quantity, unit_price, line_total)
                   VALUES (?, ?, ?, ?, ?)""", (return_id, pid, qty, price, line))
            cur.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE id = ?", (qty, pid))
        offset = 0.0
        if sale["customer_id"]:
            bal = cur.execute("SELECT balance FROM customers WHERE id = ?",
                              (sale["customer_id"],)).fetchone()["balance"]
            offset = round(min(refund, max(bal, 0.0)), 2)
            if offset > 0:
                cur.execute("UPDATE customers SET balance = balance - ? WHERE id = ?",
                            (offset, sale["customer_id"]))
                cur.execute("UPDATE returns SET credit_offset = ? WHERE id = ?",
                            (offset, return_id))
        conn.commit()
        return return_id, refund, offset
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------- Dates ----------
def parse_date(text):
    """'2026-12-31', '31-12-2026' ya '31/12/2026' ko '2026-12-31' bana deta hai. Khali ho to None."""
    if text is None:
        return None
    if isinstance(text, datetime):
        return text.strftime("%Y-%m-%d")
    text = str(text).strip()
    if not text:
        return None
    text = text.split(" ")[0]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise ValueError(raw("The date is not valid: {text} (write it like 2026-12-31)", text=text))


def expiring_products(days=30):
    """Wo products jin ki expiry guzar chuki ya {days} din ke andar hai (jin ka stock baqi hai)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM products
           WHERE expiry_date IS NOT NULL AND expiry_date != ''
             AND expiry_date <= date('now', 'localtime', ?) AND stock_qty > 0
           ORDER BY expiry_date""", (f"+{int(days)} days",)).fetchall()
    conn.close()
    return rows


# ---------- Suppliers / Purchase ----------
def add_supplier(name, phone=""):
    conn = get_connection()
    cur = conn.execute("INSERT INTO suppliers (name, phone) VALUES (?, ?)", (name, phone))
    conn.commit()
    sid = cur.lastrowid
    conn.close()
    return sid


def list_suppliers(search=""):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM suppliers WHERE name LIKE ? OR phone LIKE ? ORDER BY name",
        (f"%{search}%", f"%{search}%")).fetchall()
    conn.close()
    return rows


def pay_supplier(supplier_id, amount, note=""):
    amount = _r(amount)
    if amount <= 0:
        raise ValueError(raw("The amount must be greater than 0"))
    conn = get_connection()
    conn.execute("INSERT INTO supplier_payments (supplier_id, amount, note) VALUES (?, ?, ?)",
                 (supplier_id, amount, note))
    conn.execute("UPDATE suppliers SET balance = balance - ? WHERE id = ?", (amount, supplier_id))
    conn.commit()
    conn.close()


def save_purchase(user_id, supplier_id, items, paid=None, note=""):
    """items = [(product_id, qty, cost_price, expiry_date_or_None), ...]
    Stock barhta hai, product ki cost price update hoti hai, baqaya supplier ke khate mein jata hai."""
    total = _r(sum(q * c for _, q, c, _ in items))
    if paid is None:
        paid = total
    paid = _r(max(0.0, min(paid, total)))
    credit = _r(total - paid)
    if credit < 0.02:
        credit, paid = 0.0, total
    if credit > 0 and not supplier_id:
        raise ValueError(raw("A supplier is required for credit purchases"))

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO purchases (supplier_id, user_id, total, paid, note) VALUES (?, ?, ?, ?, ?)",
            (supplier_id, user_id, total, paid, note))
        pid_ = cur.lastrowid
        for product_id, qty, cost, expiry in items:
            cur.execute(
                """INSERT INTO purchase_items (purchase_id, product_id, quantity, cost_price, line_total)
                   VALUES (?, ?, ?, ?, ?)""", (pid_, product_id, qty, cost, qty * cost))
            cur.execute(
                """UPDATE products SET stock_qty = stock_qty + ?, cost_price = ?,
                          expiry_date = COALESCE(?, expiry_date) WHERE id = ?""",
                (qty, cost, expiry, product_id))
        if credit > 0:
            cur.execute("UPDATE suppliers SET balance = balance + ? WHERE id = ?",
                        (credit, supplier_id))
        conn.commit()
        return pid_
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------- Daily closing ----------
def daily_closing(day):
    conn = get_connection()
    s = conn.execute(
        """SELECT COUNT(*) AS n, COALESCE(SUM(total), 0) AS total,
                  COALESCE(SUM(CASE WHEN payment_method IN ('card','easypaisa','jazzcash')
                                    THEN 0 ELSE COALESCE(paid, total) END), 0) AS cash,
                  COALESCE(SUM(CASE WHEN payment_method = 'card'
                                    THEN COALESCE(paid, total) ELSE 0 END), 0) AS card,
                  COALESCE(SUM(CASE WHEN payment_method = 'easypaisa'
                                    THEN COALESCE(paid, total) ELSE 0 END), 0) AS easypaisa,
                  COALESCE(SUM(CASE WHEN payment_method = 'jazzcash'
                                    THEN COALESCE(paid, total) ELSE 0 END), 0) AS jazzcash,
                  COALESCE(SUM(total - COALESCE(paid, total)), 0) AS credit
           FROM sales WHERE date(sale_date, 'localtime') = ?""", (day,)).fetchone()
    r = conn.execute(
        """SELECT COALESCE(SUM(refund_amount), 0) AS refund, COALESCE(SUM(credit_offset), 0) AS offset
           FROM returns WHERE date(return_date, 'localtime') = ?""", (day,)).fetchone()
    cp = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM customer_payments "
                      "WHERE date(pay_date, 'localtime') = ?", (day,)).fetchone()[0]
    pp = conn.execute("SELECT COALESCE(SUM(paid), 0) FROM purchases "
                      "WHERE date(purchase_date, 'localtime') = ?", (day,)).fetchone()[0]
    sp = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM supplier_payments "
                      "WHERE date(pay_date, 'localtime') = ?", (day,)).fetchone()[0]
    conn.close()
    cash_refunds = r["refund"] - r["offset"]
    expected = s["cash"] + cp - cash_refunds - pp - sp
    return {"bills": s["n"], "sales_total": s["total"], "cash_sales": s["cash"],
            "card_sales": s["card"], "easypaisa_sales": s["easypaisa"],
            "jazzcash_sales": s["jazzcash"], "udhaar": s["credit"], "cust_payments": cp, "cash_refunds": cash_refunds,
            "purchase_paid": pp, "supplier_payments": sp, "expected_cash": expected}


# ---------- Dashboard ----------
def dashboard_data(day):
    """Admin dashboard ke numbers: aaj ki sale, munafa, 7 din ka graph, top products, udhaar wagaira."""
    c = daily_closing(day)
    conn = get_connection()
    one = lambda sql, *a: conn.execute(sql, a).fetchone()[0]
    refunds = one("SELECT COALESCE(SUM(refund_amount), 0) FROM returns WHERE date(return_date,'localtime') = ?", day)
    gross = one("""SELECT COALESCE(SUM(si.line_total - si.quantity * p.cost_price), 0)
                   FROM sale_items si JOIN products p ON p.id = si.product_id
                   JOIN sales s ON s.id = si.sale_id WHERE date(s.sale_date,'localtime') = ?""", day)
    discount = one("SELECT COALESCE(SUM(discount), 0) FROM sales WHERE date(sale_date,'localtime') = ?", day)
    ret_profit = one("""SELECT COALESCE(SUM(ri.line_total - ri.quantity * p.cost_price), 0)
                        FROM return_items ri JOIN products p ON p.id = ri.product_id
                        JOIN returns r ON r.id = ri.return_id WHERE date(r.return_date,'localtime') = ?""", day)
    top = conn.execute("""SELECT p.name AS name, SUM(si.quantity) AS qty, SUM(si.line_total) AS revenue
                          FROM sale_items si JOIN products p ON p.id = si.product_id
                          JOIN sales s ON s.id = si.sale_id WHERE date(s.sale_date,'localtime') = ?
                          GROUP BY p.id ORDER BY qty DESC, revenue DESC LIMIT 5""", (day,)).fetchall()
    days = [(date.fromisoformat(day) - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    sales7 = {r[0]: r[1] for r in conn.execute(
        "SELECT date(sale_date,'localtime'), SUM(total) FROM sales "
        "WHERE date(sale_date,'localtime') BETWEEN ? AND ? GROUP BY 1", (days[0], days[-1]))}
    ref7 = {r[0]: r[1] for r in conn.execute(
        "SELECT date(return_date,'localtime'), SUM(refund_amount) FROM returns "
        "WHERE date(return_date,'localtime') BETWEEN ? AND ? GROUP BY 1", (days[0], days[-1]))}
    credit = one("SELECT COALESCE(SUM(balance), 0) FROM customers WHERE balance > 0")
    owed = one("SELECT COALESCE(SUM(balance), 0) FROM suppliers WHERE balance > 0")
    conn.close()
    return {
        "bills": c["bills"], "net_sales": c["sales_total"] - refunds, "gross_sales": c["sales_total"],
        "refunds": refunds, "profit": gross - discount - ret_profit,
        "expected_cash": c["expected_cash"], "cash_sales": c["cash_sales"], "card_sales": c["card_sales"],
        "easypaisa_sales": c["easypaisa_sales"], "jazzcash_sales": c["jazzcash_sales"], "udhaar": c["udhaar"],
        "top": [(r["name"], r["qty"], r["revenue"]) for r in top],
        "last7": [(d, sales7.get(d, 0) - ref7.get(d, 0)) for d in days],
        "customer_credit": credit, "supplier_owed": owed,
        "low_stock": len(low_stock_products()), "expiring": len(expiring_products(30)),
    }


# ---------- Backup ----------
def backup_to(folder):
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, f"superstore_backup_{datetime.now():%Y%m%d_%H%M%S}.db")
    src = get_connection()
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return dest


def _copy_to_extra_folder(path, name=None):
    """Settings mein doosra backup folder (USB / Google Drive) likha ho to wahan bhi copy karta hai."""
    try:
        extra = get_settings().get("backup_folder", "").strip()
        if extra and os.path.isdir(extra):
            shutil.copy2(path, os.path.join(extra, name or os.path.basename(path)))
            return True
    except Exception:
        pass
    return False


def backup_on_exit():
    """App band karte waqt aakhri haalat ka backup (backups folder + doosra folder)."""
    folder = os.path.join(DATA_DIR, "backups")
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, "superstore_last_exit.db")
    src = get_connection()
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    _copy_to_extra_folder(dest, f"superstore_exit_{datetime.now():%Y%m%d}.db")


def auto_backup(keep=14):
    """Roz ek dafa khud backup banata hai (backups folder mein), purane 14 se zyada hata deta hai."""
    folder = os.path.join(DATA_DIR, "backups")
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, f"superstore_auto_{datetime.now():%Y%m%d}.db")
    if os.path.exists(dest) or not os.path.exists(DB_NAME):
        return None
    src = get_connection()
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    _copy_to_extra_folder(dest)
    autos = sorted(f for f in os.listdir(folder) if f.startswith("superstore_auto_"))
    for old in autos[:-keep]:
        try:
            os.remove(os.path.join(folder, old))
        except OSError:
            pass
    return dest


def restore_from(path):
    """Backup file se poora database wapis le aata hai. Pehle mojooda database ka backup banta hai."""
    check = sqlite3.connect(path)
    try:
        names = {r[0] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        check.close()
    if not {"products", "sales", "users"} <= names:
        raise ValueError(raw("This does not look like a superstore backup file"))
    safety = backup_to(os.path.join(DATA_DIR, "backups"))
    src = sqlite3.connect(path)
    dst = get_connection()
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    init_db()  # purani backup ho to naye tables bhi ban jayen
    return safety


# ---------- Excel / CSV import ----------
IMPORT_HEADERS = ["barcode", "name", "category", "cost_price", "sale_price", "stock", "expiry"]
_ALIASES = {
    "barcode": {"barcode", "barcodes", "code"},
    "name": {"name", "naam", "product", "productname", "item", "itemname"},
    "category": {"category", "cat"},
    "cost": {"costprice", "cost", "purchaseprice"},
    "price": {"saleprice", "price", "sellingprice", "rate"},
    "stock": {"stock", "qty", "quantity", "stockqty"},
    "expiry": {"expiry", "expirydate", "expdate", "exp"},
}


def write_import_template(path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(IMPORT_HEADERS)
        w.writerow(["8961001234567", "Lux Soap", "Soap", 60, 70, 100, ""])
        w.writerow(["", "Milk 1L", "Dairy", 200, 230, 20, "2026-12-31"])
    return path


def _read_rows(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        for enc in ("utf-8-sig", "cp1252"):
            try:
                with open(path, newline="", encoding=enc) as f:
                    return [row for row in csv.reader(f)]
            except UnicodeDecodeError:
                continue
        raise ValueError(raw("The CSV file could not be read"))
    if ext in (".xlsx", ".xlsm"):
        try:
            import openpyxl # type: ignore
        except ImportError:
            raise RuntimeError(raw("For Excel (.xlsx) run:  python -m pip install openpyxl\nor use Save As to make a CSV from Excel and import that."))
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        rows = [list(r) for r in wb.active.iter_rows(values_only=True)]
        wb.close()
        return rows
    raise ValueError(raw("Only .xlsx or .csv files are supported"))


def _clean(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _number(v, default=0.0):
    t = _clean(v).replace(",", "")
    try:
        return float(t) if t else default
    except ValueError:
        raise ValueError(raw("The number is not valid: {t}", t=t))


def import_products_file(path):
    """Returns (added, skipped, errors). Jis barcode ka product pehle se hai wo skip hota hai."""
    rows = _read_rows(path)
    if not rows:
        raise ValueError(raw("The file is empty"))
    header = ["".join(ch for ch in _clean(h).lower() if ch.isalnum()) for h in rows[0]]
    col = {}
    for key, names in _ALIASES.items():
        for i, h in enumerate(header):
            if h in names:
                col[key] = i
                break
    if "name" not in col or "price" not in col:
        raise ValueError(raw("The first row of the file must have 'name' and 'sale_price' columns"))

    def get(row, key):
        i = col.get(key)
        return row[i] if i is not None and i < len(row) else None

    added = skipped = 0
    errors = []
    conn = get_connection()
    try:
        for n, row in enumerate(rows[1:], start=2):
            if not any(_clean(c) for c in row):
                continue
            try:
                name = _clean(get(row, "name"))
                if not name:
                    raise ValueError(raw("The name is empty"))
                barcode = _clean(get(row, "barcode")) or None
                if barcode and conn.execute("SELECT 1 FROM products WHERE barcode = ?",
                                            (barcode,)).fetchone():
                    skipped += 1
                    continue
                if not barcode and conn.execute("SELECT 1 FROM products WHERE lower(name) = lower(?)",
                                                (name,)).fetchone():
                    skipped += 1
                    continue
                conn.execute(
                    """INSERT INTO products (barcode, name, category, cost_price, sale_price,
                                             stock_qty, expiry_date)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (barcode, name, _clean(get(row, "category")),
                     _number(get(row, "cost")), _number(get(row, "price")),
                     int(_number(get(row, "stock"))), parse_date(get(row, "expiry"))))
                added += 1
            except Exception as e:
                errors.append((n, str(e)))
        conn.commit()
    finally:
        conn.close()
    return added, skipped, errors


if __name__ == "__main__":
    init_db()
    print("Database ready:", DB_NAME)