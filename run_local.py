"""
Desktop use (like the original script): pick a GML file, the viewer opens
in the browser and the HTML is saved next to the GML file.

    python run_local.py
"""
import os, sys, webbrowser
import tkinter as tk
from tkinter import filedialog

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.main import run_core, _decode

r = tk.Tk(); r.withdraw()
path = filedialog.askopenfilename(title="GML Datei",
                                  filetypes=[("GML", "*.gml *.xml *.citygml"), ("All", "*.*")])
r.destroy()
if not path:
    sys.exit("No file")
with open(path, "rb") as fh:
    ns, log = run_core(_decode(fh.read()))
print(log)
out = os.path.join(os.path.dirname(path) or os.getcwd(), "gebaeude_mit_aequivalenter_kubatur.html")
with open(out, "w", encoding="utf-8") as fh:
    fh.write(ns["html_out"])
print(f"HTML: {out}")
webbrowser.open("file://" + os.path.abspath(out))
