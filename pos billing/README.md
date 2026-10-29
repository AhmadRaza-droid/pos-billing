# Superstore POS

Pakistani superstore ke liye desktop POS / billing app (Python + Tkinter + SQLite).

## Features
- Barcode billing, discount, tax, partial payment
- Payment: Cash, Card, Easypaisa, JazzCash, Udhaar
- Returns (stock wapas, udhaar adjust)
- Customer udhaar aur supplier khata
- Purchases / stock in, low-stock aur expiry alerts
- Daily closing, auto-backup, restore
- Products CSV/Excel import (`products_template.csv`)
- Barcode labels

## Chalane ka tareeqa
```
python main.py
```
Pehli dafa chalane par admin ka **random password** screen par dikhaya jata hai.
Usay note karein aur login ke baad badal dein.

Password bhool gaye? `python reset_admin.py` (naya random password) ya
`python reset_admin.py NayaPassword`.

## EXE banana (Windows)
`build.bat` chalayein. Exe `dist\SuperstorePOS.exe` mein banegi.

## Note
`superstore.db` aapka asli data hai, isay git mein commit na karein (`.gitignore` mein hai).
Purane SHA-256 passwords pehle login par khud naye salted PBKDF2 hash mein badal jate hain.
