# GML → äquivalente Kubatur

Web app: upload a CityGML file, get the interactive 3D viewer (cuboids, roof forms,
envelope areas, adjacency) plus a check whether the bounding box(es) declared in the
GML (`gml:Envelope` / `gml:Box`) really contain all building coordinates.

## Structure

```
app/gml_core.py    the calculation (your original script, no def-functions)
app/main.py        Flask web wrapper (upload, downloads)
templates/         upload page
run_local.py       desktop use: file dialog -> HTML opens in browser
render.yaml        Render deployment config
requirements.txt   Python packages
```

`gml_core.py` expects the GML content in the variable `GML_text` and leaves
`html_out`, `lego_lines` and `bbox_check` behind.

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python -m app.main              # web app on http://localhost:5000
python run_local.py             # or: old desktop workflow with file dialog
```

## Bounding-box check

* Every `gml:Envelope` / `gml:Box` belonging to the CityModel or to a Building /
  BuildingPart is checked against the coordinates of exactly those buildings.
* Tolerance 1 cm (or 1e-7° for geographic coordinates). 2D boxes are checked in X/Y only.
* If a box only fits with X and Y swapped, this is reported (axis-order error).
* Viewer: panel bottom-left (green / red / amber = none in file), the box is drawn as a
  dashed wireframe, coordinates outside are red dots (checkbox "GML-Bounding-Box prüfen").
* FileMaker output: `[BBOX] OK|FEHLER|KEINE` and one `[BBOX n]` line per box:
  `OK|FEHLER  points_outside  points_total  max_exceed_X  max_exceed_Y  [max_exceed_Z]  [SWAP_XY]`
