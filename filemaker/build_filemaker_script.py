"""Builds filemaker/gml_kubatur_filemaker.py from app/gml_core.py.

The FileMaker version is the same calculation as the web app, wrapped with
the FileMaker header (output folder) and footer (write the viewer HTML).
Run after every change to app/gml_core.py:   python filemaker/build_filemaker_script.py
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(HERE, "..", "app", "gml_core.py")
OUT = os.path.join(HERE, "gml_kubatur_filemaker.py")

HEADER = '''import xml.etree.ElementTree as ET
import numpy as np
import os, json, re, webbrowser, base64, html
from collections import defaultdict
from scipy.spatial import ConvexHull

# ============================================================================
# FileMaker version - GENERATED from app/gml_core.py by
# filemaker/build_filemaker_script.py. Do not edit here, edit gml_core.py.
# ============================================================================
OUTPUT_FOLDER = r"/opt/FileMaker/FileMaker Server/Data/Documents/tmp_gml"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# FileMaker script that the Web Viewer calls with the extracted Kubatur GML
# (button "Kubatur-GML exportieren"). It receives the GML text as script
# parameter and stores it in the text field GML_file_extracted.
FM_SCRIPT_NAME = "GML_Extrakt_speichern"

# Overwrite the previous viewer right away: if the calculation below stops
# with an error, the Web Viewer shows this message instead of an OLD model.
out_path = os.path.join(OUTPUT_FOLDER, "gebaeude_mit_aequivalenter_kubatur.html")
with open(out_path, 'w', encoding='utf-8') as f:
    f.write('<!DOCTYPE html><html><head><meta charset="UTF-8"></head>'
            '<body style="font-family:Arial;padding:40px;color:#7b241c">'
            '<h2>GML-Berechnung nicht abgeschlossen</h2>'
            '<p>Das Python-Script wurde gestartet, hat aber kein Ergebnis geschrieben. '
            'Wenn diese Seite stehen bleibt, ist es mit einem Fehler abgebrochen - '
            'bitte die Fehlermeldung des MBS-Python-Aufrufs pr&uuml;fen.</p></body></html>')

# ============================================================================
# GML DATA - Insert your CityGML XML here (FileMaker sets GML_text)
# ============================================================================

'''

FOOTER = '''

with open(out_path, 'w', encoding='utf-8') as f: f.write(html_out)
print(f"\\nHTML: {out_path}")
webbrowser.open('file://' + os.path.abspath(out_path))
'''

with open(CORE, encoding="utf-8") as fh:
    core = fh.read()
# drop the core's own import block (the header has the imports)
marker = "# === INPUT ==="
core = core[core.index(marker):]
with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(HEADER + core.rstrip("\n") + "\n" + FOOTER)
print(f"written {OUT}")
