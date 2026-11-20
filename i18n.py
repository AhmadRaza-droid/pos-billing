"""Zubaan (language) ka system: English (default) aur Roman Urdu.

Istemal:
    from i18n import _            # screen par dikhane wala text (translate + format)
    _("Save")                     # -> "Save" / "Save karein"
    _("Bill #{n} saved", n=5)     # placeholders {n} wagaira
    i18n.raw(...)                 # wahi cheez (receipts / files ke liye, lang= de kar kisi bhi zubaan mein)
    i18n.localize(widget)         # widget tree ke saare English text ko mojooda zubaan mein badal deta hai
"""
import tkinter as tk
from tkinter import ttk, messagebox as _tkmsg, simpledialog as _tksimple

try:
    from translations import TABLE
except ImportError:  # translations.py na ho to sirf English
    TABLE = {}

LANGS = [("en", "English"), ("ru", "Roman Urdu")]
_ALIAS = {"ur": "ru", "pa": "ru"}   # purani Urdu / Punjabi settings ab Roman Urdu dekhein gi

_lang = "en"


# ------------------------------------------------------------ state
def normalize(code):
    code = _ALIAS.get(code, code)
    return code if code in dict(LANGS) else "en"


def set_language(code):
    global _lang
    _lang = normalize(code)


def get_language():
    return _lang


def lang_names():
    return [name for _c, name in LANGS]


# ------------------------------------------------------------ translate
def _lookup(text, lang):
    lang = normalize(lang)
    if lang == "en":
        return text
    row = TABLE.get(text)
    if row is None:
        core = text.strip()
        if core and core in TABLE:
            lead = text[: len(text) - len(text.lstrip())]
            trail = text[len(text.rstrip()):]
            return lead + TABLE[core].get(lang, core) + trail
        return text
    return row.get(lang, text)


def raw(text, /, lang=None, **kw):
    """Translate + format. lang=None to mojooda zubaan."""
    s = _lookup(text, lang or _lang)
    if kw:
        try:
            s = s.format(**kw)
        except (KeyError, IndexError, ValueError):
            s = text.format(**kw)
    return s


def _(text, /, **kw):
    """Screen par dikhane wala text."""
    return raw(text, **kw)


# ------------------------------------------------------------ widgets
def localize(widget):
    """Widget aur us ke andar ke saare widgets ka static English text mojooda zubaan mein badalta hai."""
    if _lang == "en" or getattr(widget, "_no_i18n", False):
        return
    try:
        if isinstance(widget, (tk.Tk, tk.Toplevel)):
            t = widget.title()
            if t:
                widget.title(_(t))
        elif isinstance(widget, ttk.Treeview):
            for c in widget["columns"]:
                cur = widget.heading(c, "text")
                if cur:
                    widget.heading(c, text=_(str(cur)))
        elif "text" in widget.keys():
            cur = str(widget.cget("text"))
            if cur:
                new = _(cur)
                if new != cur:
                    widget.configure(text=new)
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        localize(child)


# ------------------------------------------------------------ dialogs (translate)
class messagebox:
    @staticmethod
    def showinfo(title, message, **kw):
        return _tkmsg.showinfo(_(title), _(message), **kw)

    @staticmethod
    def showwarning(title, message, **kw):
        return _tkmsg.showwarning(_(title), _(message), **kw)

    @staticmethod
    def showerror(title, message, **kw):
        return _tkmsg.showerror(_(title), _(message), **kw)

    @staticmethod
    def askyesno(title, message, **kw):
        return _tkmsg.askyesno(_(title), _(message), **kw)


class simpledialog:
    @staticmethod
    def askstring(title, prompt, **kw):
        return _tksimple.askstring(_(title), _(prompt), **kw)

    @staticmethod
    def askinteger(title, prompt, **kw):
        return _tksimple.askinteger(_(title), _(prompt), **kw)

    @staticmethod
    def askfloat(title, prompt, **kw):
        return _tksimple.askfloat(_(title), _(prompt), **kw)