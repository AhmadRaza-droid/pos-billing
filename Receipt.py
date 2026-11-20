"""Receipt banana aur print karna (thermal 58mm / 80mm), barcode ke saath."""
import os
import re
import base64
import html
import textwrap
import webbrowser

import db
import labels
from i18n import raw


def width_chars(paper):
    """58mm receipt = 32 harf, 80mm = 42 harf ek line mein."""
    return 32 if str(paper) == "58" else 42


def build_text(s, d, lang=None):
    """s = settings, d = bill ki details, lang = receipt ki zubaan (en/ur/pa). Receipt ka text deta hai."""
    W = width_chars(s.get("paper_width", "80"))
    NUM = 11  # amount ka column

    def L(text, **kw):
        return raw(text, lang=lang, **kw)

    def center(t):
        return t[:W].center(W)

    def row(label, value):
        return label[:W - NUM - 1].ljust(W - NUM) + f"{value:>{NUM}.2f}"

    sep = "-" * W
    lines = [center(s["store_name"].upper())]
    for part in textwrap.wrap(s.get("address", ""), W):
        lines.append(center(part))
    if s.get("phone"):
        lines.append(center(f"{L('Tel')}: " + s["phone"]))
    if s.get("ntn"):
        lines.append(center(f"{L('NTN')}: " + s["ntn"]))
    if s.get("strn"):
        lines.append(center(f"{L('STRN')}: " + s["strn"]))
    lines += [sep, center(L("SALES TAX INVOICE") if d["tax"] > 0 else L("SALES RECEIPT")), sep,
              f"{L('Bill No')} : {d['bill_no']}",
              f"{L('Date')} : {d['when']:%d-%m-%Y  %I:%M %p}",
              f"{L('Cashier')} : {d['cashier']}"]
    if d.get("customer"):
        lines.append(f"{L('Customer')} : {d['customer']}")
    lines += [f"{L('Payment')} : {d['payment']}", sep]

    qty_total = 0
    for name, qty, price in d["items"]:
        qty_total += qty
        lines += textwrap.wrap(name, W) or [""]
        lines.append(row(f"  {qty} x {price:.2f}", qty * price))
    lines += [sep, L("Items: {items}     Qty: {qty}", items=len(d["items"]), qty=qty_total), sep,
              row(L("Subtotal"), d["subtotal"])]
    if d["discount"] > 0:
        lines.append(row(L("Discount"), -d["discount"]))
    if d["tax"] > 0:
        lines.append(row(L("Sales Tax ({pct}%)", pct=f"{d['tax_pct']:g}"), d["tax"]))
    lines += [sep, row(L("TOTAL (Rs)"), d["total"]), sep,
              row(L("Amount received"), d["tendered"])]
    if d["change"] > 0:
        lines.append(row(L("Change returned"), d["change"]))
    if d["credit"] >= 0.02:
        lines += [row(L("Credit (this bill)"), d["credit"]),
                  row(L("Total balance"), d["balance"])]
    lines += [sep]
    if s.get("footer"):
        footer = L(s["footer"])   # default message ho to tarjuma ho jata hai
        for part in textwrap.wrap(footer, W):
            lines.append(center(part))
    return "\n".join(lines)


_AMOUNT = re.compile(r"^-?[\d,]+\.\d{2}$")


def _label_set(text):
    return {raw(text, lang=l) for l in ("en", "ru")}


def _html_lines(text):
    """Text receipt ko HTML lines mein badalta hai: dukaan ka naam bara, title dabbe mein, TOTAL mota."""
    lines = text.split("\n")
    seps = [len(l) for l in lines if l.strip() and set(l.strip()) == {"-"}]
    W = seps[0] if seps else 42
    NUM = 11
    titles = _label_set("SALES TAX INVOICE") | _label_set("SALES RECEIPT")
    totals = _label_set("TOTAL (Rs)")
    out, first = [], True
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append('<div class="sp"></div>')
        elif set(stripped) == {"-"}:
            out.append("<hr>")
        elif len(line) == W and _AMOUNT.match(line[-NUM:].strip()) and line[W - NUM - 1:W - NUM] in (" ", ""):
            label = line[:W - NUM].rstrip()
            lead = len(label) - len(label.lstrip())
            cls = "r tot" if label.strip() in totals else "r"
            out.append(f'<div class="{cls}" dir="auto"><span>{"&nbsp;" * lead}{html.escape(label.strip())}</span>'
                       f'<span class="n">{html.escape(line[-NUM:].strip())}</span></div>')
        elif line != line.lstrip() and len(line) == W:
            cls = "c shop" if first else ("c ttl" if stripped in titles else "c")
            out.append(f'<div class="{cls}" dir="auto">{html.escape(stripped)}</div>')
        else:
            out.append(f'<div dir="auto">{html.escape(line.rstrip())}</div>')
        if stripped:
            first = False
    return "\n".join(out)


def logo_data_uri():
    """Settings mein chuna hua logo (PNG/GIF) receipt mein jodne ke liye."""
    p = db.logo_path()
    if not p:
        return None
    mime = "image/gif" if p.lower().endswith(".gif") else "image/png"
    with open(p, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode("ascii")


def receipt_html(text, bill_no, paper="80", autoprint=True, logo_uri=None):
    """Thermal paper ke size ka HTML. Browser se print hota hai (Ctrl+P)."""
    width_mm = 48 if str(paper) == "58" else 72
    barcode = labels.code128_svg(str(bill_no), module_w=2, height=46)
    script = "<script>window.onload=function(){window.print();}</script>" if autoprint else ""
    logo = f'<div class="lg"><img src="{logo_uri}" alt=""></div>' if logo_uri else ""
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Receipt {html.escape(str(bill_no))}</title>
<style>
@page {{ size: {width_mm + 6}mm auto; margin: 2mm; }}
body {{ width: {width_mm}mm; margin: 0 auto; font-family: 'Courier New', 'Segoe UI', Tahoma, monospace;
        font-size: 9.5pt; color: #000; }}
div {{ white-space: pre-wrap; }}
.r {{ display: flex; justify-content: space-between; gap: 4px; }}
.r .n {{ white-space: nowrap; direction: ltr; }}
.c {{ text-align: center; }}
.shop {{ font-size: 14pt; font-weight: bold; letter-spacing: 1px; }}
.ttl {{ font-weight: bold; border: 1.5px solid #000; padding: 2px 0; margin: 3px 0; letter-spacing: 1px; }}
.tot {{ font-size: 12.5pt; font-weight: bold; }}
.lg {{ text-align: center; margin-bottom: 4px; }}
.lg img {{ max-width: 55%; max-height: 18mm; filter: grayscale(1) contrast(1.5); }}
.sp {{ height: 4px; }}
hr {{ border: 0; border-top: 1px dashed #000; margin: 3px 0; }}
.bc {{ text-align: center; margin-top: 6px; }}
.bc svg {{ width: 100%; height: 14mm; }}
.bc div {{ font-size: 8pt; letter-spacing: 2px; }}
</style></head><body>
{logo}{_html_lines(text)}
<div class="bc">{barcode}<div>{html.escape(str(bill_no))}</div></div>
{script}</body></html>"""


def print_html(text, bill_no, paper="80", open_browser=True):
    folder = os.path.join(db.DATA_DIR, "receipts")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"receipt_{bill_no}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(receipt_html(text, bill_no, paper, logo_uri=logo_data_uri()))
    if open_browser:
        webbrowser.open("file:///" + path.replace("\\", "/"))
    return path


def open_cash_drawer(printer_name):
    """Cash drawer kholta hai (ESC/POS command). Windows par pywin32 chahiye:
       python -m pip install pywin32"""
    try:
        import win32print  # type: ignore
    except ImportError:
        raise RuntimeError(raw("For the cash drawer run:  python -m pip install pywin32"))
    handle = win32print.OpenPrinter(printer_name)
    try:
        win32print.StartDocPrinter(handle, 1, ("Cash Drawer", None, "RAW"))
        win32print.StartPagePrinter(handle)
        win32print.WritePrinter(handle, b"\x1b\x70\x00\x19\xfa")
        win32print.EndPagePrinter(handle)
        win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)