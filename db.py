# db.py
import sqlite3
from sqlite3 import Row

DB_PATH = "reviewcash.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    # users
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        username TEXT,
        balance REAL DEFAULT 0,
        role TEXT DEFAULT 'worker'
    )""")
    # tasks
    c.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employer_id INTEGER,
        platform TEXT,
        object_name TEXT,
        object_link TEXT,
        price REAL,
        quantity INTEGER,
        remaining INTEGER,
        status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    # submissions (proofs from workers)
    c.execute("""
    CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER,
        worker_id INTEGER,
        executor_name TEXT,
        proof TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        reviewed_at TEXT
    )""")
    # withdraws
    c.execute("""
    CREATE TABLE IF NOT EXISTS withdraws (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        method TEXT,
        details TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        processed_at TEXT
    )""")
    # invoices (for topups)
    c.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_code TEXT UNIQUE,
        employer_id INTEGER,
        amount REAL,
        phone TEXT,
        status TEXT DEFAULT 'waiting',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        paid_at TEXT
    )""")
    # admin table (store admin's commission balance)
    c.execute("""
    CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        balance REAL DEFAULT 0
    )""")
    c.execute("INSERT OR IGNORE INTO admin (id, balance) VALUES (1, 0)")
    conn.commit()
    conn.close()

# helper functions
def ensure_user(telegram_id, username=None):
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (telegram_id, username) VALUES (?, ?)", (telegram_id, username))
    if username:
        c.execute("UPDATE users SET username=? WHERE telegram_id=?", (username, telegram_id))
    conn.commit(); conn.close()

def get_user_by_tid(tid):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE telegram_id=?", (tid,))
    r = c.fetchone(); conn.close(); return r

def get_user_by_id(uid):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?", (uid,))
    r = c.fetchone(); conn.close(); return r

def change_user_balance(uid, amount):
    conn = get_conn(); c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, uid))
    conn.commit(); conn.close()

def create_invoice(employer_id, amount, phone):
    import uuid
    code = str(uuid.uuid4())[:8]
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT INTO invoices (invoice_code, employer_id, amount, phone) VALUES (?, ?, ?, ?)",
              (code, employer_id, amount, phone))
    conn.commit()
    inv = get_invoice_by_code(code)
    conn.close()
    return inv

def get_invoice_by_code(code):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM invoices WHERE invoice_code=?", (code,))
    r = c.fetchone(); conn.close(); return r

def mark_invoice_paid(code):
    conn = get_conn(); c = conn.cursor()
    c.execute("UPDATE invoices SET status='paid', paid_at=CURRENT_TIMESTAMP WHERE invoice_code=?", (code,))
    conn.commit(); conn.close()

def add_admin_commission(amount):
    conn = get_conn(); c = conn.cursor()
    c.execute("UPDATE admin SET balance = balance + ? WHERE id=1", (amount,))
    conn.commit(); conn.close()

def get_admin_balance():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT balance FROM admin WHERE id=1")
    r = c.fetchone(); conn.close(); return r["balance"] if r else 0

def create_task(employer_id, platform, object_name, object_link, price, quantity):
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT INTO tasks (employer_id, platform, object_name, object_link, price, quantity, remaining) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (employer_id, platform, object_name, object_link, price, quantity, quantity))
    conn.commit()
    task_id = c.lastrowid
    conn.close()
    return task_id

def list_active_tasks():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT id, platform, object_name, price, quantity, remaining FROM tasks WHERE status='active'")
    rows = c.fetchall(); conn.close(); return rows

def decrement_task(task_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("UPDATE tasks SET remaining = remaining - 1 WHERE id=? AND remaining>0", (task_id,))
    c.execute("SELECT remaining FROM tasks WHERE id=?", (task_id,))
    rem = c.fetchone()
    conn.commit(); conn.close()
    return rem["remaining"] if rem else 0

def add_submission(task_id, worker_id, executor_name, proof):
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT INTO submissions (task_id, worker_id, executor_name, proof) VALUES (?, ?, ?, ?)",
              (task_id, worker_id, executor_name, proof))
    conn.commit(); sid = c.lastrowid; conn.close(); return sid

def list_pending_submissions():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM submissions WHERE status='pending'")
    rows = c.fetchall(); conn.close(); return rows

def set_submission_status(sub_id, status):
    conn = get_conn(); c = conn.cursor()
    c.execute("UPDATE submissions SET status=?, reviewed_at=CURRENT_TIMESTAMP WHERE id=?", (status, sub_id))
    conn.commit(); conn.close()
