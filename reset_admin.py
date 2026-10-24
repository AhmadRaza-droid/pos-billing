"""Admin ka password wapis 'admin123' kar deta hai (data ko haath nahi lagata).
Is file ko usi folder mein rakhein jahan superstore.db hai, phir:  python reset_admin.py"""
import os
import sqlite3
import hashlib

folder = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(folder, "superstore.db")

if not os.path.exists(path):
    print("superstore.db is folder mein nahi mili:", folder)
    raise SystemExit

NEW_PASSWORD = "admin123"
h = hashlib.sha256(NEW_PASSWORD.encode()).hexdigest()
conn = sqlite3.connect(path)
row = conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
if row:
    conn.execute("UPDATE users SET password_hash = ?, role = 'admin' WHERE id = ?", (h, row[0]))
else:
    conn.execute("INSERT INTO users (username, password_hash, role) VALUES ('admin', ?, 'admin')", (h,))
conn.commit()
print("Users:", [r for r in conn.execute("SELECT username, role FROM users")])
conn.close()
print(f"Theek hai! Ab login:  admin / {NEW_PASSWORD}   (login ke baad password badal dein)")