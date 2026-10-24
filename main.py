import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from datetime import datetime, timedelta

import db
import labels as lbl


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


def pay_label(method, total, paid):
    """Bill ki payment ka naam: Cash, Card, Cash + Udhaar wagaira."""
    if method == "udhaar":
        return "Cash + Udhaar" if paid > 0.01 else "Udhaar"
    base = PAY_NAMES.get(method, "Cash")
    return base + " + Udhaar" if total - paid > 0.01 else base


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Superstore POS")
        self.geometry("1150x700")
        self.user = None
        self.cart = {}  # product_id -> dict
        self.cust = None  # bill ka customer
        self.apply_theme()
        db.init_db()
        try:
            db.auto_backup()
        except Exception:
            pass
        self.show_login()

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

    def clear(self):
        for w in self.winfo_children():
            w.destroy()

    # ------------------------------------------------------------ LOGIN
    def show_login(self):
        self.clear()
        self.unbind("<Return>")
        name = db.get_settings()["store_name"]
        band = tk.Frame(self, bg=PRIMARY_DARK, height=8)
        band.pack(fill="x", side="top")
        f = tk.Frame(self, bg=CARD, padx=50, pady=36, highlightthickness=1, highlightbackground=BORDER)
        f.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(f, text=name, font=("Segoe UI", 24, "bold"), bg=CARD, fg=PRIMARY).grid(
            row=0, column=0, columnspan=2, pady=(0, 4))
        tk.Label(f, text="Billing System", font=("Segoe UI", 11), bg=CARD, fg="#64748b").grid(
            row=1, column=0, columnspan=2, pady=(0, 18))
        tk.Label(f, text="Username", font=("Segoe UI", 12), bg=CARD).grid(row=2, column=0, sticky="e", pady=8, padx=6)
        tk.Label(f, text="Password", font=("Segoe UI", 12), bg=CARD).grid(row=3, column=0, sticky="e", pady=8, padx=6)
        self.e_user = tk.Entry(f, font=("Segoe UI", 12))
        self.e_pass = tk.Entry(f, font=("Segoe UI", 12), show="*")
        self.e_user.grid(row=2, column=1, padx=8, ipady=4)
        self.e_pass.grid(row=3, column=1, padx=8, ipady=4)
        tk.Button(f, text="Login", font=("Segoe UI", 12, "bold"), width=18, bg=ACCENT,
                  activebackground="#15803d", command=self.login).grid(row=4, column=0, columnspan=2, pady=(22, 0), ipady=3)
        tk.Button(f, text="Password bhool gaye?", bg=CARD, fg=PRIMARY, activebackground=CARD,
                  activeforeground=PRIMARY_DARK, font=("Segoe UI", 10, "underline"),
                  command=self.forgot_password).grid(row=5, column=0, columnspan=2, pady=(10, 0))
        self.e_user.focus()
        self.bind("<Return>", lambda e: self.login())

    def forgot_password(self):
        if not db.has_recovery_code():
            messagebox.showinfo(
                "Recovery",
                "Recovery code abhi set nahi hai.\n\n"
                "Admin login karke Settings mein 'Recovery code' set karein.\n"
                "Abhi login nahi ho raha to reset_admin.py chalayen.")
            return
        code = simpledialog.askstring("Recovery", "Recovery code likhein:", show="*", parent=self)
        if code is None:
            return
        if not db.check_recovery_code(code):
            messagebox.showerror("Recovery", "Recovery code ghalat hai")
            return
        new = simpledialog.askstring("Naya password", "Admin ka naya password (kam az kam 4 harf):",
                                     show="*", parent=self)
        if new is None:
            return
        if len(new) < 4:
            messagebox.showwarning("Password", "Password kam az kam 4 harf ka rakhein")
            return
        db.reset_password("admin", new)
        messagebox.showinfo("Password", "Admin ka password badal gaya. Ab login karein.")

    def login(self):
        u = self.e_user.get().strip()
        p = self.e_pass.get()
        conn = db.get_connection()
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? AND password_hash = ?",
            (u, db.hash_password(p))).fetchone()
        conn.close()
        if row:
            self.user = row
            self.cart = {}
            self.cust = None
            self.show_billing()
            if row['role'] == 'admin':
                self.after(400, lambda: self.show_alerts(True))
        else:
            messagebox.showerror("Login", "Username ya password ghalat hai")

    # ---------------------------------------------------------- BILLING
    def show_billing(self):
        self.clear()
        self.unbind("<Return>")
        settings = db.get_settings()

        top = tk.Frame(self, bg="#1e3a8a")
        top.pack(fill="x")
        tk.Label(top, text=f"{settings['store_name']}  |  {self.user['username']} ({self.user['role']})",
                 bg="#1e3a8a", fg="white", font=("Segoe UI", 12, "bold")).pack(side="left", padx=10, pady=8)
        tk.Button(top, text="Logout", bg=DANGER, activebackground="#b91c1c", command=self.show_login).pack(side="right", padx=8, pady=6)

        menu = tk.Frame(self, bg="#e0e7ff")
        menu.pack(fill="x")
        buttons = [("Bills", self.open_bills), ("Returns", self.open_returns),
                   ("Customers", self.open_customers)]
        if self.user["role"] == "admin":
            low = len(db.low_stock_products()) + len(db.expiring_products(30))
            buttons += [("Inventory", self.open_inventory), ("Maal aaya", self.open_purchase),
                        ("Suppliers", self.open_suppliers), ("Reports", self.open_reports),
                        ("Closing", self.open_closing),
                        (f"Alerts ({low})", self.show_alerts), ("Backup", self.open_backup),
                        ("Users", self.open_users), ("Settings", self.open_settings)]
        for text, cmd in buttons:
            tk.Button(menu, text=text, command=cmd).pack(side="left", padx=3, pady=4)

        main = tk.Frame(self)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # left side: scan + cart
        left = tk.Frame(main)
        left.pack(side="left", fill="both", expand=True)

        sf = tk.Frame(left)
        sf.pack(fill="x")
        tk.Label(sf, text="Barcode / Naam:", font=("Segoe UI", 12)).pack(side="left")
        self.e_scan = tk.Entry(sf, font=("Segoe UI", 14))
        self.e_scan.pack(side="left", fill="x", expand=True, padx=8)
        self.e_scan.bind("<Return>", lambda e: self.add_by_text())
        tk.Button(sf, text="Add", command=self.add_by_text).pack(side="left")
        self.e_scan.focus()

        cols = ("name", "price", "qty", "total")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=15)
        for c, t, w in (("name", "Product", 320), ("price", "Price", 90),
                        ("qty", "Qty", 70), ("total", "Total", 100)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w" if c == "name" else "e")
        self.tree.pack(fill="both", expand=True, pady=10)

        bf = tk.Frame(left)
        bf.pack(fill="x")
        tk.Button(bf, text="+ Qty", width=8, command=lambda: self.change_qty(1)).pack(side="left", padx=3)
        tk.Button(bf, text="- Qty", width=8, command=lambda: self.change_qty(-1)).pack(side="left", padx=3)
        tk.Button(bf, text="Remove", width=8, bg=DANGER, activebackground="#b91c1c", command=self.remove_item).pack(side="left", padx=3)
        tk.Button(bf, text="Clear Bill", width=10, bg=DANGER, activebackground="#b91c1c", command=self.clear_cart).pack(side="left", padx=3)

        # right side: totals
        right = tk.Frame(main, padx=20, pady=6, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        right.pack(side="right", fill="y", padx=(10, 0))
        tk.Label(right, text="Bill Summary", font=("Segoe UI", 16, "bold")).pack(pady=6)

        self.lbl_sub = tk.Label(right, text="Subtotal: 0.00", font=("Segoe UI", 13))
        self.lbl_sub.pack(anchor="w", pady=2)

        df = tk.Frame(right)
        df.pack(fill="x", pady=2)
        tk.Label(df, text="Discount (Rs):", font=("Segoe UI", 11)).grid(row=0, column=0, sticky="w")
        tk.Label(df, text="Discount (%):", font=("Segoe UI", 11)).grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.e_disc = tk.Entry(df, font=("Segoe UI", 12), width=9)
        self.e_disc.insert(0, "0")
        self.e_disc.grid(row=1, column=0)
        self.e_dpct = tk.Entry(df, font=("Segoe UI", 12), width=9)
        self.e_dpct.insert(0, "0")
        self.e_dpct.grid(row=1, column=1, padx=(8, 0))
        self.e_disc.bind("<KeyRelease>", lambda e: self.refresh_totals())
        self.e_dpct.bind("<KeyRelease>", lambda e: self.refresh_totals())

        tk.Label(right, text="Tax (%):", font=("Segoe UI", 11)).pack(anchor="w")
        self.e_tax = tk.Entry(right, font=("Segoe UI", 12))
        self.e_tax.insert(0, settings["default_tax"])
        self.e_tax.pack(fill="x", pady=2)
        self.e_tax.bind("<KeyRelease>", lambda e: self.refresh_totals())

        self.lbl_total = tk.Label(right, text="TOTAL: 0.00", font=("Segoe UI", 20, "bold"), fg="#16a34a")
        self.lbl_total.pack(pady=8)

        tk.Label(right, text="Payment kaise ho rahi hai:", font=("Segoe UI", 11)).pack(anchor="w")
        pf = tk.Frame(right)
        pf.pack(fill="x", pady=2)
        self.pay_buttons = {}
        for i, (key, label) in enumerate(PAY_METHODS):
            b = tk.Button(pf, text=label, command=lambda k=key: self.set_pay(k))
            b.grid(row=i // 2, column=i % 2, padx=2, pady=2, sticky="ew")
            self.pay_buttons[key] = b
        pf.columnconfigure((0, 1), weight=1)
        self.set_pay("cash")

        tk.Label(right, text="Customer (udhaar ke liye):", font=("Segoe UI", 11)).pack(anchor="w", pady=(6, 0))
        self.lbl_cust = tk.Label(right, text="— koi nahi —", font=("Segoe UI", 11, "bold"), fg="#1e3a8a")
        self.lbl_cust.pack(anchor="w")
        cf = tk.Frame(right)
        cf.pack(fill="x", pady=2)
        tk.Button(cf, text="Chunein", command=self.choose_customer).pack(side="left")
        tk.Button(cf, text="Hatayen", command=self.clear_customer).pack(side="left", padx=4)

        tk.Label(right, text="Customer ne kitne paise diye (khali = bilkul bill ke):", font=("Segoe UI", 10)).pack(anchor="w", pady=(8, 0))
        self.e_paid = tk.Entry(right, font=("Segoe UI", 12))
        self.e_paid.pack(fill="x", pady=2)
        self.e_paid.bind("<KeyRelease>", lambda e: self.refresh_change())
        self.lbl_change = tk.Label(right, text="", font=("Segoe UI", 13, "bold"))
        self.lbl_change.pack(anchor="w", pady=2)

        tk.Button(right, text="Save Bill & Receipt", font=("Segoe UI", 13, "bold"),
                  bg="#16a34a", fg="white", command=self.checkout).pack(fill="x", ipady=8, pady=12)
        self.paint(right, CARD)
        self.update_customer_label()

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
            if w.winfo_class() in ("Label", "Frame"):
                w.configure(bg=color)
            self.paint(w, color)

    def add_by_text(self):
        text = self.e_scan.get().strip()
        if not text:
            return
        product = db.get_product_by_barcode(text)
        if product:
            self.add_to_cart(product)
        else:
            results = db.search_products(text)
            if not results:
                messagebox.showwarning("Not found", "Product nahi mila")
            elif len(results) == 1:
                self.add_to_cart(results[0])
            else:
                self.choose_product(results)
        self.e_scan.delete(0, "end")
        self.e_scan.focus()

    def choose_product(self, results, on_pick=None):
        win = tk.Toplevel(self)
        win.title("Product chunein")
        win.geometry("400x300")
        self.autosize(win)
        lb = tk.Listbox(win, font=("Segoe UI", 12))
        lb.pack(fill="both", expand=True)
        for r in results:
            lb.insert("end", f"{r['name']}  -  Rs {r['sale_price']}  (stock {r['stock_qty']})")

        def pick(event=None):
            sel = lb.curselection()
            if sel:
                (on_pick or self.add_to_cart)(results[sel[0]])
                win.destroy()
        lb.bind("<Double-Button-1>", pick)
        lb.bind("<Return>", pick)
        lb.focus()

    def add_to_cart(self, product):
        pid = product["id"]
        in_cart = self.cart[pid]["qty"] if pid in self.cart else 0
        if in_cart + 1 > product["stock_qty"]:
            messagebox.showwarning("Stock", f"Sirf {product['stock_qty']} stock mojood hai")
            return
        if pid not in self.cart and product["expiry_date"] and \
                product["expiry_date"] < datetime.now().strftime("%Y-%m-%d"):
            if not messagebox.askyesno(
                    "Expiry", f"{product['name']} ki expiry date guzar chuki hai ({product['expiry_date']}).\n"
                              "Phir bhi bechna hai?"):
                return
        if pid in self.cart:
            self.cart[pid]["qty"] += 1
        else:
            self.cart[pid] = {"id": pid, "name": product["name"],
                              "price": product["sale_price"], "qty": 1,
                              "stock": product["stock_qty"]}
        self.refresh_cart()

    def selected_pid(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def change_qty(self, delta):
        pid = self.selected_pid()
        if pid is None:
            return
        item = self.cart[pid]
        new_qty = item["qty"] + delta
        if new_qty < 1:
            return
        if new_qty > item["stock"]:
            messagebox.showwarning("Stock", f"Sirf {item['stock']} stock mojood hai")
            return
        item["qty"] = new_qty
        self.refresh_cart()
        self.tree.selection_set(str(pid))

    def remove_item(self):
        pid = self.selected_pid()
        if pid is not None:
            del self.cart[pid]
            self.refresh_cart()

    def clear_cart(self):
        self.cart = {}
        self.refresh_cart()

    def refresh_cart(self):
        self.tree.delete(*self.tree.get_children())
        for pid, it in self.cart.items():
            self.tree.insert("", "end", iid=str(pid), values=(
                it["name"], f"{it['price']:.2f}", it["qty"], f"{it['price'] * it['qty']:.2f}"))
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
        self.lbl_sub.config(text=f"Subtotal: {subtotal:.2f}")
        self.lbl_total.config(text=f"TOTAL: {total:.2f}")
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
                text, color = f"Wapis dena: {given - total:.2f}", ACCENT
            elif total - given >= 0.02:
                text, color = f"Udhaar (baqaya): {total - given:.2f}", DANGER
        try:
            self.lbl_change.config(text=text, fg=color)
        except tk.TclError:
            pass

    # --- customer chunna
    def update_customer_label(self):
        if self.cust:
            fresh = db.get_customer(self.cust["id"])
            self.lbl_cust.config(text=f"{fresh['name']}  (baqaya {fresh['balance']:.0f})")
        else:
            self.lbl_cust.config(text="— koi nahi —")

    def clear_customer(self):
        self.cust = None
        self.update_customer_label()

    def choose_customer(self):
        win = tk.Toplevel(self)
        win.title("Customer chunein")
        win.geometry("420x440")
        self.autosize(win)
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
                lb.insert("end", f"{r['name']}  {r['phone'] or ''}  (baqaya {r['balance']:.0f})")

        def pick(event=None):
            sel = lb.curselection()
            if sel:
                self.cust = rows[sel[0]]
                self.update_customer_label()
                win.destroy()

        e_search.bind("<KeyRelease>", load)
        lb.bind("<Double-Button-1>", pick)
        lb.bind("<Return>", pick)
        tk.Button(win, text="Chunein", command=pick).pack(pady=4)

        nf = tk.LabelFrame(win, text="Naya customer", padx=8, pady=8)
        nf.pack(fill="x", padx=10, pady=8)
        e_name = tk.Entry(nf, width=16)
        e_phone = tk.Entry(nf, width=14)
        tk.Label(nf, text="Naam").grid(row=0, column=0)
        tk.Label(nf, text="Phone").grid(row=0, column=1)
        e_name.grid(row=1, column=0, padx=3)
        e_phone.grid(row=1, column=1, padx=3)

        def add_new():
            name = e_name.get().strip()
            if not name:
                messagebox.showwarning("Customer", "Naam likhein", parent=win)
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
            messagebox.showinfo("Bill", "Bill khali hai")
            return
        subtotal, discount, tax_pct, tax, total = self.calc()
        paid_text = self.e_paid.get().strip()
        try:
            tendered = float(paid_text) if paid_text else total
        except ValueError:
            messagebox.showwarning("Paid", "Diye gaye paise sahi likhein")
            return
        tendered = max(0.0, tendered)
        paid = min(tendered, total)          # bill mein lagne wale paise
        change = tendered - total if tendered - total >= 0.02 else 0.0   # customer ko wapis
        cust_id = self.cust["id"] if self.cust else None
        if total - paid >= 0.02 and not cust_id:
            messagebox.showwarning("Udhaar", "Poore paise nahi diye: pehle customer chunein")
            return

        items = [(i["id"], i["qty"], i["price"]) for i in self.cart.values()]
        try:
            sale_id = db.save_sale(self.user["id"], items, discount, tax_pct, cust_id, paid,
                                   self.pay_method)
        except Exception as e:
            messagebox.showerror("Error", f"Bill save nahi hua: {e}")
            return

        s = db.get_settings()
        lines = [s["store_name"].center(40)]
        if s["address"]:
            lines.append(s["address"].center(40))
        if s["phone"]:
            lines.append(("Phone: " + s["phone"]).center(40))
        lines += ["-" * 40,
                  f"BILL NO: {sale_id}".center(40),
                  f"Date: {datetime.now():%d-%m-%Y %H:%M}",
                  f"Cashier: {self.user['username']}"]
        if cust_id:
            lines.append(f"Customer: {db.get_customer(cust_id)['name']}")
        lines.append("Payment: " + pay_label("udhaar" if paid <= 0 else self.pay_method, total, paid))
        lines.append("-" * 40)
        for i in self.cart.values():
            lines.append(i["name"][:40])
            lines.append(f"   {i['qty']} x {i['price']:.2f}".ljust(28) + f"{i['qty'] * i['price']:>12.2f}")
        lines += ["-" * 40,
                  f"{'Subtotal':<28}{subtotal:>12.2f}",
                  f"{'Discount':<28}{discount:>12.2f}",
                  f"{'Tax':<28}{tax:>12.2f}",
                  f"{'TOTAL':<28}{total:>12.2f}"]
        lines.append(f"{'Diye gaye':<28}{tendered:>12.2f}")
        if change > 0:
            lines.append(f"{'Wapis diye':<28}{change:>12.2f}")
        credit = total - paid
        if credit >= 0.02:
            lines += [f"{'Udhaar (is bill ka)':<28}{credit:>12.2f}",
                      f"{'Kul baqaya':<28}{db.get_customer(cust_id)['balance']:>12.2f}"]
        lines += ["-" * 40, s["footer"].center(40)]
        receipt = "\n".join(lines)

        receipts_dir = os.path.join(db.BASE_DIR, "receipts")
        os.makedirs(receipts_dir, exist_ok=True)
        path = os.path.join(receipts_dir, f"receipt_{sale_id}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(receipt)

        self.show_receipt(receipt, path)
        self.cart = {}
        self.cust = None
        self.e_disc.delete(0, "end")
        self.e_disc.insert(0, "0")
        self.e_dpct.delete(0, "end")
        self.e_dpct.insert(0, "0")
        self.e_tax.delete(0, "end")
        self.e_tax.insert(0, s["default_tax"])
        self.e_paid.delete(0, "end")
        self.set_pay("cash")
        self.update_customer_label()
        self.refresh_cart()

    def show_receipt(self, receipt, path):
        win = tk.Toplevel(self)
        win.title("Receipt")
        txt = tk.Text(win, font=("Courier New", 10), width=44, height=28)
        txt.insert("1.0", receipt)
        txt.config(state="disabled")
        txt.pack(padx=10, pady=10)

        def do_print():
            try:
                os.startfile(os.path.abspath(path), "print")
            except Exception as e:
                messagebox.showerror("Print", f"Print nahi ho saka: {e}", parent=win)
        tk.Button(win, text="Print", command=do_print).pack(side="left", padx=20, pady=8)
        tk.Button(win, text="Close", command=win.destroy).pack(side="right", padx=20, pady=8)

    # -------------------------------------------------------- CUSTOMERS
    def open_customers(self):
        win = tk.Toplevel(self)
        win.title("Customers / Udhaar Khata")
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
        for c, t, w in (("name", "Naam", 250), ("phone", "Phone", 150), ("balance", "Baqaya (Rs)", 130)):
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
            lbl_total.config(text=f"Kul udhaar: {total:.0f}")
        e_search.bind("<KeyRelease>", load)

        def receive():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Payment", "Pehle customer chunein", parent=win)
                return
            amt = simpledialog.askfloat("Payment", "Kitne paise wasool hue?", minvalue=0.01, parent=win)
            if amt:
                db.receive_payment(int(sel[0]), amt)
                load()

        nf = tk.LabelFrame(win, text="Naya customer", padx=8, pady=8)
        nf.pack(fill="x", padx=10, pady=8)
        e_name = tk.Entry(nf, width=22)
        e_phone = tk.Entry(nf, width=16)
        tk.Label(nf, text="Naam").grid(row=0, column=0)
        tk.Label(nf, text="Phone").grid(row=0, column=1)
        e_name.grid(row=1, column=0, padx=4)
        e_phone.grid(row=1, column=1, padx=4)

        def add():
            if not e_name.get().strip():
                messagebox.showwarning("Customer", "Naam likhein", parent=win)
                return
            db.add_customer(e_name.get().strip(), e_phone.get().strip())
            e_name.delete(0, "end")
            e_phone.delete(0, "end")
            load()
        tk.Button(nf, text="Add", bg="#16a34a", fg="white", command=add).grid(row=1, column=2, padx=8)
        tk.Button(win, text="Payment wasool karein", command=receive).pack(pady=(0, 10))
        load()

    # ------------------------------------------------------------ BILLS
    def open_bills(self):
        win = tk.Toplevel(self)
        win.title("Bills (purane bills)")
        win.geometry("860x540")
        self.autosize(win)
        today = datetime.now().strftime("%Y-%m-%d")

        top = tk.Frame(win)
        top.pack(fill="x", padx=10, pady=10)
        tk.Label(top, text="Date (YYYY-MM-DD):").pack(side="left")
        e_date = tk.Entry(top, width=12)
        e_date.insert(0, today)
        e_date.pack(side="left", padx=4)
        tk.Label(top, text="   ya Bill No:").pack(side="left")
        e_no = tk.Entry(top, width=8)
        e_no.pack(side="left", padx=4)

        cols = ("no", "time", "customer", "pay", "total", "refunded")
        tree = ttk.Treeview(win, columns=cols, show="headings")
        for c, t, w in (("no", "Bill No", 70), ("time", "Date / Time", 140),
                        ("customer", "Customer", 170), ("pay", "Payment", 130),
                        ("total", "Total", 100), ("refunded", "Wapis hua", 100)):
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
            no = e_no.get().strip()
            if no:
                if not no.isdigit():
                    messagebox.showwarning("Bill", "Bill number sirf number hota hai", parent=win)
                    conn.close()
                    return
                rows = conn.execute(base + "WHERE s.id = ?", (int(no),)).fetchall()
            else:
                d = e_date.get().strip()
                try:
                    datetime.strptime(d, "%Y-%m-%d")
                except ValueError:
                    messagebox.showerror("Date", "Date aise likhein: 2026-10-20", parent=win)
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
                messagebox.showinfo("Bill", "Pehle list mein se bill chunein", parent=win)
                return None
            return int(sel[0])

        def view_receipt():
            bid = selected()
            if bid is None:
                return
            path = os.path.join(db.BASE_DIR, "receipts", f"receipt_{bid}.txt")
            if not os.path.exists(path):
                messagebox.showinfo("Receipt", "Is bill ki receipt file nahi mili", parent=win)
                return
            with open(path, encoding="utf-8") as f:
                self.show_receipt(f.read(), path)

        def do_return():
            bid = selected()
            if bid is not None:
                self.open_returns(bid)

        tk.Button(top, text="Dhundein", bg="#1e3a8a", fg="white", command=load).pack(side="left", padx=8)
        e_date.bind("<Return>", load)
        e_no.bind("<Return>", load)
        bf = tk.Frame(win)
        bf.pack(pady=10)
        tk.Button(bf, text="Receipt dekhein / dobara print", command=view_receipt).pack(side="left", padx=6)
        tk.Button(bf, text="Is bill ki wapsi (Return)", bg="#dc2626", fg="white",
                  command=do_return).pack(side="left", padx=6)
        tk.Label(win, text="Laal bill = is mein se kuch saaman wapis ho chuka hai", fg="#dc2626").pack()
        load()

    # ---------------------------------------------------------- RETURNS
    def open_returns(self, bill_id=None):
        win = tk.Toplevel(self)
        win.title("Returns (wapsi)")
        win.geometry("760x520")
        self.autosize(win)

        top = tk.Frame(win)
        top.pack(fill="x", padx=10, pady=10)
        tk.Label(top, text="Bill No:", font=("Segoe UI", 12)).pack(side="left")
        e_bill = tk.Entry(top, width=10, font=("Segoe UI", 12))
        e_bill.pack(side="left", padx=6)
        info = tk.Label(win, text="", font=("Segoe UI", 11), fg="#1e3a8a")
        info.pack(anchor="w", padx=10)

        cols = ("name", "price", "sold", "returned", "now")
        tree = ttk.Treeview(win, columns=cols, show="headings")
        for c, t, w in (("name", "Product", 280), ("price", "Price", 90), ("sold", "Bika", 80),
                        ("returned", "Pehle wapis", 100), ("now", "Ab wapis", 90)):
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
                sid = int(e_bill.get().strip())
            except ValueError:
                messagebox.showwarning("Bill", "Bill number likhein", parent=win)
                return
            sale = db.get_sale(sid)
            if sale is None:
                messagebox.showwarning("Bill", "Ye bill nahi mila", parent=win)
                return
            state["sale"] = sale
            state["items"] = {r["product_id"]: r for r in db.get_returnable_items(sid)}
            state["pending"] = {}
            who = f"  |  Customer: {sale['customer_name']}" if sale["customer_name"] else ""
            info.config(text=f"Bill #{sid}  |  {sale['sale_date']}  |  Total {sale['total']:.2f}{who}")
            draw()

        def set_qty():
            sel = tree.selection()
            if not sel or state["sale"] is None:
                return
            pid = int(sel[0])
            r = state["items"][pid]
            avail = r["sold"] - r["returned"]
            if avail <= 0:
                messagebox.showinfo("Return", "Is product ki sari quantity pehle hi wapis ho chuki", parent=win)
                return
            q = simpledialog.askinteger("Wapsi", f"Kitni quantity wapis? (zyada se zyada {avail})",
                                        minvalue=0, maxvalue=avail, parent=win)
            if q is not None:
                state["pending"][pid] = q
                draw()

        def confirm():
            items = [(p, q) for p, q in state["pending"].items() if q > 0]
            if not items:
                messagebox.showinfo("Return", "Pehle product chunein aur 'Quantity chunein' dabayen", parent=win)
                return
            if not messagebox.askyesno("Confirm", "Wapsi confirm karein?", parent=win):
                return
            try:
                _, refund, offset = db.process_return(state["sale"]["id"], self.user["id"], items)
            except Exception as e:
                messagebox.showerror("Return", str(e), parent=win)
                return
            msg = f"Wapsi ho gayi. Stock wapis add ho gaya.\nRefund: {refund:.2f}"
            if offset > 0:
                msg += f"\nIn mein se {offset:.2f} customer ke udhaar se kam kiye gaye."
                msg += f"\nCash wapis dena: {refund - offset:.2f}"
            messagebox.showinfo("Return", msg, parent=win)
            load()

        tk.Button(top, text="Load Bill", command=load).pack(side="left")
        e_bill.bind("<Return>", lambda e: load())
        bf = tk.Frame(win)
        bf.pack(pady=(0, 10))
        tk.Button(bf, text="Quantity chunein", command=set_qty).pack(side="left", padx=6)
        tk.Button(bf, text="Wapsi confirm karein", bg="#dc2626", fg="white", command=confirm).pack(side="left", padx=6)
        e_bill.focus()
        if bill_id:
            e_bill.insert(0, str(bill_id))
            load()

    # ------------------------------------------------------------ USERS
    def open_users(self):
        win = tk.Toplevel(self)
        win.title("Users")
        win.geometry("520x420")
        self.autosize(win)

        form = tk.LabelFrame(win, text="Naya user", padx=8, pady=8)
        form.pack(fill="x", padx=10, pady=10)
        tk.Label(form, text="Username").grid(row=0, column=0, padx=4)
        tk.Label(form, text="Password").grid(row=0, column=1, padx=4)
        tk.Label(form, text="Role").grid(row=0, column=2, padx=4)
        e_name = tk.Entry(form, width=14)
        e_pass = tk.Entry(form, width=14, show="*")
        cb_role = ttk.Combobox(form, values=("cashier", "admin"), width=9, state="readonly")
        cb_role.set("cashier")
        e_name.grid(row=1, column=0, padx=4)
        e_pass.grid(row=1, column=1, padx=4)
        cb_role.grid(row=1, column=2, padx=4)

        tree = ttk.Treeview(win, columns=("name", "role"), show="headings", height=6)
        tree.heading("name", text="Username")
        tree.heading("role", text="Role")
        tree.pack(fill="both", expand=True, padx=10)

        def load():
            tree.delete(*tree.get_children())
            conn = db.get_connection()
            for r in conn.execute("SELECT * FROM users ORDER BY username"):
                tree.insert("", "end", iid=str(r["id"]), values=(r["username"], r["role"]))
            conn.close()

        def add():
            name, pw = e_name.get().strip(), e_pass.get()
            if not name or len(pw) < 4:
                messagebox.showwarning("User", "Username likhein aur password kam az kam 4 harf ka rakhein", parent=win)
                return
            try:
                conn = db.get_connection()
                conn.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                             (name, db.hash_password(pw), cb_role.get()))
                conn.commit()
                conn.close()
            except Exception:
                messagebox.showerror("User", "Ye username pehle se mojood hai", parent=win)
                return
            e_name.delete(0, "end")
            e_pass.delete(0, "end")
            load()

        def change_password():
            sel = tree.selection()
            if not sel:
                return
            pw = simpledialog.askstring("Password", "Naya password:", show="*", parent=win)
            if pw and len(pw) >= 4:
                conn = db.get_connection()
                conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                             (db.hash_password(pw), int(sel[0])))
                conn.commit()
                conn.close()
                messagebox.showinfo("Password", "Password badal gaya", parent=win)
            elif pw:
                messagebox.showwarning("Password", "Kam az kam 4 harf rakhein", parent=win)

        def delete():
            sel = tree.selection()
            if not sel:
                return
            if int(sel[0]) == self.user["id"]:
                messagebox.showwarning("User", "Aap apna login khud delete nahi kar sakte", parent=win)
                return
            if messagebox.askyesno("Delete", "Ye user delete karein?", parent=win):
                try:
                    conn = db.get_connection()
                    conn.execute("DELETE FROM users WHERE id = ?", (int(sel[0]),))
                    conn.commit()
                    conn.close()
                except Exception:
                    messagebox.showerror("User", "Is user ke bills mojood hain, delete nahi ho sakta", parent=win)
                load()

        tk.Button(form, text="Add User", bg="#16a34a", fg="white", command=add).grid(row=1, column=3, padx=10)
        bf = tk.Frame(win)
        bf.pack(fill="x", padx=10, pady=10, side="bottom", before=tree)
        tk.Button(bf, text="Password badlein", bg=ACCENT, activebackground="#15803d",
                  font=("Segoe UI", 10, "bold"), command=change_password).pack(side="left")
        tk.Button(bf, text="Delete", bg=DANGER, activebackground="#b91c1c", command=delete).pack(side="left", padx=8)
        tk.Label(bf, text="Pehle list mein se user chunein", fg="#64748b").pack(side="left", padx=10)
        load()

    # --------------------------------------------------------- SETTINGS
    def open_settings(self):
        win = tk.Toplevel(self)
        win.title("Dukaan ki Settings")
        win.geometry("480x410")
        self.autosize(win)
        s = db.get_settings()
        fields = [("store_name", "Dukaan ka naam"), ("address", "Address"),
                  ("phone", "Phone"), ("footer", "Receipt ke neeche message"),
                  ("default_tax", "Default tax (%)")]
        entries = {}
        for i, (key, label) in enumerate(fields):
            tk.Label(win, text=label, font=("Segoe UI", 11)).grid(row=i, column=0, sticky="e", padx=10, pady=10)
            e = tk.Entry(win, width=32, font=("Segoe UI", 11))
            e.insert(0, s[key])
            e.grid(row=i, column=1, padx=6)
            entries[key] = e

        tk.Label(win, text="Recovery code\n(password bhoolne par)", font=("Segoe UI", 11)).grid(
            row=len(fields), column=0, sticky="e", padx=10, pady=10)
        e_rec = tk.Entry(win, width=32, font=("Segoe UI", 11), show="*")
        e_rec.grid(row=len(fields), column=1, padx=6)
        tk.Label(win, text=("Set hai. Badalna ho to naya code likhein, warna khali chhorein."
                            if db.has_recovery_code() else "Abhi set nahi hai. Koi yaad rehne wala code likhein."),
                 fg="#64748b", font=("Segoe UI", 9)).grid(row=len(fields) + 1, column=1, sticky="w", padx=6)

        def save():
            rec = e_rec.get().strip()
            if rec and len(rec) < 4:
                messagebox.showwarning("Recovery", "Recovery code kam az kam 4 harf ka rakhein", parent=win)
                return
            try:
                float(entries["default_tax"].get() or 0)
            except ValueError:
                messagebox.showwarning("Tax", "Tax sirf number hona chahiye", parent=win)
                return
            if rec:
                db.set_recovery_code(rec)
            for key, e in entries.items():
                db.set_setting(key, e.get().strip() or ("0" if key == "default_tax" else ""))
            messagebox.showinfo("Settings", "Save ho gayi. Agle bill se receipt par nazar aayegi.", parent=win)
            win.destroy()
            self.show_billing()
        tk.Button(win, text="Save", bg="#16a34a", fg="white", width=14, command=save).grid(
            row=len(fields) + 2, column=0, columnspan=2, pady=14)

    # ---------------------------------------------------------- REPORTS
    def open_reports(self):
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
                messagebox.showerror("Date", "Date aise likhein: 2026-10-19", parent=win)
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
                [f"{PAY_NAMES[k]}: {amounts.get(k, 0):.0f}" for k, _ in PAY_METHODS]
                + [f"Udhaar: {udhaar:.0f}"]))

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
        tk.Button(top, text="Aaj", command=lambda: set_range(today, today)).pack(side="left", padx=2)
        tk.Button(top, text="Is Mahine", command=lambda: set_range(month_start, today)).pack(side="left", padx=2)
        show()

    # ----------------------------------------------------------- ALERTS
    def show_alerts(self, only_if_any=False):
        low = db.low_stock_products()
        exp = db.expiring_products(30)
        if only_if_any and not low and not exp:
            return
        win = tk.Toplevel(self)
        win.title("Alerts: kam stock aur expiry")
        win.geometry("600x520")
        self.autosize(win)
        txt = tk.Text(win, font=("Segoe UI", 11), wrap="word")
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        txt.tag_configure("h", font=("Segoe UI", 13, "bold"))
        txt.tag_configure("red", foreground="#dc2626")
        today = datetime.now().date()

        txt.insert("end", f"Kam stock ({len(low)})\n", "h")
        if not low:
            txt.insert("end", "  Sab theek hai.\n")
        for r in low:
            txt.insert("end", f"  {r['name']}  -  baqi {r['stock_qty']}  (limit {r['low_stock_limit']})\n")
        txt.insert("end", f"\nExpiry (30 din ke andar ya guzar chuki) ({len(exp)})\n", "h")
        if not exp:
            txt.insert("end", "  Koi nahi.\n")
        for r in exp:
            try:
                days = (datetime.strptime(r["expiry_date"], "%Y-%m-%d").date() - today).days
            except ValueError:
                days = None
            if days is None:
                status, tag = r["expiry_date"], ()
            elif days < 0:
                status, tag = f"EXPIRE ho chuka ({-days} din pehle)", ("red",)
            else:
                status, tag = f"{days} din baqi", ()
            txt.insert("end", f"  {r['name']}  -  {r['expiry_date']}  -  {status}  (stock {r['stock_qty']})\n", tag)
        txt.config(state="disabled")
        tk.Button(win, text="Theek hai", command=win.destroy).pack(pady=(0, 10))

    # --------------------------------------------------------- SUPPLIERS
    def open_suppliers(self):
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
        for c, t, w in (("name", "Supplier", 250), ("phone", "Phone", 150), ("balance", "Humein dena hai (Rs)", 150)):
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
            lbl_total.config(text=f"Kul dena: {total:.0f}")
        e_search.bind("<KeyRelease>", load)

        def pay():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Payment", "Pehle supplier chunein", parent=win)
                return
            amt = simpledialog.askfloat("Payment", "Supplier ko kitne paise diye?", minvalue=0.01, parent=win)
            if amt:
                db.pay_supplier(int(sel[0]), amt)
                load()

        nf = tk.LabelFrame(win, text="Naya supplier", padx=8, pady=8)
        nf.pack(fill="x", padx=10, pady=8)
        e_name = tk.Entry(nf, width=22)
        e_phone = tk.Entry(nf, width=16)
        tk.Label(nf, text="Naam").grid(row=0, column=0)
        tk.Label(nf, text="Phone").grid(row=0, column=1)
        e_name.grid(row=1, column=0, padx=4)
        e_phone.grid(row=1, column=1, padx=4)

        def add():
            if not e_name.get().strip():
                messagebox.showwarning("Supplier", "Naam likhein", parent=win)
                return
            db.add_supplier(e_name.get().strip(), e_phone.get().strip())
            e_name.delete(0, "end")
            e_phone.delete(0, "end")
            load()
        tk.Button(nf, text="Add", bg="#16a34a", fg="white", command=add).grid(row=1, column=2, padx=8)
        tk.Button(win, text="Supplier ko payment karein", command=pay).pack(pady=(0, 10))
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
        for i, (label, default) in enumerate((("Quantity", "1"), ("Cost price (ek ki)", product["cost_price"]),
                                              ("Expiry (khali ho sakti hai)", product["expiry_date"] or ""))):
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
                    raise ValueError("Quantity aur cost sahi likhein")
            except ValueError as e:
                messagebox.showwarning("Maal", str(e), parent=dlg)
                return
            result["v"] = (qty, cost, expiry)
            dlg.destroy()
        tk.Button(dlg, text="OK", width=10, command=ok).grid(row=4, column=0, columnspan=2, pady=12)
        dlg.bind("<Return>", ok)
        entries[0].focus()
        entries[0].select_range(0, "end")
        dlg.grab_set()
        dlg.wait_window()
        return result.get("v")

    def open_purchase(self):
        win = tk.Toplevel(self)
        win.title("Maal aaya (Purchase)")
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
            cb["values"] = ["(cash khareedari / koi supplier nahi)"] + [
                f"{r['name']}  (dena {r['balance']:.0f})" for r in suppliers]
            idx = 0
            for i, r in enumerate(suppliers, start=1):
                if r["id"] == select_id:
                    idx = i
            cb.current(idx)

        def new_supplier():
            name = simpledialog.askstring("Supplier", "Supplier ka naam:", parent=win)
            if name and name.strip():
                load_suppliers(db.add_supplier(name.strip()))
        tk.Button(top, text="Naya supplier", command=new_supplier).pack(side="left")
        load_suppliers()

        sf = tk.Frame(win)
        sf.pack(fill="x", padx=10)
        tk.Label(sf, text="Barcode / Naam:", font=("Segoe UI", 12)).pack(side="left")
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
            lbl_total.config(text=f"TOTAL: {sum(i['qty'] * i['cost'] for i in lines.values()):.2f}")

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
                    messagebox.showwarning("Maal", "Product nahi mila. Pehle Inventory mein add karein.", parent=win)
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
        tk.Button(bf, text="Line hatayen", command=remove).pack(side="left")
        tk.Label(bf, text="   Diye gaye paise (khali = poore):").pack(side="left")
        e_paid = tk.Entry(bf, width=12)
        e_paid.pack(side="left", padx=4)

        def save():
            if not lines:
                messagebox.showinfo("Maal", "Koi product add nahi kiya", parent=win)
                return
            total = sum(i["qty"] * i["cost"] for i in lines.values())
            try:
                paid = float(e_paid.get()) if e_paid.get().strip() else total
            except ValueError:
                messagebox.showwarning("Maal", "Diye gaye paise sahi likhein", parent=win)
                return
            idx = cb.current()
            supplier_id = suppliers[idx - 1]["id"] if idx > 0 else None
            items = [(pid, i["qty"], i["cost"], i["expiry"]) for pid, i in lines.items()]
            try:
                db.save_purchase(self.user["id"], supplier_id, items, paid)
            except Exception as e:
                messagebox.showerror("Maal", str(e), parent=win)
                return
            messagebox.showinfo("Maal", "Maal save ho gaya. Stock barh gaya aur cost price update ho gayi.", parent=win)
            lines.clear()
            e_paid.delete(0, "end")
            load_suppliers(supplier_id)
            redraw()
        tk.Button(bf, text="Save (stock barhayen)", bg="#16a34a", fg="white",
                  font=("Segoe UI", 12, "bold"), command=save).pack(side="right")

    # ----------------------------------------------------------- CLOSING
    def open_closing(self):
        win = tk.Toplevel(self)
        win.title("Daily Closing (din ka hisab)")
        win.geometry("560x600")
        self.autosize(win)
        today = datetime.now().strftime("%Y-%m-%d")

        top = tk.Frame(win)
        top.pack(fill="x", padx=12, pady=10)
        tk.Label(top, text="Date (YYYY-MM-DD):").pack(side="left")
        e_date = tk.Entry(top, width=12)
        e_date.insert(0, today)
        e_date.pack(side="left", padx=6)

        spec = [("Bills ki ginti", "bills", False), ("Kul sale", "sales_total", True),
                ("   us mein se CASH mila", "cash_sales", True),
                ("   us mein se Card se mila", "card_sales", True),
                ("   us mein se Easypaisa se mila", "easypaisa_sales", True),
                ("   us mein se JazzCash se mila", "jazzcash_sales", True),
                ("   us mein se udhaar diya", "udhaar", True),
                ("Purane udhaar ki wasooli (+)", "cust_payments", True),
                ("Wapsi par cash wapis diya (-)", "cash_refunds", True),
                ("Maal kharidne par cash diya (-)", "purchase_paid", True),
                ("Suppliers ko payment (-)", "supplier_payments", True)]
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

        cf = tk.LabelFrame(win, text="Cash gin kar milayen", padx=10, pady=10)
        cf.pack(fill="x", padx=12)
        tk.Label(cf, text="Subah drawer mein cash:").grid(row=0, column=0, sticky="w", pady=3)
        e_open = tk.Entry(cf, width=12)
        e_open.insert(0, "0")
        e_open.grid(row=0, column=1, padx=8)
        tk.Label(cf, text="Abhi gin kar kitna hai:").grid(row=1, column=0, sticky="w", pady=3)
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
                lbl_diff.config(text="Hisab bilkul theek hai", fg="#16a34a")
            elif diff > 0:
                lbl_diff.config(text=f"{diff:.2f} cash ZYADA hai", fg="#b36b00")
            else:
                lbl_diff.config(text=f"{-diff:.2f} cash KAM hai", fg="#dc2626")

        def show(event=None):
            try:
                datetime.strptime(e_date.get().strip(), "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Date", "Date aise likhein: 2026-10-20", parent=win)
                return
            d = db.daily_closing(e_date.get().strip())
            for _, key, money in spec:
                vals[key].config(text=f"{d[key]:.2f}" if money else str(d[key]))
            state["expected"] = d["expected_cash"]
            lbl_expected.config(text=f"Drawer mein CASH hona chahiye: {d['expected_cash']:.2f}")
            compare()

        e_open.bind("<KeyRelease>", compare)
        e_count.bind("<KeyRelease>", compare)
        e_date.bind("<Return>", show)
        tk.Button(top, text="Show", bg="#1e3a8a", fg="white", command=show).pack(side="left", padx=6)
        tk.Label(win, text="Drawer mein hona chahiye = subah ka cash + din ka cash",
                 fg="#555").pack(pady=8)
        show()

    # ------------------------------------------------------------ BACKUP
    def open_backup(self):
        win = tk.Toplevel(self)
        win.title("Backup")
        win.geometry("480x300")
        self.autosize(win)
        tk.Label(win, text="Poora record ek file (superstore.db) mein hai.\n"
                           "Roz ek backup khud 'backups' folder mein banta hai.",
                 font=("Segoe UI", 11), justify="left").pack(padx=14, pady=14, anchor="w")

        def backup():
            folder = filedialog.askdirectory(parent=win, title="Backup kahan rakhni hai? (USB / folder)")
            if not folder:
                return
            try:
                dest = db.backup_to(folder)
            except Exception as e:
                messagebox.showerror("Backup", str(e), parent=win)
                return
            messagebox.showinfo("Backup", f"Backup ban gayi:\n{dest}", parent=win)

        def restore():
            path = filedialog.askopenfilename(parent=win, title="Backup file chunein",
                                              filetypes=[("Backup", "*.db"), ("All", "*.*")])
            if not path:
                return
            if not messagebox.askyesno(
                    "Restore", "Ab ka poora data is backup se REPLACE ho jaye ga.\n"
                               "(Pehle ka data bhi 'backups' folder mein mehfooz kar liya jata hai.)\nJari rakhein?",
                    parent=win):
                return
            try:
                safety = db.restore_from(path)
            except Exception as e:
                messagebox.showerror("Restore", str(e), parent=win)
                return
            messagebox.showinfo("Restore", f"Data wapis aa gaya.\nPehle wala data yahan mehfooz hai:\n{safety}", parent=win)
            win.destroy()
            self.show_billing()

        tk.Button(win, text="Backup banayen (USB / folder mein)", width=34, bg="#16a34a", fg="white",
                  command=backup).pack(pady=6)
        tk.Button(win, text="Backup se data wapis lein (Restore)", width=34, command=restore).pack(pady=6)

    # -------------------------------------------------------- INVENTORY
    def open_inventory(self):
        win = tk.Toplevel(self)
        win.title("Inventory")
        win.geometry("1100x620")
        self.autosize(win)

        form = tk.LabelFrame(win, text="Naya product add karein (barcode aur expiry khali chhor sakte hain)",
                             padx=8, pady=8)
        form.pack(fill="x", padx=10, pady=8)
        fields = [("Barcode", 14), ("Naam", 22), ("Category", 12), ("Cost Price", 8),
                  ("Sale Price", 8), ("Stock", 6), ("Expiry", 11)]
        entries = {}
        for i, (label, w) in enumerate(fields):
            tk.Label(form, text=label).grid(row=0, column=i, padx=4)
            e = tk.Entry(form, width=w)
            e.grid(row=1, column=i, padx=4)
            entries[label] = e

        cols = ("barcode", "name", "category", "cost", "price", "stock", "expiry")
        tree = ttk.Treeview(win, columns=cols, show="headings", selectmode="extended")
        for c, t, w in (("barcode", "Barcode", 130), ("name", "Naam", 270),
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
                    entries["Naam"].get().strip(),
                    entries["Category"].get().strip(),
                    float(entries["Cost Price"].get() or 0),
                    float(entries["Sale Price"].get()),
                    int(entries["Stock"].get() or 0),
                    expiry_date=db.parse_date(entries["Expiry"].get()))
            except Exception as e:
                messagebox.showerror("Error", f"Product add nahi hua: {e}", parent=win)
                return
            for e in entries.values():
                e.delete(0, "end")
            load()

        def restock():
            sel = tree.selection()
            if not sel:
                return
            qty = simpledialog.askinteger("Restock", "Kitna stock add karna hai?", parent=win)
            if qty:
                conn = db.get_connection()
                conn.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE id = ?",
                             (qty, int(sel[0])))
                conn.commit()
                conn.close()
                load()

        def change_price():
            sel = tree.selection()
            if not sel:
                return
            price = simpledialog.askfloat("Price", "Nayi sale price:", minvalue=0, parent=win)
            if price is not None:
                conn = db.get_connection()
                conn.execute("UPDATE products SET sale_price = ? WHERE id = ?", (price, int(sel[0])))
                conn.commit()
                conn.close()
                load()

        def change_expiry():
            sel = tree.selection()
            if not sel:
                return
            text = simpledialog.askstring("Expiry", "Nayi expiry date (2026-12-31), khali = hata dein:", parent=win)
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
            if sel and messagebox.askyesno("Delete", "Ye product delete karein?", parent=win):
                for iid in sel:
                    try:
                        conn = db.get_connection()
                        conn.execute("DELETE FROM products WHERE id = ?", (int(iid),))
                        conn.commit()
                        conn.close()
                    except Exception:
                        messagebox.showerror("Error", "Is product ki sale/maal ka record hai, delete nahi ho sakta", parent=win)
                load()

        def print_labels():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Labels", "Pehle product(s) chunein (Ctrl dabaye rakh kar kai chun sakte hain)", parent=win)
                return
            copies = simpledialog.askinteger("Labels", "Har product ke kitne labels?",
                                             initialvalue=1, minvalue=1, maxvalue=500, parent=win)
            if not copies:
                return
            try:
                lbl.make_labels([int(i) for i in sel], copies)
            except Exception as e:
                messagebox.showerror("Labels", f"Labels nahi ban sake: {e}", parent=win)
                return
            load()

        def make_template():
            path = os.path.join(db.BASE_DIR, "products_template.csv")
            try:
                db.write_import_template(path)
            except Exception as e:
                messagebox.showerror("Template", str(e), parent=win)
                return
            messagebox.showinfo("Template", f"Sample file ban gayi:\n{path}\n\nIs ko Excel mein khol kar apne products "
                                            "likhein, phir 'Products import' dabayen.\n"
                                            "Excel (.xlsx) ya CSV dono chalti hain.", parent=win)
            try:
                os.startfile(db.BASE_DIR)
            except Exception:
                pass

        def import_file():
            path = filedialog.askopenfilename(parent=win, title="Products ki file chunein",
                                              filetypes=[("Excel / CSV", "*.xlsx *.csv"), ("All", "*.*")])
            if not path:
                return
            try:
                added, skipped, errors = db.import_products_file(path)
            except Exception as e:
                messagebox.showerror("Import", str(e), parent=win)
                return
            msg = f"{added} naye products add hue.\n{skipped} pehle se mojood the (barcode same), skip kiye."
            if errors:
                msg += f"\n\n{len(errors)} rows mein masla tha:\n" + "\n".join(
                    f"Row {n}: {m}" for n, m in errors[:8])
            messagebox.showinfo("Import", msg, parent=win)
            load()

        tk.Button(form, text="Add Product", bg="#16a34a", fg="white", command=add).grid(
            row=1, column=len(fields), padx=10)
        tree.pack(fill="both", expand=True, padx=10)

        bf = tk.Frame(win)
        bf.pack(fill="x", padx=10, pady=8)
        for text, cmd in (("Restock", restock), ("Price badlein", change_price),
                          ("Expiry badlein", change_expiry), ("Barcode Labels print", print_labels),
                          ("Products import (Excel/CSV)", import_file), ("Import template", make_template),
                          ("Delete", delete)):
            tk.Button(bf, text=text, command=cmd).pack(side="left", padx=4)
        tk.Label(win, text="Laal = stock kam   |   Narangi = expiry qareeb/guzar gayi",
                 fg="#dc2626").pack(pady=(0, 8))
        load()

if __name__ == "__main__":
    App().mainloop()