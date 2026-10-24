"""Barcode labels (Code 128) bana kar browser mein kholta hai, wahan se print karein."""
import os
import html
import webbrowser

import db

PATTERNS = """212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 221312 231212
112232 122132 122231 113222 123122 123221 223211 221132 221231 213212 223112 312131 311222
321122 321221 312212 322112 322211 212123 212321 232121 111323 131123 131321 112313 132113
132311 211313 231113 231311 112133 112331 132131 113123 113321 133121 313121 211331 231131
213113 213311 213131 311123 311321 331121 312113 312311 332111 314111 221411 431111 111224
111422 121124 121421 141122 141221 112214 112412 122114 122411 142112 142211 241211 221114
413111 241112 134111 111242 121142 121241 114212 124112 124211 411212 421112 421211 212141
214121 412121 111143 111341 131141 114113 114311 411113 411311 113141 114131 311141 411131
211412 211214 211232""".split()
STOP = "2331112"
START_B = 104


def _modules(pattern):
    out, bar = "", True
    for d in pattern:
        out += ("1" if bar else "0") * int(d)
        bar = not bar
    return out


def code128_svg(text, module_w=2, height=45):
    for ch in text:
        if not 32 <= ord(ch) <= 126:
            raise ValueError("Barcode mein sirf English harf/number chal sakte hain")
    values = [ord(ch) - 32 for ch in text]
    checksum = (START_B + sum(i * v for i, v in enumerate(values, 1))) % 103
    codes = [START_B] + values + [checksum]
    mods = "".join(_modules(PATTERNS[c]) for c in codes) + _modules(STOP)
    quiet = 10
    rects, i = [], 0
    while i < len(mods):
        if mods[i] == "1":
            j = i
            while j < len(mods) and mods[j] == "1":
                j += 1
            rects.append(f'<rect x="{(i + quiet) * module_w}" y="0" '
                         f'width="{(j - i) * module_w}" height="{height}"/>')
            i = j
        else:
            i += 1
    width = (len(mods) + 2 * quiet) * module_w
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" fill="black">{"".join(rects)}</svg>')


def ensure_barcode(product):
    """Agar product ka barcode nahi hai to apna internal barcode bana kar save kar deta hai."""
    if product["barcode"]:
        return product["barcode"]
    code = "2" + str(product["id"]).zfill(8)
    conn = db.get_connection()
    conn.execute("UPDATE products SET barcode = ? WHERE id = ?", (code, product["id"]))
    conn.commit()
    conn.close()
    return code


def make_labels(product_ids, copies=1, open_browser=True):
    conn = db.get_connection()
    products = []
    for pid in product_ids:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
        if row:
            products.append(row)
    conn.close()

    cells = []
    for p in products:
        code = ensure_barcode(p)
        svg = code128_svg(code)
        cell = (f'<div class="label"><div class="name">{html.escape(p["name"])}</div>'
                f'{svg}<div class="code">{html.escape(code)}</div>'
                f'<div class="price">Rs {p["sale_price"]:g}</div></div>')
        cells.extend([cell] * copies)

    page = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Barcode Labels</title>
<style>
@page {{ margin: 8mm; }}
body {{ font-family: Arial, sans-serif; margin: 0; }}
.sheet {{ display: flex; flex-wrap: wrap; gap: 3mm; }}
.label {{ width: 50mm; border: 1px dashed #999; padding: 2mm; text-align: center;
          box-sizing: border-box; page-break-inside: avoid; }}
.label svg {{ width: 100%; height: 14mm; }}
.name {{ font-size: 10pt; font-weight: bold; white-space: nowrap; overflow: hidden;
         text-overflow: ellipsis; }}
.code {{ font-size: 8pt; letter-spacing: 1px; }}
.price {{ font-size: 12pt; font-weight: bold; }}
.hint {{ font-size: 11pt; margin: 6px 0 10px; }}
@media print {{ .hint {{ display: none; }} }}
</style></head><body>
<div class="hint">Print karne ke liye Ctrl + P dabayen.</div>
<div class="sheet">{"".join(cells)}</div></body></html>"""

    folder = os.path.join(db.BASE_DIR, "labels")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "labels.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    if open_browser:
        webbrowser.open("file:///" + path.replace("\\", "/"))
    return path