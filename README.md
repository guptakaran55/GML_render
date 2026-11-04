# GML → äquivalente Kubatur

Web app with two tabs:

* **3D-Kubatur** (`/`): upload one CityGML file, get the interactive 3D viewer (cuboids, roof
  forms, envelope areas, adjacency) plus a check whether the bounding box(es) declared in the
  GML (`gml:Envelope` / `gml:Box`) really contain all building coordinates.
* **Bounding-Box-Prüfung** (`/pruefung`): check several GML files at once, optionally against
  a Kubatur file, without rendering.

## Structure

```
app/gml_core.py    the calculation (your original script, no def-functions)
app/gml_check.py   bounding-box check over several GML files (no rendering)
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

## Bounding-Box-Prüfung (several files)

Upload any number of GML files and, optionally, one Kubatur GML as reference. Nothing is
rendered; the report page checks for every file (the Kubatur file included):

* its own `gml:Envelope` / `gml:Box` against its building coordinates (same rule as above), and
* if a Kubatur file is given: whether every building lies inside the **Kubatur bounding box**,
  i.e. the CityModel envelope of the Kubatur file, or its real coordinate extent if it declares
  none. Buildings are reported as inside / partly outside / outside, with the maximum
  exceedance per axis.
* Files in a different coordinate system (EPSG code) than the Kubatur file get a warning.
* LBB numbers (`we_nr` / `ge_nr`) used by different building IDs across the files are listed.

The 3D viewer's "Datei" panel links to `/pruefung?kub=<token>`, which opens the check tab with
the file just rendered pre-selected as Kubatur (kept on the server for 2 h like the results).

## Teile ausschließen + Kubatur-GML (3D-Kubatur viewer)

* Panel "Teile – Auswahl" in the viewer: one row per Teil with a **−** button. A Teil marked
  with − is hidden in every view (building, Quader, Dachform, labels, reference edge, original
  wireframe) and removed from the legend; **+** takes it back. The NET-Kubatur and the area
  figures are still computed from all Teile.
* "Kubatur-GML herunterladen" writes a CityGML 2.0 file in the browser containing only the
  Teile that are still included, in the original coordinates and SRS:
  * **Quader (LoD1-Solid)**: one `lod1Solid` cuboid per Teil.
  * **Dachform (LoD2-Flächen)**: the reconstructed roof form as planar Roof/Wall/Ground
    surfaces, with `roofType`.
  The Building / BuildingPart structure and the `gml:id`s of the source file are kept, the
  cuboid dimensions are added as generic attributes, and a `gml:Envelope` is written. The file
  can be opened in the viewer again, or used as the Kubatur file in the Bounding-Box-Prüfung.
* GML parts without semantic surfaces (e.g. plain LoD1 solids) are now split into wall / roof /
  ground by their face normals, so such files produce cuboids too.
