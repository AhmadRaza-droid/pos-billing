"""Admin ka password reset karta hai (data ko haath nahi lagata).
Is file ko usi folder mein rakhein jahan superstore.db hai, phir:

    python reset_admin.py                 -> naya random password bana kar dikhata hai
    python reset_admin.py MeraNayaPass    -> aapka diya hua password lagata hai
"""
import os
import sys
import sqlite3
import secrets
import hashlib

ITERATIONS = 200_000


def hash_password(password):
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS)
    return f"pbkdf2${ITERATIONS}${salt}${h.hex()}"


folder = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(folder, "superstore.db")

if not os.path.exists(path):
    print("superstore.db is folder mein nahi mili:", folder)
    raise SystemExit

new_password = sys.argv[1] if len(sys.argv) > 1 else secrets.token_urlsafe(8)
if len(new_password) < 4:
    print("Password kam az kam 4 harf ka rakhein")
    raise SystemExit

h = hash_password(new_password)
conn = sqlite3.connect(path)
row = conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
if row:
    conn.execute("UPDATE users SET password_hash = ?, role = 'admin' WHERE id = ?", (h, row[0]))
else:
    conn.execute("INSERT INTO users (username, password_hash, role) VALUES ('admin', ?, 'admin')", (h,))
conn.commit()
print("Users:", [r for r in conn.execute("SELECT username, role FROM users")])
conn.close()
print(f"Theek hai! Ab login:  admin / {new_password}   (login ke baad password badal dein)")
