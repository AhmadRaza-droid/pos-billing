import os
import re
import sys
import csv
import copy
import time
import tkinter as tk
from tkinter import ttk, filedialog
from datetime import datetime, timedelta

import db
import i18n
import labels as lbl
import Receipt as rcpt
from i18n import _ as tr, raw, messagebox, simpledialog
from version import APP_NAME, APP_VERSION


PRIMARY = "#2563eb"      # nila
PRIMARY_DARK = "#1e3a8a"  # gehra nila (header)
ACCENT = "#16a34a"       # hara
DANGER = "#dc2626"       # laal
BG = "#f1f5f9"           # halka background
CARD = "#ffffff"
BORDER = "#cbd5e1"
TEXT = "#0f172a"


PAY_METHODS = [("cash", "Cash"), ("card", "Card"), ("easypaisa", "Easypaisa"), ("jazzcash", "JazzCash")]
PAY_NAMES = dict(PAY_METHODS)
HINT_TEXT = "Scan a barcode or type a name and press Enter.   5*barcode = 5 pieces at once."
PAPER_CHOICES = ["80 mm (large thermal)", "58 mm (small thermal)"]


def pay_label(method, total, paid, fn=None):
    """Bill ki payment ka naam: Cash, Card, Cash + Credit wagaira. fn = tarjuma karne wala function."""
    fn = fn or tr
    if method == "udhaar":
        return fn("Cash + Credit") if paid > 0.01 else fn("Credit")
    base = fn(PAY_NAMES.get(method, "Cash"))
    return base + fn(" + Credit") if total - paid > 0.01 else base


def resource_path(name):
    """Icon wagaira: exe ke andar (PyInstaller) ya script ke saath wali file."""
    base = getattr(sys, "_MEIPASS", None) or db.APP_DIR
    return os.path.join(base, name)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME}  {APP_VERSION}")
        try:
            self.iconbitmap(default=resource_path("icon.ico"))
        except tk.TclError:
            pass
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._imgs = []
        self._fail_count = 0
        self._lock_until = 0.0
        self.geometry("1150x700")
        self.user = None
        self.cart = {}  # product_id -> dict
        self.cust = None  # bill ka customer
        self.held = []  # hold kiye hue bills
        self._keys = {}
        self._clock_job = None
        self._flash_job = None
        self._drawer_warned = False
        self.apply_theme()
        db.init_db()
        try:
            db.auto_backup()
        except Exception:
            pass
        self.login_lang = None
        self.login_picked = False
        self.apply_language(db.get_settings()["language"])
        if db.NEEDS_SETUP:
            self.show_setup()
        else:
            self.show_login()
        if db.MIGRATED_FROM:
            self.after(900, lambda: messagebox.showinfo(
                "Data in one folder",
                raw("Your old data was copied from this location into the new folder:\n{src}\n\nEverything (database, receipts, backups) now lives here:\n{dst}", src=db.MIGRATED_FROM, dst=db.DATA_DIR)))

    def apply_theme(self):
        self.configure(bg=BG)
        o = self.option_add
        o("*Font", "{Segoe UI} 10")
        o("*Background", BG)
        o("*Foreground", TEXT)
        o("*Toplevel.Background", BG)
        o("*Frame.Background", BG)
        o("*Label.Background", BG)
        o("*LabelFrame.Background", BG)
        o("*LabelFrame.Foreground", PRIMARY_DARK)
        o("*LabelFrame.Font", "{Segoe UI} 10 bold")
        o("*Button.Background", PRIMARY)
        o("*Button.Foreground", "white")
        o("*Button.activeBackground", "#1d4ed8")
        o("*Button.activeForeground", "white")
        o("*Button.relief", "flat")
        o("*Button.borderWidth", 0)
        o("*Button.padX", 12)
        o("*Button.padY", 5)
        o("*Button.cursor", "hand2")
        o("*Entry.Background", CARD)
        o("*Entry.relief", "flat")
        o("*Entry.highlightThickness", 1)
        o("*Entry.highlightBackground", BORDER)
        o("*Entry.highlightColor", PRIMARY)
        o("*Listbox.Background", CARD)
        o("*Listbox.selectBackground", PRIMARY)
        o("*Listbox.selectForeground", "white")
        o("*Listbox.relief", "flat")
        o("*Listbox.highlightThickness", 1)
        o("*Listbox.highlightBackground", BORDER)
        o("*Text.Background", CARD)
        o("*Text.relief", "flat")

        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT,
                     rowheight=28, borderwidth=0, font=("Segoe UI", 10))
        st.configure("Treeview.Heading", background=PRIMARY_DARK, foreground="white",
                     relief="flat", font=("Segoe UI", 10, "bold"), padding=6)
        st.map("Treeview.Heading", background=[("active", PRIMARY)])
        st.map("Treeview", background=[("selected", "#bfdbfe")], foreground=[("selected", TEXT)])
        st.configure("TCombobox", fieldbackground=CARD, padding=4)
        st.configure("Cart.Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT,
                     rowheight=38, borderwidth=0, font=("Segoe UI", 12))
        st.configure("Cart.Treeview.Heading", background=PRIMARY_DARK, foreground="white",
                     relief="flat", font=("Segoe UI", 11, "bold"), padding=8)
        st.map("Cart.Treeview.Heading", background=[("active", PRIMARY)])
        st.map("Cart.Treeview", background=[("selected", "#bfdbfe")], foreground=[("selected", TEXT)])

    # ---- zubaan (language)
    def audit(self, action, details=""):
        u = self.user
        db.log_action(u["id"] if u else None, u["username"] if u else "-", action, details)

    def is_admin(self):
        """Super Admin (malik). Sirf wohi users aur sab kuch sambhal sakta hai."""
        return bool(self.user) and self.user["role"] == "admin"

    def can(self, key):
        """Kya mojooda user ko ye ijazat hai? (taza ijazaten database se, taake badalne par fauran asar ho)"""
        if not self.user:
            return False
        return key in db.get_perms(db.get_user(self.user["id"]) or self.user)

    def can_return(self):
        return self.can("returns")

    def can_discount(self):
        return self.can("discounts")

    def allowed(self, key, parent=None):
        if self.can(key):
            return True
        messagebox.showwarning("Permission", "You do not have permission for this", parent=parent)
        return False

    def logo_image(self, max_w, max_h):
        """Dukaan ka logo (Settings mein chuna hua) chhota kar ke deta hai. Na ho to None."""
        p = db.logo_path()
        if not p:
            return None
        try:
            img = tk.PhotoImage(file=p)
            f = max(1, -(-img.width() // max_w), -(-img.height() // max_h))
            if f > 1:
                img = img.subsample(f, f)
            self._imgs.append(img)
            return img
        except tk.TclError:
            return None

    def on_close(self):
        try:
            db.backup_on_exit()
        except Exception:
            pass
        self.destroy()

    def logout(self):
        self.audit("logout")
        self.user = None
        self.show_login()

    def apply_language(self, code):
        i18n.set_language(code)
        self.login_lang = i18n.get_language()

    def make_lang_combo(self, parent, on_select):
        cb = ttk.Combobox(parent, state="readonly", width=9,
                          values=i18n.lang_names())
        codes = [c for c, _n in i18n.LANGS]
        cb.current(codes.index(i18n.get_language()))
        cb.bind("<<ComboboxSelected>>", lambda e: on_select(i18n.LANGS[cb.current()][0]))
        cb._no_i18n = True
        return cb

    def switch_language(self, code):
        """Billing screen par zubaan badalna (har user ki apni zubaan yaad rehti hai)."""
        keep = None
        try:
            keep = {"disc": self.e_disc.get(), "dpct": self.e_dpct.get(), "tax": self.e_tax.get(),
                    "paid": self.e_paid.get(), "pay": self.pay_method}
        except (AttributeError, tk.TclError):
            pass
        self.apply_language(code)
        if self.user:
            db.set_user_language(self.user["id"], code)
        self.show_billing()
        if keep:
            for e, k in ((self.e_disc, "disc"), (self.e_dpct, "dpct"), (self.e_tax, "tax"), (self.e_paid, "paid")):
                e.delete(0, "end")
                e.insert(0, keep[k])
            self.set_pay(keep["pay"])
            self.refresh_totals()

    def login_switch(self, code):
        u, p = self.e_user.get(), self.e_pass.get()
        self.apply_language(code)
        self.login_picked = True
        self.show_login(reset_lang=False)
        self.e_user.insert(0, u)
        self.e_pass.insert(0, p)

    def autosize(self, win):
        """Window ko itna bara kar deta hai ke saare buttons nazar aayen (screen/DPI kuch bhi ho)."""
        def fit():
            try:
                win.update_idletasks()
                w = max(win.winfo_width(), win.winfo_reqwidth())
                h = max(win.winfo_height(), win.winfo_reqheight())
                win.geometry(f"{w}x{h}")
            except tk.TclError:
                pass
        win.after(100, fit)
        win.after_idle(lambda: i18n.localize(win))

    def clear(self):
        if self._clock_job:
            try:
                self.after_cancel(self._clock_job)
            except Exception:
                pass
            self._clock_job = None
        self.unbind_keys()
        self._imgs = []
        for w in self.winfo_children():
            w.destroy()

    # ------------------------------------------------------------ LOGIN
    def card(self, title_text, subtitle):
        """Login / setup ka card: logo + naam. (frame, agli khali row) deta hai."""
        tk.Frame(self, bg=PRIMARY_DARK, height=8).pack(fill="x", side="top")
        f = tk.Frame(self, bg=CARD, padx=50, pady=30, highlightthickness=1, highlightbackground=BORDER)
        f.place(relx=0.5, rely=0.5, anchor="center")
        r = 0
        img = self.logo_image(220, 90)
        if img:
            tk.Label(f, image=img, bg=CARD).grid(row=r, column=0, columnspan=2, pady=(0, 8))
            r += 1
        tk.Label(f, text=title_text, font=("Segoe UI", 24, "bold"), bg=CARD, fg=PRIMARY).grid(
            row=r, column=0, columnspan=2, pady=(0, 4))
        tk.Label(f, text=subtitle, font=("Segoe UI", 11), bg=CARD, fg="#64748b").grid(
            row=r + 1, column=0, columnspan=2, pady=(0, 16))
        tk.Label(self, text=f"{APP_NAME}   v{APP_VERSION}", fg="#94a3b8", font=("Segoe UI", 9)).place(
            relx=0.5, rely=1.0, y=-10, anchor="s")
        return f, r + 2

    def show_login(self, reset_lang=True):
        self.clear()
        if reset_lang:   # logout ke baad login screen dukaan ki default zubaan mein
            self.login_picked = False
            self.apply_language(db.get_settings()["language"])
        try:
            self.state("normal")
        except tk.TclError:
            pass
        self.unbind("<Return>")
        f, r = self.card(db.get_settings()["store_name"], "Billing System")
        tk.Label(f, text="Username", font=("Segoe UI", 12), bg=CARD).grid(row=r, column=0, sticky="e", pady=8, padx=6)
        tk.Label(f, text="Password", font=("Segoe UI", 12), bg=CARD).grid(row=r + 1, column=0, sticky="e", pady=8, padx=6)
        self.e_user = tk.Entry(f, font=("Segoe UI", 12))
        self.e_pass = tk.Entry(f, font=("Segoe UI", 12), show="*")
        self.e_user.grid(row=r, column=1, padx=8, ipady=4)
        self.e_pass.grid(row=r + 1, column=1, padx=8, ipady=4)
        tk.Button(f, text="Login", font=("Segoe UI", 12, "bold"), width=18, bg=ACCENT,
                  activebackground="#15803d", command=self.login).grid(
            row=r + 2, column=0, columnspan=2, pady=(22, 0), ipady=3)
        tk.Button(f, text="Forgot password?", bg=CARD, fg=PRIMARY, activebackground=CARD,
                  activeforeground=PRIMARY_DARK, font=("Segoe UI", 10, "underline"),
                  command=self.forgot_password).grid(row=r + 3, column=0, columnspan=2, pady=(10, 0))
        self.e_user.focus()
        self.bind("<Return>", lambda e: self.login())
        lang_bar = tk.Frame(self)
        lang_bar.place(relx=1.0, x=-16, y=16, anchor="ne")
        self.make_lang_combo(lang_bar, self.login_switch).pack()
        i18n.localize(self)

    def setup_switch(self, code):
        keep = {k: getattr(self, k).get() for k in ("s_shop", "s_user", "s_pw", "s_pw2", "s_rec") if hasattr(self, k)}
        self.apply_language(code)
        self.show_setup(keep)

    def show_setup(self, keep=None):
        """Pehli dafa: dukaan ka naam aur admin ka password khud set karein."""
        keep = keep or {}
        self.clear()
        self.unbind("<Return>")
        f, r = self.card("Welcome!", "Set up your shop")
        fields = [("s_shop", "Shop name", "My Superstore", False), ("s_user", "Super Admin username", "admin", False),
                  ("s_pw", "Password (at least 6 characters)", "", True), ("s_pw2", "Confirm password", "", True),
                  ("s_rec", "Recovery code (optional)", "", True)]
        for i, (attr, label, default, secret) in enumerate(fields):
            tk.Label(f, text=label, font=("Segoe UI", 11), bg=CARD).grid(row=r + i, column=0, sticky="e", pady=6, padx=6)
            e = tk.Entry(f, font=("Segoe UI", 12), width=26, show="*" if secret else "")
            e.insert(0, keep.get(attr, default))
            e.grid(row=r + i, column=1, padx=8, ipady=3)
            setattr(self, attr, e)
        tk.Label(f, text="The recovery code lets you reset a forgotten admin password. Write it down and keep it safe.",
                 font=("Segoe UI", 9), fg="#64748b", bg=CARD, wraplength=420, justify="left").grid(
            row=r + len(fields), column=0, columnspan=2, pady=(6, 0))
        tk.Button(f, text="Create account and start", font=("Segoe UI", 12, "bold"), bg=ACCENT,
                  activebackground="#15803d", command=self.finish_setup).grid(
            row=r + len(fields) + 1, column=0, columnspan=2, pady=(18, 0), ipady=4, ipadx=16)
        self.s_pw.focus() if keep.get("s_shop") else self.s_shop.focus()
        self.bind("<Return>", lambda e: self.finish_setup())
        lang_bar = tk.Frame(self)
        lang_bar.place(relx=1.0, x=-16, y=16, anchor="ne")
        self.make_lang_combo(lang_bar, self.setup_switch).pack()
        i18n.localize(self)

    def finish_setup(self):
        shop, user = self.s_shop.get().strip(), self.s_user.get().strip()
        p1, p2, rec = self.s_pw.get(), self.s_pw2.get(), self.s_rec.get().strip()
        if not shop:
            messagebox.showwarning("Setup", "Enter your shop name")
        elif len(user) < 3 or " " in user:
            messagebox.showwarning("Setup", "The username must be at least 3 characters, without spaces")
        elif len(p1) < 6:
            messagebox.showwarning("Setup", "The password must be at least 6 characters")
        elif p1 != p2:
            messagebox.showwarning("Setup", "The two passwords do not match")
        elif rec and len(rec) < 4:
            messagebox.showwarning("Setup", "Use a recovery code of at least 4 characters")
        else:
            db.create_admin(user, p1)
            db.set_setting("store_name", shop)
            db.set_setting("language", i18n.get_language())
            if rec:
                db.set_recovery_code(rec)
            db.log_action(None, user, "setup", "first-time setup completed")
            messagebox.showinfo("Setup complete", "Your account is ready. Please log in.")
            self.show_login()
            self.e_user.insert(0, user)
            self.e_pass.focus()

    def forgot_password(self):
        if not db.has_recovery_code():
            messagebox.showinfo(
                "Recovery",
                "Recovery code is not set yet.\n\nLog in as admin and set a 'Recovery code' in Settings.\nIf you cannot log in right now, run reset_admin.py.")
            return
        code = simpledialog.askstring("Recovery", "Enter the recovery code:", show="*", parent=self)
        if code is None:
            return
        if not db.check_recovery_code(code):
            messagebox.showerror("Recovery", "The recovery code is wrong")
            return
        new = simpledialog.askstring("New password", "New admin password (at least 4 characters):",
                                     show="*", parent=self)
        if new is None:
            return
        if len(new) < 4:
            messagebox.showwarning("Password", "Use a password of at least 4 characters")
            return
        db.reset_password("admin", new)
        messagebox.showinfo("Password", "The admin password has been changed. Please log in.")

    def login(self):
        now = time.time()
        if now < self._lock_until:
            messagebox.showwarning("Login", raw("Too many wrong attempts. Please wait {s} seconds.",
                                                s=int(self._lock_until - now) + 1))
            return
        u = self.e_user.get().strip()
        p = self.e_pass.get()
        row = db.authenticate(u, p)
        if row:
            self._fail_count = 0
            self.user = row
            self.cart = {}
            self.cust = None
            mine = row["language"] if "language" in row.keys() else None
            if self.login_picked:          # login screen par khud zubaan chuni thi: wahi rakhein aur yaad rakhein
                code = self.login_lang
                db.set_user_language(row["id"], code)
            else:
                code = mine or db.get_settings()["language"]
            self.login_picked = False
            self.apply_language(code)
            self.audit("login")
            self.show_billing()
            if self.can("inventory") or self.can("dashboard"):
                self.after(400, lambda: self.show_alerts(True))
        else:
            self._fail_count += 1
            db.log_action(None, u or "-", "login_failed", "")
            if self._fail_count >= 5:      # 5 ghalat koshishon ke baad 30 second ruk jayen
                self._fail_count = 0
                self._lock_until = time.time() + 30
                messagebox.showerror("Login", raw("Too many wrong attempts. Please wait {s} seconds.", s=30))
            else:
                messagebox.showerror("Login", "Wrong username or password")

    # ---------------------------------------------------------- BILLING
    def show_billing(self):
        self.clear()
        self.unbind("<Return>")
        settings = db.get_settings()
        try:
            self.state("zoomed")  # asli POS ki tarah poori screen
        except tk.TclError:
            pass

        # ---- header
        top = tk.Frame(self, bg=PRIMARY_DARK)
        top.pack(fill="x")
        logo = self.logo_image(130, 36)
        if logo:
            tk.Label(top, image=logo, bg=PRIMARY_DARK).pack(side="left", padx=(12, 0), pady=4)
        tk.Label(top, text=settings["store_name"], bg=PRIMARY_DARK, fg="white",
                 font=("Segoe UI", 16, "bold")).pack(side="left", padx=14, pady=8)
        tk.Label(top, text="POS Terminal", bg=PRIMARY_DARK, fg="#93c5fd",
                 font=("Segoe UI", 10)).pack(side="left", pady=8)
        tk.Button(top, text="Logout", bg=DANGER, activebackground="#b91c1c",
                  command=self.logout).pack(side="right", padx=10, pady=8)
        self.make_lang_combo(top, self.switch_language).pack(side="right", padx=4)
        self.lbl_clock = tk.Label(top, bg=PRIMARY_DARK, fg="white", font=("Segoe UI", 11, "bold"))
        self.lbl_clock.pack(side="right", padx=14)
        tk.Label(top, text=tr("User: {name} - {role}", name=self.user['username'], role=tr(db.ROLE_LABELS.get(self.user['role'], self.user['role']))),
                 bg=PRIMARY_DARK, fg="#bfdbfe", font=("Segoe UI", 10)).pack(side="right", padx=8)
        self.tick_clock()

        # ---- menu
        menu = tk.Frame(self, bg="#e0e7ff")
        menu.pack(fill="x")
        buttons = [("Bills", self.open_bills)]
        if self.can("returns"):
            buttons.append(("Returns", self.open_returns))
        buttons.append(("Customers", self.open_customers))
        if self.can("dashboard"):
            buttons.insert(0, ("Dashboard", self.open_dashboard))
        buttons += [(t, c) for t, c, k in (("Inventory", self.open_inventory, "inventory"),
                                           ("Stock In", self.open_purchase, "purchases"),
                                           ("Suppliers", self.open_suppliers, "suppliers"),
                                           ("Reports", self.open_reports, "reports"),
                                           ("Closing", self.open_closing, "closing")) if self.can(k)]
        if self.can("inventory") or self.can("dashboard"):
            low = len(db.low_stock_products()) + len(db.expiring_products(30))
            buttons.append((tr("Alerts ({n})", n=low), self.show_alerts))
        buttons += [(t, c) for t, c, k in (("Backup", self.open_backup, "backup"),
                                           ("Audit Log", self.open_audit, "audit"),
                                           ("Users", self.open_users, "users"),
                                           ("Settings", self.open_settings, "settings")) if self.can(k)]
        for text, cmd in buttons:
            tk.Button(menu, text=text, command=cmd).pack(side="left", padx=3, pady=4)

        # ---- shortcut bar (neeche)
        foot = tk.Frame(self, bg="#e2e8f0")
        foot.pack(fill="x", side="bottom")
        tk.Label(foot, bg="#e2e8f0", fg="#475569", font=("Segoe UI", 9),
                 text="F2 Scan    F3 Remove    F4 Hold    F5 Recall    F6 / F7 Qty    F8 Customer    F9 Payment    F10 New bill    F12 Save    |    Empty Enter = go to amount received"
                 ).pack(side="left", padx=10, pady=5)

        main = tk.Frame(self)
        main.pack(fill="both", expand=True, padx=10, pady=(8, 4))

        # ================= left: scan + cart
        left = tk.Frame(main)
        left.pack(side="left", fill="both", expand=True)

        sf = tk.Frame(left, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        sf.pack(fill="x")
        tk.Label(sf, text="SCAN / SEARCH", bg=CARD, fg="#64748b",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12, pady=(8, 0))
        row = tk.Frame(sf, bg=CARD)
        row.pack(fill="x", padx=12, pady=(0, 4))
        self.e_scan = tk.Entry(row, font=("Segoe UI", 18))
        self.e_scan.pack(side="left", fill="x", expand=True, ipady=5)
        self.e_scan.bind("<Return>", self.on_scan_enter)
        self.e_scan.bind("<Up>", lambda e: self.move_sel(-1))
        self.e_scan.bind("<Down>", lambda e: self.move_sel(1))
        self.e_scan.bind("<Escape>", lambda e: self.e_scan.delete(0, "end"))
        tk.Button(row, text="Add", font=("Segoe UI", 12, "bold"),
                  command=self.add_by_text).pack(side="left", padx=(8, 0), ipady=6)
        self.lbl_hint = tk.Label(sf, text=HINT_TEXT, bg=CARD, fg="#94a3b8", font=("Segoe UI", 9))
        self.lbl_hint.pack(anchor="w", padx=12, pady=(0, 8))

        cols = ("no", "name", "price", "qty", "total")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", style="Cart.Treeview",
                                 selectmode="browse")
        for c, t, w, a in (("no", "#", 46, "center"), ("name", "Product", 360, "w"),
                           ("price", "Price", 110, "e"), ("qty", "Qty", 80, "center"),
                           ("total", "Total", 130, "e")):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor=a, stretch=(c == "name"))
        self.tree.tag_configure("odd", background="#f1f5f9")
        self.tree.pack(fill="both", expand=True, pady=(8, 6))
        self.tree.bind("<Delete>", lambda e: self.remove_item())

        info = tk.Frame(left)
        info.pack(fill="x")
        self.lbl_items = tk.Label(info, text="Items: 0     Qty: 0", font=("Segoe UI", 12, "bold"),
                                  fg=PRIMARY_DARK)
        self.lbl_items.pack(side="left")
        bf = tk.Frame(left)
        bf.pack(fill="x", pady=(6, 0))
        for text, cmd, color in (("+ Qty  F6", lambda: self.change_qty(1), None),
                                 ("- Qty  F7", lambda: self.change_qty(-1), None),
                                 ("Remove  F3", self.remove_item, DANGER),
                                 ("Hold  F4", self.hold_bill, "#f59e0b"),
                                 ("New bill  F10", self.new_bill, DANGER)):
            b = tk.Button(bf, text=text, command=cmd)
            if color:
                b.config(bg=color)
            b.pack(side="left", padx=(0, 6), ipady=3)
        self.btn_recall = tk.Button(bf, text="Recall  F5", bg="#0ea5e9", command=self.recall_bill)
        self.btn_recall.pack(side="left", padx=(0, 6), ipady=3)

        # ================= right: payment panel
        right = tk.Frame(main, bg=CARD, highlightthickness=1, highlightbackground=BORDER,
                         padx=14, pady=8)
        right.pack(side="right", fill="y", padx=(10, 0))
        self.lbl_billno = tk.Label(right, text=tr("Bill #{n}", n=db.next_bill_no()), fg="#64748b",
                                   font=("Segoe UI", 11, "bold"))
        self.lbl_billno.pack(anchor="w")

        total_box = tk.Frame(right, bg=PRIMARY_DARK)
        total_box._keep = True
        total_box.pack(fill="x", pady=(2, 8))
        tk.Label(total_box, text="PAYABLE  (Rs)", bg=PRIMARY_DARK, fg="#93c5fd",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(8, 0))
        self.lbl_total = tk.Label(total_box, text="0.00", bg=PRIMARY_DARK, fg="#4ade80",
                                  font=("Segoe UI", 32, "bold"))
        self.lbl_total.pack(anchor="e", padx=12, pady=(0, 8))

        grid = tk.Frame(right)
        grid.pack(fill="x")
        self.v = {}
        for i, (key, label) in enumerate((("sub", "Subtotal"), ("disc", "Discount"), ("tax", "Tax"))):
            tk.Label(grid, text=label, font=("Segoe UI", 11)).grid(row=i, column=0, sticky="w")
            self.v[key] = tk.Label(grid, text="0.00", font=("Segoe UI", 11, "bold"))
            self.v[key].grid(row=i, column=1, sticky="e")
        grid.columnconfigure(1, weight=1)

        inp = tk.Frame(right)
        inp.pack(fill="x", pady=(8, 0))
        for col, (label, attr, default) in enumerate((("Discount Rs", "e_disc", "0"),
                                                      ("Discount %", "e_dpct", "0"),
                                                      ("Tax %", "e_tax", settings["default_tax"]))):
            pad = (0, 0) if col == 0 else (8, 0)
            tk.Label(inp, text=label, font=("Segoe UI", 9)).grid(row=0, column=col, sticky="w", padx=pad)
            e = tk.Entry(inp, font=("Segoe UI", 12), width=8)
            e.insert(0, default)
            e.grid(row=1, column=col, padx=pad)
            e.bind("<KeyRelease>", lambda ev: self.refresh_totals())
            setattr(self, attr, e)
        if not self.can_discount():          # is cashier ko discount ki ijazat nahi
            for e in (self.e_disc, self.e_dpct):
                e.config(state="disabled")

        tk.Label(right, text="Payment  (F9)", font=("Segoe UI", 9)).pack(anchor="w", pady=(10, 0))
        pf = tk.Frame(right)
        pf.pack(fill="x", pady=2)
        self.pay_buttons = {}
        for i, (key, label) in enumerate(PAY_METHODS):
            b = tk.Button(pf, text=label, font=("Segoe UI", 9, "bold"), padx=4,
                          command=lambda k=key: self.set_pay(k))
            b.grid(row=0, column=i, padx=2, sticky="ew")
            self.pay_buttons[key] = b
        pf.columnconfigure((0, 1, 2, 3), weight=1)
        self.set_pay("cash")

        tk.Label(right, text="Customer, for credit  (F8)", font=("Segoe UI", 9)).pack(
            anchor="w", pady=(10, 0))
        cf = tk.Frame(right)
        cf.pack(fill="x")
        self.lbl_cust = tk.Label(cf, text="— none —", font=("Segoe UI", 11, "bold"), fg=PRIMARY_DARK)
        self.lbl_cust.pack(side="left")
        tk.Button(cf, text="x", width=2, command=self.clear_customer).pack(side="right")
        tk.Button(cf, text="Select", command=self.choose_customer).pack(side="right", padx=4)

        tk.Label(right, text="Amount received  (empty = exact bill amount)", font=("Segoe UI", 9)).pack(
            anchor="w", pady=(10, 0))
        self.e_paid = tk.Entry(right, font=("Segoe UI", 18, "bold"), justify="right")
        self.e_paid.pack(fill="x", ipady=3)
        self.e_paid.bind("<KeyRelease>", lambda e: self.refresh_change())
        self.e_paid.bind("<Return>", lambda e: self.checkout())
        self.e_paid.bind("<Escape>", lambda e: self.focus_scan())
        self.lbl_change = tk.Label(right, text="", font=("Segoe UI", 14, "bold"))
        self.lbl_change.pack(anchor="e", pady=2)

        tk.Button(right, text="PAY & SAVE   (F12)", font=("Segoe UI", 14, "bold"), bg=ACCENT,
                  activebackground="#15803d", command=self.checkout).pack(fill="x", ipady=10, pady=(6, 0))

        self.paint(right, CARD)
        self.bind_keys()
        self.update_customer_label()
        self.update_held_label()
        self.refresh_cart()
        i18n.localize(self)
        self.focus_scan()

    # ---- keyboard shortcuts
    def bind_keys(self):
        self._keys = {
            "<F2>": self.focus_scan, "<F3>": self.remove_item, "<F4>": self.hold_bill,
            "<F5>": self.recall_bill, "<F6>": lambda: self.change_qty(1),
            "<F7>": lambda: self.change_qty(-1), "<F8>": self.choose_customer,
            "<F9>": self.cycle_pay, "<F10>": self.new_bill, "<Control-n>": self.new_bill,
            "<F12>": self.checkout,
        }
        for seq, fn in self._keys.items():
            self.bind(seq, lambda e, f=fn: (f(), "break")[1])

    def unbind_keys(self):
        for seq in list(self._keys):
            try:
                self.unbind(seq)
            except tk.TclError:
                pass
        self._keys = {}

    def focus_scan(self):
        try:
            self.e_scan.focus_set()
        except (tk.TclError, AttributeError):
            pass

    def tick_clock(self):
        try:
            self.lbl_clock.config(text=datetime.now().strftime("%d %b %Y    %I:%M:%S %p"))
            self._clock_job = self.after(1000, self.tick_clock)
        except tk.TclError:
            self._clock_job = None

    def flash(self, msg, color=DANGER, ms=3500):
        """Scan ke neeche chhota message (messagebox ki tarah scanning nahi rokta)."""
        try:
            self.lbl_hint.config(text=tr(msg), fg=color)
            if self._flash_job:
                self.after_cancel(self._flash_job)
            self._flash_job = self.after(ms, self.reset_hint)
        except tk.TclError:
            pass

    def reset_hint(self):
        try:
            self.lbl_hint.config(text=tr(HINT_TEXT), fg="#94a3b8")
        except tk.TclError:
            pass

    def on_scan_enter(self, event=None):
        if self.e_scan.get().strip():
            self.add_by_text()
        elif self.cart:
            self.e_paid.focus_set()      # khali Enter = ab paise likhein
            self.e_paid.select_range(0, "end")

    def move_sel(self, delta):
        items = self.tree.get_children()
        if not items:
            return "break"
        sel = self.tree.selection()
        idx = items.index(sel[0]) if sel and sel[0] in items else len(items) - 1
        idx = max(0, min(len(items) - 1, idx + delta))
        self.tree.selection_set(items[idx])
        self.tree.see(items[idx])
        return "break"

    def cycle_pay(self):
        keys = [k for k, _ in PAY_METHODS]
        self.set_pay(keys[(keys.index(self.pay_method) + 1) % len(keys)])

    def reset_bill_inputs(self):
        s = db.get_settings()
        for e, v in ((self.e_disc, "0"), (self.e_dpct, "0"), (self.e_tax, s["default_tax"]),
                     (self.e_paid, "")):
            e.delete(0, "end")
            if v:
                e.insert(0, v)
        self.cust = None
        self.set_pay("cash")
        self.update_customer_label()

    def new_bill(self):
        if self.cart and not messagebox.askyesno("New bill", "Discard the current bill and start a new one?"):
            self.focus_scan()
            return
        self.cart = {}
        self.reset_bill_inputs()
        self.refresh_cart()
        self.focus_scan()

    # ---- hold / recall
    def update_held_label(self):
        try:
            self.btn_recall.config(text=tr("Recall ({n})  F5", n=len(self.held)))
        except (tk.TclError, AttributeError):
            pass

    def hold_bill(self):
        if not self.cart:
            self.flash("The bill is empty, it cannot be held")
            return
        self.held.append({
            "cart": copy.deepcopy(self.cart), "cust_id": self.cust["id"] if self.cust else None,
            "disc": self.e_disc.get(), "dpct": self.e_dpct.get(), "tax": self.e_tax.get(),
            "when": datetime.now()})
        self.cart = {}
        self.reset_bill_inputs()
        self.refresh_cart()
        self.update_held_label()
        self.flash(raw("Bill held ({n} on hold). Use Recall (F5) to bring it back.", n=len(self.held)), ACCENT)
        self.focus_scan()

    def restore_held(self, index):
        h = self.held.pop(index)
        self.cart = h["cart"]
        self.cust = db.get_customer(h["cust_id"]) if h["cust_id"] else None
        for e, v in ((self.e_disc, h["disc"]), (self.e_dpct, h["dpct"]), (self.e_tax, h["tax"])):
            e.delete(0, "end")
            e.insert(0, v)
        self.update_customer_label()
        self.update_held_label()
        self.refresh_cart()
        self.focus_scan()

    def recall_bill(self):
        if not self.held:
            self.flash("There is no bill on hold")
            return
        if self.cart:
            self.flash("Please save or hold the current bill first")
            return
        if len(self.held) == 1:
            self.restore_held(0)
            return
        win = tk.Toplevel(self)
        win.title("Held bills")
        win.geometry("420x300")
        self.autosize(win)
        win.bind("<Destroy>", lambda e: self.after(80, self.focus_scan) if e.widget is win else None)
        lb = tk.Listbox(win, font=("Segoe UI", 12))
        lb.pack(fill="both", expand=True, padx=10, pady=10)
        for h in self.held:
            total = sum(i["price"] * i["qty"] for i in h["cart"].values())
            lb.insert("end", tr("{time}   {n} items   Rs {total}", time=f"{h['when']:%I:%M %p}", n=len(h['cart']), total=f"{total:,.0f}"))
        lb.selection_set(0)
        lb.activate(0)

        def pick(event=None):
            sel = lb.curselection()
            if sel:
                idx = sel[0]
                win.destroy()
                self.restore_held(idx)
        lb.bind("<Return>", pick)
        lb.bind("<Double-Button-1>", pick)
        win.bind("<Escape>", lambda e: win.destroy())
        lb.focus_set()

    def set_pay(self, method):
        self.pay_method = method
        for key, b in self.pay_buttons.items():
            if key == method:
                b.config(bg=ACCENT, fg="white", activebackground="#15803d")
            else:
                b.config(bg="#e2e8f0", fg=TEXT, activebackground="#cbd5e1")

    def paint(self, widget, color):
        """Card ke andar ke labels/frames ka background card jaisa kar deta hai."""
        for w in widget.winfo_children():
            if getattr(w, "_keep", False):
                continue
            if w.winfo_class() in ("Label", "Frame"):
                w.configure(bg=color)
            self.paint(w, color)

    def add_by_text(self):
        text = self.e_scan.get().strip()
        if not text:
            return
        qty = 1
        m = re.match(r"^(\d{1,3})\s*[*xX]\s*(.+)$", text)   # 5*barcode  ya  5x naam
        if m:
            qty, text = int(m.group(1)), m.group(2).strip()
        product = db.get_product_by_barcode(text)
        if product:
            self.add_to_cart(product, qty)
        else:
            results = db.search_products(text)
            if not results:
                self.flash(raw("Product not found: {text}", text=text))
                self.bell()
            elif len(results) == 1:
                self.add_to_cart(results[0], qty)
            else:
                self.choose_product(results, on_pick=lambda p: self.add_to_cart(p, qty))
        self.e_scan.delete(0, "end")
        self.focus_scan()

    def choose_product(self, results, on_pick=None):
        win = tk.Toplevel(self)
        win.title("Select a product")
        win.geometry("460x320")
        self.autosize(win)
        win.bind("<Destroy>", lambda e: self.after(80, self.focus_scan) if e.widget is win else None)
        lb = tk.Listbox(win, font=("Segoe UI", 12))
        lb.pack(fill="both", expand=True)
        for r in results:
            lb.insert("end", tr("{name}  -  Rs {price}  (stock {stock})", name=r['name'], price=r['sale_price'], stock=r['stock_qty']))
        lb.selection_set(0)
        lb.activate(0)

        def pick(event=None):
            sel = lb.curselection()
            if sel:
                product = results[sel[0]]
                win.destroy()
                (on_pick or self.add_to_cart)(product)
        lb.bind("<Double-Button-1>", pick)
        lb.bind("<Return>", pick)
        win.bind("<Escape>", lambda e: win.destroy())
        lb.focus_set()

    def add_to_cart(self, product, qty=1):
        pid = product["id"]
        in_cart = self.cart[pid]["qty"] if pid in self.cart else 0
        if in_cart + qty > product["stock_qty"]:
            messagebox.showwarning("Stock", raw("{name}: only {stock} in stock", name=product['name'], stock=product['stock_qty']))
            return
        if pid not in self.cart and product["expiry_date"] and \
                product["expiry_date"] < datetime.now().strftime("%Y-%m-%d"):
            if not messagebox.askyesno(
                    "Expiry", raw("{name} has passed its expiry date ({date}).\nSell it anyway?", name=product['name'], date=product['expiry_date'])):
                return
        if pid in self.cart:
            self.cart[pid]["qty"] += qty
        else:
            self.cart[pid] = {"id": pid, "name": product["name"],
                              "price": product["sale_price"], "qty": qty,
                              "stock": product["stock_qty"]}
        self.refresh_cart()
        self.tree.selection_set(str(pid))
        self.tree.see(str(pid))

    def selected_pid(self):
        sel = self.tree.selection()
        if sel:
            return int(sel[0])
        return list(self.cart)[-1] if self.cart else None   # kuch chuna nahi to aakhri item

    def change_qty(self, delta):
        pid = self.selected_pid()
        if pid is None:
            return
        item = self.cart[pid]
        new_qty = item["qty"] + delta
        if new_qty < 1:
            return
        if new_qty > item["stock"]:
            self.flash(raw("{name}: only {stock} in stock", name=item['name'], stock=item['stock']))
            return
        item["qty"] = new_qty
        self.refresh_cart()
        self.tree.selection_set(str(pid))

    def remove_item(self):
        pid = self.selected_pid()
        if pid is not None:
            del self.cart[pid]
            self.refresh_cart()
            if self.cart:
                last = str(list(self.cart)[-1])
                self.tree.selection_set(last)
        self.focus_scan()

    def clear_cart(self):
        self.cart = {}
        self.refresh_cart()

    def refresh_cart(self):
        self.tree.delete(*self.tree.get_children())
        for n, (pid, it) in enumerate(self.cart.items(), start=1):
            self.tree.insert("", "end", iid=str(pid), tags=("odd",) if n % 2 == 0 else (), values=(
                n, it["name"], f"{it['price']:,.2f}", it["qty"], f"{it['price'] * it['qty']:,.2f}"))
        self.lbl_items.config(text=tr("Items: {items}     Qty: {qty}", items=len(self.cart), qty=sum(i['qty'] for i in self.cart.values())))
        self.refresh_totals()

    def get_number(self, entry):
        try:
            return max(0.0, float(entry.get() or 0))
        except ValueError:
            return 0.0

    def calc(self):
        subtotal = sum(i["price"] * i["qty"] for i in self.cart.values())
        discount = min(self.get_number(self.e_disc)
                       + subtotal * min(self.get_number(self.e_dpct), 100) / 100, subtotal)
        tax_pct = self.get_number(self.e_tax)
        tax = (subtotal - discount) * tax_pct / 100
        return subtotal, discount, tax_pct, tax, subtotal - discount + tax

    def refresh_totals(self):
        subtotal, discount, tax_pct, tax, total = self.calc()
        self.lbl_total.config(text=f"{total:,.2f}")
        self.v["sub"].config(text=f"{subtotal:,.2f}")
        self.v["disc"].config(text=f"- {discount:,.2f}" if discount > 0 else "0.00")
        self.v["tax"].config(text=f"{tax:,.2f}")
        self.refresh_change()

    def refresh_change(self):
        """Customer ne jitne diye, us se 'wapis dena' ya 'udhaar' live dikhata hai."""
        total = self.calc()[4]
        txt = self.e_paid.get().strip()
        try:
            given = float(txt) if txt else None
        except ValueError:
            given = None
        text, color = "", TEXT
        if given is not None and total > 0:
            if given - total >= 0.02:
                text, color = tr("Change to give: {x}", x=f"{given - total:.2f}"), ACCENT
            elif total - given >= 0.02:
                text, color = tr("Credit (balance): {x}", x=f"{total - given:.2f}"), DANGER
        try:
            self.lbl_change.config(text=text, fg=color)
        except tk.TclError:
            pass

    # --- customer chunna
    def update_customer_label(self):
        if self.cust:
            fresh = db.get_customer(self.cust["id"])
            self.lbl_cust.config(text=tr("{name}  (balance {bal})", name=fresh['name'][:18], bal=f"{fresh['balance']:.0f}"))
        else:
            self.lbl_cust.config(text=tr("— none —"))

    def clear_customer(self):
        self.cust = None
        self.update_customer_label()

    def choose_customer(self):
        win = tk.Toplevel(self)
        win.title("Select a customer")
        win.geometry("420x440")
        self.autosize(win)
        win.bind("<Destroy>", lambda e: self.after(80, self.focus_scan) if e.widget is win else None)
        e_search = tk.Entry(win, font=("Segoe UI", 12))
        e_search.pack(fill="x", padx=10, pady=8)
        lb = tk.Listbox(win, font=("Segoe UI", 12), height=10)
        lb.pack(fill="both", expand=True, padx=10)
        rows = []

        def load(event=None):
            rows.clear()
            rows.extend(db.list_customers(e_search.get().strip()))
            lb.delete(0, "end")
            for r in rows:
                lb.insert("end", tr("{name}  {phone}  (balance {bal})", name=r['name'], phone=r['phone'] or '', bal=f"{r['balance']:.0f}"))

        def pick(event=None):
            sel = lb.curselection()
            if sel:
                self.cust = rows[sel[0]]
                self.update_customer_label()
                win.destroy()

        e_search.bind("<KeyRelease>", load)
        lb.bind("<Double-Button-1>", pick)
        lb.bind("<Return>", pick)
        tk.Button(win, text="Select", command=pick).pack(pady=4)

        nf = tk.LabelFrame(win, text="New customer", padx=8, pady=8)
        nf.pack(fill="x", padx=10, pady=8)
        e_name = tk.Entry(nf, width=16)
        e_phone = tk.Entry(nf, width=14)
        tk.Label(nf, text="Name").grid(row=0, column=0)
        tk.Label(nf, text="Phone").grid(row=0, column=1)
        e_name.grid(row=1, column=0, padx=3)
        e_phone.grid(row=1, column=1, padx=3)

        def add_new():
            name = e_name.get().strip()
            if not name:
                messagebox.showwarning("Customer", "Please enter a name", parent=win)
                return
            cid = db.add_customer(name, e_phone.get().strip())
            self.cust = db.get_customer(cid)
            self.update_customer_label()
            win.destroy()
        tk.Button(nf, text="Add", command=add_new).grid(row=1, column=2, padx=6)
        load()
        e_search.focus()

    # --- bill save
    def checkout(self):
        if not self.cart:
            self.flash("The bill is empty")
            return
        subtotal, discount, tax_pct, tax, total = self.calc()
        paid_text = self.e_paid.get().strip()
        try:
            tendered = float(paid_text) if paid_text else total
        except ValueError:
            messagebox.showwarning("Paid", "Enter the amount received correctly")
            return
        tendered = max(0.0, tendered)
        paid = min(tendered, total)          # bill mein lagne wale paise
        change = tendered - total if tendered - total >= 0.02 else 0.0   # customer ko wapis
        cust_id = self.cust["id"] if self.cust else None
        if total - paid >= 0.02 and not cust_id:
            messagebox.showwarning("Credit", "Full payment was not given: select a customer first")
            return

        items = [(i["id"], i["qty"], i["price"]) for i in self.cart.values()]
        try:
            sale_id = db.save_sale(self.user["id"], items, discount, tax_pct, cust_id, paid,
                                   self.pay_method)
        except Exception as e:
            messagebox.showerror("Error", raw("Could not save the bill: {err}", err=e))
            return

        self.audit("bill_saved", f"#{sale_id} total {total:.2f} {self.pay_method}"
                   + (f" discount {discount:.2f}" if discount > 0 else ""))
        s = db.get_settings()
        credit = total - paid if total - paid >= 0.02 else 0.0
        rl = s["receipt_language"]
        rlang = i18n.get_language() if rl == "same" else rl
        text = rcpt.build_text(s, {
            "bill_no": sale_id, "when": datetime.now(), "cashier": self.user["username"],
            "customer": db.get_customer(cust_id)["name"] if cust_id else "",
            "payment": pay_label("udhaar" if paid <= 0 else self.pay_method, total, paid,
                                 fn=lambda t: raw(t, lang=rlang)),
            "items": [(i["name"], i["qty"], i["price"]) for i in self.cart.values()],
            "subtotal": subtotal, "discount": discount, "tax_pct": tax_pct, "tax": tax,
            "total": total, "tendered": tendered, "change": change, "credit": credit,
            "balance": db.get_customer(cust_id)["balance"] if cust_id else 0.0}, rlang)

        receipts_dir = os.path.join(db.DATA_DIR, "receipts")
        os.makedirs(receipts_dir, exist_ok=True)
        path = os.path.join(receipts_dir, f"receipt_{sale_id}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

        # cash drawer (agar setting mein printer ka naam likha ho)
        if s.get("drawer_printer") and self.pay_method == "cash" and paid > 0:
            try:
                rcpt.open_cash_drawer(s["drawer_printer"])
            except Exception as e:
                if not self._drawer_warned:
                    self._drawer_warned = True
                    messagebox.showwarning("Cash drawer", raw("Cash drawer did not open:\n{err}", err=e))

        self.cart = {}
        self.reset_bill_inputs()
        self.refresh_cart()
        self.lbl_billno.config(text=tr("Bill #{n}", n=db.next_bill_no()))
        self.flash(raw("Bill #{n} saved  |  Total {total}", n=sale_id, total=f"{total:,.2f}"), ACCENT, 5000)
        self.focus_scan()
        if s.get("auto_print") == "1":
            self.print_receipt(text, sale_id)
            self.focus_scan()
        else:
            self.show_receipt(text, path, sale_id)

    def print_receipt(self, text, bill_no):
        try:
            rcpt.print_html(text, bill_no, db.get_settings().get("paper_width", "80"))
        except Exception as e:
            messagebox.showerror("Print", raw("Could not print: {err}", err=e))

    def show_receipt(self, receipt_text, path, bill_no=None):
        if bill_no is None:
            m = re.search(r"receipt_(\d+)", os.path.basename(path))
            bill_no = m.group(1) if m else ""
        win = tk.Toplevel(self)
        win.title(tr("Receipt  #{n}", n=bill_no))
        logo = self.logo_image(220, 70)
        if logo:
            tk.Label(win, image=logo).pack(pady=(10, 0))
        txt = tk.Text(win, font=("Courier New", 10), width=44, height=30)
        txt.insert("1.0", receipt_text)
        txt.config(state="disabled")
        txt.pack(padx=10, pady=10)

        def close(event=None):
            win.destroy()
            self.focus_scan()

        def do_print(event=None):
            self.print_receipt(receipt_text, bill_no)
        tk.Button(win, text="Print  (Enter)", bg=ACCENT, command=do_print).pack(side="left", padx=20, pady=8)
        tk.Button(win, text="Close  (Esc)", command=close).pack(side="right", padx=20, pady=8)
        win.bind("<Return>", do_print)
        win.bind("<Escape>", close)
        win.protocol("WM_DELETE_WINDOW", close)
        i18n.localize(win)
        win.focus_force()

    # -------------------------------------------------------- CUSTOMERS
    def open_customers(self):
        win = tk.Toplevel(self)
        win.title("Customers / Credit Ledger")
        win.geometry("640x520")
        self.autosize(win)

        top = tk.Frame(win)
        top.pack(fill="x", padx=10, pady=8)
        tk.Label(top, text="Search:").pack(side="left")
        e_search = tk.Entry(top, width=24)
        e_search.pack(side="left", padx=6)
        lbl_total = tk.Label(top, text="", font=("Segoe UI", 12, "bold"), fg="#dc2626")
        lbl_total.pack(side="right")

        tree = ttk.Treeview(win, columns=("name", "phone", "balance"), show="headings")
        for c, t, w in (("name", "Name", 250), ("phone", "Phone", 150), ("balance", "Balance (Rs)", 130)):
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="e" if c == "balance" else "w")
        tree.tag_configure("owes", foreground="#dc2626")
        tree.pack(fill="both", expand=True, padx=10)

        def load(event=None):
            tree.delete(*tree.get_children())
            total = 0.0
            for r in db.list_customers(e_search.get().strip()):
                total += r["balance"]
                tree.insert("", "end", iid=str(r["id"]),
                            tags=("owes",) if r["balance"] > 0.01 else (),
                            values=(r["name"], r["phone"], f"{r['balance']:.2f}"))
            lbl_total.config(text=tr("Total credit: {x}", x=f"{total:.0f}"))
        e_search.bind("<KeyRelease>", load)

        def receive():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Payment", "Select a customer first", parent=win)
                return
            amt = simpledialog.askfloat("Payment", "How much was received?", minvalue=0.01, parent=win)
            if amt:
                db.receive_payment(int(sel[0]), amt)
                self.audit("customer_payment", f"{tree.item(sel[0])['values'][0]} {amt:.2f}")
                load()

        nf = tk.LabelFrame(win, text="New customer", padx=8, pady=8)
        nf.pack(fill="x", padx=10, pady=8)
        e_name = tk.Entry(nf, width=22)
        e_phone = tk.Entry(nf, width=16)
        tk.Label(nf, text="Name").grid(row=0, column=0)
        tk.Label(nf, text="Phone").grid(row=0, column=1)
        e_name.grid(row=1, column=0, padx=4)
        e_phone.grid(row=1, column=1, padx=4)

        def add():
            if not e_name.get().strip():
                messagebox.showwarning("Customer", "Please enter a name", parent=win)
                return
            db.add_customer(e_name.get().strip(), e_phone.get().strip())
            e_name.delete(0, "end")
            e_phone.delete(0, "end")
            load()
        tk.Button(nf, text="Add", bg="#16a34a", fg="white", command=add).grid(row=1, column=2, padx=8)
        tk.Button(win, text="Receive payment", command=receive).pack(pady=(0, 10))
        load()

    # ------------------------------------------------------------ BILLS
    def open_bills(self):
        win = tk.Toplevel(self)
        win.title("Bills (past bills)")
        win.geometry("860x540")
        self.autosize(win)
        today = datetime.now().strftime("%Y-%m-%d")

        top = tk.Frame(win)
        top.pack(fill="x", padx=10, pady=10)
        tk.Label(top, text="Date (YYYY-MM-DD):").pack(side="left")
        e_date = tk.Entry(top, width=12)
        e_date.insert(0, today)
        e_date.pack(side="left", padx=4)
        tk.Label(top, text="   or Bill No:").pack(side="left")
        e_no = tk.Entry(top, width=8)
        e_no.pack(side="left", padx=4)

        cols = ("no", "time", "customer", "pay", "total", "refunded")
        tree = ttk.Treeview(win, columns=cols, show="headings")
        for c, t, w in (("no", "Bill No", 70), ("time", "Date / Time", 140),
                        ("customer", "Customer", 170), ("pay", "Payment", 130),
                        ("total", "Total", 100), ("refunded", "Returned", 100)):
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="w" if c in ("time", "customer", "pay") else "e")
        tree.tag_configure("ret", foreground="#dc2626")
        tree.pack(fill="both", expand=True, padx=10)

        def load(event=None):
            conn = db.get_connection()
            base = """SELECT s.id, strftime('%d-%m-%Y %H:%M', s.sale_date, 'localtime') AS t,
                             c.name AS cname, s.total, s.payment_method AS pm,
                             COALESCE(s.paid, s.total) AS paid,
                             (SELECT COALESCE(SUM(refund_amount), 0) FROM returns r
                              WHERE r.sale_id = s.id) AS refunded
                      FROM sales s LEFT JOIN customers c ON c.id = s.customer_id """
            no = re.sub(r"\D", "", e_no.get())
            if no:
                if not no.isdigit():
                    messagebox.showwarning("Bill", "A bill number is only digits", parent=win)
                    conn.close()
                    return
                rows = conn.execute(base + "WHERE s.id = ?", (int(no),)).fetchall()
            else:
                d = e_date.get().strip()
                try:
                    datetime.strptime(d, "%Y-%m-%d")
                except ValueError:
                    messagebox.showerror("Date", "Write the date like this: 2026-10-20", parent=win)
                    conn.close()
                    return
                rows = conn.execute(
                    base + "WHERE date(s.sale_date, 'localtime') = ? ORDER BY s.id DESC", (d,)).fetchall()
            conn.close()
            tree.delete(*tree.get_children())
            for r in rows:
                tree.insert("", "end", iid=str(r["id"]),
                            tags=("ret",) if r["refunded"] > 0 else (),
                            values=(r["id"], r["t"], r["cname"] or "",
                                    pay_label(r["pm"], r["total"], r["paid"]), f"{r['total']:.2f}",
                                    f"{r['refunded']:.2f}" if r["refunded"] > 0 else ""))

        def selected():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Bill", "Select a bill from the list first", parent=win)
                return None
            return int(sel[0])

        def view_receipt():
            bid = selected()
            if bid is None:
                return
            path = os.path.join(db.DATA_DIR, "receipts", f"receipt_{bid}.txt")
            if not os.path.exists(path):
                messagebox.showinfo("Receipt", "The receipt file for this bill was not found", parent=win)
                return
            with open(path, encoding="utf-8") as f:
                self.show_receipt(f.read(), path, bid)

        def do_return():
            bid = selected()
            if bid is not None:
                self.open_returns(bid)

        tk.Button(top, text="Search", bg="#1e3a8a", fg="white", command=load).pack(side="left", padx=8)
        e_date.bind("<Return>", load)
        e_no.bind("<Return>", load)
        bf = tk.Frame(win)
        bf.pack(pady=10)
        tk.Button(bf, text="View / reprint receipt", command=view_receipt).pack(side="left", padx=6)
        tk.Button(bf, text="Return items of this bill", bg="#dc2626", fg="white",
                  command=do_return).pack(side="left", padx=6)
        tk.Label(win, text="Red bill = some items from it have been returned", fg="#dc2626").pack()
        load()

    # ---------------------------------------------------------- RETURNS
    def open_returns(self, bill_id=None):
        if not self.can_return():
            messagebox.showwarning("Returns", "You do not have permission to process returns")
            return
        win = tk.Toplevel(self)
        win.title("Returns")
        win.geometry("760x520")
        self.autosize(win)

        top = tk.Frame(win)
        top.pack(fill="x", padx=10, pady=10)
        tk.Label(top, text="Bill No  (or scan the receipt barcode):", font=("Segoe UI", 12)).pack(side="left")
        e_bill = tk.Entry(top, width=10, font=("Segoe UI", 12))
        e_bill.pack(side="left", padx=6)
        info = tk.Label(win, text="", font=("Segoe UI", 11), fg="#1e3a8a")
        info.pack(anchor="w", padx=10)

        cols = ("name", "price", "sold", "returned", "now")
        tree = ttk.Treeview(win, columns=cols, show="headings")
        for c, t, w in (("name", "Product", 280), ("price", "Price", 90), ("sold", "Sold", 80),
                        ("returned", "Returned before", 100), ("now", "Return now", 90)):
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="w" if c == "name" else "e")
        tree.pack(fill="both", expand=True, padx=10, pady=8)

        state = {"sale": None, "items": {}, "pending": {}}

        def draw():
            tree.delete(*tree.get_children())
            for pid, r in state["items"].items():
                tree.insert("", "end", iid=str(pid), values=(
                    r["name"], f"{r['unit_price']:.2f}", r["sold"], r["returned"],
                    state["pending"].get(pid, 0)))

        def load():
            try:
                sid = int(re.sub(r"\D", "", e_bill.get()))
            except ValueError:
                messagebox.showwarning("Bill", "Enter the bill number", parent=win)
                return
            sale = db.get_sale(sid)
            if sale is None:
                messagebox.showwarning("Bill", "This bill was not found", parent=win)
                return
            state["sale"] = sale
            state["items"] = {r["product_id"]: r for r in db.get_returnable_items(sid)}
            state["pending"] = {}
            who = raw("  |  Customer: {name}", name=sale['customer_name']) if sale["customer_name"] else ""
            info.config(text=tr("Bill #{id}  |  {date}  |  Total {total}{who}", id=sid, date=sale['sale_date'], total=f"{sale['total']:.2f}", who=who))
            draw()

        def set_qty():
            sel = tree.selection()
            if not sel or state["sale"] is None:
                return
            pid = int(sel[0])
            r = state["items"][pid]
            avail = r["sold"] - r["returned"]
            if avail <= 0:
                messagebox.showinfo("Return", "All of this product has already been returned", parent=win)
                return
            q = simpledialog.askinteger("Return", raw("How many to return? (at most {n})", n=avail),
                                        minvalue=0, maxvalue=avail, parent=win)
            if q is not None:
                state["pending"][pid] = q
                draw()

        def confirm():
            items = [(p, q) for p, q in state["pending"].items() if q > 0]
            if not items:
                messagebox.showinfo("Return", "Select a product first and press 'Choose quantity'", parent=win)
                return
            if not messagebox.askyesno("Confirm", "Confirm the return?", parent=win):
                return
            try:
                _, refund, offset = db.process_return(state["sale"]["id"], self.user["id"], items)
            except Exception as e:
                messagebox.showerror("Return", str(e), parent=win)
                return
            self.audit("return", f"bill #{state['sale']['id']} refund {refund:.2f}")
            msg = raw("Return done. Stock was added back.\nRefund: {x}", x=f"{refund:.2f}")
            if offset > 0:
                msg += raw("\n{x} of this was deducted from the customer's credit.", x=f"{offset:.2f}")
                msg += raw("\nCash to hand back: {x}", x=f"{refund - offset:.2f}")
            messagebox.showinfo("Return", msg, parent=win)
            load()

        tk.Button(top, text="Load Bill", command=load).pack(side="left")
        e_bill.bind("<Return>", lambda e: load())
        bf = tk.Frame(win)
        bf.pack(pady=(0, 10))
        tk.Button(bf, text="Choose quantity", command=set_qty).pack(side="left", padx=6)
        tk.Button(bf, text="Confirm return", bg="#dc2626", fg="white", command=confirm).pack(side="left", padx=6)
        e_bill.focus()
        if bill_id:
            e_bill.insert(0, str(bill_id))
            load()

    # ------------------------------------------------------------ USERS
    def open_users(self):
        if not self.allowed("users"):
            return
        win = tk.Toplevel(self)
        win.title("Users")
        win.geometry("760x520")
        self.autosize(win)
        sup = self.is_admin()
        # Super Admin: Admin (limited) aur Cashier bana sakta hai. Admin (limited): sirf Cashier.
        role_opts = [("manager", "Admin"), ("cashier", "Cashier")] if sup else [("cashier", "Cashier")]

        form = tk.LabelFrame(win, text="New user", padx=8, pady=8)
        form.pack(fill="x", padx=10, pady=10)
        tk.Label(form, text="Username").grid(row=0, column=0, padx=4)
        tk.Label(form, text="Password").grid(row=0, column=1, padx=4)
        tk.Label(form, text="Role").grid(row=0, column=2, padx=4)
        e_name = tk.Entry(form, width=14)
        e_pass = tk.Entry(form, width=14, show="*")
        cb_role = ttk.Combobox(form, values=[tr(label) for _c, label in role_opts], width=10, state="readonly")
        cb_role.current(len(role_opts) - 1)
        e_name.grid(row=1, column=0, padx=4)
        e_pass.grid(row=1, column=1, padx=4)
        cb_role.grid(row=1, column=2, padx=4)
        tk.Label(form, text="A new account starts with the standard permissions for its role. Use 'Permissions' to change them.",
                 fg="#64748b", font=("Segoe UI", 9)).grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))

        tree = ttk.Treeview(win, columns=("name", "role", "perms"), show="headings", height=7)
        for c, t, w, a in (("name", "Username", 220, "w"), ("role", "Role", 150, "w"), ("perms", "Permissions", 150, "center")):
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor=a)
        tree.pack(fill="both", expand=True, padx=10)

        def load():
            tree.delete(*tree.get_children())
            conn = db.get_connection()
            sql = "SELECT * FROM users" + ("" if sup else " WHERE role = 'cashier'") + " ORDER BY role, username"
            for r in conn.execute(sql):
                perms = db.get_perms(r)
                tree.insert("", "end", iid=str(r["id"]), values=(
                    r["username"], tr(db.ROLE_LABELS.get(r["role"], r["role"])),
                    tr("All") if r["role"] == "admin" else f"{len(perms)} / {len(db.PERM_KEYS)}"))
            conn.close()

        def add():
            name, pw = e_name.get().strip(), e_pass.get()
            if not name or len(pw) < 4:
                messagebox.showwarning("User", "Enter a username and a password of at least 4 characters", parent=win)
                return
            role = role_opts[cb_role.current()][0]
            if role == "manager" and not sup:
                return
            try:
                db.create_user(name, pw, role)
            except Exception:
                messagebox.showerror("User", "This username already exists", parent=win)
                return
            self.audit("user_added", f"{name} ({role})")
            e_name.delete(0, "end")
            e_pass.delete(0, "end")
            load()

        def selected_user():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("User", "Select a user from the list first", parent=win)
                return None
            row = db.get_user(int(sel[0]))
            if row is None:
                return None
            if not sup and row["role"] != "cashier":      # Admin (limited) sirf cashiers ko sambhal sakta hai
                messagebox.showwarning("User", "This account can only be changed by the Super Admin", parent=win)
                return None
            return row

        def change_password():
            row = selected_user()
            if row is None:
                return
            pw = simpledialog.askstring("Password", "New password:", show="*", parent=win)
            if pw and len(pw) >= 4:
                conn = db.get_connection()
                conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (db.hash_password(pw), row["id"]))
                conn.commit()
                conn.close()
                self.audit("password_changed", row["username"])
                messagebox.showinfo("Password", "Password changed", parent=win)
            elif pw:
                messagebox.showwarning("Password", "Use at least 4 characters", parent=win)

        def edit_perms():
            row = selected_user()
            if row is None:
                return
            if row["role"] == "admin":
                messagebox.showinfo("Permissions", "The Super Admin always has every permission", parent=win)
                return
            # Super Admin sab ijazaten de sakta hai; Admin (limited) sirf Returns / Discounts
            grantable = [k for k, _l in db.PERMISSIONS] if sup else list(db.MANAGER_GRANTABLE)
            current = db.get_perms(row)
            dlg = tk.Toplevel(win)
            dlg.title(tr("Permissions for {name}", name=row["username"]))
            dlg.transient(win)
            tk.Label(dlg, text=tr("Permissions for {name}", name=row["username"]), font=("Segoe UI", 12, "bold")).pack(
                anchor="w", padx=16, pady=(14, 6))
            vars_ = {}
            for k, label in db.PERMISSIONS:
                if k in grantable:
                    vars_[k] = tk.IntVar(value=1 if k in current else 0)
                    tk.Checkbutton(dlg, text=label, variable=vars_[k], font=("Segoe UI", 11)).pack(anchor="w", padx=22)

            def save_perms():
                new = [k for k in current if k not in grantable] + [k for k, v in vars_.items() if v.get()]
                db.set_perms(row["id"], new)
                self.audit("permissions_changed", f"{row['username']}: {','.join(k for k in db.PERM_KEYS if k in new)}")
                dlg.destroy()
                load()
                tree.selection_set(str(row["id"]))
            bb = tk.Frame(dlg)
            bb.pack(fill="x", padx=16, pady=14)
            tk.Button(bb, text="Save", bg=ACCENT, activebackground="#15803d", command=save_perms).pack(side="left")
            tk.Button(bb, text="Cancel", command=dlg.destroy).pack(side="left", padx=8)
            self.autosize(dlg)
            dlg.grab_set()

        def delete():
            row = selected_user()
            if row is None:
                return
            if row["id"] == self.user["id"]:
                messagebox.showwarning("User", "You cannot delete your own login", parent=win)
                return
            if messagebox.askyesno("Delete", "Delete this user?", parent=win):
                try:
                    conn = db.get_connection()
                    conn.execute("DELETE FROM users WHERE id = ?", (row["id"],))
                    conn.commit()
                    conn.close()
                    self.audit("user_deleted", row["username"])
                except Exception:
                    messagebox.showerror("User", "This user has bills, so it cannot be deleted", parent=win)
                load()

        tk.Button(form, text="Add User", bg="#16a34a", fg="white", command=add).grid(row=1, column=3, padx=10)
        bf = tk.Frame(win)
        bf.pack(fill="x", padx=10, pady=10, side="bottom", before=tree)
        tk.Button(bf, text="Permissions", bg=PRIMARY, command=edit_perms).pack(side="left")
        tk.Button(bf, text="Change password", bg=ACCENT, activebackground="#15803d",
                  font=("Segoe UI", 10, "bold"), command=change_password).pack(side="left", padx=6)
        tk.Button(bf, text="Delete", bg=DANGER, activebackground="#b91c1c", command=delete).pack(side="left")
        tk.Label(bf, text=("The Super Admin can always do everything." if sup
                           else "You can manage cashier accounts only."), fg="#64748b").pack(side="left", padx=10)
        load()

    # --------------------------------------------------------- SETTINGS
    def open_settings(self):
        if not self.allowed("settings"):
            return
        win = tk.Toplevel(self)
        win.title("Shop Settings")
        win.geometry("620x640")
        self.autosize(win)
        s = db.get_settings()
        fields = [("store_name", "Shop name"), ("address", "Address"), ("phone", "Phone"),
                  ("ntn", "NTN (tax number)"), ("strn", "STRN (sales tax)"),
                  ("footer", "Message at the bottom of the receipt"), ("default_tax", "Default sales tax (%)")]
        entries = {}
        r = 0
        for key, label in fields:
            tk.Label(win, text=label, font=("Segoe UI", 11)).grid(row=r, column=0, sticky="e", padx=10, pady=7)
            e = tk.Entry(win, width=34, font=("Segoe UI", 11))
            e.insert(0, s[key])
            e.grid(row=r, column=1, padx=6)
            entries[key] = e
            r += 1

        tk.Label(win, text="Receipt paper", font=("Segoe UI", 11)).grid(row=r, column=0, sticky="e", padx=10, pady=7)
        cb_paper = ttk.Combobox(win, values=[tr(p) for p in PAPER_CHOICES], state="readonly", width=32)
        cb_paper.current(1 if s["paper_width"] == "58" else 0)
        cb_paper.grid(row=r, column=1, sticky="w", padx=6)
        r += 1
        auto_var = tk.IntVar(value=1 if s["auto_print"] == "1" else 0)
        tk.Checkbutton(win, text="Print the receipt automatically when a bill is saved", variable=auto_var,
                       font=("Segoe UI", 11)).grid(row=r, column=1, sticky="w", padx=6)
        r += 1
        tk.Label(win, text="Cash drawer\nprinter name", font=("Segoe UI", 11)).grid(
            row=r, column=0, sticky="e", padx=10, pady=7)
        e_drawer = tk.Entry(win, width=34, font=("Segoe UI", 11))
        e_drawer.insert(0, s["drawer_printer"])
        e_drawer.grid(row=r, column=1, padx=6)
        r += 1
        tk.Label(win, text="Empty = drawer off. Needs pywin32 (experimental).",
                 fg="#64748b", font=("Segoe UI", 9)).grid(row=r, column=1, sticky="w", padx=6)
        r += 1

        codes = [c for c, _n in i18n.LANGS]
        names = i18n.lang_names()
        # --- logo
        tk.Label(win, text="Shop logo", font=("Segoe UI", 11)).grid(row=r, column=0, sticky="e", padx=10, pady=7)
        lf = tk.Frame(win)
        lf.grid(row=r, column=1, sticky="w", padx=6)
        lbl_logo = tk.Label(lf, fg="#64748b", font=("Segoe UI", 9))

        def refresh_logo():
            lbl_logo.config(text=tr("Logo is set") if db.logo_path() else tr("No logo"))

        def choose_logo():
            path = filedialog.askopenfilename(parent=win, title=tr("Choose a logo (PNG or GIF)"),
                                              filetypes=[("PNG / GIF", "*.png *.gif")])
            if path:
                try:
                    db.set_logo(path)
                except Exception as e:
                    messagebox.showerror("Logo", str(e), parent=win)
                    return
                self.audit("logo_changed")
                refresh_logo()

        def clear_logo():
            db.remove_logo()
            self.audit("logo_removed")
            refresh_logo()
        tk.Button(lf, text="Choose logo", command=choose_logo).pack(side="left")
        tk.Button(lf, text="Remove logo", command=clear_logo).pack(side="left", padx=6)
        lbl_logo.pack(side="left", padx=6)
        refresh_logo()
        r += 1
        # --- extra backup folder
        tk.Label(win, text="Extra backup folder\n(USB / Google Drive)", font=("Segoe UI", 11)).grid(
            row=r, column=0, sticky="e", padx=10, pady=7)
        bfm = tk.Frame(win)
        bfm.grid(row=r, column=1, sticky="w", padx=6)
        e_backup = tk.Entry(bfm, width=26, font=("Segoe UI", 11))
        e_backup.insert(0, s["backup_folder"])
        e_backup.pack(side="left")

        def browse_backup():
            d = filedialog.askdirectory(parent=win, title=tr("Choose the backup folder"))
            if d:
                e_backup.delete(0, "end")
                e_backup.insert(0, d)
        tk.Button(bfm, text="Browse", command=browse_backup).pack(side="left", padx=6)
        r += 1
        tk.Label(win, text="Every daily backup and the backup on exit are also copied here.",
                 fg="#64748b", font=("Segoe UI", 9)).grid(row=r, column=1, sticky="w", padx=6)
        r += 1
        tk.Label(win, text="Default language", font=("Segoe UI", 11)).grid(row=r, column=0, sticky="e", padx=10, pady=7)
        cb_lang = ttk.Combobox(win, values=names, state="readonly", width=32)
        cb_lang.current(codes.index(s["language"]) if s["language"] in codes else 0)
        cb_lang.grid(row=r, column=1, sticky="w", padx=6)
        r += 1
        rl_codes = ["same", "en", "ru"]
        tk.Label(win, text="Receipt language", font=("Segoe UI", 11)).grid(row=r, column=0, sticky="e", padx=10, pady=7)
        cb_rlang = ttk.Combobox(win, values=[tr("Same as screen")] + names, state="readonly", width=32)
        cb_rlang.current(rl_codes.index(s["receipt_language"]) if s["receipt_language"] in rl_codes else 1)
        cb_rlang.grid(row=r, column=1, sticky="w", padx=6)
        r += 1
        e_rec = None
        if self.is_admin():            # recovery code sirf Super Admin dekh / badal sakta hai
            tk.Label(win, text="Recovery code\n(if you forget the password)", font=("Segoe UI", 11)).grid(
                row=r, column=0, sticky="e", padx=10, pady=7)
            e_rec = tk.Entry(win, width=34, font=("Segoe UI", 11), show="*")
            e_rec.grid(row=r, column=1, padx=6)
            r += 1
            tk.Label(win, text=("It is set. To change it, type a new code; otherwise leave it empty."
                                if db.has_recovery_code() else "Not set yet. Type a code you can remember."),
                     fg="#64748b", font=("Segoe UI", 9)).grid(row=r, column=1, sticky="w", padx=6)
            r += 1

        def save():
            rec = e_rec.get().strip() if e_rec else ""
            if rec and len(rec) < 4:
                messagebox.showwarning("Recovery", "Use a recovery code of at least 4 characters", parent=win)
                return
            try:
                float(entries["default_tax"].get() or 0)
            except ValueError:
                messagebox.showwarning("Tax", "Tax must be a number", parent=win)
                return
            if rec:
                db.set_recovery_code(rec)
            for key, e in entries.items():
                db.set_setting(key, e.get().strip() or ("0" if key == "default_tax" else ""))
            db.set_setting("paper_width", "58" if cb_paper.current() == 1 else "80")
            db.set_setting("auto_print", "1" if auto_var.get() else "0")
            db.set_setting("drawer_printer", e_drawer.get().strip())
            db.set_setting("backup_folder", e_backup.get().strip())
            self.audit("settings_saved")
            db.set_setting("language", codes[cb_lang.current()])
            db.set_setting("receipt_language", rl_codes[cb_rlang.current()])
            self.apply_language(i18n.get_language())
            messagebox.showinfo("Settings", "Saved. It will appear on receipts from the next bill.", parent=win)
            win.destroy()
            self.show_billing()
        tk.Label(win, text=f"{APP_NAME}   v{APP_VERSION}", fg="#94a3b8", font=("Segoe UI", 9)).grid(
            row=r, column=0, columnspan=2, pady=(8, 0))
        tk.Button(win, text="Save", bg="#16a34a", fg="white", width=14, command=save).grid(
            row=r + 1, column=0, columnspan=2, pady=14)

    # ------------------------------------------------------------ AUDIT LOG
    def open_audit(self):
        if not self.allowed("audit"):
            return
        win = tk.Toplevel(self)
        win.title("Audit Log")
        win.geometry("980x560")
        self.autosize(win)

        top = tk.Frame(win)
        top.pack(fill="x", padx=10, pady=10)
        tk.Label(top, text="Date (YYYY-MM-DD, empty = all):").pack(side="left")
        e_day = tk.Entry(top, width=12)
        e_day.pack(side="left", padx=4)
        tk.Label(top, text="User:").pack(side="left", padx=(10, 0))
        conn = db.get_connection()
        names = [r[0] for r in conn.execute("SELECT username FROM users ORDER BY username")]
        conn.close()
        cb_user = ttk.Combobox(top, values=[tr("All")] + names, state="readonly", width=12)
        cb_user.current(0)
        cb_user.pack(side="left", padx=4)
        tk.Label(top, text="Search:").pack(side="left", padx=(10, 0))
        e_text = tk.Entry(top, width=16)
        e_text.pack(side="left", padx=4)

        tree = ttk.Treeview(win, columns=("time", "user", "action", "details"), show="headings")
        for c, t, w in (("time", "Time", 150), ("user", "User", 110), ("action", "Action", 150), ("details", "Details", 480)):
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="w")
        tree.tag_configure("bad", foreground=DANGER)
        tree.pack(fill="both", expand=True, padx=10)
        state = {"rows": []}

        def load(event=None):
            day = e_day.get().strip()
            if day:
                try:
                    datetime.strptime(day, "%Y-%m-%d")
                except ValueError:
                    messagebox.showerror("Date", "Write the date like this: 2026-10-20", parent=win)
                    return
            user = None if cb_user.current() <= 0 else cb_user.get()
            state["rows"] = db.list_audit(2000, day or None, user, e_text.get().strip() or None)
            tree.delete(*tree.get_children())
            for r in state["rows"]:
                tree.insert("", "end", iid=str(r["id"]), tags=("bad",) if "failed" in r["action"] else (),
                            values=(r["t"], r["username"], r["action"], r["details"]))
            lbl_count.config(text=raw("{n} entries", n=len(state["rows"])))

        def export():
            if not state["rows"]:
                messagebox.showinfo("Audit Log", "Nothing to export", parent=win)
                return
            path = filedialog.asksaveasfilename(parent=win, defaultextension=".csv", initialfile="audit_log.csv",
                                                filetypes=[("CSV", "*.csv")], title=tr("Save the audit log"))
            if path:
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f)
                    w.writerow(["time", "user", "action", "details"])
                    for r in state["rows"]:
                        w.writerow([r["t"], r["username"], r["action"], r["details"]])
                messagebox.showinfo("Audit Log", raw("Saved: {path}", path=path), parent=win)

        tk.Button(top, text="Show", bg=PRIMARY_DARK, fg="white", command=load).pack(side="left", padx=8)
        tk.Button(top, text="Export CSV", command=export).pack(side="left")
        lbl_count = tk.Label(win, fg="#64748b")
        lbl_count.pack(anchor="w", padx=12, pady=6)
        e_day.bind("<Return>", load)
        e_text.bind("<Return>", load)
        load()

    # ------------------------------------------------------------ DASHBOARD
    def open_dashboard(self):
        if not self.allowed("dashboard"):
            return
        win = tk.Toplevel(self)
        win.title("Dashboard")
        win.geometry("1060x720")
        self.autosize(win)
        today = datetime.now().strftime("%Y-%m-%d")

        top = tk.Frame(win)
        top.pack(fill="x", padx=14, pady=(12, 2))
        tk.Label(top, text="Dashboard", font=("Segoe UI", 20, "bold"), fg=PRIMARY_DARK).pack(side="left")
        lbl_when = tk.Label(top, fg="#64748b", font=("Segoe UI", 10))
        lbl_when.pack(side="left", padx=14)
        tk.Button(top, text="Refresh", command=lambda: refresh()).pack(side="right")

        cards = tk.Frame(win)
        cards.pack(fill="x", padx=9, pady=6)
        defs = [("net_sales", "Net sales today", PRIMARY), ("bills", "Bills today", PRIMARY_DARK),
                ("profit", "Profit today", ACCENT), ("expected_cash", "Cash that should be in drawer", "#0ea5e9"),
                ("customer_credit", "Customers owe you", DANGER), ("supplier_owed", "You owe suppliers", "#f59e0b"),
                ("low_stock", "Low-stock items", DANGER), ("expiring", "Expiring soon", "#f59e0b")]
        kpi = {}
        for i, (key, label, color) in enumerate(defs):
            card = tk.Frame(cards, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
            card.grid(row=i // 4, column=i % 4, sticky="nsew", padx=5, pady=5)
            tk.Frame(card, bg=color, height=4).pack(fill="x")
            tk.Label(card, text=label, bg=CARD, fg="#64748b", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12, pady=(8, 0))
            kpi[key] = tk.Label(card, text="0", bg=CARD, fg=color, font=("Segoe UI", 22, "bold"))
            kpi[key].pack(anchor="w", padx=12, pady=(0, 10))
        for c in range(4):
            cards.columnconfigure(c, weight=1)

        lower = tk.Frame(win)
        lower.pack(fill="both", expand=True, padx=14, pady=6)
        chart_box = tk.LabelFrame(lower, text="Last 7 days (net sales)", padx=8, pady=8)
        chart_box.pack(side="left", fill="both", expand=True)
        canvas = tk.Canvas(chart_box, width=560, height=260, bg=CARD, highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        side = tk.Frame(lower)
        side.pack(side="right", fill="y", padx=(12, 0))
        top_box = tk.LabelFrame(side, text="Top products today", padx=8, pady=8)
        top_box.pack(fill="x")
        ttree = ttk.Treeview(top_box, columns=("name", "qty", "rev"), show="headings", height=5)
        for c, t, w, a in (("name", "Product", 170, "w"), ("qty", "Qty", 50, "center"), ("rev", "Amount", 90, "e")):
            ttree.heading(c, text=t)
            ttree.column(c, width=w, anchor=a)
        ttree.pack()
        pay_box = tk.LabelFrame(side, text="Payments today", padx=8, pady=8)
        pay_box.pack(fill="x", pady=(10, 0))
        pay_lbls = {}
        for i, (key, label) in enumerate((("cash_sales", "Cash"), ("card_sales", "Card"), ("easypaisa_sales", "Easypaisa"),
                                          ("jazzcash_sales", "JazzCash"), ("udhaar", "Credit"))):
            tk.Label(pay_box, text=label, font=("Segoe UI", 10)).grid(row=i, column=0, sticky="w", pady=2)
            pay_lbls[key] = tk.Label(pay_box, text="0", font=("Segoe UI", 10, "bold"))
            pay_lbls[key].grid(row=i, column=1, sticky="e", padx=(40, 0))
        pay_box.columnconfigure(1, weight=1)

        def draw_chart(points):
            canvas.delete("all")
            w = int(canvas.winfo_width() or 560)
            h = int(canvas.winfo_height() or 260)
            pad_l, pad_b, pad_t = 14, 34, 24
            vals = [max(v, 0) for _d, v in points]
            vmax = max(vals) or 1
            n = len(points)
            slot = (w - pad_l * 2) / n
            bar = slot * 0.56
            base = h - pad_b
            canvas.create_line(pad_l, base, w - pad_l, base, fill=BORDER)
            for i, (d, v) in enumerate(points):
                x0 = pad_l + i * slot + (slot - bar) / 2
                hh = (base - pad_t) * (max(v, 0) / vmax)
                last = i == n - 1
                canvas.create_rectangle(x0, base - hh, x0 + bar, base, fill=PRIMARY if last else "#93c5fd", outline="")
                canvas.create_text(x0 + bar / 2, base - hh - 8, text=f"{v:,.0f}", font=("Segoe UI", 8, "bold"), fill=TEXT)
                canvas.create_text(x0 + bar / 2, base + 14, text=datetime.strptime(d, "%Y-%m-%d").strftime("%a %d"),
                                   font=("Segoe UI", 8), fill="#64748b")

        def refresh():
            if not win.winfo_exists():
                return
            d = db.dashboard_data(today)
            lbl_when.config(text=f"{datetime.now():%d %b %Y}")
            for key in ("net_sales", "profit", "expected_cash", "customer_credit", "supplier_owed"):
                kpi[key].config(text=f"{d[key]:,.0f}")
            for key in ("bills", "low_stock", "expiring"):
                kpi[key].config(text=str(d[key]))
            for key, lab in pay_lbls.items():
                lab.config(text=f"{d[key]:,.0f}")
            ttree.delete(*ttree.get_children())
            for name, qty, rev in d["top"]:
                ttree.insert("", "end", values=(name, qty, f"{rev:,.0f}"))
            win.update_idletasks()
            draw_chart(d["last7"])
            win.after(60000, refresh)      # har minute khud update
        win.after(200, refresh)

    # ---------------------------------------------------------- REPORTS
    def open_reports(self):
        if not self.allowed("reports"):
            return
        win = tk.Toplevel(self)
        win.title("Sales Reports")
        win.geometry("980x580")
        self.autosize(win)

        today = datetime.now().strftime("%Y-%m-%d")
        month_start = datetime.now().strftime("%Y-%m-01")

        top = tk.Frame(win)
        top.pack(fill="x", padx=10, pady=10)
        tk.Label(top, text="From (YYYY-MM-DD):").pack(side="left")
        e_from = tk.Entry(top, width=12)
        e_from.insert(0, today)
        e_from.pack(side="left", padx=4)
        tk.Label(top, text="To:").pack(side="left")
        e_to = tk.Entry(top, width=12)
        e_to.insert(0, today)
        e_to.pack(side="left", padx=4)

        summary = tk.Frame(win)
        summary.pack(fill="x", padx=10)
        lbls = {}
        for key in ("Bills", "Total Sale", "Returns", "Net Sale", "Discount", "Tax", "Profit"):
            box = tk.LabelFrame(summary, text=key, padx=8, pady=6)
            box.pack(side="left", expand=True, fill="x", padx=3)
            lbls[key] = tk.Label(box, text="0", font=("Segoe UI", 13, "bold"))
            lbls[key].pack()

        lbl_pay = tk.Label(win, text="", font=("Segoe UI", 10, "bold"), fg=PRIMARY_DARK)
        lbl_pay.pack(anchor="w", padx=12, pady=(8, 0))

        cols = ("name", "qty", "revenue", "profit")
        tree = ttk.Treeview(win, columns=cols, show="headings")
        for c, t, w in (("name", "Product", 380), ("qty", "Qty Sold (net)", 120),
                        ("revenue", "Sale Amount", 140), ("profit", "Profit", 140)):
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="w" if c == "name" else "e")
        tree.pack(fill="both", expand=True, padx=10, pady=10)

        def show():
            d1, d2 = e_from.get().strip(), e_to.get().strip()
            try:
                datetime.strptime(d1, "%Y-%m-%d")
                datetime.strptime(d2, "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Date", "Write the date like this: 2026-10-19", parent=win)
                return
            conn = db.get_connection()
            s = conn.execute(
                """SELECT COUNT(*), COALESCE(SUM(total),0), COALESCE(SUM(discount),0),
                          COALESCE(SUM(tax),0)
                   FROM sales WHERE date(sale_date,'localtime') BETWEEN ? AND ?""",
                (d1, d2)).fetchone()
            bymethod = conn.execute(
                """SELECT CASE WHEN payment_method IN ('card','easypaisa','jazzcash')
                               THEN payment_method ELSE 'cash' END AS m,
                          COALESCE(SUM(COALESCE(paid, total)), 0) AS amt,
                          COALESCE(SUM(total - COALESCE(paid, total)), 0) AS credit
                   FROM sales WHERE date(sale_date,'localtime') BETWEEN ? AND ?
                   GROUP BY m""", (d1, d2)).fetchall()
            refunds = conn.execute(
                """SELECT COALESCE(SUM(refund_amount),0) FROM returns
                   WHERE date(return_date,'localtime') BETWEEN ? AND ?""", (d1, d2)).fetchone()[0]
            sold = conn.execute(
                """SELECT p.id, p.name, SUM(si.quantity) AS q, SUM(si.line_total) AS rev,
                          SUM(si.line_total - si.quantity * p.cost_price) AS profit
                   FROM sale_items si
                   JOIN products p ON p.id = si.product_id
                   JOIN sales s ON s.id = si.sale_id
                   WHERE date(s.sale_date,'localtime') BETWEEN ? AND ?
                   GROUP BY p.id""", (d1, d2)).fetchall()
            back = conn.execute(
                """SELECT p.id, p.name, SUM(ri.quantity) AS q, SUM(ri.line_total) AS rev,
                          SUM(ri.line_total - ri.quantity * p.cost_price) AS profit
                   FROM return_items ri
                   JOIN products p ON p.id = ri.product_id
                   JOIN returns r ON r.id = ri.return_id
                   WHERE date(r.return_date,'localtime') BETWEEN ? AND ?
                   GROUP BY p.id""", (d1, d2)).fetchall()
            conn.close()

            data = {}
            for r in sold:
                data[r["id"]] = [r["name"], r["q"], r["rev"], r["profit"]]
            for r in back:
                d = data.setdefault(r["id"], [r["name"], 0, 0.0, 0.0])
                d[1] -= r["q"]
                d[2] -= r["rev"]
                d[3] -= r["profit"]
            rows = sorted(data.values(), key=lambda d: d[1], reverse=True)
            net_profit = sum(d[3] for d in rows) - s[2]

            lbls["Bills"].config(text=str(s[0]))
            lbls["Total Sale"].config(text=f"{s[1]:.2f}")
            lbls["Returns"].config(text=f"{refunds:.2f}")
            lbls["Net Sale"].config(text=f"{s[1] - refunds:.2f}")
            lbls["Discount"].config(text=f"{s[2]:.2f}")
            lbls["Tax"].config(text=f"{s[3]:.2f}")
            lbls["Profit"].config(text=f"{net_profit:.2f}")
            amounts = {r["m"]: r["amt"] for r in bymethod}
            udhaar = sum(r["credit"] for r in bymethod)
            lbl_pay.config(text="   |   ".join(
                [f"{tr(PAY_NAMES[k])}: {amounts.get(k, 0):.0f}" for k, _x in PAY_METHODS]
                + [tr("Credit: {x}", x=f"{udhaar:.0f}")]))

            tree.delete(*tree.get_children())
            for name, q, rev, prof in rows:
                tree.insert("", "end", values=(name, q, f"{rev:.2f}", f"{prof:.2f}"))

        def set_range(a, b):
            e_from.delete(0, "end")
            e_from.insert(0, a)
            e_to.delete(0, "end")
            e_to.insert(0, b)
            show()

        tk.Button(top, text="Show", bg="#1e3a8a", fg="white", command=show).pack(side="left", padx=8)
        tk.Button(top, text="Today", command=lambda: set_range(today, today)).pack(side="left", padx=2)
        tk.Button(top, text="This month", command=lambda: set_range(month_start, today)).pack(side="left", padx=2)
        show()

    # ----------------------------------------------------------- ALERTS
    def show_alerts(self, only_if_any=False):
        low = db.low_stock_products()
        exp = db.expiring_products(30)
        if only_if_any and not low and not exp:
            return
        win = tk.Toplevel(self)
        win.title("Alerts: low stock and expiry")
        win.geometry("600x520")
        self.autosize(win)
        txt = tk.Text(win, font=("Segoe UI", 11), wrap="word")
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        txt.tag_configure("h", font=("Segoe UI", 13, "bold"))
        txt.tag_configure("red", foreground="#dc2626")
        today = datetime.now().date()

        txt.insert("end", tr("Low stock ({n})\n", n=len(low)), "h")
        if not low:
            txt.insert("end", tr("  All good.\n"))
        for r in low:
            txt.insert("end", tr("  {name}  -  {qty} left  (limit {limit})\n", name=r['name'], qty=r['stock_qty'], limit=r['low_stock_limit']))
        txt.insert("end", tr("\nExpiry (within 30 days or already passed) ({n})\n", n=len(exp)), "h")
        if not exp:
            txt.insert("end", tr("  None.\n"))
        for r in exp:
            try:
                days = (datetime.strptime(r["expiry_date"], "%Y-%m-%d").date() - today).days
            except ValueError:
                days = None
            if days is None:
                status, tag = r["expiry_date"], ()
            elif days < 0:
                status, tag = raw("EXPIRED ({d} days ago)", d=-days), ("red",)
            else:
                status, tag = raw("{d} days left", d=days), ()
            txt.insert("end", tr("  {name}  -  {date}  -  {status}  (stock {stock})\n", name=r['name'], date=r['expiry_date'], status=status, stock=r['stock_qty']), tag)
        txt.config(state="disabled")
        tk.Button(win, text="OK", command=win.destroy).pack(pady=(0, 10))

    # --------------------------------------------------------- SUPPLIERS
    def open_suppliers(self):
        if not self.allowed("suppliers"):
            return
        win = tk.Toplevel(self)
        win.title("Suppliers")
        win.geometry("640x520")
        self.autosize(win)

        top = tk.Frame(win)
        top.pack(fill="x", padx=10, pady=8)
        tk.Label(top, text="Search:").pack(side="left")
        e_search = tk.Entry(top, width=24)
        e_search.pack(side="left", padx=6)
        lbl_total = tk.Label(top, text="", font=("Segoe UI", 12, "bold"), fg="#dc2626")
        lbl_total.pack(side="right")

        tree = ttk.Treeview(win, columns=("name", "phone", "balance"), show="headings")
        for c, t, w in (("name", "Supplier", 250), ("phone", "Phone", 150), ("balance", "We owe (Rs)", 150)):
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="e" if c == "balance" else "w")
        tree.tag_configure("owes", foreground="#dc2626")
        tree.pack(fill="both", expand=True, padx=10)

        def load(event=None):
            tree.delete(*tree.get_children())
            total = 0.0
            for r in db.list_suppliers(e_search.get().strip()):
                total += r["balance"]
                tree.insert("", "end", iid=str(r["id"]),
                            tags=("owes",) if r["balance"] > 0.01 else (),
                            values=(r["name"], r["phone"], f"{r['balance']:.2f}"))
            lbl_total.config(text=tr("Total owed: {x}", x=f"{total:.0f}"))
        e_search.bind("<KeyRelease>", load)

        def pay():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Payment", "Select a supplier first", parent=win)
                return
            amt = simpledialog.askfloat("Payment", "How much did you pay the supplier?", minvalue=0.01, parent=win)
            if amt:
                db.pay_supplier(int(sel[0]), amt)
                self.audit("supplier_payment", f"{tree.item(sel[0])['values'][0]} {amt:.2f}")
                load()

        nf = tk.LabelFrame(win, text="New supplier", padx=8, pady=8)
        nf.pack(fill="x", padx=10, pady=8)
        e_name = tk.Entry(nf, width=22)
        e_phone = tk.Entry(nf, width=16)
        tk.Label(nf, text="Name").grid(row=0, column=0)
        tk.Label(nf, text="Phone").grid(row=0, column=1)
        e_name.grid(row=1, column=0, padx=4)
        e_phone.grid(row=1, column=1, padx=4)

        def add():
            if not e_name.get().strip():
                messagebox.showwarning("Supplier", "Please enter a name", parent=win)
                return
            db.add_supplier(e_name.get().strip(), e_phone.get().strip())
            e_name.delete(0, "end")
            e_phone.delete(0, "end")
            load()
        tk.Button(nf, text="Add", bg="#16a34a", fg="white", command=add).grid(row=1, column=2, padx=8)
        tk.Button(win, text="Pay supplier", command=pay).pack(pady=(0, 10))
        load()

    # ---------------------------------------------------------- PURCHASE
    def ask_purchase_line(self, parent, product):
        dlg = tk.Toplevel(parent)
        dlg.title(product["name"])
        dlg.transient(parent)
        result = {}
        tk.Label(dlg, text=product["name"], font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=2, padx=12, pady=10)
        entries = []
        for i, (label, default) in enumerate((("Quantity", "1"), ("Cost price (each)", product["cost_price"]),
                                              ("Expiry (can be empty)", product["expiry_date"] or ""))):
            tk.Label(dlg, text=label).grid(row=i + 1, column=0, sticky="e", padx=8, pady=4)
            e = tk.Entry(dlg, width=16)
            e.insert(0, str(default))
            e.grid(row=i + 1, column=1, padx=8)
            entries.append(e)

        def ok(event=None):
            try:
                qty = int(entries[0].get())
                cost = float(entries[1].get())
                expiry = db.parse_date(entries[2].get())
                if qty < 1 or cost < 0:
                    raise ValueError("Enter the quantity and cost correctly")
            except ValueError as e:
                messagebox.showwarning("Stock In", str(e), parent=dlg)
                return
            result["v"] = (qty, cost, expiry)
            dlg.destroy()
        tk.Button(dlg, text="OK", width=10, command=ok).grid(row=4, column=0, columnspan=2, pady=12)
        dlg.bind("<Return>", ok)
        entries[0].focus()
        entries[0].select_range(0, "end")
        i18n.localize(dlg)
        dlg.grab_set()
        dlg.wait_window()
        return result.get("v")

    def open_purchase(self):
        if not self.allowed("purchases"):
            return
        win = tk.Toplevel(self)
        win.title("Stock In (Purchase)")
        win.geometry("900x620")
        self.autosize(win)
        suppliers = []
        lines = {}  # product_id -> dict

        top = tk.Frame(win)
        top.pack(fill="x", padx=10, pady=10)
        tk.Label(top, text="Supplier:", font=("Segoe UI", 12)).pack(side="left")
        cb = ttk.Combobox(top, width=30, state="readonly")
        cb.pack(side="left", padx=6)

        def load_suppliers(select_id=None):
            suppliers.clear()
            suppliers.extend(db.list_suppliers())
            cb["values"] = [tr("(cash purchase / no supplier)")] + [
                tr("{name}  (owed {bal})", name=r['name'], bal=f"{r['balance']:.0f}") for r in suppliers]
            idx = 0
            for i, r in enumerate(suppliers, start=1):
                if r["id"] == select_id:
                    idx = i
            cb.current(idx)

        def new_supplier():
            name = simpledialog.askstring("Supplier", "Supplier name:", parent=win)
            if name and name.strip():
                load_suppliers(db.add_supplier(name.strip()))
        tk.Button(top, text="New supplier", command=new_supplier).pack(side="left")
        load_suppliers()

        sf = tk.Frame(win)
        sf.pack(fill="x", padx=10)
        tk.Label(sf, text="Barcode / Name:", font=("Segoe UI", 12)).pack(side="left")
        e_scan = tk.Entry(sf, font=("Segoe UI", 13))
        e_scan.pack(side="left", fill="x", expand=True, padx=8)

        cols = ("name", "qty", "cost", "total", "expiry")
        tree = ttk.Treeview(win, columns=cols, show="headings")
        for c, t, w in (("name", "Product", 330), ("qty", "Qty", 70), ("cost", "Cost", 100),
                        ("total", "Total", 110), ("expiry", "Expiry", 110)):
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="w" if c == "name" else "e")
        tree.pack(fill="both", expand=True, padx=10, pady=10)

        lbl_total = tk.Label(win, text="TOTAL: 0.00", font=("Segoe UI", 16, "bold"), fg="#16a34a")
        lbl_total.pack()

        def redraw():
            tree.delete(*tree.get_children())
            for pid, it in lines.items():
                tree.insert("", "end", iid=str(pid), values=(
                    it["name"], it["qty"], f"{it['cost']:.2f}", f"{it['qty'] * it['cost']:.2f}", it["expiry"] or ""))
            lbl_total.config(text=tr("TOTAL: {x}", x=f"{sum(i['qty'] * i['cost'] for i in lines.values()):.2f}"))

        def add_product(product):
            v = self.ask_purchase_line(win, product)
            if v:
                lines[product["id"]] = {"name": product["name"], "qty": v[0], "cost": v[1], "expiry": v[2]}
                redraw()

        def scan(event=None):
            text = e_scan.get().strip()
            if not text:
                return
            product = db.get_product_by_barcode(text)
            if product:
                add_product(product)
            else:
                results = db.search_products(text)
                if not results:
                    messagebox.showwarning("Stock In", "Product not found. Add it in Inventory first.", parent=win)
                elif len(results) == 1:
                    add_product(results[0])
                else:
                    self.choose_product(results, on_pick=add_product)
            e_scan.delete(0, "end")
            e_scan.focus()
        e_scan.bind("<Return>", scan)
        tk.Button(sf, text="Add", command=scan).pack(side="left")
        e_scan.focus()

        def remove():
            sel = tree.selection()
            if sel:
                lines.pop(int(sel[0]), None)
                redraw()

        bf = tk.Frame(win)
        bf.pack(fill="x", padx=10, pady=8)
        tk.Button(bf, text="Remove line", command=remove).pack(side="left")
        tk.Label(bf, text="   Amount paid (empty = full):").pack(side="left")
        e_paid = tk.Entry(bf, width=12)
        e_paid.pack(side="left", padx=4)

        def save():
            if not lines:
                messagebox.showinfo("Stock In", "No product has been added", parent=win)
                return
            total = sum(i["qty"] * i["cost"] for i in lines.values())
            try:
                paid = float(e_paid.get()) if e_paid.get().strip() else total
            except ValueError:
                messagebox.showwarning("Stock In", "Enter the amount received correctly", parent=win)
                return
            idx = cb.current()
            supplier_id = suppliers[idx - 1]["id"] if idx > 0 else None
            items = [(pid, i["qty"], i["cost"], i["expiry"]) for pid, i in lines.items()]
            try:
                db.save_purchase(self.user["id"], supplier_id, items, paid)
                self.audit("purchase_saved", f"{len(items)} items, total {total:.2f}")
            except Exception as e:
                messagebox.showerror("Stock In", str(e), parent=win)
                return
            messagebox.showinfo("Stock In", "Saved. Stock has increased and the cost price was updated.", parent=win)
            lines.clear()
            e_paid.delete(0, "end")
            load_suppliers(supplier_id)
            redraw()
        tk.Button(bf, text="Save (add to stock)", bg="#16a34a", fg="white",
                  font=("Segoe UI", 12, "bold"), command=save).pack(side="right")

    # ----------------------------------------------------------- CLOSING
    def open_closing(self):
        if not self.allowed("closing"):
            return
        win = tk.Toplevel(self)
        win.title("Daily Closing")
        win.geometry("560x600")
        self.autosize(win)
        today = datetime.now().strftime("%Y-%m-%d")

        top = tk.Frame(win)
        top.pack(fill="x", padx=12, pady=10)
        tk.Label(top, text="Date (YYYY-MM-DD):").pack(side="left")
        e_date = tk.Entry(top, width=12)
        e_date.insert(0, today)
        e_date.pack(side="left", padx=6)

        spec = [("Number of bills", "bills", False), ("Total sales", "sales_total", True),
                ("   of which received in CASH", "cash_sales", True),
                ("   of which received by Card", "card_sales", True),
                ("   of which received by Easypaisa", "easypaisa_sales", True),
                ("   of which received by JazzCash", "jazzcash_sales", True),
                ("   of which given on credit", "udhaar", True),
                ("Old credit collected (+)", "cust_payments", True),
                ("Cash refunded on returns (-)", "cash_refunds", True),
                ("Cash paid for stock (-)", "purchase_paid", True),
                ("Payments to suppliers (-)", "supplier_payments", True)]
        grid = tk.Frame(win)
        grid.pack(fill="x", padx=12)
        vals = {}
        for i, (label, key, _) in enumerate(spec):
            tk.Label(grid, text=label, font=("Segoe UI", 11)).grid(row=i, column=0, sticky="w", pady=3)
            vals[key] = tk.Label(grid, text="0", font=("Segoe UI", 11, "bold"))
            vals[key].grid(row=i, column=1, sticky="e", padx=20)
        grid.columnconfigure(1, weight=1)

        lbl_expected = tk.Label(win, text="", font=("Segoe UI", 15, "bold"), fg="#16a34a")
        lbl_expected.pack(pady=14)

        cf = tk.LabelFrame(win, text="Count the cash and compare", padx=10, pady=10)
        cf.pack(fill="x", padx=12)
        tk.Label(cf, text="Cash in drawer this morning:").grid(row=0, column=0, sticky="w", pady=3)
        e_open = tk.Entry(cf, width=12)
        e_open.insert(0, "0")
        e_open.grid(row=0, column=1, padx=8)
        tk.Label(cf, text="Counted cash now:").grid(row=1, column=0, sticky="w", pady=3)
        e_count = tk.Entry(cf, width=12)
        e_count.grid(row=1, column=1, padx=8)
        lbl_diff = tk.Label(cf, text="", font=("Segoe UI", 13, "bold"))
        lbl_diff.grid(row=2, column=0, columnspan=2, pady=8)
        state = {"expected": 0.0}

        def num(entry):
            try:
                return float(entry.get() or 0)
            except ValueError:
                return 0.0

        def compare(event=None):
            if not e_count.get().strip():
                lbl_diff.config(text="")
                return
            should = num(e_open) + state["expected"]
            diff = num(e_count) - should
            if abs(diff) < 0.5:
                lbl_diff.config(text=tr("The accounts match exactly"), fg="#16a34a")
            elif diff > 0:
                lbl_diff.config(text=tr("{x} cash EXTRA", x=f"{diff:.2f}"), fg="#b36b00")
            else:
                lbl_diff.config(text=tr("{x} cash SHORT", x=f"{-diff:.2f}"), fg="#dc2626")

        def show(event=None):
            try:
                datetime.strptime(e_date.get().strip(), "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Date", "Write the date like this: 2026-10-20", parent=win)
                return
            d = db.daily_closing(e_date.get().strip())
            for _, key, money in spec:
                vals[key].config(text=f"{d[key]:.2f}" if money else str(d[key]))
            state["expected"] = d["expected_cash"]
            lbl_expected.config(text=tr("Cash that should be in the drawer: {x}", x=f"{d['expected_cash']:.2f}"))
            compare()

        e_open.bind("<KeyRelease>", compare)
        e_count.bind("<KeyRelease>", compare)
        e_date.bind("<Return>", show)
        tk.Button(top, text="Show", bg="#1e3a8a", fg="white", command=show).pack(side="left", padx=6)
        tk.Label(win, text="Cash that should be in the drawer = morning cash + the day's cash",
                 fg="#555").pack(pady=8)
        show()

    # ------------------------------------------------------------ BACKUP
    def open_backup(self):
        if not self.allowed("backup"):
            return
        win = tk.Toplevel(self)
        win.title("Backup")
        win.geometry("480x300")
        self.autosize(win)
        tk.Label(win, text=tr("All data (database, receipts, labels, backups)\nis in ONE folder:\n\n{path}\n\nA backup is created automatically every day in the 'backups' folder.", path=db.DATA_DIR),
                 font=("Segoe UI", 11), justify="left").pack(padx=14, pady=(14, 6), anchor="w")

        def open_folder():
            try:
                os.startfile(db.DATA_DIR)
            except Exception as e:
                messagebox.showerror("Folder", str(e), parent=win)
        tk.Button(win, text="Open data folder", command=open_folder).pack(pady=(0, 8))

        def backup():
            folder = filedialog.askdirectory(parent=win, title=tr("Where should the backup be saved? (USB / folder)"))
            if not folder:
                return
            try:
                dest = db.backup_to(folder)
            except Exception as e:
                messagebox.showerror("Backup", str(e), parent=win)
                return
            self.audit("backup_created", dest)
            messagebox.showinfo("Backup", raw("Backup created:\n{path}", path=dest), parent=win)

        def restore():
            path = filedialog.askopenfilename(parent=win, title=tr("Select a backup file"),
                                              filetypes=[(tr("Backup"), "*.db"), (tr("All"), "*.*")])
            if not path:
                return
            if not messagebox.askyesno(
                    "Restore", "All current data will be REPLACED by this backup.\n(The existing data is also saved in the 'backups' folder first.)\nContinue?",
                    parent=win):
                return
            try:
                safety = db.restore_from(path)
            except Exception as e:
                messagebox.showerror("Restore", str(e), parent=win)
                return
            self.audit("backup_restored", path)
            messagebox.showinfo("Restore", raw("Data restored.\nThe previous data is saved here:\n{path}", path=safety), parent=win)
            win.destroy()
            self.show_billing()

        tk.Button(win, text="Create a backup (USB / folder)", width=34, bg="#16a34a", fg="white",
                  command=backup).pack(pady=6)
        if self.is_admin():            # restore sirf Super Admin kar sakta hai
            tk.Button(win, text="Restore data from a backup", width=34, command=restore).pack(pady=6)
        else:
            tk.Label(win, text="Only the Super Admin can restore a backup", fg="#64748b").pack(pady=6)

    # -------------------------------------------------------- INVENTORY
    def open_inventory(self):
        if not self.allowed("inventory"):
            return
        win = tk.Toplevel(self)
        win.title("Inventory")
        win.geometry("1100x620")
        self.autosize(win)

        form = tk.LabelFrame(win, text="Add a new product (barcode and expiry can be left empty)",
                             padx=8, pady=8)
        form.pack(fill="x", padx=10, pady=8)
        fields = [("Barcode", 14), ("Name", 22), ("Category", 12), ("Cost Price", 8),
                  ("Sale Price", 8), ("Stock", 6), ("Expiry", 11)]
        entries = {}
        for i, (label, w) in enumerate(fields):
            tk.Label(form, text=label).grid(row=0, column=i, padx=4)
            e = tk.Entry(form, width=w)
            e.grid(row=1, column=i, padx=4)
            entries[label] = e

        cols = ("barcode", "name", "category", "cost", "price", "stock", "expiry")
        tree = ttk.Treeview(win, columns=cols, show="headings", selectmode="extended")
        for c, t, w in (("barcode", "Barcode", 130), ("name", "Name", 270),
                        ("category", "Category", 110), ("cost", "Cost", 70),
                        ("price", "Price", 70), ("stock", "Stock", 70), ("expiry", "Expiry", 100)):
            tree.heading(c, text=t)
            tree.column(c, width=w)
        tree.tag_configure("low", background="#ffd6d6")
        tree.tag_configure("exp", background="#ffe2b8")

        def load():
            tree.delete(*tree.get_children())
            soon = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            conn = db.get_connection()
            for r in conn.execute("SELECT * FROM products ORDER BY name"):
                tag = ()
                if r["stock_qty"] <= r["low_stock_limit"]:
                    tag = ("low",)
                if r["expiry_date"] and r["expiry_date"] <= soon:
                    tag = ("exp",)
                tree.insert("", "end", iid=str(r["id"]), tags=tag, values=(
                    r["barcode"] or "", r["name"], r["category"], r["cost_price"],
                    r["sale_price"], r["stock_qty"], r["expiry_date"] or ""))
            conn.close()

        def add():
            try:
                db.add_product(
                    entries["Barcode"].get().strip() or None,
                    entries["Name"].get().strip(),
                    entries["Category"].get().strip(),
                    float(entries["Cost Price"].get() or 0),
                    float(entries["Sale Price"].get()),
                    int(entries["Stock"].get() or 0),
                    expiry_date=db.parse_date(entries["Expiry"].get()))
            except Exception as e:
                messagebox.showerror("Error", raw("Could not add the product: {err}", err=e), parent=win)
                return
            self.audit("product_added", f"{entries['Name'].get()} price {entries['Sale Price'].get()}")
            for e in entries.values():
                e.delete(0, "end")
            load()

        def restock():
            sel = tree.selection()
            if not sel:
                return
            qty = simpledialog.askinteger("Restock", "How much stock do you want to add?", parent=win)
            if qty:
                conn = db.get_connection()
                conn.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE id = ?",
                             (qty, int(sel[0])))
                conn.commit()
                conn.close()
                self.audit("stock_added", f"{tree.item(sel[0])['values'][1]} +{qty}")
                load()

        def change_price():
            sel = tree.selection()
            if not sel:
                return
            price = simpledialog.askfloat("Price", "New sale price:", minvalue=0, parent=win)
            if price is not None:
                old = tree.item(sel[0])["values"][4]
                conn = db.get_connection()
                conn.execute("UPDATE products SET sale_price = ? WHERE id = ?", (price, int(sel[0])))
                conn.commit()
                conn.close()
                self.audit("price_changed", f"{tree.item(sel[0])['values'][1]}: {old} -> {price}")
                load()

        def change_expiry():
            sel = tree.selection()
            if not sel:
                return
            text = simpledialog.askstring("Expiry", "New expiry date (2026-12-31); empty = remove:", parent=win)
            if text is None:
                return
            try:
                value = db.parse_date(text)
            except ValueError as e:
                messagebox.showwarning("Expiry", str(e), parent=win)
                return
            conn = db.get_connection()
            for iid in sel:
                conn.execute("UPDATE products SET expiry_date = ? WHERE id = ?", (value, int(iid)))
            conn.commit()
            conn.close()
            load()

        def delete():
            sel = tree.selection()
            if sel and messagebox.askyesno("Delete", "Delete this product?", parent=win):
                for iid in sel:
                    try:
                        self.audit("product_deleted", str(tree.item(iid)["values"][1]))
                        conn = db.get_connection()
                        conn.execute("DELETE FROM products WHERE id = ?", (int(iid),))
                        conn.commit()
                        conn.close()
                    except Exception:
                        messagebox.showerror("Error", "This product has sales/stock records, so it cannot be deleted", parent=win)
                load()

        def print_labels():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Labels", "Select product(s) first (hold Ctrl to select several)", parent=win)
                return
            copies = simpledialog.askinteger("Labels", "How many labels per product?",
                                             initialvalue=1, minvalue=1, maxvalue=500, parent=win)
            if not copies:
                return
            try:
                lbl.make_labels([int(i) for i in sel], copies)
            except Exception as e:
                messagebox.showerror("Labels", raw("Could not create labels: {err}", err=e), parent=win)
                return
            load()

        def make_template():
            path = os.path.join(db.DATA_DIR, "products_template.csv")
            try:
                db.write_import_template(path)
            except Exception as e:
                messagebox.showerror("Template", str(e), parent=win)
                return
            messagebox.showinfo("Template", raw("Sample file created:\n{path}\n\nOpen it in Excel, enter your products, then press 'Import products'.\nBoth Excel (.xlsx) and CSV work.", path=path), parent=win)
            try:
                os.startfile(db.DATA_DIR)
            except Exception:
                pass

        def import_file():
            path = filedialog.askopenfilename(parent=win, title=tr("Select the products file"),
                                              filetypes=[("Excel / CSV", "*.xlsx *.csv"), (tr("All"), "*.*")])
            if not path:
                return
            try:
                added, skipped, errors = db.import_products_file(path)
            except Exception as e:
                messagebox.showerror("Import", str(e), parent=win)
                return
            msg = raw("{added} new products added.\n{skipped} already existed (same barcode), skipped.", added=added, skipped=skipped)
            if errors:
                msg += raw("\n\n{n} rows had problems:\n", n=len(errors)) + "\n".join(
                    raw("Row {n}: {msg}", n=n, msg=m) for n, m in errors[:8])
            self.audit("products_imported", f"{added} added, {skipped} skipped")
            messagebox.showinfo("Import", msg, parent=win)
            load()

        tk.Button(form, text="Add Product", bg="#16a34a", fg="white", command=add).grid(
            row=1, column=len(fields), padx=10)
        tree.pack(fill="both", expand=True, padx=10)

        bf = tk.Frame(win)
        bf.pack(fill="x", padx=10, pady=8)
        for text, cmd, perm in (("Restock", restock, None), ("Change price", change_price, "prices"),
                                ("Change expiry", change_expiry, None), ("Print barcode labels", print_labels, None),
                                ("Import products (Excel/CSV)", import_file, None), ("Import template", make_template, None),
                                ("Delete", delete, "delete_products")):
            if perm and not self.can(perm):
                continue
            tk.Button(bf, text=text, command=cmd).pack(side="left", padx=4)
        tk.Label(win, text="Red = low stock   |   Orange = expiry near / passed",
                 fg="#dc2626").pack(pady=(0, 8))
        load()

if __name__ == "__main__":
    App().mainloop()