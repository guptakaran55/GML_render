"""
GML -> äquivalente Kubatur  ·  web app for Render

Upload a CityGML file, the core script (app/gml_core.py) runs on it and the
interactive 3D viewer comes back. The core script itself stays free of
def-functions (FileMaker MBS compatible); this file is only the web wrapper.
"""
import io
import os
import time
import uuid
import traceback
import contextlib
import html as _html

from flask import Flask, request, render_template, send_file, abort, Response

from app import gml_check

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_PATH = os.path.join(BASE_DIR, "gml_core.py")
RESULT_DIR = os.environ.get("RESULT_DIR", "/tmp/gml_results")
RESULT_TTL = 2 * 3600                       # results are kept 2 h, then deleted
MAX_MB = int(os.environ.get("MAX_UPLOAD_MB", "100"))

os.makedirs(RESULT_DIR, exist_ok=True)
with open(CORE_PATH, encoding="utf-8") as _f:
    CORE_CODE = compile(_f.read(), CORE_PATH, "exec")

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "..", "templates"))
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024


def _decode(raw: bytes) -> str:
    """GML files are usually UTF-8, but older exports are ISO-8859-1."""
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _cleanup_old_results():
    now = time.time()
    for name in os.listdir(RESULT_DIR):
        path = os.path.join(RESULT_DIR, name)
        try:
            if now - os.path.getmtime(path) > RESULT_TTL:
                os.remove(path)
        except OSError:
            pass


def run_core(gml_text: str):
    """Run the core script in a fresh namespace; return (namespace, log)."""
    ns = {"__name__": "gml_core", "GML_text": gml_text}
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        exec(CORE_CODE, ns)
    return ns, log.getvalue()


def _toolbar(token: str, filename: str, status: str, check: dict | None = None) -> str:
    """Small 'Datei' section injected into the viewer's control panel."""
    fn = _html.escape(filename)
    multi = ""
    if check:
        ok = check["status"] == "ok"
        multi = f"""
  <div style="margin:8px 0;padding:6px 8px;border-radius:6px;font-size:12px;
              background:{'#e6f4ea' if ok else '#fbeceb'};color:{'#1e8449' if ok else '#b03a2e'}">
    <b>{'✓' if ok else '✗'} BBox-Prüfung über {len(check['files'])} Dateien: {'OK' if ok else 'FEHLER'}</b><br>
    <a href="/report/{token}" target="_blank" style="font-size:12px">Prüfbericht öffnen</a>
  </div>"""
    return f"""
  <div class="sep"></div>
  <div class="hdr">Datei</div>
  <div style="font-size:12px;color:#444;margin-bottom:6px;word-break:break-all">{fn}</div>{multi}
  <div style="display:flex;flex-wrap:wrap;gap:6px">
    <a href="/download/{token}.txt" style="font-size:12px">FileMaker-Ausgabe (.txt)</a>
    <a href="/download/{token}.html" style="font-size:12px">Viewer (.html)</a>
    <a href="/download/{token}.log" style="font-size:12px">Protokoll</a>
    <a href="/" style="font-size:12px;font-weight:bold">Neue Datei</a>
  </div>
"""


@app.get("/")
def index():
    return render_template("index.html", max_mb=MAX_MB, error=None)


@app.get("/healthz")
def healthz():
    return "ok"


@app.post("/process")
def process():
    _cleanup_old_results()
    f = request.files.get("gml")
    if f is None or not f.filename:
        return render_template("index.html", max_mb=MAX_MB, error="Bitte eine GML-Datei auswählen."), 400

    raw = f.read()
    if not raw.strip():
        return render_template("index.html", max_mb=MAX_MB, error="Die Datei ist leer."), 400
    # optional further GML files: only checked against the bounding boxes, not rendered
    extras = [x for x in request.files.getlist("extra") if x and x.filename]

    t0 = time.time()
    gml_text = _decode(raw)
    try:
        ns, log = run_core(gml_text)
    except Exception as exc:                     # show a readable error, keep details in the server log
        traceback.print_exc()
        msg = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else f"{type(exc).__name__}: {exc}"
        return render_template("index.html", max_mb=MAX_MB,
                               error=f"Verarbeitung fehlgeschlagen: {msg}"), 422
    html_out = ns["html_out"]
    lines = ns.get("lego_lines", [])
    bbox = ns.get("bbox_check", {})
    token = uuid.uuid4().hex

    check = None
    if extras:
        check = gml_check.check_files([(f.filename, gml_text)] +
                                      [(x.filename, _decode(x.read())) for x in extras])
        log += "\n".join(gml_check.report_lines(check)) + "\n"
        with open(os.path.join(RESULT_DIR, token + ".report.html"), "w", encoding="utf-8") as fh:
            fh.write(gml_check.report_html(check))
    dt = time.time() - t0

    # inject the 'Datei' section into the right-hand control panel
    marker = '</details></div>\n<div class="ebox">'
    if marker in html_out:
        html_out = html_out.replace(marker, _toolbar(token, f.filename, bbox.get("status", ""), check) + marker, 1)

    with open(os.path.join(RESULT_DIR, token + ".html"), "w", encoding="utf-8") as fh:
        fh.write(html_out)
    with open(os.path.join(RESULT_DIR, token + ".txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(os.path.join(RESULT_DIR, token + ".log"), "w", encoding="utf-8") as fh:
        fh.write(log + f"\n[web] processed in {dt:.1f} s\n")

    print(f"[web] {f.filename}: {len(raw)/1e6:.2f} MB in {dt:.1f} s, bbox={bbox.get('status')}"
          + (f", {len(extras)} weitere Dateien geprüft: {check['status']}" if check else ""), flush=True)
    return Response(html_out, mimetype="text/html")


@app.get("/report/<token>")
def report(token):
    """Multi-file bounding-box report, shown in the browser."""
    if not token.isalnum():
        abort(404)
    path = os.path.join(RESULT_DIR, f"{token}.report.html")
    if not os.path.exists(path):
        abort(410, "Ergebnis ist abgelaufen – bitte die Dateien erneut hochladen.")
    return send_file(path, mimetype="text/html")


@app.get("/download/<name>")
def download(name):
    token, _, ext = name.partition(".")
    if ext not in ("html", "txt", "log") or not token.isalnum():
        abort(404)
    path = os.path.join(RESULT_DIR, f"{token}.{ext}")
    if not os.path.exists(path):
        abort(410, "Ergebnis ist abgelaufen – bitte die Datei erneut hochladen.")
    names = {"html": "gebaeude_mit_aequivalenter_kubatur.html",
             "txt": "filemaker_ausgabe.txt", "log": "protokoll.txt"}
    return send_file(path, as_attachment=True, download_name=names[ext])


@app.errorhandler(413)
def too_large(_e):
    return render_template("index.html", max_mb=MAX_MB,
                           error=f"Die Datei(en) sind zusammen größer als {MAX_MB} MB."), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)
