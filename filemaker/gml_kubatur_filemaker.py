import xml.etree.ElementTree as ET
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

# === INPUT ===
# This core script contains NO file dialog and NO def-functions.
# The caller (web app: app/main.py, desktop: run_local.py, or FileMaker)
# must put the GML content into the variable  GML_text  before running it.
# Results left behind in the namespace:
#   html_out    -> complete viewer HTML page (string)
#   lego_lines  -> list of FileMaker output lines
#   bbox_check  -> dict with the GML bounding-box check result
# Optional: FM_SCRIPT_NAME = name of the FileMaker script that receives the
# extracted Kubatur GML when the viewer runs inside a FileMaker Web Viewer
# (FileMaker.PerformScript). Outside FileMaker the GML is downloaded instead.
VIEWER_VERSION = "2026-11-04 · Teile-Auswahl + Kubatur-GML-Export"
try:
    FM_SCRIPT_NAME
except NameError:
    FM_SCRIPT_NAME = "GML_Extrakt_speichern"
try:
    GML_text
except NameError:
    raise RuntimeError("GML_text is not set - the caller must provide the GML content")
if 'GML_text' in GML_text and '"""' in GML_text:
    m=re.search(r'GML_text\s*=\s*"""(.*?)"""',GML_text,re.DOTALL)
    if m: GML_text=m.group(1).strip()

# ===================================================================
# NAMESPACE REPAIR for broken / aggregated GML files
# ===================================================================
_COMMON_NS = {
    'core':'http://www.opengis.net/citygml/2.0',
    'citygml':'http://www.opengis.net/citygml/2.0',
    'bldg':'http://www.opengis.net/citygml/building/2.0',
    'gml':'http://www.opengis.net/gml',
    'gen':'http://www.opengis.net/citygml/generics/2.0',
    'xlink':'http://www.w3.org/1999/xlink',
    'xAL':'urn:oasis:names:tc:ciq:xsdschema:xAL:2.0',
    'xal':'urn:oasis:names:tc:ciq:xsdschema:xAL:2.0',
    'app':'http://www.opengis.net/citygml/appearance/2.0',
    'luse':'http://www.opengis.net/citygml/landuse/2.0',
    'dem':'http://www.opengis.net/citygml/relief/2.0',
    'frn':'http://www.opengis.net/citygml/cityfurniture/2.0',
    'grp':'http://www.opengis.net/citygml/cityobjectgroup/2.0',
    'tran':'http://www.opengis.net/citygml/transportation/2.0',
    'tun':'http://www.opengis.net/citygml/tunnel/2.0',
    'veg':'http://www.opengis.net/citygml/vegetation/2.0',
    'wtr':'http://www.opengis.net/citygml/waterbody/2.0',
    'tex':'http://www.opengis.net/citygml/texturedsurface/2.0',
    'smil20':'http://www.w3.org/2001/SMIL20/',
    'smil20lang':'http://www.w3.org/2001/SMIL20/Language',
    'xsi':'http://www.w3.org/2001/XMLSchema-instance',
    'xs':'http://www.w3.org/2001/XMLSchema',
    'xml':'http://www.w3.org/XML/1998/namespace',
    'wfs':'http://www.opengis.net/wfs',
    'ade':'http://www.3dcitydb.org/3dcitydb-ade/citygml',
    'energy':'http://www.sig3d.org/citygml/2.0/energy/1.0',
    'noise':'http://www.citygml.org/ade/noise_de/2.0',
    'pbase':'http://www.opengis.net/citygml/profiles/base/2.0',
    'ogr':'http://ogr.maptools.org/',
    'schema':'http://schema.opengis.net/citygml',
    'pfx0':'http://www.opengis.net/citygml/2.0',
}

_SURFACE_TYPE_MAP = {
    'wallsurface':'walls','roofsurface':'roofs','groundsurface':'ground',
    'closuresurface':'closure','ceilingsurface':'closure','floorsurface':'ground',
    'outerfloor':'ground','outerceiling':'closure','interiorwall':'walls',
    'outerceilingsurface':'closure','outerfloorsurface':'ground',
}

# roofType code list (SIG3D / AdV, used in German LoD2 data)
_ROOF_NAMES = {
    '1000':'Flachdach', '2100':'Pultdach', '2200':'Versetztes Pultdach',
    '3100':'Satteldach', '3200':'Walmdach', '3300':'Krüppelwalmdach',
    '3400':'Mansardendach', '3500':'Zeltdach', '3600':'Kegeldach',
    '3700':'Kuppeldach', '3800':'Sheddach', '3900':'Bogendach',
    '4000':'Turmdach', '5000':'Mischform', '9999':'Sonstiges',
}

# --- Attempt 1: direct parse ---
root = None
try:
    root = ET.fromstring(GML_text)
except ET.ParseError as e1:
    print(f"[parser] Direct parse failed: {e1}")
    declared = set(re.findall(r'xmlns:(\w+)\s*=', GML_text))
    used_in_tags = set(re.findall(r'</?(\w+):', GML_text))
    used_in_attrs = set(re.findall(r'\s(\w+):\w+\s*=', GML_text))
    all_used = (used_in_tags | used_in_attrs) - {'xmlns','xml'}
    missing = all_used - declared
    if missing:
        print(f"[repair] Injecting missing namespace declarations: {sorted(missing)}")
        injections = []
        for prefix in sorted(missing):
            uri = _COMMON_NS.get(prefix)
            if uri:
                injections.append(f'xmlns:{prefix}="{uri}"')
            else:
                injections.append(f'xmlns:{prefix}="urn:unknown:{prefix}"')
                print(f"  [warn] Unknown prefix '{prefix}' - using placeholder URI")
        inject_str = ' ' + ' '.join(injections)
        match = re.search(r'<(?!\?|!)(\S+)', GML_text)
        if match:
            ip = match.end()
            GML_repaired = GML_text[:ip] + inject_str + GML_text[ip:]
        else:
            GML_repaired = GML_text
        try:
            root = ET.fromstring(GML_repaired)
            print("[parser] Namespace repair succeeded!")
        except ET.ParseError as e2:
            print(f"[parser] Namespace repair failed: {e2}")
    if root is None:
        print("[parser] Attempting prefix-strip fallback...")
        GML_stripped = re.sub(r'\s+xmlns(:\w+)?="[^"]*"', '', GML_text)
        GML_stripped = re.sub(r'<(/?)(\w+):', r'<\1', GML_stripped)
        GML_stripped = re.sub(r'\s(\w+):(\w+)=', r' \2=', GML_stripped)
        try:
            root = ET.fromstring(GML_stripped)
            print("[parser] Prefix-strip fallback succeeded!")
        except ET.ParseError as e3:
            print(f"[parser] ERROR: All parse attempts failed: {e3}")
            raise ValueError(f"Die Datei ist kein lesbares GML/XML: {e3}")

# ===================================================================
# AUTO-DETECT NAMESPACES from parsed tree
# ===================================================================
_uri_set = set()
for _i, _el in enumerate(root.iter()):
    if _i > 3000: break
    _m = re.match(r'\{(.+?)\}', _el.tag)
    if _m: _uri_set.add(_m.group(1))
    for _an in _el.attrib:
        _m2 = re.match(r'\{(.+?)\}', _an)
        if _m2: _uri_set.add(_m2.group(1))

_NS_PATTERNS = {
    'core':['citygml/3.0','citygml/2.0','citygml/1.0','opengis.net/citygml'],
    'bldg':['citygml/building/3.0','citygml/building/2.0','citygml/building/1.0','citygml/building'],
    'gml':['opengis.net/gml/3.2','opengis.net/gml/3.3','opengis.net/gml'],
    'gen':['citygml/generics'],
    'xlink':['w3.org/1999/xlink'],
}
ns_detected = {}
for _pfx, _pats in _NS_PATTERNS.items():
    for _pat in _pats:
        _found = False
        for _uri in _uri_set:
            if _pat in _uri:
                ns_detected[_pfx] = _uri; _found = True; break
        if _found: break

print(f"\n[parser] Detected namespaces:")
for _k, _v in ns_detected.items():
    print(f"         {_k:8s} -> {_v}")

# ===================================================================
# BUILD XLINK INDEX for href resolution
# ===================================================================
_xlink_index = {}
for _el in root.iter():
    for _an, _av in _el.attrib.items():
        _ln = _an.split('}',1)[1] if '}' in _an else _an
        if _ln == 'id':
            _xlink_index[_av] = _el; break

# ===================================================================
# DISCOVER BUILDINGS AND BUILDING PARTS
# ===================================================================
_buildings = [el for el in root.iter() if (el.tag.split('}',1)[1] if '}' in el.tag else el.tag).lower() == 'building']
print(f"[parser] Found {len(_buildings)} <Building> elements")

_units = []
_unit_parent = {}
for _bldg in _buildings:
    _parts = [el for el in _bldg.iter() if (el.tag.split('}',1)[1] if '}' in el.tag else el.tag).lower() == 'buildingpart']
    if _parts:
        for _p in _parts:
            _units.append(_p); _unit_parent[id(_p)] = _bldg
    else:
        _units.append(_bldg)

if not _units:
    _units = [el for el in root.iter() if (el.tag.split('}',1)[1] if '}' in el.tag else el.tag).lower() == 'buildingpart']
if not _units:
    _units = [el for el in root.iter() if (el.tag.split('}',1)[1] if '}' in el.tag else el.tag).lower() in ('building','genericcityobject')]

print(f"[parser] Processing {len(_units)} building units")

# ===================================================================
# ADDRESS EXTRACTION
#   1) xAL 2.0 (CityGML 1.0/2.0): ThoroughfareName / ThoroughfareNumber /
#      PostalCodeNumber / LocalityName inside <Address>
#   2) xAL 3.0 (CityGML 3.0): Thoroughfare/NameElement, Thoroughfare/Number,
#      Locality/NameElement, PostCode/Identifier
#   3) Fallback: generic attributes (gen:stringAttribute name="Strasse" ...)
# ===================================================================
_addresses = []
_addr_scope = _buildings if _buildings else _units
for _ab in _addr_scope:
    for _ael in _ab.iter():
        _alt = (_ael.tag.split('}',1)[1] if '}' in _ael.tag else _ael.tag).lower()
        if _alt != 'address': continue
        _a_street = None; _a_nums = []; _a_plz = None; _a_city = None
        for _x in _ael.iter():
            _xl = (_x.tag.split('}',1)[1] if '}' in _x.tag else _x.tag).lower()
            _tx = _x.text.strip() if _x.text else ''
            if _xl == 'thoroughfarename' and _tx and _a_street is None: _a_street = _tx
            elif _xl == 'thoroughfarenumber' and _tx and _tx not in _a_nums: _a_nums.append(_tx)
            elif _xl == 'postalcodenumber' and _tx and _a_plz is None: _a_plz = _tx
            elif _xl == 'localityname' and _tx and _a_city is None: _a_city = _tx
            elif _xl in ('thoroughfare', 'locality', 'postcode'):
                for _xc in _x:
                    _xcl = (_xc.tag.split('}',1)[1] if '}' in _xc.tag else _xc.tag).lower()
                    _xct = _xc.text.strip() if _xc.text else ''
                    if not _xct: continue
                    if _xl == 'thoroughfare' and _xcl == 'nameelement' and _a_street is None: _a_street = _xct
                    elif _xl == 'thoroughfare' and _xcl == 'number' and _xct not in _a_nums: _a_nums.append(_xct)
                    elif _xl == 'locality' and _xcl == 'nameelement' and _a_city is None: _a_city = _xct
                    elif _xl == 'postcode' and _xcl == 'identifier' and _a_plz is None: _a_plz = _xct
        _a_l1 = ' '.join([_p for _p in [_a_street, '/'.join(_a_nums)] if _p])
        _a_l2 = ' '.join([_p for _p in [_a_plz, _a_city] if _p])
        _a_full = ', '.join([_p for _p in [_a_l1, _a_l2] if _p])
        if _a_full and _a_full not in _addresses: _addresses.append(_a_full)

if not _addresses:
    _g_street = None; _g_num = None; _g_plz = None; _g_city = None
    for _gel in root.iter():
        _gl = (_gel.tag.split('}',1)[1] if '}' in _gel.tag else _gel.tag).lower()
        if 'attribute' not in _gl: continue
        _gname = None
        for _an, _av in _gel.attrib.items():
            if (_an.split('}',1)[1] if '}' in _an else _an).lower() == 'name':
                _gname = _av.lower(); break
        if not _gname: continue
        _gval = None
        for _gc in _gel:
            if (_gc.tag.split('}',1)[1] if '}' in _gc.tag else _gc.tag).lower() == 'value' and _gc.text and _gc.text.strip():
                _gval = _gc.text.strip(); break
        if not _gval: continue
        _is_code = any(_k in _gname for _k in ('schl', 'key', '_id', 'code', 'kennung'))
        if _g_num is None and any(_k in _gname for _k in ('hausnummer', 'hausnr', 'housenumber', 'house_number')):
            _g_num = _gval
        elif _g_street is None and not _is_code and any(_k in _gname for _k in ('strasse', 'straße', 'street')):
            _g_street = _gval
        elif _g_plz is None and any(_k in _gname for _k in ('plz', 'postleitzahl', 'postalcode', 'postcode')):
            _g_plz = _gval
        elif _g_city is None and not _is_code and (_gname in ('ort', 'stadt', 'city', 'gemeinde', 'locality') or 'ortsname' in _gname or 'gemeindename' in _gname):
            _g_city = _gval
    _a_l1 = ' '.join([_p for _p in [_g_street, _g_num] if _p])
    _a_l2 = ' '.join([_p for _p in [_g_plz, _g_city] if _p])
    _a_full = ', '.join([_p for _p in [_a_l1, _a_l2] if _p])
    if _a_full: _addresses.append(_a_full)

if _addresses:
    print(f"[parser] Address(es): {' | '.join(_addresses)}")
else:
    print("[parser] No address found in GML")

# ===================================================================
# TWO-PHASE GEOMETRY COLLECTION
# ===================================================================
building_data = []
bcolors = ['lightcoral','lightskyblue','lightgreen','lightsalmon','plum']

for _idx, _unit in enumerate(_units):
    _h_text = None; _s_text = None; _r_text = None
    for _mel in _unit.iter():
        _mlt = (_mel.tag.split('}',1)[1] if '}' in _mel.tag else _mel.tag).lower()
        if _mlt == 'measuredheight' and _mel.text and _mel.text.strip() and _h_text is None:
            _h_text = _mel.text.strip()
        if _mlt == 'storeysaboveground' and _mel.text and _mel.text.strip() and _s_text is None:
            _s_text = _mel.text.strip()
        if _mlt == 'rooftype' and _mel.text and _mel.text.strip() and _r_text is None:
            _r_text = _mel.text.strip()
    if _r_text is None and id(_unit) in _unit_parent:
        for _mel in _unit_parent[id(_unit)]:
            _mlt = (_mel.tag.split('}',1)[1] if '}' in _mel.tag else _mel.tag).lower()
            if _mlt == 'rooftype' and _mel.text and _mel.text.strip():
                _r_text = _mel.text.strip(); break
    if _h_text is None:
        for _mel in _unit.iter():
            _mlt = (_mel.tag.split('}',1)[1] if '}' in _mel.tag else _mel.tag).lower()
            if _mlt == 'height' and _mel.text and _mel.text.strip():
                _h_text = _mel.text.strip(); break

    meta = {
        'storeys': int(float(_s_text)) if _s_text else 3,
        'height': float(_h_text) if _h_text else 10.0,
        'roof_type': _r_text   # None = not defined in GML
    }

    _surfs = defaultdict(list)
    _claimed_ids = set()

    # ---- PHASE 1: boundedBy ----
    _bby_els = []
    for _child in _unit:
        _clt = (_child.tag.split('}',1)[1] if '}' in _child.tag else _child.tag).lower()
        if _clt == 'boundedby':
            _bby_els.append(_child)

    for _bby in _bby_els:
        _stack = [(_bby, 'other')]
        _visited = set()
        while _stack:
            _cur_el, _cur_stype = _stack.pop()
            _cur_id = id(_cur_el)
            if _cur_id in _visited: continue
            _visited.add(_cur_id)
            _cur_lt = (_cur_el.tag.split('}',1)[1] if '}' in _cur_el.tag else _cur_el.tag).lower()

            for _spat, _skey in _SURFACE_TYPE_MAP.items():
                if _spat in _cur_lt:
                    _cur_stype = _skey; break

            if _cur_lt == 'poslist':
                if _cur_el.text and _cur_el.text.strip():
                    _nums = list(map(float, _cur_el.text.split()))
                    if len(_nums) >= 9:
                        _dim = 3 if len(_nums) % 3 == 0 else 2
                        _arr = np.array(_nums).reshape(-1, _dim)
                        if _dim == 2: _arr = np.column_stack([_arr, np.zeros(len(_arr))])
                        _surfs[_cur_stype].append(_arr)
                continue

            if _cur_lt == 'coordinates':
                if _cur_el.text and _cur_el.text.strip():
                    _rows = []
                    for _tok in re.split(r'\s+', _cur_el.text.strip()):
                        if _tok: _rows.append([float(_p) for _p in _tok.split(',')])
                    if len(_rows) >= 3:
                        for _r in _rows:
                            while len(_r) < 3: _r.append(0.0)
                        _surfs[_cur_stype].append(np.array(_rows)[:,:3])
                continue

            if _cur_lt == 'linearring':
                _pos_kids = [c for c in _cur_el if (c.tag.split('}',1)[1] if '}' in c.tag else c.tag).lower() == 'pos']
                if _pos_kids:
                    _pts = []
                    for _pc in _pos_kids:
                        if _pc.text and _pc.text.strip():
                            _pnums = list(map(float, _pc.text.split()))
                            if len(_pnums) >= 2:
                                while len(_pnums) < 3: _pnums.append(0.0)
                                _pts.append(_pnums[:3])
                    if len(_pts) >= 3:
                        _surfs[_cur_stype].append(np.array(_pts))
                        continue

            _href = None
            for _an, _av in _cur_el.attrib.items():
                if 'href' in _an:
                    _href = _av; break
            if _href and _href.startswith('#'):
                _ref_id = _href[1:]
                _claimed_ids.add(_ref_id)
                _ref_el = _xlink_index.get(_ref_id)
                if _ref_el is not None:
                    _stack.append((_ref_el, _cur_stype))
                    continue

            if _cur_lt == 'polygon':
                for _an, _av in _cur_el.attrib.items():
                    _ln2 = _an.split('}',1)[1] if '}' in _an else _an
                    if _ln2 == 'id': _claimed_ids.add(_av); break

            for _child in reversed(list(_cur_el)):
                _stack.append((_child, _cur_stype))

    # ---- PHASE 2: solid / multiSurface ----
    _solid_els = []
    for _child in _unit:
        _clt = (_child.tag.split('}',1)[1] if '}' in _child.tag else _child.tag).lower()
        if 'solid' in _clt or ('multisurface' in _clt and 'boundedby' not in _clt):
            _solid_els.append(_child)

    for _sol in _solid_els:
        _stack = [(_sol, 'other')]
        _visited = set()
        while _stack:
            _cur_el, _cur_stype = _stack.pop()
            _cur_id = id(_cur_el)
            if _cur_id in _visited: continue
            _visited.add(_cur_id)
            _cur_lt = (_cur_el.tag.split('}',1)[1] if '}' in _cur_el.tag else _cur_el.tag).lower()

            if _cur_lt == 'polygon':
                _poly_gid = None
                for _an, _av in _cur_el.attrib.items():
                    _ln2 = _an.split('}',1)[1] if '}' in _an else _an
                    if _ln2 == 'id': _poly_gid = _av; break
                if _poly_gid and _poly_gid in _claimed_ids:
                    continue

            if _cur_lt == 'poslist':
                if _cur_el.text and _cur_el.text.strip():
                    _nums = list(map(float, _cur_el.text.split()))
                    if len(_nums) >= 9:
                        _dim = 3 if len(_nums) % 3 == 0 else 2
                        _arr = np.array(_nums).reshape(-1, _dim)
                        if _dim == 2: _arr = np.column_stack([_arr, np.zeros(len(_arr))])
                        _surfs[_cur_stype].append(_arr)
                continue

            if _cur_lt == 'coordinates':
                if _cur_el.text and _cur_el.text.strip():
                    _rows = []
                    for _tok in re.split(r'\s+', _cur_el.text.strip()):
                        if _tok: _rows.append([float(_p) for _p in _tok.split(',')])
                    if len(_rows) >= 3:
                        for _r in _rows:
                            while len(_r) < 3: _r.append(0.0)
                        _surfs[_cur_stype].append(np.array(_rows)[:,:3])
                continue

            if _cur_lt == 'linearring':
                _pos_kids = [c for c in _cur_el if (c.tag.split('}',1)[1] if '}' in c.tag else c.tag).lower() == 'pos']
                if _pos_kids:
                    _pts = []
                    for _pc in _pos_kids:
                        if _pc.text and _pc.text.strip():
                            _pnums = list(map(float, _pc.text.split()))
                            if len(_pnums) >= 2:
                                while len(_pnums) < 3: _pnums.append(0.0)
                                _pts.append(_pnums[:3])
                    if len(_pts) >= 3:
                        _surfs[_cur_stype].append(np.array(_pts))
                        continue

            for _child in reversed(list(_cur_el)):
                _stack.append((_child, _cur_stype))

    surfs = {
        'walls': _surfs.get('walls', []),
        'roofs': _surfs.get('roofs', []),
        'ground': _surfs.get('ground', []),
        'closure': _surfs.get('closure', []),
    }
    if _surfs.get('other'):
        if surfs['roofs'] or surfs['ground']:
            surfs['walls'].extend(_surfs['other'])
        else:
            # no semantic surfaces at all (e.g. a plain LoD1 solid): classify by
            # the face normal - horizontal at the lowest level = ground, other
            # horizontal / sloped = roof, (near) vertical = wall
            _oz = min(float(np.asarray(_o)[:, 2].min()) for _o in _surfs['other'])
            for _o in _surfs['other']:
                _oa = np.asarray(_o, dtype=float); _onw = np.zeros(3)
                for _q in range(len(_oa)): _onw += np.cross(_oa[_q], _oa[(_q+1) % len(_oa)])
                _onl = float(np.linalg.norm(_onw))
                _onz = abs(_onw[2]) / _onl if _onl > 1e-12 else 0.0
                if _onz < 0.3: surfs['walls'].append(_o)
                elif _onz > 0.95 and float(_oa[:, 2].max()) < _oz + 0.05: surfs['ground'].append(_o)
                else: surfs['roofs'].append(_o)

    ac = []
    for sl in surfs.values(): ac.extend(sl)
    bbox = None
    if ac:
        st = np.vstack(ac); mn, mx = st.min(0), st.max(0)
        bbox = {'min': mn, 'max': mx, 'dimensions': mx - mn}

    _n_polys = sum(len(v) for v in surfs.values())
    print(f"  Unit {_idx+1}: {_n_polys} polygons "
          f"(W:{len(surfs['walls'])} R:{len(surfs['roofs'])} "
          f"G:{len(surfs['ground'])} C:{len(surfs['closure'])})")

    building_data.append({'idx':_idx+1, 'surfaces':surfs, 'bbox':bbox, 'metadata':meta})

# ===================================================================
# OFFSET TO LOCAL ORIGIN
# ===================================================================
ag = []
for bd in building_data:
    for sl in bd['surfaces'].values():
        for s in sl: ag.extend(s)
if not ag:
    print("[main] No geometry found.")
    raise ValueError("Im GML wurde keine Gebäudegeometrie gefunden.")

# ===================================================================
# GML BOUNDING-BOX CHECK  (done on the RAW coordinates, before offset)
#
# Every <gml:Envelope> (GML 3: lowerCorner/upperCorner or two <pos>) and
# every <gml:Box> (GML 2: <coordinates>) found in the file is checked:
# does it really contain all building coordinates it is responsible for?
#   scope = the element that owns the envelope (CityModel -> all buildings,
#           Building / BuildingPart -> only that building's coordinates)
# A 2D envelope is checked in X/Y only. If an envelope fails but would pass
# with X and Y swapped, this is reported (typical axis-order mistake).
# ===================================================================
print("\n" + "="*60)
print("GML BOUNDING-BOX CHECK")
print("="*60)
_raw_unit_pts = []                       # building_data[i] <-> _units[i]
for bd in building_data:
    _rp = []
    for sl in bd['surfaces'].values():
        for s in sl: _rp.append(np.asarray(s, dtype=float)[:, :3])
    _raw_unit_pts.append(np.vstack(_rp) if _rp else np.zeros((0, 3)))
_raw_all = np.vstack([p for p in _raw_unit_pts if len(p)])
_raw_min = _raw_all.min(0); _raw_max = _raw_all.max(0)
_geo_deg = bool(np.all(np.abs(_raw_all[:, :2]) <= 360.0))   # lat/lon in degrees?
_bb_tol = 1e-7 if _geo_deg else 0.01                       # 1 cm (metric) tolerance

_parent_of = {}
for _pe in root.iter():
    for _ce in _pe: _parent_of[id(_ce)] = _pe
_unit_ids = {}
for _ui, _ue in enumerate(_units): _unit_ids[id(_ue)] = _ui

bbox_check = {'status': 'none', 'envelopes': [], 'tol': _bb_tol, 'degrees': _geo_deg,
              'actual_min': _raw_min.tolist(), 'actual_max': _raw_max.tolist()}
_env_seen = 0
for _env in root.iter():
    _elt = (_env.tag.split('}',1)[1] if '}' in _env.tag else _env.tag).lower()
    if _elt not in ('envelope', 'box'): continue
    _env_seen += 1
    _lo = None; _hi = None; _srs = None
    for _an, _av in _env.attrib.items():
        if (_an.split('}',1)[1] if '}' in _an else _an).lower() == 'srsname': _srs = _av
    _poss = []
    for _ec in _env:
        _ecl = (_ec.tag.split('}',1)[1] if '}' in _ec.tag else _ec.tag).lower()
        _ect = _ec.text.strip() if _ec.text else ''
        if not _ect: continue
        try:
            if _ecl == 'lowercorner': _lo = [float(v) for v in _ect.split()]
            elif _ecl == 'uppercorner': _hi = [float(v) for v in _ect.split()]
            elif _ecl == 'pos': _poss.append([float(v) for v in _ect.split()])
            elif _ecl == 'coordinates':
                for _tok in _ect.split():
                    _poss.append([float(v) for v in _tok.split(',')])
        except ValueError:
            pass
    if (_lo is None or _hi is None) and len(_poss) >= 2:
        _lo = _poss[0]; _hi = _poss[1]
    if _lo is None or _hi is None or len(_lo) < 2 or len(_hi) < 2: continue
    _dimb = min(len(_lo), len(_hi), 3)
    _lo = np.array(_lo[:_dimb]); _hi = np.array(_hi[:_dimb])
    _lo, _hi = np.minimum(_lo, _hi), np.maximum(_lo, _hi)

    # --- scope: which building units does this envelope describe? ---
    _bby = _parent_of.get(id(_env))
    _owner = _parent_of.get(id(_bby)) if _bby is not None else None
    if _owner is None: _owner = root
    _own_lt = (_owner.tag.split('}',1)[1] if '}' in _owner.tag else _owner.tag)
    _scope_units = []
    for _oe in _owner.iter():
        if id(_oe) in _unit_ids: _scope_units.append(_unit_ids[id(_oe)])
    if not _scope_units: continue          # envelope of a non-building object
    _scope_pts = np.vstack([_raw_unit_pts[u] for u in _scope_units if len(_raw_unit_pts[u])])
    _own_id = None
    for _an, _av in _owner.attrib.items():
        if (_an.split('}',1)[1] if '}' in _an else _an) == 'id': _own_id = _av
    if _owner is root:
        _scope_lbl = f"{_own_lt} (gesamte Datei)"
    else:
        _scope_lbl = f"{_own_lt} {_own_id or ''}".strip()
    _teile = sorted(set(u + 1 for u in _scope_units))

    _P = _scope_pts[:, :_dimb]
    _below = _lo[None, :] - _P             # > 0 : point is below the lower corner
    _above = _P - _hi[None, :]             # > 0 : point is above the upper corner
    _exc = np.maximum(np.maximum(_below, _above), 0.0)
    _out_mask = np.any(_exc > _bb_tol, axis=1)
    _n_out = int(_out_mask.sum())
    _max_exc = _exc.max(0).tolist()
    _swap_ok = False
    if _n_out and _dimb >= 2:
        _Ps = _P.copy(); _Ps[:, [0, 1]] = _Ps[:, [1, 0]]
        _swap_ok = bool(np.all(_Ps >= _lo[None, :] - _bb_tol) and np.all(_Ps <= _hi[None, :] + _bb_tol))
    _pm = _scope_pts.min(0)[:_dimb]; _pM = _scope_pts.max(0)[:_dimb]
    _slack_lo = (_pm - _lo).tolist(); _slack_hi = (_hi - _pM).tolist()
    _ok = (_n_out == 0)
    bbox_check['envelopes'].append({
        'scope': _scope_lbl, 'teile': _teile, 'srs': _srs, 'dim': int(_dimb),
        'lower': _lo.tolist(), 'upper': _hi.tolist(),
        'n_pts': int(len(_P)), 'n_out': _n_out, 'ok': _ok,
        'max_exceed': _max_exc, 'axis_swapped': _swap_ok,
        'slack_lower': _slack_lo, 'slack_upper': _slack_hi,
        'out_pts': _scope_pts[_out_mask][:2000].tolist()})
    _axn = 'XYZ'
    _exs = ' '.join(f"{_axn[a]}+{_max_exc[a]:.3f}" for a in range(_dimb))
    print(f"  [{'OK' if _ok else 'FEHLER'}] {_scope_lbl}  ({_dimb}D, Teile {_teile})  "
          f"{_n_out}/{len(_P)} Punkte außerhalb  max. Überschreitung: {_exs}"
          + ("  -> passt mit vertauschten X/Y-Achsen!" if _swap_ok else ""))

if bbox_check['envelopes']:
    bbox_check['status'] = 'ok' if all(e['ok'] for e in bbox_check['envelopes']) else 'fail'
print(f"  Envelopes in file: {_env_seen}, checked: {len(bbox_check['envelopes'])}  -> {bbox_check['status'].upper()}")
print(f"  Actual coordinate extent: min {np.round(_raw_min, 3).tolist()}  max {np.round(_raw_max, 3).tolist()}")

offset = np.array(ag).min(axis=0)
for bd in building_data:
    for k in bd['surfaces']: bd['surfaces'][k] = [s - offset for s in bd['surfaces'][k]]
    if bd['bbox']:
        bd['bbox']['min'] -= offset; bd['bbox']['max'] -= offset
        bd['bbox']['dimensions'] = bd['bbox']['max'] - bd['bbox']['min']

# ===================================================================
# REAL-GEOMETRY ENVELOPE  (true GML polygons — no convex hulls)
#
#  1) every polygon is triangulated (ear clipping, works for concave rings)
#     and its normal is turned OUTWARD (vertical-ray inside test on its part)
#  2) each triangle is sampled on a ~0.5 m grid; every sample is one of:
#       shared  : lies on a polygon of ANOTHER part (coplanar within 3 cm,
#                 facing the opposite way)  -> common wall / slab
#       internal: lies inside another part's solid (overlapping parts)
#       exposed : everything else            -> real thermal envelope
#  3) exposed area is split into Fassade / Dach / Boden (semantic surface
#     type from the GML; walls without semantics by their normal)
#  4) shared + internal area is accumulated PER PAIR of parts -> this is the
#     original adjacency used later to keep the reconstruction connected.
#
#   south = -Y (compass: North = +Y, East = +X)
# ===================================================================
print("\n" + "="*60)
print("ENERGY ENVELOPE (real GML polygons)")
print("="*60)

_cell = 0.35                # target sample-patch edge length in metres
_ctol = 0.03                # coplanar contact tolerance (3 cm)
_poff = 0.02                # probe offset for the "inside another part" test

# ---------- 1) triangulate + outward normals ----------
_polys = []                 # one dict per polygon
for bd in building_data:
    for _kind, _sl in bd['surfaces'].items():
        for _sf in _sl:
            _P = np.asarray(_sf, dtype=float)
            _kp = [0]
            for _q in range(1, len(_P)):
                if np.linalg.norm(_P[_q] - _P[_kp[-1]]) > 1e-4: _kp.append(_q)
            _P = _P[_kp]
            if len(_P) > 1 and np.linalg.norm(_P[0] - _P[-1]) <= 1e-4: _P = _P[:-1]
            if len(_P) < 3: continue
            _nw = np.zeros(3)
            for _q in range(len(_P)): _nw += np.cross(_P[_q], _P[(_q+1) % len(_P)])
            _na = float(np.linalg.norm(_nw))
            if _na < 1e-8: continue
            _nu = _nw / _na
            _ax = int(np.argmax(np.abs(_nu)))
            _ij = [0, 1, 2]; _ij.remove(_ax)
            _Q = _P[:, _ij]
            _sa2 = 0.5 * float(np.sum(_Q[:, 0]*np.roll(_Q[:, 1], -1) - np.roll(_Q[:, 0], -1)*_Q[:, 1]))
            _idx = list(range(len(_P))) if _sa2 > 0 else list(range(len(_P)))[::-1]
            _tris = []
            _guard = 0
            while len(_idx) > 3 and _guard < 4*len(_P) + 10:
                _guard += 1; _found = False
                for _k in range(len(_idx)):
                    _i0 = _idx[_k-1]; _i1 = _idx[_k]; _i2 = _idx[(_k+1) % len(_idx)]
                    _a = _Q[_i0]; _b = _Q[_i1]; _c = _Q[_i2]
                    _cr = (_b[0]-_a[0])*(_c[1]-_b[1]) - (_b[1]-_a[1])*(_c[0]-_b[0])
                    if abs(_cr) < 1e-10:
                        _idx.pop(_k); _found = True; break          # collinear vertex
                    if _cr < 0: continue                             # reflex vertex
                    _ok = True
                    for _o in _idx:
                        if _o == _i0 or _o == _i1 or _o == _i2: continue
                        _p = _Q[_o]
                        if ((_b[0]-_a[0])*(_p[1]-_a[1]) - (_b[1]-_a[1])*(_p[0]-_a[0]) >= 0 and
                            (_c[0]-_b[0])*(_p[1]-_b[1]) - (_c[1]-_b[1])*(_p[0]-_b[0]) >= 0 and
                            (_a[0]-_c[0])*(_p[1]-_c[1]) - (_a[1]-_c[1])*(_p[0]-_c[0]) >= 0):
                            _ok = False; break
                    if _ok:
                        _tris.append((_i0, _i1, _i2)); _idx.pop(_k); _found = True; break
                if not _found: break
            if len(_idx) == 3:
                _tris.append((_idx[0], _idx[1], _idx[2]))
            elif len(_idx) > 3:
                for _k in range(1, len(_idx) - 1): _tris.append((_idx[0], _idx[_k], _idx[_k+1]))
            if not _tris: continue
            _polys.append({'part': bd['idx'], 'kind': _kind, 'pts': _P, 'n': _nu, 'area': 0.5*_na,
                           'tris': _tris, 'ij': _ij, 'q2': _Q, 'p0': _P[0].copy(),
                           'bmin': _P.min(0), 'bmax': _P.max(0)})

# per-part triangle arrays (for the vertical-ray inside test) + part bboxes
_ptri = {}
for _pl in _polys:
    _t = _ptri.setdefault(_pl['part'], [[], [], []])
    for _tr in _pl['tris']:
        _t[0].append(_pl['pts'][_tr[0]]); _t[1].append(_pl['pts'][_tr[1]]); _t[2].append(_pl['pts'][_tr[2]])
for _k in list(_ptri.keys()):
    _ptri[_k] = (np.array(_ptri[_k][0]), np.array(_ptri[_k][1]), np.array(_ptri[_k][2]))
_pbb = {}
for _pl in _polys:
    if _pl['part'] in _pbb:
        _pbb[_pl['part']] = (np.minimum(_pbb[_pl['part']][0], _pl['bmin']), np.maximum(_pbb[_pl['part']][1], _pl['bmax']))
    else:
        _pbb[_pl['part']] = (_pl['bmin'].copy(), _pl['bmax'].copy())

# outward normals: probe just in front of each polygon; inside own part -> flip
for _pidx in _ptri:
    _mine = []
    for _pl in _polys:
        if _pl['part'] == _pidx: _mine.append(_pl)
    _PP = []
    for _pl in _mine:
        _tr = _pl['tris'][0]
        _cen = (_pl['pts'][_tr[0]] + _pl['pts'][_tr[1]] + _pl['pts'][_tr[2]]) / 3.0
        _PP.append(_cen + _pl['n']*0.05 + np.array([1.3e-4, 0.7e-4, 0.0]))
    _PP = np.array(_PP)
    _TA, _TB, _TC = _ptri[_pidx]
    _cnt = np.zeros(len(_PP), dtype=int)
    for _m in range(len(_TA)):
        _a = _TA[_m]; _v0 = _TB[_m] - _a; _v1 = _TC[_m] - _a
        _det = _v0[0]*_v1[1] - _v0[1]*_v1[0]
        if abs(_det) < 1e-9: continue
        _wx = _PP[:, 0] - _a[0]; _wy = _PP[:, 1] - _a[1]
        _s = (_wx*_v1[1] - _wy*_v1[0]) / _det; _t = (_v0[0]*_wy - _v0[1]*_wx) / _det
        _hit = (_s >= 0) & (_t >= 0) & (_s + _t <= 1)
        _cnt += (_hit & ((_a[2] + _s*_v0[2] + _t*_v1[2]) > _PP[:, 2])).astype(int)
    for _q in range(len(_mine)):
        if _cnt[_q] % 2 == 1: _mine[_q]['n'] = -_mine[_q]['n']

# ---------- 2) sample, classify, accumulate ----------
_total_gross = 0.0; _total_exposed = 0.0; _exposed_air = 0.0
_exp_facade = 0.0; _exp_roof = 0.0; _exp_ground = 0.0
_south_exposed = 0.0; _shared_once = 0.0
_pair_area = {}             # (i, j) with i < j  ->  m² of common / internal surface
_penv = {}                  # part -> [exposed, Fassade, Dach, Boden]
_flaechen_lines = []
_fas_vx=[]; _fas_vy=[]; _fas_vz=[]; _fas_i=[]; _fas_j=[]; _fas_k=[]
_dch_vx=[]; _dch_vy=[]; _dch_vz=[]; _dch_i=[]; _dch_j=[]; _dch_k=[]
_shr_vx=[]; _shr_vy=[]; _shr_vz=[]; _shr_i=[]; _shr_j=[]; _shr_k=[]
_sth_vx=[]; _sth_vy=[]; _sth_vz=[]; _sth_i=[]; _sth_j=[]; _sth_k=[]
_all_bb_min = np.min([v[0] for v in _pbb.values()], axis=0) if _pbb else np.zeros(3)
_all_bb_max = np.max([v[1] for v in _pbb.values()], axis=0) if _pbb else np.ones(3)
_ov_gap = max(0.05, 0.004*float(np.linalg.norm(_all_bb_max - _all_bb_min)))

for _pl in _polys:
    _pa = _pl['part']; _nrm = _pl['n']
    _e = _penv.setdefault(_pa, [0.0, 0.0, 0.0, 0.0])
    # class of this polygon
    if _pl['kind'] == 'roofs':    _cls = 'D'
    elif _pl['kind'] == 'ground': _cls = 'B'
    elif abs(_nrm[2]) < 0.5:      _cls = 'F'
    elif _nrm[2] >= 0.5:          _cls = 'D'
    else:                         _cls = 'B'
    _total_gross += _pl['area']
    for _tr in _pl['tris']:
        _A0 = _pl['pts'][_tr[0]]; _B0 = _pl['pts'][_tr[1]]; _C0 = _pl['pts'][_tr[2]]
        _area = 0.5 * float(np.linalg.norm(np.cross(_B0 - _A0, _C0 - _A0)))
        if _area < 1e-9: continue
        _emax = max(float(np.linalg.norm(_B0-_A0)), float(np.linalg.norm(_C0-_A0)), float(np.linalg.norm(_C0-_B0)))
        _m = max(1, min(45, int(np.ceil(_emax / _cell))))
        _ss = (np.arange(_m) + 0.5) / _m
        _S, _T = np.meshgrid(_ss, _ss); _S = _S.ravel(); _T = _T.ravel()
        _keep = (_S + _T) <= 1.0
        _S = _S[_keep]; _T = _T[_keep]
        if len(_S) == 0: _S = np.array([1/3.]); _T = np.array([1/3.])
        _patch = _area / len(_S)
        _Pf = _A0[None, :] + np.outer(_S, (_B0 - _A0)) + np.outer(_T, (_C0 - _A0))
        _tbmin = np.minimum(np.minimum(_A0, _B0), _C0) - 0.1
        _tbmax = np.maximum(np.maximum(_A0, _B0), _C0) + 0.1
        _contact = np.zeros(len(_Pf), dtype=bool)
        _owned = np.zeros(len(_Pf), dtype=bool)        # counted for a pair on THIS side
        _cand = []
        for _pb in _pbb:
            if _pb == _pa: continue
            if np.all(_pbb[_pb][0] <= _tbmax) and np.all(_pbb[_pb][1] >= _tbmin): _cand.append(_pb)
        # (a) coplanar contact with another part's polygon (opposite facing)
        for _pb in _cand:
            _cB = np.zeros(len(_Pf), dtype=bool)
            for _ql in _polys:
                if _ql['part'] != _pb: continue
                if float(_ql['n'] @ _nrm) > -0.5: continue
                if np.any(_ql['bmin'] > _tbmax) or np.any(_ql['bmax'] < _tbmin): continue
                _dpl = np.abs((_Pf - _ql['p0']) @ _ql['n'])
                _near = _dpl < _ctol
                if not _near.any(): continue
                _P2 = _Pf[:, _ql['ij']]; _qq = _ql['q2']
                _inq = np.zeros(len(_Pf), dtype=bool)
                for _eg in range(len(_qq)):
                    _x1 = _qq[_eg, 0]; _y1 = _qq[_eg, 1]
                    _x2 = _qq[(_eg+1) % len(_qq), 0]; _y2 = _qq[(_eg+1) % len(_qq), 1]
                    if _y1 == _y2: continue
                    _cond = (_y1 > _P2[:, 1]) != (_y2 > _P2[:, 1])
                    _xi = _x1 + (_P2[:, 1] - _y1) * (_x2 - _x1) / (_y2 - _y1)
                    _inq ^= _cond & (_P2[:, 0] < _xi)
                _cB |= _near & _inq
            if _cB.any():
                _contact |= _cB
                _key = (min(_pa, _pb), max(_pa, _pb))
                _pair_area[_key] = _pair_area.get(_key, 0.0) + 0.5 * float(_cB.sum()) * _patch
                if _pa < _pb: _owned |= _cB
        # (b) inside another part's solid (overlapping parts)
        _buried = np.zeros(len(_Pf), dtype=bool)
        _PP = _Pf + _nrm[None, :]*_poff + np.array([1.3e-4, 0.7e-4, 0.0])
        for _pb in _cand:
            _TA, _TB, _TC = _ptri[_pb]
            _cnt = np.zeros(len(_PP), dtype=int)
            for _mm in range(len(_TA)):
                _a = _TA[_mm]; _v0 = _TB[_mm] - _a; _v1 = _TC[_mm] - _a
                _det = _v0[0]*_v1[1] - _v0[1]*_v1[0]
                if abs(_det) < 1e-9: continue
                _wx = _PP[:, 0] - _a[0]; _wy = _PP[:, 1] - _a[1]
                _s = (_wx*_v1[1] - _wy*_v1[0]) / _det; _t = (_v0[0]*_wy - _v0[1]*_wx) / _det
                _hit = (_s >= 0) & (_t >= 0) & (_s + _t <= 1)
                _cnt += (_hit & ((_a[2] + _s*_v0[2] + _t*_v1[2]) > _PP[:, 2])).astype(int)
            _bB = ((_cnt % 2) == 1) & ~_contact & ~_buried
            if _bB.any():
                _buried |= _bB
                _key = (min(_pa, _pb), max(_pa, _pb))
                _pair_area[_key] = _pair_area.get(_key, 0.0) + float(_bB.sum()) * _patch
                _owned |= _bB
        _em = ~_contact & ~_buried
        _exp_area = float(_em.sum()) * _patch
        _total_exposed += _exp_area; _e[0] += _exp_area
        if _cls == 'F':
            _exp_facade += _exp_area; _e[1] += _exp_area; _exposed_air += _exp_area
            _south_exposed += _exp_area * max(0.0, -float(_nrm[1]))
        elif _cls == 'D':
            _exp_roof += _exp_area; _e[2] += _exp_area; _exposed_air += _exp_area
        else:
            _exp_ground += _exp_area; _e[3] += _exp_area
        # --- overlays (same light run-merged parallelograms as before) ---
        _zero_msk = np.zeros(len(_em), dtype=bool)
        _fas_msk = _em if _cls == 'F' else _zero_msk
        _dch_msk = _em if _cls == 'D' else _zero_msk
        _sth_msk = _em if (_cls == 'F' and (-_nrm[1]) > 1e-6) else _zero_msk
        _hc = 0.5 / _m
        _eu = _B0 - _A0; _ev = _C0 - _A0
        _col = np.rint(_S*_m - 0.5).astype(int)
        _row = np.rint(_T*_m - 0.5).astype(int)
        for _msk, _gm, _VX,_VY,_VZ,_TI,_TJ,_TK in (
            (_fas_msk, 1.0, _fas_vx,_fas_vy,_fas_vz,_fas_i,_fas_j,_fas_k),
            (_dch_msk, 1.0, _dch_vx,_dch_vy,_dch_vz,_dch_i,_dch_j,_dch_k),
            (_owned,   1.0, _shr_vx,_shr_vy,_shr_vz,_shr_i,_shr_j,_shr_k),
            (_sth_msk, 2.0, _sth_vx,_sth_vy,_sth_vz,_sth_i,_sth_j,_sth_k)):
            if not _msk.any(): continue
            if _msk.all():                     # whole triangle in this class -> draw it as ONE triangle
                _bo = _nrm*_ov_gap*_gm; _i0 = len(_VX)
                for _vq in (_A0 + _bo, _B0 + _bo, _C0 + _bo):
                    _VX.append(float(_vq[0])); _VY.append(float(_vq[1])); _VZ.append(float(_vq[2]))
                _TI.append(_i0); _TJ.append(_i0 + 1); _TK.append(_i0 + 2)
                continue
            _Sk = _S[_msk]; _Tk = _T[_msk]; _ck = _col[_msk]; _rk = _row[_msk]
            _new = np.ones(len(_Sk), dtype=bool)
            _new[1:] = (_rk[1:] != _rk[:-1]) | (_ck[1:] != _ck[:-1] + 1)
            _rs = np.flatnonzero(_new)
            _re = np.append(_rs[1:], len(_Sk)) - 1
            _s0 = _Sk[_rs] - _hc; _s1 = _Sk[_re] + _hc
            _t0 = _Tk[_rs] - _hc; _t1 = _Tk[_rs] + _hc
            _base = _A0 + _nrm*_ov_gap*_gm
            _v0 = _base + np.outer(_s0, _eu) + np.outer(_t0, _ev)
            _v1 = _base + np.outer(_s1, _eu) + np.outer(_t0, _ev)
            _v2 = _base + np.outer(_s1, _eu) + np.outer(_t1, _ev)
            _v3 = _base + np.outer(_s0, _eu) + np.outer(_t1, _ev)
            _M = len(_rs)
            _V = np.stack([_v0,_v1,_v2,_v3], axis=1).reshape(-1,3)
            _i0 = len(_VX) + 4*np.arange(_M)
            _VX.extend(_V[:,0].tolist()); _VY.extend(_V[:,1].tolist()); _VZ.extend(_V[:,2].tolist())
            _TI.extend(_i0.tolist()); _TI.extend(_i0.tolist())
            _TJ.extend((_i0+1).tolist()); _TJ.extend((_i0+2).tolist())
            _TK.extend((_i0+2).tolist()); _TK.extend((_i0+3).tolist())

_shared_once = 0.0
for _key in _pair_area: _shared_once += _pair_area[_key]
for _pidx in sorted(_penv):
    _e = _penv[_pidx]
    print(f"  Teil {_pidx}: exposed {_e[0]:.2f} m²  (Fassade {_e[1]:.2f} / Dach {_e[2]:.2f} / Boden {_e[3]:.2f})")
    _flaechen_lines.append(f"[FLAECHEN {_pidx}] {_e[1]:.2f} {_e[2]:.2f} {_e[3]:.2f}  "
                           f"(m2: Fassade / Dach / Boden, Teil {_pidx})")
print(f"\n  Gross surface (all GML polygons):               {_total_gross:.2f} m²")
print(f"  Gemeinsame/innere Fläche (einfach gezählt):     {_shared_once:.2f} m²")
for _key in sorted(_pair_area):
    print(f"    Teil {_key[0]} <-> Teil {_key[1]}: {_pair_area[_key]:.2f} m²")
print(f"  Exposed envelope, all faces:                    {_total_exposed:.2f} m²")
print(f"    Fassadenfläche:                               {_exp_facade:.2f} m²")
print(f"    Dachfläche:                                   {_exp_roof:.2f} m²")
print(f"    Bodenfläche (erdberührt):                     {_exp_ground:.2f} m²")
print(f"  Air-exchange envelope (Fassade + Dach):         {_exposed_air:.2f} m²")
print(f"  South-facing exposed area (component):          {_south_exposed:.2f} m²")
print("="*60)

# ===================================================================
# CUBOID COMPUTATION — fully inlined (no def, FileMaker MBS compatible)
#
# The same block of logic is used twice: once per unit, once for the NET
# (merged) cuboid. To avoid def-functions the whole computation is
# duplicated inline in two clearly-labeled sections below.
# ===================================================================

cuboid_data = []
print("="*60)
print("DEBUG: Per-part cuboid computation")
print("="*60)

for bd in building_data:
    if not bd['bbox'] or not bd['surfaces']['ground']: continue
    bbox = bd['bbox']; meta = bd['metadata']
    bbox_height = bbox['dimensions'][2]; storeys = meta['storeys']

    # --- assemble the 2D unique footprint + 3D ground (for real-edge snapping) ---
    gnd = bd['surfaces']['ground'][0]; c2d = gnd[:,:2]
    uniq = [c2d[0]]
    for c in c2d[1:]:
        if all(np.linalg.norm(c - u) > 0.05 for u in uniq): uniq.append(c)
    u2d = np.array(uniq)
    # --- remove SPIKES (zero-width out-and-back digitising artefacts) ---
    # A vertex is a spike tip if the outline reverses there (turn > ~155 deg)
    # and the triangle (prev, tip, next) has almost no area. Spikes add no
    # area but distort the hull, the longest edge and the cuboid centre.
    _n_spk = 0
    _chg = True
    while _chg and len(u2d) > 3:
        _chg = False
        for _si in range(len(u2d)):
            _pa = u2d[_si-1]; _pm = u2d[_si]; _pb = u2d[(_si+1) % len(u2d)]
            _d1 = _pm - _pa; _d2 = _pb - _pm
            _n1 = np.linalg.norm(_d1); _n2 = np.linalg.norm(_d2)
            if _n1 < 1e-9 or _n2 < 1e-9: continue
            _tri_a = 0.5 * abs(_d1[0]*_d2[1] - _d1[1]*_d2[0])
            if float(_d1 @ _d2) / (_n1*_n2) < -0.9 and _tri_a < 0.25:
                u2d = np.delete(u2d, _si, axis=0); _n_spk += 1; _chg = True; break
        if _chg:   # tip removed -> its two base points may now coincide
            _keep = [0]
            for _si in range(1, len(u2d)):
                if np.linalg.norm(u2d[_si] - u2d[_keep[-1]]) > 0.05: _keep.append(_si)
            u2d = u2d[_keep]
    if _n_spk:
        print(f"  [clean] Teil {bd['idx']}: {_n_spk} spike vertex/vertices removed from footprint")
    ground3d = gnd

    all_pts = []
    for sl in bd['surfaces'].values():
        for sf in sl: all_pts.extend(sf.tolist())
    all_pts_3d = np.array(all_pts) if all_pts else np.zeros((0,3))

    z_base = float(bbox['min'][2])
    label = f"Teil {bd['idx']}"

    # --- footprint area (convex hull preferred, shoelace fallback) ---
    if len(u2d) >= 3:
        try:
            _h2 = ConvexHull(u2d); fpa = _h2.volume
        except:
            _xx, _yy = u2d[:,0], u2d[:,1]
            fpa = 0.5 * abs(np.dot(_xx, np.roll(_yy, 1)) - np.dot(_yy, np.roll(_xx, 1)))
    else:
        fpa = 0.0

    # --- actual 3D volume (convex hull of all surface points) ---
    actual_vol = None
    if len(all_pts_3d) >= 4:
        pts3d = np.unique(all_pts_3d, axis=0)
        if len(pts3d) >= 4:
            try: actual_vol = ConvexHull(pts3d).volume
            except: pass
    if actual_vol is not None and fpa > 0:
        eff_h = actual_vol / fpa
    else:
        eff_h = bbox_height
    _hull_vol = actual_vol; _hull_fpa = fpa

    # --- TRUE solid volume + projected footprint (vertical ray casting) ---
    # The convex hull above over-estimates concave parts (L-shapes, dormers)
    # and parts whose roof overhangs a neighbour (roof reaching beyond the
    # ground polygon -> eff_h > real height, a tall thin "wall" cuboid).
    # Here: a vertical ray through every grid cell crosses the closed shell;
    # inside length = sum of (z_out - z_in). Orientation-independent.
    #   V_true = sum(inside length) * cell area
    #   A_proj = cells with material * cell area   (top-down shadow)
    _cs = 0.25
    _xy_all = all_pts_3d[:, :2]
    _g0 = _xy_all.min(0); _g1 = _xy_all.max(0)
    while ((_g1[0]-_g0[0])/_cs + 1) * ((_g1[1]-_g0[1])/_cs + 1) > 400000: _cs *= 1.5
    _nxg = int(np.ceil((_g1[0]-_g0[0]) / _cs)) + 1
    _nyg = int(np.ceil((_g1[1]-_g0[1]) / _cs)) + 1
    _gxs = _g0[0] + (np.arange(_nxg) + 0.5137) * _cs      # slight jitter: never exactly on an edge
    _gys = _g0[1] + (np.arange(_nyg) + 0.4871) * _cs
    _cell_ids = []; _cell_z = []
    for _sl in bd['surfaces'].values():
        for _sf in _sl:
            for _k in range(1, len(_sf) - 1):
                _A = _sf[0]; _Bv = _sf[_k] - _A; _Cv = _sf[_k+1] - _A
                _det = _Bv[0]*_Cv[1] - _Bv[1]*_Cv[0]
                if abs(_det) < 1e-9: continue              # vertical / degenerate triangle
                _tx = np.array([_A[0], _sf[_k][0], _sf[_k+1][0]]); _ty = np.array([_A[1], _sf[_k][1], _sf[_k+1][1]])
                _i0 = np.searchsorted(_gxs, _tx.min()); _i1 = np.searchsorted(_gxs, _tx.max())
                _j0 = np.searchsorted(_gys, _ty.min()); _j1 = np.searchsorted(_gys, _ty.max())
                if _i1 <= _i0 or _j1 <= _j0: continue
                _IX, _JY = np.meshgrid(np.arange(_i0, _i1), np.arange(_j0, _j1), indexing='ij')
                _wx = _gxs[_IX] - _A[0]; _wy = _gys[_JY] - _A[1]
                _s = (_wx*_Cv[1] - _wy*_Cv[0]) / _det
                _t = (_Bv[0]*_wy - _Bv[1]*_wx) / _det
                _in = (_s >= 0) & (_t >= 0) & (_s + _t <= 1)
                if not _in.any(): continue
                _cell_ids.append((_IX[_in] * _nyg + _JY[_in]).ravel())
                _cell_z.append((_A[2] + _s[_in]*_Bv[2] + _t[_in]*_Cv[2]).ravel())
    _vol_ok = False
    if _cell_ids:
        _cid = np.concatenate(_cell_ids); _cz = np.concatenate(_cell_z)
        _ord = np.lexsort((_cz, _cid)); _cid = _cid[_ord]; _cz = _cz[_ord]
        _ustart = np.flatnonzero(np.r_[True, _cid[1:] != _cid[:-1]])
        _ucnt = np.diff(np.r_[_ustart, len(_cid)])
        _rank = np.arange(len(_cid)) - np.repeat(_ustart, _ucnt)
        _sgn = np.where(_rank % 2 == 1, 1.0, -1.0)
        _clen = np.add.reduceat(_sgn * _cz, _ustart)    # (z1-z0)+(z3-z2)+... per cell
        _even = (_ucnt % 2 == 0)
        _odd_frac = 1.0 - _even.mean()
        _clen = np.where(_even, _clen, 0.0)
        _v_true = float(_clen.sum()) * _cs * _cs
        _a_proj = float((_clen > 1e-6).sum()) * _cs * _cs
        if _odd_frac < 0.05 and _v_true > 0 and _a_proj > 0:
            _vol_ok = True
    if _vol_ok:
        actual_vol = _v_true; fpa = _a_proj
        eff_h = actual_vol / fpa
        print(f"  [vol {label}] true solid: V={_v_true:.2f} m³  A_proj={_a_proj:.2f} m²  "
              f"(convex hull was V={_hull_vol if _hull_vol is not None else float('nan'):.2f}, A={_hull_fpa:.2f})")
    else:
        print(f"  [vol {label}] WARNING: shell not closed ({_odd_frac*100 if _cell_ids else 100:.0f}% open rays) "
              f"-> falling back to convex hull volume")
    eff_h = min(eff_h, bbox_height)                   # an equivalent cuboid is never taller than the part

    # --- MBR (inlined) — used for footprint center cx, cy ---
    if len(u2d) < 3:
        _mn, _mx = u2d.min(0), u2d.max(0); _d = _mx - _mn
        cx, cy, de, dn, mbr_ea = (_mn[0]+_mx[0])/2, (_mn[1]+_mx[1])/2, _d[0], _d[1], 0.0
    else:
        _hull_mbr = None
        try: _hull_mbr = ConvexHull(u2d)
        except: pass
        if _hull_mbr is None:
            _mn, _mx = u2d.min(0), u2d.max(0); _d = _mx - _mn
            cx, cy, de, dn, mbr_ea = (_mn[0]+_mx[0])/2, (_mn[1]+_mx[1])/2, _d[0], _d[1], 0.0
        else:
            hp = u2d[_hull_mbr.vertices]; n = len(hp)
            ba = np.inf; bc = None; bde = 0; bdn = 0; bang = 0
            for i in range(n):
                e = hp[(i+1)%n] - hp[i]; el = np.linalg.norm(e)
                if el < 1e-10: continue
                eu = e / el; nm = np.array([-eu[1], eu[0]])
                pe = hp @ eu; pn = hp @ nm
                _de = pe.max() - pe.min(); _dn = pn.max() - pn.min()
                a = _de * _dn
                if a < ba:
                    ba = a
                    ce = (pe.min()+pe.max())/2; cn = (pn.min()+pn.max())/2
                    bc = ce*eu + cn*nm; bde = _de; bdn = _dn
                    bang = np.degrees(np.arctan2(eu[1], eu[0]))
            if bc is None:
                _mn, _mx = u2d.min(0), u2d.max(0); _d = _mx - _mn
                cx, cy, de, dn, mbr_ea = (_mn[0]+_mx[0])/2, (_mn[1]+_mx[1])/2, _d[0], _d[1], 0.0
            else:
                cx, cy, de, dn, mbr_ea = bc[0], bc[1], bde, bdn, bang

    # --- REFERENCE EDGE: longest convex-hull edge of the real footprint (inlined) ---
    ref = None
    if len(u2d) >= 3:
        _hull_ref = None
        try: _hull_ref = ConvexHull(u2d)
        except: pass
        if _hull_ref is not None:
            hp_r = u2d[_hull_ref.vertices]
            # MERGE nearly collinear hull edges into one "side": a long wall that is
            # split by a small notch / extra vertex must count as ONE edge, otherwise
            # L = one segment only and W = A/L is inflated (long building -> square).
            # Vertex removed if the turn there is < 8 deg AND it lies < 0.5 m off the
            # line joining its neighbours (keeps real corners and chamfers).
            _chg = True
            while _chg and len(hp_r) > 3:
                _chg = False
                for _mi in range(len(hp_r)):
                    _pa = hp_r[_mi-1]; _pm = hp_r[_mi]; _pb = hp_r[(_mi+1) % len(hp_r)]
                    _d1 = _pm - _pa; _d2 = _pb - _pm; _dl = _pb - _pa
                    _n1 = np.linalg.norm(_d1); _n2 = np.linalg.norm(_d2); _nl = np.linalg.norm(_dl)
                    if _n1 < 1e-9 or _n2 < 1e-9 or _nl < 1e-9:
                        hp_r = np.delete(hp_r, _mi, axis=0); _chg = True; break
                    _cosang = float(_d1 @ _d2) / (_n1 * _n2)
                    _dist = abs(_dl[0]*(_pm[1]-_pa[1]) - _dl[1]*(_pm[0]-_pa[0])) / _nl
                    if _cosang > np.cos(np.radians(8.0)) and _dist < 0.5:
                        hp_r = np.delete(hp_r, _mi, axis=0); _chg = True; break
            best_len = 0.0; best_a2d = None; best_b2d = None
            for i in range(len(hp_r)):
                _aa = hp_r[i]; _bb = hp_r[(i+1) % len(hp_r)]
                _L = np.linalg.norm(_bb - _aa)
                if _L > best_len:
                    best_len = _L; best_a2d = _aa; best_b2d = _bb
            if best_a2d is not None:
                _ang = np.degrees(np.arctan2(best_b2d[1]-best_a2d[1], best_b2d[0]-best_a2d[0]))
                # snap to nearest real 3D ground point
                if ground3d is not None and len(ground3d) >= 3:
                    _dA = np.linalg.norm(ground3d[:,:2] - best_a2d, axis=1)
                    _dB = np.linalg.norm(ground3d[:,:2] - best_b2d, axis=1)
                    _s3 = ground3d[int(np.argmin(_dA))]
                    _e3 = ground3d[int(np.argmin(_dB))]
                else:
                    _s3 = np.array([best_a2d[0], best_a2d[1], 0.0])
                    _e3 = np.array([best_b2d[0], best_b2d[1], 0.0])
                ref = {'start': _s3, 'end': _e3, 'length': best_len, 'angle_deg': _ang,
                       'start2d': best_a2d, 'end2d': best_b2d}

    # --- cuboid length / width / rotation from reference edge ---
    if ref is not None:
        # consistent direction: start from endpoint closer to origin
        s = ref['start']; e = ref['end']
        if np.linalg.norm(e[:2]) < np.linalg.norm(s[:2]):
            s, e = e, s
            ref['start'] = s; ref['end'] = e
            ref['angle_deg'] = np.degrees(np.arctan2(e[1]-s[1], e[0]-s[0]))
        ref_angle = ref['angle_deg']
        cl = ref['length']
        cw = fpa / cl if cl > 0 else dn
        crot = ref_angle - 90.0
        reason = "longest_hull_edge"
    else:
        # MBR fallback — longest-axis detection inlined
        la = 0.0
        if len(u2d) >= 3:
            try:
                _hla = ConvexHull(u2d)
                _hpla = u2d[_hla.vertices]; _bl = 0; _ba_la = 0
                for i in range(len(_hpla)):
                    v = _hpla[(i+1)%len(_hpla)] - _hpla[i]; l = np.linalg.norm(v)
                    if l > _bl: _bl = l; _ba_la = np.degrees(np.arctan2(v[1], v[0]))
                la = _ba_la
            except: pass
        diff = (la - mbr_ea) % 180
        if diff > 90: diff = 180 - diff
        if diff < 45:
            cl = de; crot = mbr_ea + 90
        else:
            cl = dn; crot = mbr_ea
        cw = fpa / cl if cl > 0 else dn
        reason = "mbr_fallback"

    ch = eff_h

    # --- Ausrichtung (orientation from north) ---
    if ref is not None:
        _a = ref['angle_deg']
        if _a < 0: _a += 360
        ofn = (_a - 90.0) % 360
    else:
        ofn = (crot - 90) % 360

    # --- CONTACT-PRESERVING FIT ---
    # The cuboid keeps the true footprint area, so one side has to shrink for
    # non-rectangular footprints. Shrinking the wrong side detaches a part from
    # its neighbours (e.g. a connector between two buildings). Here: find which
    # faces of the part's footprint box touch a NEIGHBOUR's footprint, keep the
    # extent between touching faces, shrink only the free direction, and keep
    # the touching face in place (anchor). No contact -> previous behaviour.
    _crr2 = np.radians(crot)
    _wdc = np.array([np.cos(_crr2), np.sin(_crr2)])     # width axis  (u)
    _ldc = np.array([-np.sin(_crr2), np.cos(_crr2)])    # length axis (v)
    _pu = u2d @ _wdc; _pv = u2d @ _ldc
    _umin = float(_pu.min()); _umax = float(_pu.max()); _vmin = float(_pv.min()); _vmax = float(_pv.max())
    _eu = _umax - _umin; _ev = _vmax - _vmin
    _gr = np.asarray(gnd[:, :2], dtype=float)
    if not np.allclose(_gr[0], _gr[-1]): _gr = np.vstack([_gr, _gr[:1]])
    _crs = _gr[:-1, 0]*_gr[1:, 1] - _gr[1:, 0]*_gr[:-1, 1]
    _ag = 0.5 * float(_crs.sum())
    if abs(_ag) > 1e-9:
        _gc = np.array([float(((_gr[:-1, 0] + _gr[1:, 0]) * _crs).sum()) / (6*_ag),
                        float(((_gr[:-1, 1] + _gr[1:, 1]) * _crs).sum()) / (6*_ag)])
    else:
        _gc = u2d.mean(0)
    _ag = abs(_ag)
    _segA = []; _segB = []
    for _ob in building_data:
        if _ob is bd: continue
        for _og in _ob['surfaces']['ground']:
            _o2 = np.asarray(_og[:, :2], dtype=float)
            _segA.append(_o2); _segB.append(np.roll(_o2, -1, axis=0))
    _contact = np.zeros(len(u2d), dtype=bool)
    if _segA:
        _SA = np.vstack(_segA); _SD = np.vstack(_segB) - _SA
        _sl2 = (_SD**2).sum(1); _sl2[_sl2 < 1e-12] = 1e-12
        for _q in range(len(u2d)):
            _tq = np.clip(((u2d[_q] - _SA) * _SD).sum(1) / _sl2, 0.0, 1.0)
            _dq = np.linalg.norm(_SA + _tq[:, None]*_SD - u2d[_q], axis=1).min()
            _contact[_q] = _dq < 0.3                  # own corner lies on a neighbour's wall
    _ft = 0.5                                         # point belongs to a box face if within 0.5 m
    _c_umin = int((_contact & (_pu < _umin + _ft)).sum()) >= 2   # a shared wall has 2 ends
    _c_umax = int((_contact & (_pu > _umax - _ft)).sum()) >= 2
    _c_vmin = int((_contact & (_pv < _vmin + _ft)).sum()) >= 2
    _c_vmax = int((_contact & (_pv > _vmax - _ft)).sum()) >= 2
    _tu_any = _c_umin or _c_umax; _tv_any = _c_vmin or _c_vmax
    if ((_tu_any or _tv_any) and _ag > 0 and _eu > 0 and _ev > 0
            and abs(fpa - _ag) <= 0.10 * _ag):        # footprint = ground polygon (no overhang)
        _A = fpa
        if _c_umin and _c_umax:   _W = _eu; _L = _A / _W
        elif _c_vmin and _c_vmax: _L = _ev; _W = _A / _L
        elif _tu_any and not _tv_any: _W = _eu; _L = _A / _W
        elif _tv_any and not _tu_any: _L = _ev; _W = _A / _L
        else:
            _sc = (_A / (_eu * _ev)) ** 0.5; _W = _eu * _sc; _L = _ev * _sc
        _W = min(_W, _eu); _L = min(_L, _ev)
        _gcu = float(_gc @ _wdc); _gcv = float(_gc @ _ldc)
        if _W >= _eu - 1e-6:          _cu = 0.5*(_umin + _umax)
        elif _c_umin and not _c_umax: _cu = _umin + _W/2
        elif _c_umax and not _c_umin: _cu = _umax - _W/2
        else:                         _cu = min(max(_gcu, _umin + _W/2), _umax - _W/2)
        if _L >= _ev - 1e-6:          _cv = 0.5*(_vmin + _vmax)
        elif _c_vmin and not _c_vmax: _cv = _vmin + _L/2
        elif _c_vmax and not _c_vmin: _cv = _vmax - _L/2
        else:                         _cv = min(max(_gcv, _vmin + _L/2), _vmax - _L/2)
        _cxy = _cu*_wdc + _cv*_ldc
        print(f"  [fit] contact faces W-:{int(_c_umin)} W+:{int(_c_umax)} L-:{int(_c_vmin)} L+:{int(_c_vmax)}"
              f"  L {cl:.2f}->{_L:.2f}  W {cw:.2f}->{_W:.2f}")
        cx, cy = float(_cxy[0]), float(_cxy[1]); cl = _L; cw = _W
        reason = reason + "+contact"

    # --- make cuboid corners (inlined) ---
    rrad = np.radians(crot); _cc = np.cos(rrad); _ss = np.sin(rrad)
    Rmat = np.array([[_cc, -_ss], [_ss, _cc]])
    hw = cw/2; hl = cl/2
    loc = np.array([[-hw, -hl], [hw, -hl], [hw, hl], [-hw, hl]])
    rot2d = (Rmat @ loc.T).T + [cx, cy]
    co = np.zeros((8, 3))
    co[:4,:2] = rot2d; co[:4,2] = z_base
    co[4:,:2] = rot2d; co[4:,2] = z_base + ch

    # --- verification ---
    co_b = co[:4,:2]; rr = np.radians(crot)
    ld = np.array([-np.sin(rr), np.cos(rr)]); wd = np.array([np.cos(rr), np.sin(rr)])
    aL = max(co_b @ ld) - min(co_b @ ld); aW = max(co_b @ wd) - min(co_b @ wd)

    print(f"\n{label}:")
    print(f"  MBR center: ({cx:.2f},{cy:.2f})")
    if ref is not None:
        print(f"  Longest hull edge: len={ref['length']:.2f} angle={ref['angle_deg']:.1f}")
    print(f"  Rotation (crot): {crot:.1f}  Orientation from N: {ofn:.1f}")
    print(f"  Heights: bbox={bbox_height:.2f}  effective={eff_h:.2f}")
    if actual_vol is not None:
        print(f"  Actual 3D vol: {actual_vol:.2f}  Cuboid vol: {cl*cw*ch:.2f}")
    print(f"  Intended: L={cl:.2f} W={cw:.2f} H={ch:.2f}  ({reason})")
    print(f"  Verified: L={aL:.2f} W={aW:.2f}")
    print(f"  [LEGO] 4 {storeys} {cl:.2f} {cw:.2f} {ch:.2f}")


    # ---------------------------------------------------------------
    # ROOF TYPE (as text) + ROOF-FORM RECONSTRUCTION on the cuboid footprint
    #   footprint  = equivalent cuboid (L x W, rotation, centre)
    #   heights    = REAL eave / ridge heights from the GML RoofSurfaces
    #   ridge axis = from the real roof-face normals (along L or along W)
    # ---------------------------------------------------------------
    _rt_raw = meta.get('roof_type')
    _rt_code = None
    if _rt_raw:
        try: _rt_code = str(int(float(_rt_raw)))
        except: _rt_code = str(_rt_raw)
    if _rt_code is None:
        _rt_name = 'nicht definiert'; _rt_label = 'nicht definiert'
    elif _rt_code in _ROOF_NAMES:
        _rt_name = _ROOF_NAMES[_rt_code]; _rt_label = f"{_rt_name} ({_rt_code})"
    else:
        _rt_name = _rt_code; _rt_label = f"{_rt_code} (unbekannter Code)"

    _rf_list = bd['surfaces']['roofs']
    if _rf_list:
        _rf_all = np.vstack(_rf_list)
        _H_eave = float(_rf_all[:,2].min()) - z_base
        _H_ridge = float(_rf_all[:,2].max()) - z_base
    else:
        _H_eave = float(bbox_height); _H_ridge = float(bbox_height)
    _H_ridge = max(_H_ridge, 0.1)
    _H_eave = min(max(_H_eave, 0.0), _H_ridge)
    _Dz = _H_ridge - _H_eave

    _crr = np.radians(crot)
    _wdir_u = np.array([np.cos(_crr), np.sin(_crr)])     # cuboid width axis
    _ldir_u = np.array([-np.sin(_crr), np.cos(_crr)])    # cuboid length axis
    _tu = 0.0; _tv = 0.0; _su = 0.0; _sv = 0.0
    for _rf in _rf_list:
        _rn = np.zeros(3)
        for _q in range(len(_rf)):
            _rn += np.cross(_rf[_q], _rf[(_q+1) % len(_rf)])   # Newell normal
        if _rn[2] < 0: _rn = -_rn                            # roof normal points up
        _tu += abs(float(_rn[:2] @ _wdir_u)); _tv += abs(float(_rn[:2] @ _ldir_u))
        _su += float(_rn[:2] @ _wdir_u);      _sv += float(_rn[:2] @ _ldir_u)
    _swap = _tv > 1.2 * _tu        # roof faces tilt along L -> ridge runs along W
    if _swap:
        _adir = _ldir_u; _bdir = _wdir_u; _ha = cl/2.0; _hb = cw/2.0; _sa = _sv
    else:
        _adir = _wdir_u; _bdir = _ldir_u; _ha = cw/2.0; _hb = cl/2.0; _sa = _su
    _hi = -1.0 if _sa > 0 else 1.0  # normal points downhill -> high side is opposite

    # local coords: a = across ridge (+-_ha), b = along ridge (+-_hb), z from z_base
    _rect0 = [[-_ha,-_hb,0.0],[_ha,-_hb,0.0],[_ha,_hb,0.0],[-_ha,_hb,0.0]]
    _eave  = [[-_ha,-_hb,_H_eave],[_ha,-_hb,_H_eave],[_ha,_hb,_H_eave],[-_ha,_hb,_H_eave]]
    _pieces = []                   # list of CONVEX point sets (each -> ConvexHull)
    _roof_mode = 'dachform'
    if _rt_code == '1000':
        _pieces.append(_rect0 + [[-_ha,-_hb,_H_ridge],[_ha,-_hb,_H_ridge],[_ha,_hb,_H_ridge],[-_ha,_hb,_H_ridge]])
    elif _rt_code == '2100':
        _pieces.append(_rect0 + [[-_hi*_ha,-_hb,_H_eave],[-_hi*_ha,_hb,_H_eave],
                                 [_hi*_ha,-_hb,_H_ridge],[_hi*_ha,_hb,_H_ridge]])
    elif _rt_code == '2200':
        _Hm = _H_eave + 0.6*_Dz
        _pieces.append([[-_ha,-_hb,0.0],[0.0,-_hb,0.0],[0.0,_hb,0.0],[-_ha,_hb,0.0],
                        [-_ha,-_hb,_H_eave],[-_ha,_hb,_H_eave],[0.0,-_hb,_H_ridge],[0.0,_hb,_H_ridge]])
        _pieces.append([[0.0,-_hb,0.0],[_ha,-_hb,0.0],[_ha,_hb,0.0],[0.0,_hb,0.0],
                        [0.0,-_hb,_Hm],[0.0,_hb,_Hm],[_ha,-_hb,_H_eave],[_ha,_hb,_H_eave]])
    elif _rt_code == '3100':
        _pieces.append(_rect0 + _eave + [[0.0,-_hb,_H_ridge],[0.0,_hb,_H_ridge]])
    elif _rt_code == '3200':
        _rl = max(_hb - _ha, 0.0)
        _pieces.append(_rect0 + _eave + [[0.0,-_rl,_H_ridge],[0.0,_rl,_H_ridge]])
    elif _rt_code == '3300':
        _ak = 0.4*_ha; _Hk = _H_eave + 0.6*_Dz; _rl = max(_hb - 0.4*_ha, 0.0)
        _pieces.append(_rect0 + _eave + [[_ak,-_hb,_Hk],[-_ak,-_hb,_Hk],[_ak,_hb,_Hk],[-_ak,_hb,_Hk],
                                         [0.0,-_rl,_H_ridge],[0.0,_rl,_H_ridge]])
    elif _rt_code == '3400':
        _Hb = _H_eave + 0.65*_Dz; _ab = 0.7*_ha
        _pieces.append(_rect0 + _eave + [[-_ab,-_hb,_Hb],[_ab,-_hb,_Hb],[-_ab,_hb,_Hb],[_ab,_hb,_Hb],
                                         [0.0,-_hb,_H_ridge],[0.0,_hb,_H_ridge]])
    elif _rt_code in ('3500', '4000'):
        _pieces.append(_rect0 + _eave + [[0.0,0.0,_H_ridge]])
    elif _rt_code in ('3600', '3700'):
        # round plan: ellipse with the same area as the cuboid footprint
        _kk = 2.0/np.sqrt(np.pi)
        _pp = []
        for _t in np.linspace(0, 2*np.pi, 24, endpoint=False):
            _pp.append([_kk*_ha*np.cos(_t), _kk*_hb*np.sin(_t), 0.0])
            _pp.append([_kk*_ha*np.cos(_t), _kk*_hb*np.sin(_t), _H_eave])
            if _rt_code == '3700':
                for _j in range(1, 6):
                    _ph = _j/6.0*np.pi/2
                    _pp.append([_kk*_ha*np.cos(_t)*np.cos(_ph), _kk*_hb*np.sin(_t)*np.cos(_ph),
                                _H_eave + _Dz*np.sin(_ph)])
        _pp.append([0.0, 0.0, _H_ridge])
        _pieces.append(_pp)
    elif _rt_code == '3800':
        _nb = 3
        for _k in range(_nb):
            _b0 = -_hb + 2*_hb*_k/_nb; _b1 = -_hb + 2*_hb*(_k+1)/_nb
            _pieces.append([[-_ha,_b0,0.0],[_ha,_b0,0.0],[_ha,_b1,0.0],[-_ha,_b1,0.0],
                            [-_ha,_b0,_H_ridge],[_ha,_b0,_H_ridge],[-_ha,_b1,_H_eave],[_ha,_b1,_H_eave]])
    elif _rt_code == '3900':
        _pp = list(_rect0)
        for _t in np.linspace(0, np.pi, 13):
            _pp.append([_ha*np.cos(_t), -_hb, _H_eave + _Dz*np.sin(_t)])
            _pp.append([_ha*np.cos(_t),  _hb, _H_eave + _Dz*np.sin(_t)])
        _pieces.append(_pp)
    else:
        # not defined / Mischform / Sonstiges / unknown: no parametric roof form.
        # Dachform view shows the ORIGINAL GML geometry of this part instead
        # (a cuboid is already shown in the Quader view). Fallback: cuboid.
        _roof_mode = 'quader'
        for _pl in _polys:
            if _pl['part'] == bd['idx']: _roof_mode = 'original'; break
        if _roof_mode == 'quader':
            _pieces.append(_rect0 + [[-_ha,-_hb,ch],[_ha,-_hb,ch],[_ha,_hb,ch],[-_ha,_hb,ch]])

    # pieces -> world coords -> one mesh + feature edges (no def, plain loops)
    _rX=[]; _rY=[]; _rZ=[]; _rI=[]; _rJ=[]; _rK=[]
    _eX=[]; _eY=[]; _eZ=[]
    _rF = []        # planar faces [kind, ring] for the Kubatur-GML export (outward ring order)
    _rvol = 0.0
    for _pc in _pieces:
        _P = np.array(_pc, dtype=float)
        _Wp = np.zeros_like(_P)
        _Wp[:,0] = cx + _P[:,0]*_adir[0] + _P[:,1]*_bdir[0]
        _Wp[:,1] = cy + _P[:,0]*_adir[1] + _P[:,1]*_bdir[1]
        _Wp[:,2] = z_base + _P[:,2]
        try: _hpc = ConvexHull(_Wp)
        except: continue
        _rvol += float(_hpc.volume)
        _o = len(_rX)
        _rX.extend(_Wp[:,0].tolist()); _rY.extend(_Wp[:,1].tolist()); _rZ.extend(_Wp[:,2].tolist())
        _rI.extend((_hpc.simplices[:,0] + _o).tolist())
        _rJ.extend((_hpc.simplices[:,1] + _o).tolist())
        _rK.extend((_hpc.simplices[:,2] + _o).tolist())
        # coplanar hull facets -> one convex polygon each (outward normal = hull equation)
        _fgrp = {}
        for _f in range(len(_hpc.simplices)):
            _fk = tuple(np.round(_hpc.equations[_f], 4))
            _fgrp.setdefault(_fk, set()).update(int(_v) for _v in _hpc.simplices[_f])
        for _fk, _fv in _fgrp.items():
            _fn = np.array(_fk[:3]); _fP = _Wp[sorted(_fv)]; _fc = _fP.mean(0)
            _fu = _fP[0] - _fc; _fu = _fu / (np.linalg.norm(_fu) + 1e-12); _fw = np.cross(_fn, _fu)
            _fang = np.arctan2((_fP - _fc) @ _fw, (_fP - _fc) @ _fu)
            _fring = _fP[np.argsort(_fang)]
            _fkind = 'WallSurface' if abs(_fn[2]) < 0.15 else ('GroundSurface' if _fn[2] < -0.9 else 'RoofSurface')
            _rF.append([_fkind, np.round(_fring, 3).tolist()])
        _nq = _hpc.equations[:, :3]
        for _f in range(len(_hpc.simplices)):
            for _v in range(3):
                _g = int(_hpc.neighbors[_f][_v])
                if _g <= _f: continue
                if float(_nq[_f] @ _nq[_g]) > 0.94: continue      # < ~20 deg kink: no edge
                _e0 = None; _e1 = None
                for _w in range(3):
                    if _w == _v: continue
                    if _e0 is None: _e0 = int(_hpc.simplices[_f][_w])
                    else: _e1 = int(_hpc.simplices[_f][_w])
                _eX.extend([float(_Wp[_e0,0]), float(_Wp[_e1,0]), None])
                _eY.extend([float(_Wp[_e0,1]), float(_Wp[_e1,1]), None])
                _eZ.extend([float(_Wp[_e0,2]), float(_Wp[_e1,2]), None])

    if _roof_mode == 'original':
        for _pl in _polys:
            if _pl['part'] != bd['idx']: continue
            _o = len(_rX); _np_ = len(_pl['pts'])
            for _q in range(_np_):
                _rX.append(float(_pl['pts'][_q][0])); _rY.append(float(_pl['pts'][_q][1])); _rZ.append(float(_pl['pts'][_q][2]))
            for _tr in _pl['tris']:
                _rI.append(_tr[0] + _o); _rJ.append(_tr[1] + _o); _rK.append(_tr[2] + _o)
            _fkind = {'roofs':'RoofSurface','ground':'GroundSurface'}.get(_pl['kind'], 'WallSurface')
            _fring = np.asarray(_pl['pts'], dtype=float)
            _fnw = np.zeros(3)
            for _q in range(len(_fring)): _fnw += np.cross(_fring[_q], _fring[(_q+1) % len(_fring)])
            if float(_fnw @ np.asarray(_pl['n'])) < 0: _fring = _fring[::-1]
            _rF.append([_fkind, np.round(_fring, 3).tolist()])
            for _q in range(_np_):
                _pq = _pl['pts'][_q]; _pr = _pl['pts'][(_q+1) % _np_]
                _eX.extend([float(_pq[0]), float(_pr[0]), None])
                _eY.extend([float(_pq[1]), float(_pr[1]), None])
                _eZ.extend([float(_pq[2]), float(_pr[2]), None])
        _rvol = float(actual_vol) if actual_vol is not None else 0.0
    print(f"  Dach: {_rt_label}  Traufe={_H_eave:.2f} First={_H_ridge:.2f}  "
          f"First entlang {'Breite' if _swap else 'Länge'}  V_Dachform={_rvol:.2f}  ({_roof_mode})")

    cuboid_data.append({'part_idx':bd['idx'],'storeys':storeys,'length':cl,'width':cw,'height':ch,
        'rotation_deg':crot,'orientation_from_north':ofn,'center':(cx,cy),'z_base':z_base,
        'corners':co,'footprint_area':fpa,'volume':cl*cw*ch,
        'bbox_height':bbox_height,'eff_height':eff_h,'actual_vol':actual_vol,
        'ref_edge':ref,
        'roof_code':_rt_code,'roof_name':_rt_name,'roof_label':_rt_label,
        'eave_h':_H_eave,'ridge_h':_H_ridge,'ridge_along':('W' if _swap else 'L'),
        'roof_mode':_roof_mode,'roof_vol':_rvol,
        'roof_mesh':(_rX,_rY,_rZ,_rI,_rJ,_rK),'roof_edges':(_eX,_eY,_eZ),'roof_faces':_rF})

# ===================================================================
# KEEP NEIGHBOURS CONNECTED  (thermal-zone adjacency of the reconstruction)
#
# Every pair of parts that shares surface in the ORIGINAL GML (_pair_area,
# from the real-geometry envelope) must also touch after reconstruction:
#   1) parallel faces : the moving part is rotated (about its own centre) to
#      the neighbour's axis if the two differ by <= 5 deg (mod 90 deg)
#   2) close the gap  : if the two footprints are separated, the moving part
#      is translated by the shortest gap vector until the faces touch
# Pairs are processed largest original contact first. A part that has been
# placed is "locked"; the unlocked partner of a pair is the one that moves
# (if both are free, the smaller volume moves). Rigid moves only: L, W, H and
# volume of every cuboid stay exactly the same.
# Afterwards the reconstructed contact area of every pair is measured
# (cuboid faces probed 3 cm outward into the neighbour) for comparison.
# ===================================================================
print("\n" + "="*60)
print("ADJACENCY: keep originally connected parts connected")
print("="*60)
_cd_by = {}
for _cdx in cuboid_data: _cd_by[_cdx['part_idx']] = _cdx
_adj = []
for _key in _pair_area:
    if _pair_area[_key] >= 0.5 and _key[0] in _cd_by and _key[1] in _cd_by:
        _adj.append((_pair_area[_key], _key[0], _key[1]))
_adj.sort(reverse=True)
_locked = set()
for _aa, _pi, _pj in _adj:
    _CA = _cd_by[_pi]; _CB = _cd_by[_pj]
    if _pi in _locked and _pj in _locked:
        _mov = None
    elif _pi in _locked:
        _mov = _CB; _fix = _CA
    elif _pj in _locked:
        _mov = _CA; _fix = _CB
    elif _CA['volume'] >= _CB['volume']:
        _mov = _CB; _fix = _CA
    else:
        _mov = _CA; _fix = _CB
    if _mov is not None:
        # z ranges must overlap for a side contact (stacked parts: leave as is)
        _za0 = _mov['z_base']; _za1 = _mov['z_base'] + _mov['height']
        _zb0 = _fix['z_base']; _zb1 = _fix['z_base'] + _fix['height']
        _rot_d = 0.0; _tvec = np.zeros(2)
        _dlt = ((_fix['rotation_deg'] - _mov['rotation_deg'] + 45.0) % 90.0) - 45.0
        if abs(_dlt) <= 5.0: _rot_d = _dlt
        # rotated footprint of the moving part (candidate), fixed footprint
        _mc = np.array([_mov['center'][0], _mov['center'][1]])
        _rr = np.radians(_rot_d); _rc = np.cos(_rr); _rs_ = np.sin(_rr)
        _Rm = np.array([[_rc, -_rs_], [_rs_, _rc]])
        _qm = (_Rm @ (_mov['corners'][:4, :2] - _mc).T).T + _mc
        _qf = _fix['corners'][:4, :2]
        if min(_za1, _zb1) - max(_za0, _zb0) > 0.1:
            # separating-axis test (4 edge normals of both rectangles)
            _sep = False
            for _poly2 in (_qm, _qf):
                for _k in range(4):
                    _ed = _poly2[(_k+1) % 4] - _poly2[_k]
                    _ax2 = np.array([-_ed[1], _ed[0]]); _nl = np.linalg.norm(_ax2)
                    if _nl < 1e-12: continue
                    _ax2 = _ax2 / _nl
                    _p1 = _qm @ _ax2; _p2 = _qf @ _ax2
                    if _p1.max() < _p2.min() - 1e-6 or _p2.max() < _p1.min() - 1e-6: _sep = True
            if _sep:
                # shortest vector from the moving rectangle to the fixed one
                _best = None
                for _src, _dst, _sg in ((_qm, _qf, 1.0), (_qf, _qm, -1.0)):
                    for _k in range(4):
                        _p = _src[_k]
                        for _l in range(4):
                            _s0 = _dst[_l]; _s1 = _dst[(_l+1) % 4]; _sd = _s1 - _s0
                            _tt = float(np.clip(((_p - _s0) @ _sd) / max(float(_sd @ _sd), 1e-12), 0.0, 1.0))
                            _vv = (_s0 + _tt*_sd - _p) * _sg        # move direction for the moving part
                            _dd = float(np.linalg.norm(_vv))
                            if _best is None or _dd < _best[0]: _best = (_dd, _vv)
                if _best is not None and _best[0] > 0.01:
                    _tvec = _best[1]
        if abs(_rot_d) > 1e-9 or np.linalg.norm(_tvec) > 0:
            # apply the rigid move to EVERYTHING of the moving part
            _co = _mov['corners']
            _co[:, :2] = (_Rm @ (_co[:, :2] - _mc).T).T + _mc + _tvec
            _rm = _mov.get('roof_mesh')
            if _rm and _rm[0] and _mov.get('roof_mode') != 'original':
                _rx = np.array(_rm[0]); _ry = np.array(_rm[1])
                _xy = (_Rm @ (np.column_stack([_rx, _ry]) - _mc).T).T + _mc + _tvec
                _mov['roof_mesh'] = (_xy[:, 0].tolist(), _xy[:, 1].tolist(), _rm[2], _rm[3], _rm[4], _rm[5])
            _re_ = _mov.get('roof_edges')
            if _re_ and _re_[0] and _mov.get('roof_mode') != 'original':
                _nx_ = []; _ny_ = []
                for _q in range(len(_re_[0])):
                    if _re_[0][_q] is None:
                        _nx_.append(None); _ny_.append(None)
                    else:
                        _pq = _Rm @ (np.array([_re_[0][_q], _re_[1][_q]]) - _mc) + _mc + _tvec
                        _nx_.append(float(_pq[0])); _ny_.append(float(_pq[1]))
                _mov['roof_edges'] = (_nx_, _ny_, _re_[2])
            _rf = _mov.get('ref_edge')
            if _rf is not None:
                for _kk in ('start', 'end'):
                    _pq = _Rm @ (np.array(_rf[_kk][:2], dtype=float) - _mc) + _mc + _tvec
                    _rf[_kk] = np.array([_pq[0], _pq[1], _rf[_kk][2]])
            _nc = _mc + _tvec
            _mov['center'] = (float(_nc[0]), float(_nc[1]))
            _mov['rotation_deg'] = float(_mov['rotation_deg'] + _rot_d)
            _mov['orientation_from_north'] = float((_mov['orientation_from_north'] + _rot_d) % 360)
            print(f"  Teil {_mov['part_idx']} -> Teil {_fix['part_idx']}: rotated {_rot_d:+.2f} deg, "
                  f"moved {np.linalg.norm(_tvec):.2f} m")
        _locked.add(_mov['part_idx'])
    _locked.add(_pi); _locked.add(_pj)

# --- reconstructed contact area per pair (cuboid faces probed into neighbour) ---
_rek_pair = {}
_rek_vx=[]; _rek_vy=[]; _rek_vz=[]; _rek_i=[]; _rek_j=[]; _rek_k=[]
_rk_gap = max(0.05, 0.004*float(np.linalg.norm(_all_bb_max - _all_bb_min)))
_cdl = list(_cd_by.values())
for _CA in _cdl:
    _co = _CA['corners']; _bc = _co.mean(0)
    for _fq in ((0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7), (0,1,2,3), (4,5,6,7)):
        _o = _co[_fq[0]]; _e1 = _co[_fq[1]] - _o; _e2 = _co[_fq[3]] - _o
        _l1 = float(np.linalg.norm(_e1)); _l2 = float(np.linalg.norm(_e2))
        if _l1 < 1e-6 or _l2 < 1e-6: continue
        _fn = np.cross(_e1, _e2); _fn = _fn / np.linalg.norm(_fn)
        if float(_fn @ ((_o + 0.5*_e1 + 0.5*_e2) - _bc)) < 0: _fn = -_fn
        _n1 = max(1, int(np.ceil(_l1 / 0.25))); _n2 = max(1, int(np.ceil(_l2 / 0.25)))
        _g1, _g2 = np.meshgrid((np.arange(_n1) + 0.5)/_n1, (np.arange(_n2) + 0.5)/_n2)
        _FP = _o + np.outer(_g1.ravel(), _e1) + np.outer(_g2.ravel(), _e2) + _fn*0.03
        _pt = _l1*_l2 / (_n1*_n2)
        for _CB in _cdl:
            if _CB is _CA or _CB['part_idx'] < _CA['part_idx']: continue
            _ru = np.radians(_CB['rotation_deg'])
            _wdu = np.array([np.cos(_ru), np.sin(_ru)]); _ldu = np.array([-np.sin(_ru), np.cos(_ru)])
            _dv = _FP[:, :2] - np.array(_CB['center'])
            _inb = ((np.abs(_dv @ _wdu) <= _CB['width']/2 + 1e-6) & (np.abs(_dv @ _ldu) <= _CB['length']/2 + 1e-6) &
                    (_FP[:, 2] >= _CB['z_base'] - 1e-6) & (_FP[:, 2] <= _CB['z_base'] + _CB['height'] + 1e-6))
            if _inb.any():
                _key = (_CA['part_idx'], _CB['part_idx'])
                _rek_pair[_key] = _rek_pair.get(_key, 0.0) + float(_inb.sum()) * _pt
                _G = _inb.reshape(_n2, _n1)
                for _r in range(_n2):
                    _c = 0
                    while _c < _n1:
                        if not _G[_r, _c]: _c += 1; continue
                        _c0 = _c
                        while _c < _n1 and _G[_r, _c]: _c += 1
                        _q0 = _o + _fn*_rk_gap
                        _i0 = len(_rek_vx)
                        for _uu, _vv in ((_c0/_n1, _r/_n2), (_c/_n1, _r/_n2), (_c/_n1, (_r+1)/_n2), (_c0/_n1, (_r+1)/_n2)):
                            _vq = _q0 + _uu*_e1 + _vv*_e2
                            _rek_vx.append(float(_vq[0])); _rek_vy.append(float(_vq[1])); _rek_vz.append(float(_vq[2]))
                        _rek_i.extend([_i0, _i0]); _rek_j.extend([_i0+1, _i0+2]); _rek_k.extend([_i0+2, _i0+3])
_adj_lines = []
_adj_set = set()
for _key in _pair_area:
    if _pair_area[_key] >= 0.5: _adj_set.add(_key)
for _key in _rek_pair:
    if _rek_pair[_key] >= 0.5: _adj_set.add(_key)
_adj_keys = sorted(_adj_set)
for _key in _adj_keys:
    _ao = _pair_area.get(_key, 0.0); _ar = _rek_pair.get(_key, 0.0)
    _flag = "OK" if (_ao >= 0.5) == (_ar >= 0.5) else ("GETRENNT" if _ao >= 0.5 else "NEU")
    _adj_lines.append(f"[ADJ {_key[0]} {_key[1]}] {_ao:.2f} {_ar:.2f} {_flag}  "
                      f"(m2: gemeinsame Fläche Original-GML / Rekonstruktion, Teil {_key[0]}-{_key[1]})")
    print(f"  Teil {_key[0]} <-> Teil {_key[1]}: original {_ao:7.2f} m²   rekonstruiert {_ar:7.2f} m²   {_flag}")
for _cdx in cuboid_data:
    _cdx['corners'] = np.asarray(_cdx['corners'])

# ===================================================================
# NET (EQUIVALENT) CUBOID — single cuboid for ALL units combined
# Same computation block, inlined a second time over the merged data.
# ===================================================================
print("\n" + "="*60)
print("DEBUG: NET (equivalent) cuboid for all units combined")
print("="*60)
net_cuboid = None

_all_ground_2d = []
_all_ground_3d = []
_all_pts_3d_net = []
_all_z_min = []
for bd in building_data:
    for g in bd['surfaces']['ground']:
        _all_ground_2d.extend(g[:,:2].tolist())
        _all_ground_3d.extend(g.tolist())
    for sl in bd['surfaces'].values():
        for sf in sl: _all_pts_3d_net.extend(sf.tolist())
    if bd['bbox']: _all_z_min.append(float(bd['bbox']['min'][2]))

if _all_ground_2d and _all_pts_3d_net:
    _g2d = np.array(_all_ground_2d)
    ground3d = np.array(_all_ground_3d)
    # dedupe 2D
    _uniq_n = [_g2d[0]]
    for c in _g2d[1:]:
        if all(np.linalg.norm(c - u) > 0.01 for u in _uniq_n): _uniq_n.append(c)
    u2d = np.array(_uniq_n)
    all_pts_3d = np.array(_all_pts_3d_net)
    z_base = min(_all_z_min) if _all_z_min else 0.0
    _zmax = all_pts_3d[:,2].max()
    bbox_height = _zmax - z_base
    storeys = max((bd['metadata']['storeys'] for bd in building_data if bd['metadata'].get('storeys')), default=3)
    label = "NET cuboid (all units)"

    # --- footprint area ---
    if len(u2d) >= 3:
        try:
            _h2 = ConvexHull(u2d); fpa = _h2.volume
        except:
            _xx, _yy = u2d[:,0], u2d[:,1]
            fpa = 0.5 * abs(np.dot(_xx, np.roll(_yy, 1)) - np.dot(_yy, np.roll(_xx, 1)))
    else:
        fpa = 0.0

    # --- actual 3D volume ---
    actual_vol = None
    if len(all_pts_3d) >= 4:
        pts3d = np.unique(all_pts_3d, axis=0)
        if len(pts3d) >= 4:
            try: actual_vol = ConvexHull(pts3d).volume
            except: pass
    if actual_vol is not None and fpa > 0:
        eff_h = actual_vol / fpa
    else:
        eff_h = bbox_height

    # --- MBR inlined ---
    if len(u2d) < 3:
        _mn, _mx = u2d.min(0), u2d.max(0); _d = _mx - _mn
        cx, cy, de, dn, mbr_ea = (_mn[0]+_mx[0])/2, (_mn[1]+_mx[1])/2, _d[0], _d[1], 0.0
    else:
        _hull_mbr = None
        try: _hull_mbr = ConvexHull(u2d)
        except: pass
        if _hull_mbr is None:
            _mn, _mx = u2d.min(0), u2d.max(0); _d = _mx - _mn
            cx, cy, de, dn, mbr_ea = (_mn[0]+_mx[0])/2, (_mn[1]+_mx[1])/2, _d[0], _d[1], 0.0
        else:
            hp = u2d[_hull_mbr.vertices]; n = len(hp)
            ba = np.inf; bc = None; bde = 0; bdn = 0; bang = 0
            for i in range(n):
                e = hp[(i+1)%n] - hp[i]; el = np.linalg.norm(e)
                if el < 1e-10: continue
                eu = e / el; nm = np.array([-eu[1], eu[0]])
                pe = hp @ eu; pn = hp @ nm
                _de = pe.max() - pe.min(); _dn = pn.max() - pn.min()
                a = _de * _dn
                if a < ba:
                    ba = a
                    ce = (pe.min()+pe.max())/2; cn = (pn.min()+pn.max())/2
                    bc = ce*eu + cn*nm; bde = _de; bdn = _dn
                    bang = np.degrees(np.arctan2(eu[1], eu[0]))
            if bc is None:
                _mn, _mx = u2d.min(0), u2d.max(0); _d = _mx - _mn
                cx, cy, de, dn, mbr_ea = (_mn[0]+_mx[0])/2, (_mn[1]+_mx[1])/2, _d[0], _d[1], 0.0
            else:
                cx, cy, de, dn, mbr_ea = bc[0], bc[1], bde, bdn, bang

    # --- reference edge inlined ---
    ref = None
    if len(u2d) >= 3:
        _hull_ref = None
        try: _hull_ref = ConvexHull(u2d)
        except: pass
        if _hull_ref is not None:
            hp_r = u2d[_hull_ref.vertices]
            # MERGE nearly collinear hull edges into one "side": a long wall that is
            # split by a small notch / extra vertex must count as ONE edge, otherwise
            # L = one segment only and W = A/L is inflated (long building -> square).
            # Vertex removed if the turn there is < 8 deg AND it lies < 0.5 m off the
            # line joining its neighbours (keeps real corners and chamfers).
            _chg = True
            while _chg and len(hp_r) > 3:
                _chg = False
                for _mi in range(len(hp_r)):
                    _pa = hp_r[_mi-1]; _pm = hp_r[_mi]; _pb = hp_r[(_mi+1) % len(hp_r)]
                    _d1 = _pm - _pa; _d2 = _pb - _pm; _dl = _pb - _pa
                    _n1 = np.linalg.norm(_d1); _n2 = np.linalg.norm(_d2); _nl = np.linalg.norm(_dl)
                    if _n1 < 1e-9 or _n2 < 1e-9 or _nl < 1e-9:
                        hp_r = np.delete(hp_r, _mi, axis=0); _chg = True; break
                    _cosang = float(_d1 @ _d2) / (_n1 * _n2)
                    _dist = abs(_dl[0]*(_pm[1]-_pa[1]) - _dl[1]*(_pm[0]-_pa[0])) / _nl
                    if _cosang > np.cos(np.radians(8.0)) and _dist < 0.5:
                        hp_r = np.delete(hp_r, _mi, axis=0); _chg = True; break
            best_len = 0.0; best_a2d = None; best_b2d = None
            for i in range(len(hp_r)):
                _aa = hp_r[i]; _bb = hp_r[(i+1) % len(hp_r)]
                _L = np.linalg.norm(_bb - _aa)
                if _L > best_len:
                    best_len = _L; best_a2d = _aa; best_b2d = _bb
            if best_a2d is not None:
                _ang = np.degrees(np.arctan2(best_b2d[1]-best_a2d[1], best_b2d[0]-best_a2d[0]))
                if ground3d is not None and len(ground3d) >= 3:
                    _dA = np.linalg.norm(ground3d[:,:2] - best_a2d, axis=1)
                    _dB = np.linalg.norm(ground3d[:,:2] - best_b2d, axis=1)
                    _s3 = ground3d[int(np.argmin(_dA))]
                    _e3 = ground3d[int(np.argmin(_dB))]
                else:
                    _s3 = np.array([best_a2d[0], best_a2d[1], 0.0])
                    _e3 = np.array([best_b2d[0], best_b2d[1], 0.0])
                ref = {'start': _s3, 'end': _e3, 'length': best_len, 'angle_deg': _ang,
                       'start2d': best_a2d, 'end2d': best_b2d}

    # --- cuboid L/W/rot ---
    if ref is not None:
        s = ref['start']; e = ref['end']
        if np.linalg.norm(e[:2]) < np.linalg.norm(s[:2]):
            s, e = e, s
            ref['start'] = s; ref['end'] = e
            ref['angle_deg'] = np.degrees(np.arctan2(e[1]-s[1], e[0]-s[0]))
        ref_angle = ref['angle_deg']
        cl = ref['length']
        cw = fpa / cl if cl > 0 else dn
        crot = ref_angle - 90.0
        reason = "longest_hull_edge"
    else:
        la = 0.0
        if len(u2d) >= 3:
            try:
                _hla = ConvexHull(u2d)
                _hpla = u2d[_hla.vertices]; _bl = 0; _ba_la = 0
                for i in range(len(_hpla)):
                    v = _hpla[(i+1)%len(_hpla)] - _hpla[i]; l = np.linalg.norm(v)
                    if l > _bl: _bl = l; _ba_la = np.degrees(np.arctan2(v[1], v[0]))
                la = _ba_la
            except: pass
        diff = (la - mbr_ea) % 180
        if diff > 90: diff = 180 - diff
        if diff < 45:
            cl = de; crot = mbr_ea + 90
        else:
            cl = dn; crot = mbr_ea
        cw = fpa / cl if cl > 0 else dn
        reason = "mbr_fallback"

    ch = eff_h

    # --- NET ORIENTATION OVERRIDE ---
    # The longest edge of the merged hull is often a spurious diagonal between
    # extreme corners of separated buildings. Instead, inherit orientation from
    # the DOMINANT (largest-footprint) unit so the NET cuboid aligns with the
    # main building axis the user sees.
    _net_ofn_override = None
    if cuboid_data:
        _dominant = max(cuboid_data, key=lambda _c: _c.get('footprint_area', 0.0))
        if _dominant.get('footprint_area', 0.0) > 0:
            crot = float(_dominant['rotation_deg'])
            # Area-weighted centroid of per-unit cuboid centers (XY plane)
            _wsum = 0.0; _cxw = 0.0; _cyw = 0.0
            _vol_sum = 0.0
            for _cd_u in cuboid_data:
                _w = _cd_u.get('footprint_area', 0.0)
                if _w <= 0: continue
                _cxw += _w * _cd_u['center'][0]
                _cyw += _w * _cd_u['center'][1]
                _wsum += _w
                _vol_sum += _cd_u.get('volume', 0.0)
            if _wsum > 0:
                cx = _cxw / _wsum; cy = _cyw / _wsum
            # Area-weighted average HEIGHT of per-unit cuboids
            _h_wsum = 0.0
            for _cd_u in cuboid_data:
                _w = _cd_u.get('footprint_area', 0.0)
                if _w <= 0: continue
                _h_wsum += _w * _cd_u['height']
            if _wsum > 0:
                ch = _h_wsum / _wsum
            else:
                ch = bbox_height
            # Project merged footprint onto dominant orientation axes for L,W ratio
            _r = np.radians(crot); _cc = np.cos(_r); _ss = np.sin(_r)
            _ldir = np.array([-_ss, _cc]); _wdir = np.array([_cc, _ss])
            _proj_l = u2d @ _ldir; _proj_w = u2d @ _wdir
            _l_raw = float(_proj_l.max() - _proj_l.min())
            _w_raw = float(_proj_w.max() - _proj_w.min())
            # --- TRUE MERGED (UNION) VOLUME via voxel sampling ---
            # Overlapping part cuboids would otherwise be double-counted in the
            # naive sum. Sample a 3D grid over the cluster and count each cell
            # once if it lies inside ANY part cuboid. No functions / no CSG lib.
            _vox = 0.5
            _allc_n = np.vstack([_cd_u['corners'] for _cd_u in cuboid_data])
            _mn_n = _allc_n.min(0); _ext_n = _allc_n.max(0) - _mn_n
            _ncells = np.maximum(np.ceil(_ext_n / _vox), 1).astype(int)
            while int(_ncells[0])*int(_ncells[1])*int(_ncells[2]) > 2000000:
                _vox *= 1.5
                _ncells = np.maximum(np.ceil(_ext_n / _vox), 1).astype(int)
            _gx = _mn_n[0] + (np.arange(_ncells[0]) + 0.5) * _vox
            _gy = _mn_n[1] + (np.arange(_ncells[1]) + 0.5) * _vox
            _gz = _mn_n[2] + (np.arange(_ncells[2]) + 0.5) * _vox
            _GX, _GY, _GZ = np.meshgrid(_gx, _gy, _gz, indexing='ij')
            _VP = np.column_stack([_GX.ravel(), _GY.ravel(), _GZ.ravel()])
            _in_union = np.zeros(len(_VP), dtype=bool)
            for _cd_u in cuboid_data:
                _ru = np.radians(_cd_u['rotation_deg']); _cu = np.cos(_ru); _su = np.sin(_ru)
                _wdu = np.array([_cu, _su]); _ldu = np.array([-_su, _cu])
                _ocu = np.array([_cd_u['center'][0], _cd_u['center'][1]])
                _z0u = _cd_u['z_base']; _z1u = _cd_u['z_base'] + _cd_u['height']
                _hwu = _cd_u['width']/2.0; _hlu = _cd_u['length']/2.0
                _dv = _VP[:,:2] - _ocu[None,:]
                _in_union |= ((np.abs(_dv @ _wdu) <= _hwu) & (np.abs(_dv @ _ldu) <= _hlu) &
                              (_VP[:,2] >= _z0u) & (_VP[:,2] <= _z1u))
            _vol_union = float(_in_union.sum()) * (_vox**3)
            print(f"  Union volume (voxel {_vox:.2f}m, no double-count): {_vol_union:.2f}  (naive sum: {_vol_sum:.2f})")
            # Scale L,W uniformly so L*W*H = TRUE merged volume (overlap removed)
            if _vol_union > 0 and ch > 0 and _l_raw > 0 and _w_raw > 0:
                _target_area = _vol_union / ch
                _scale = (_target_area / (_l_raw * _w_raw)) ** 0.5
                cl = _l_raw * _scale
                cw = _w_raw * _scale
            else:
                cl = _l_raw; cw = _w_raw
            _half_l = cl / 2.0
            _ref_s = np.array([cx - _half_l*_ldir[0], cy - _half_l*_ldir[1], z_base])
            _ref_e = np.array([cx + _half_l*_ldir[0], cy + _half_l*_ldir[1], z_base])
            ref = {'start': _ref_s, 'end': _ref_e, 'length': cl, 'angle_deg': crot,
                   'start2d': _ref_s[:2], 'end2d': _ref_e[:2]}
            reason = "dominant_unit_orientation"
            _net_ofn_override = float(_dominant['orientation_from_north'])

    # --- Ausrichtung ---
    if _net_ofn_override is not None:
        ofn = _net_ofn_override
    elif ref is not None:
        _a = ref['angle_deg']
        if _a < 0: _a += 360
        ofn = (_a - 90.0) % 360
    else:
        ofn = (crot - 90) % 360

    # --- corners ---
    rrad = np.radians(crot); _cc = np.cos(rrad); _ss = np.sin(rrad)
    Rmat = np.array([[_cc, -_ss], [_ss, _cc]])
    hw = cw/2; hl = cl/2
    loc = np.array([[-hw, -hl], [hw, -hl], [hw, hl], [-hw, hl]])
    rot2d = (Rmat @ loc.T).T + [cx, cy]
    co = np.zeros((8, 3))
    co[:4,:2] = rot2d; co[:4,2] = z_base
    co[4:,:2] = rot2d; co[4:,2] = z_base + ch

    # --- verification ---
    co_b = co[:4,:2]; rr = np.radians(crot)
    ld = np.array([-np.sin(rr), np.cos(rr)]); wd = np.array([np.cos(rr), np.sin(rr)])
    aL = max(co_b @ ld) - min(co_b @ ld); aW = max(co_b @ wd) - min(co_b @ wd)

    print(f"\n{label}:")
    print(f"  MBR center: ({cx:.2f},{cy:.2f})")
    if ref is not None:
        print(f"  Longest hull edge: len={ref['length']:.2f} angle={ref['angle_deg']:.1f}")
    print(f"  Rotation (crot): {crot:.1f}  Orientation from N: {ofn:.1f}")
    print(f"  Heights: bbox={bbox_height:.2f}  effective={eff_h:.2f}")
    if actual_vol is not None:
        print(f"  Actual 3D vol: {actual_vol:.2f}  Cuboid vol: {cl*cw*ch:.2f}")
    print(f"  Intended: L={cl:.2f} W={cw:.2f} H={ch:.2f}  ({reason})")
    print(f"  Verified: L={aL:.2f} W={aW:.2f}")
    print(f"  [LEGO] 4 {storeys} {cl:.2f} {cw:.2f} {ch:.2f}")

    net_cuboid = {'part_idx':0,'storeys':storeys,'length':cl,'width':cw,'height':ch,
        'rotation_deg':crot,'orientation_from_north':ofn,'center':(cx,cy),'z_base':z_base,
        'corners':co,'footprint_area':fpa,'volume':cl*cw*ch,
        'bbox_height':bbox_height,'eff_height':eff_h,'actual_vol':actual_vol,
        'ref_edge':ref}

print("\n"+"="*50)
print("LEGO OUTPUT")
print("="*50)
lego_lines = []
_lego_n = 0
for cd in cuboid_data:
    _lego_n += 1
    line = f"[LEGO {_lego_n}] 4 {cd['storeys']} {cd['length']:.2f} {cd['width']:.2f} {cd['height']:.2f}  (Teil {cd['part_idx']})"
    print(line); lego_lines.append(line)
if net_cuboid:
    line = f"[COMBINED] 4 {net_cuboid['storeys']} {net_cuboid['length']:.2f} {net_cuboid['width']:.2f} {net_cuboid['height']:.2f}  (NET)"
    print(line); lego_lines.append(line)
for cd in cuboid_data:
    line = (f"[DACHTYP {cd['part_idx']}] {cd['roof_code'] or '-'} {cd['eave_h']:.2f} {cd['ridge_h']:.2f} "
            f"{cd['roof_vol']:.2f} {cd['ridge_along']} {cd['roof_name']}  "
            f"(Teil {cd['part_idx']}: Code / Traufhöhe m / Firsthöhe m / V_Dachform m3 / First entlang L|W / Name)")
    print(line); lego_lines.append(line)
print("="*50)

lego_lines.append(f"[ENVELOPE] {_total_exposed:.2f} {_exposed_air:.2f}  (m2: total / air-exchange)")
lego_lines.append(f"[FASSADE] {_exp_facade:.2f}  (m2: Fassadenfläche netto, alle Teile)")
lego_lines.append(f"[DACHFLAECHE] {_exp_roof:.2f}  (m2: Dachfläche netto, alle Teile)")
lego_lines.append(f"[BODEN] {_exp_ground:.2f}  (m2: Bodenfläche erdberührt, alle Teile)")
for _fl in _flaechen_lines: lego_lines.append(_fl)
lego_lines.append(f"[SHARED] {_shared_once:.2f}  (m2: common / internal area, single count)")
for _al in _adj_lines: lego_lines.append(_al)
lego_lines.append(f"[SOUTH] {_south_exposed:.2f}  (m2: south-facing component)")
if _addresses:
    for _ai, _a in enumerate(_addresses): lego_lines.append(f"[ADRESSE {_ai+1}] {_a}")
else:
    lego_lines.append("[ADRESSE] -")
if bbox_check['status'] == 'none':
    lego_lines.append("[BBOX] KEINE  (keine gml:Envelope / gml:Box zu Gebäuden im GML)")
else:
    lego_lines.append(f"[BBOX] {'OK' if bbox_check['status'] == 'ok' else 'FEHLER'}  "
                      f"({len(bbox_check['envelopes'])} Bounding-Box(en) geprüft, Toleranz {bbox_check['tol']:g})")
    for _bi, _be in enumerate(bbox_check['envelopes']):
        lego_lines.append(f"[BBOX {_bi+1}] {'OK' if _be['ok'] else 'FEHLER'} {_be['n_out']} {_be['n_pts']} "
                          + ' '.join(f"{v:.3f}" for v in _be['max_exceed'])
                          + ("  SWAP_XY" if _be['axis_swapped'] else "")
                          + f"  ({_be['scope']}: Punkte außerhalb / Punkte gesamt / max. Überschreitung X Y [Z])")

print("\n" + "="*60)
print("FILEMAKER OUTPUT (vollständig)")
print("="*60)
for _ln in lego_lines: print(_ln)
print("="*60)

# ===================================================================
# PLOTLY HTML VISUALIZATION
# ===================================================================
traces = []

# --- building meshes (always visible): REAL GML polygons, ear-clipped ---
# LIGHT OUTPUT: packed like the overlays (base64 float32 xyz / uint32 ijk).
_bm_idx = {}                # part -> trace index of its building mesh ("Aus" view)
for bd in building_data:
    _bv = []; _bf = []
    for _pl in _polys:
        if _pl['part'] != bd['idx']: continue
        _o = len(_bv)
        for _q in range(len(_pl['pts'])): _bv.append(_pl['pts'][_q])
        for _tr in _pl['tris']: _bf.append((_tr[0] + _o, _tr[1] + _o, _tr[2] + _o))
    if not _bf: continue
    _BV = np.round(np.array(_bv), 3); _BF = np.array(_bf, dtype=np.int64)
    _bm_idx[bd['idx']] = len(traces)
    traces.append({"type":"mesh3d","color":bcolors[(bd['idx']-1)%len(bcolors)],"opacity":1.0,"flatshading":True,
        "name":f"Teil {bd['idx']}","showlegend":True,
        "_b":[base64.b64encode(_BV.T.astype('<f4').tobytes()).decode('ascii'),
              base64.b64encode(_BF.T.astype('<u4').tobytes()).decode('ascii'),
              int(len(_BV)), int(len(_BF))]})

# --- LABELS: scene annotations, drawn on top of the 3D scene ---
# _ann_meta[k] = {"md": view the label belongs to, "tr": trace index of the
# geometry it describes}. The JS shows a label only if labels are switched on,
# its view is active AND that geometry is currently visible (legend clicks too).
scene_ann = []
_ann_meta = []
_kt_idx = {}; _kr_idx = {}; _net_idx = None
# --- per-unit cuboids (kubatur group) ---
ccol = ['gold','darkorange','tomato','orchid','turquoise']
ep = [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]]

# Solid (opacity exactly 1.0): anything below 1.0 - even 0.99 - makes Plotly
# draw the mesh in its unsorted transparency pass (see-through while rotating).
# While shown, the building solids are hidden by the "Pro Teil" radio button
# (see JS below): the cuboids sit on the same walls and would flicker.
for i, cd in enumerate(cuboid_data):
    co = cd['corners']; clr = ccol[i%len(ccol)]
    lg = f"kubatur{cd['part_idx']}"; pn = f"Kubatur {cd['part_idx']}"
    _kt_idx[cd['part_idx']] = len(traces)
    traces.append({"type":"mesh3d","x":co[:,0].tolist(),"y":co[:,1].tolist(),"z":co[:,2].tolist(),
        "alphahull":0,"color":clr,"opacity":1.0,"flatshading":True,"name":pn,"legendgroup":lg,"showlegend":True,"visible":False})
    for a, b in ep:
        traces.append({"type":"scatter3d","mode":"lines","x":[float(co[a][0]),float(co[b][0])],
            "y":[float(co[a][1]),float(co[b][1])],"z":[float(co[a][2]),float(co[b][2])],
            "line":{"color":clr,"width":4},"legendgroup":lg,"showlegend":False,"visible":False,"hoverinfo":"skip"})
    _tc = co[4:8].mean(axis=0)
    _ktxt = '<br>'.join([f"<b>{pn}</b>",
            f"{cd['length']:.1f}×{cd['width']:.1f}×{cd['height']:.1f}m  ({cd['storeys']}G)",
            f"Ausr.: {cd['orientation_from_north']:.0f}°  V: {cd['volume']:.0f}m³"])
    _ann_meta.append({"md":"kubPer","tr":_kt_idx[cd['part_idx']]})
    scene_ann.append({"x":float(_tc[0]),"y":float(_tc[1]),"z":float(_tc[2]),"text":_ktxt,"visible":False,
        "showarrow":True,"arrowhead":0,"arrowwidth":1,"arrowcolor":"#777","ax":-60-35*(i%3),"ay":-40-45*(i%3),
        "font":{"size":10,"color":"#a02020"},"align":"left","bgcolor":"rgba(255,255,255,0.96)",
        "bordercolor":"#bbbbbb","borderwidth":1,"borderpad":3})

# --- per-unit ROOF-FORM reconstruction (dachform group) ---
for i, cd in enumerate(cuboid_data):
    _rm = cd.get('roof_mesh')
    if not _rm or not _rm[3]: continue
    clr = ccol[i%len(ccol)]
    lg = f"dachform{cd['part_idx']}"; pn = f"Dachform {cd['part_idx']}"
    _kr_idx[cd['part_idx']] = len(traces)
    traces.append({"type":"mesh3d","x":_rm[0],"y":_rm[1],"z":_rm[2],"i":_rm[3],"j":_rm[4],"k":_rm[5],
        "color":clr,"opacity":1.0,"flatshading":True,"name":pn,"legendgroup":lg,"showlegend":True,"visible":False})
    _red = cd['roof_edges']
    if _red[0]:
        traces.append({"type":"scatter3d","mode":"lines","x":_red[0],"y":_red[1],"z":_red[2],
            "line":{"color":clr,"width":4},"legendgroup":lg,"showlegend":False,"visible":False,"hoverinfo":"skip"})
    _rl3 = [f"<b>{pn}</b>", cd['roof_label'],
            f"Traufe {cd['eave_h']:.1f} m · First {cd['ridge_h']:.1f} m",
            f"V: {cd['roof_vol']:.0f}m³"]
    if cd['roof_mode'] == 'original':
        _rl3.append("(kein parametrischer Dachtyp → Original-GML-Geometrie)")
    if cd['roof_mode'] == 'quader':
        _rl3.append("(kein rekonstruierbarer Dachtyp → Quader)")
    _ann_meta.append({"md":"kubRoof","tr":_kr_idx[cd['part_idx']]})
    scene_ann.append({"x":float(cd['center'][0]),"y":float(cd['center'][1]),"z":float(cd['z_base'] + cd['ridge_h']),"text":'<br>'.join(_rl3),"visible":False,
        "showarrow":True,"arrowhead":0,"arrowwidth":1,"arrowcolor":"#777","ax":-60-35*(i%3),"ay":-40-45*(i%3),
        "font":{"size":10,"color":"#a02020"},"align":"left","bgcolor":"rgba(255,255,255,0.96)",
        "bordercolor":"#bbbbbb","borderwidth":1,"borderpad":3})

# --- NET cuboid (netkubatur group) ---
if net_cuboid:
    co = net_cuboid['corners']; clr = 'royalblue'
    lg = "netkubatur"; pn = "NET Kubatur"
    _net_idx = len(traces)
    traces.append({"type":"mesh3d","x":co[:,0].tolist(),"y":co[:,1].tolist(),"z":co[:,2].tolist(),
        "alphahull":0,"color":clr,"opacity":0.25,"name":pn,"legendgroup":lg,"showlegend":True,"visible":False})
    for a, b in ep:
        traces.append({"type":"scatter3d","mode":"lines","x":[float(co[a][0]),float(co[b][0])],
            "y":[float(co[a][1]),float(co[b][1])],"z":[float(co[a][2]),float(co[b][2])],
            "line":{"color":clr,"width":5},"legendgroup":lg,"showlegend":False,"visible":False,"hoverinfo":"skip"})
    tc = co[4:8].mean(axis=0)
    _ntxt = '<br>'.join([f"<b>{pn}</b>",
            f"{net_cuboid['length']:.1f}×{net_cuboid['width']:.1f}×{net_cuboid['height']:.1f}m  ({net_cuboid['storeys']}G)",
            f"Ausr.: {net_cuboid['orientation_from_north']:.0f}°  V: {net_cuboid['volume']:.0f}m³",
            f"Grundfläche (Hülle): {net_cuboid['footprint_area']:.0f}m²"])
    _ann_meta.append({"md":"kubNet","tr":_net_idx})
    scene_ann.append({"x":float(tc[0]),"y":float(tc[1]),"z":float(tc[2]),"text":_ntxt,"visible":False,
        "showarrow":True,"arrowhead":0,"arrowwidth":1,"arrowcolor":"#777","ax":-70,"ay":-70,
        "font":{"size":11,"color":"darkblue"},"align":"left","bgcolor":"rgba(255,255,255,0.96)",
        "bordercolor":"#bbbbbb","borderwidth":1,"borderpad":3})

# --- "Aus" view labels: one per Teil (dimensions of its cuboid + roof type) ---
for _li, bd in enumerate(building_data):
    if not bd['bbox'] or bd['idx'] not in _bm_idx: continue
    cdm = None
    for _cdx in cuboid_data:
        if _cdx['part_idx'] == bd['idx']: cdm = _cdx
    if cdm is None: continue
    cen = (bd['bbox']['min'] + bd['bbox']['max']) / 2
    lbl = '<br>'.join([f"<b>Teil {bd['idx']}</b>",
        f"Quader: {cdm['length']:.1f}×{cdm['width']:.1f}×{cdm['height']:.1f}m  ({cdm['storeys']}G)",
        f"Ausr.: {cdm['orientation_from_north']:.0f}°  Grfl.: {cdm['footprint_area']:.0f}m²",
        f"Dach: {cdm['roof_label']}",
        f"Traufe {cdm['eave_h']:.1f} m · First {cdm['ridge_h']:.1f} m"])
    _ann_meta.append({"md":"kubOff","tr":_bm_idx[bd['idx']]})
    scene_ann.append({"x":float(cen[0]),"y":float(cen[1]),"z":float(bd['bbox']['max'][2]),"text":lbl,"visible":False,
        "showarrow":True,"arrowhead":0,"arrowwidth":1,"arrowcolor":"#777","ax":60+35*(_li%3),"ay":-50-45*(_li%3),
        "font":{"size":10,"color":"#000"},"align":"left","bgcolor":"rgba(255,255,255,0.96)",
        "bordercolor":"#bbbbbb","borderwidth":1,"borderpad":3})

# --- reference edges: shown with the geometry they belong to, in any view ---
# _ref_meta[k] = {"tr": edge trace, "own": {view: trace index of the owner}}
_ref_meta = []
for cd in cuboid_data:
    ref = cd.get('ref_edge')
    if ref is None: continue
    _own = {}
    if cd['part_idx'] in _bm_idx: _own["kubOff"] = _bm_idx[cd['part_idx']]
    if cd['part_idx'] in _kt_idx: _own["kubPer"] = _kt_idx[cd['part_idx']]
    if cd['part_idx'] in _kr_idx: _own["kubRoof"] = _kr_idx[cd['part_idx']]
    s_ = ref['start']; e_ = ref['end']
    _ref_meta.append({"tr":len(traces),"own":_own})
    traces.append({"type":"scatter3d","mode":"lines",
        "x":[float(s_[0]),float(e_[0])],"y":[float(s_[1]),float(e_[1])],"z":[float(s_[2])+0.05,float(e_[2])+0.05],
        "line":{"color":"magenta","width":10},"name":f"Referenzkante Teil {cd['part_idx']}",
        "legendgroup":f"ref{cd['part_idx']}","showlegend":False,"visible":False,"hoverinfo":"text",
        "text":[f"Referenzkante Teil {cd['part_idx']}: {ref['length']:.2f}m"]*2})
if net_cuboid and net_cuboid.get('ref_edge') is not None and _net_idx is not None:
    ref = net_cuboid['ref_edge']; s_ = ref['start']; e_ = ref['end']
    _ref_meta.append({"tr":len(traces),"own":{"kubNet":_net_idx}})
    traces.append({"type":"scatter3d","mode":"lines",
        "x":[float(s_[0]),float(e_[0])],"y":[float(s_[1]),float(e_[1])],"z":[float(s_[2])+0.05,float(e_[2])+0.05],
        "line":{"color":"magenta","width":12},"name":"Referenzkante NET",
        "legendgroup":"refnet","showlegend":False,"visible":False,"hoverinfo":"text",
        "text":[f"Referenzkante NET: {ref['length']:.2f}m"]*2})

# --- compass ---
if building_data and building_data[0]['bbox']:
    bb = building_data[0]['bbox']
    cpx = float(bb['max'][0]*1.2); cpy = float(bb['max'][1]*1.2); cpz = float(bb['max'][2]*1.1)
    arr = float((bb['max'][0]-bb['min'][0])*0.15)
    traces.append({"type":"scatter3d","mode":"lines","x":[cpx,cpx],"y":[cpy,cpy+arr],"z":[cpz,cpz],"line":{"color":"red","width":8},"legendgroup":"kompass","showlegend":False})
    traces.append({"type":"cone","x":[cpx],"y":[cpy+arr],"z":[cpz],"u":[0],"v":[arr*0.15],"w":[0],"colorscale":[[0,"red"],[1,"red"]],"showscale":False,"legendgroup":"kompass","showlegend":False,"hoverinfo":"skip"})
    traces.append({"type":"scatter3d","mode":"lines","x":[cpx,cpx+arr*0.7],"y":[cpy,cpy],"z":[cpz,cpz],"line":{"color":"green","width":6},"legendgroup":"kompass","showlegend":False})
    traces.append({"type":"cone","x":[cpx+arr*0.7],"y":[cpy],"z":[cpz],"u":[arr*0.7*0.15],"v":[0],"w":[0],"colorscale":[[0,"green"],[1,"green"]],"showscale":False,"legendgroup":"kompass","showlegend":False,"hoverinfo":"skip"})
    traces.append({"type":"scatter3d","mode":"text","x":[cpx],"y":[cpy+arr*1.15],"z":[cpz],"text":["N"],"textfont":{"size":20,"color":"red"},"legendgroup":"kompass","showlegend":False,"hoverinfo":"skip"})
    traces.append({"type":"scatter3d","mode":"text","x":[cpx+arr*0.85],"y":[cpy],"z":[cpz],"text":["O"],"textfont":{"size":16,"color":"green"},"legendgroup":"kompass","showlegend":False,"hoverinfo":"skip"})

# --- ORIGINAL GML geometry as a light WIREFRAME (real polygon rings, not hulls) ---
# For comparing the reconstruction (Quader / Dachform) with the true geometry.
# LIGHT OUTPUT: one trace, coordinates packed as base64 float32 (x|y|z), NaN
# between rings = line break; consecutive duplicate points dropped.
# One trace per Teil, so an excluded Teil can be hidden here as well.
for bd in building_data:
    _wf = []
    for _sl in bd['surfaces'].values():
        for _sf in _sl:
            _r = np.round(np.asarray(_sf, dtype=float), 3)
            if len(_r) < 3: continue
            _kp = np.r_[True, np.any(np.abs(np.diff(_r, axis=0)) > 0, axis=1)]
            _r = _r[_kp]
            if len(_r) < 3: continue
            if np.any(_r[0] != _r[-1]): _r = np.vstack([_r, _r[:1]])
            _wf.append(_r); _wf.append(np.full((1, 3), np.nan))
    if not _wf: continue
    _WF = np.vstack(_wf)
    traces.append({"type":"scatter3d","mode":"lines","name":f"Original GML Teil {bd['idx']}","legendgroup":f"origwf{bd['idx']}",
        "line":{"color":"#111111","width":3},"showlegend":False,"visible":False,"hoverinfo":"skip",
        "_bl":[base64.b64encode(_WF.T.astype('<f4').tobytes()).decode('ascii'), int(len(_WF))]})

# --- GML BOUNDING BOX(ES) as wireframe + coordinates lying outside them ---
# Green = box contains all its coordinates, red = it does not. Points outside
# are drawn as red markers. Boxes that are absurdly far away / huge (e.g. a
# whole city tile, or degrees vs metres) are not drawn, only reported.
_bb_diag = float(np.linalg.norm(_raw_max - _raw_min)) + 1.0
_bb_drawn = 0
for _bi, _be in enumerate(bbox_check['envelopes']):
    _lo3 = list(_be['lower']); _hi3 = list(_be['upper'])
    if _be['dim'] < 3:
        _lo3.append(float(_raw_min[2])); _hi3.append(float(_raw_max[2]))
    _lo3 = np.array(_lo3) - offset; _hi3 = np.array(_hi3) - offset
    _far = float(np.linalg.norm(_hi3 - _lo3)) > 20.0*_bb_diag + 500.0 or \
           float(np.abs(np.r_[_lo3, _hi3]).max()) > 20.0*_bb_diag + 500.0
    _be['drawn'] = not _far
    if _far: continue
    _bc = [[_lo3[0],_lo3[1],_lo3[2]],[_hi3[0],_lo3[1],_lo3[2]],[_hi3[0],_hi3[1],_lo3[2]],[_lo3[0],_hi3[1],_lo3[2]],
           [_lo3[0],_lo3[1],_hi3[2]],[_hi3[0],_lo3[1],_hi3[2]],[_hi3[0],_hi3[1],_hi3[2]],[_lo3[0],_hi3[1],_hi3[2]]]
    _lx=[]; _ly=[]; _lz=[]
    for a, b in [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]]:
        _lx.extend([float(_bc[a][0]), float(_bc[b][0]), None])
        _ly.extend([float(_bc[a][1]), float(_bc[b][1]), None])
        _lz.extend([float(_bc[a][2]), float(_bc[b][2]), None])
    traces.append({"type":"scatter3d","mode":"lines","x":_lx,"y":_ly,"z":_lz,
        "line":{"color":("#1e8449" if _be['ok'] else "#c0392b"),"width":5,"dash":"dash"},
        "name":f"GML-BBox {_bi+1}","legendgroup":"gmlbbox","showlegend":False,"visible":False,
        "hoverinfo":"text","text":[f"GML-Bounding-Box {_bi+1}: {_be['scope']}"]*len(_lx)})
    _bb_drawn += 1
_bb_out = []
for _be in bbox_check['envelopes']:
    for _op in _be['out_pts']: _bb_out.append(_op)
if _bb_out:
    _BO = np.unique(np.round(np.array(_bb_out), 3), axis=0)[:3000] - offset
    traces.append({"type":"scatter3d","mode":"markers","x":_BO[:,0].tolist(),"y":_BO[:,1].tolist(),"z":_BO[:,2].tolist(),
        "marker":{"size":4,"color":"#e74c3c","line":{"color":"#7b241c","width":1}},
        "name":"Punkte außerhalb BBox","legendgroup":"gmlbbox","showlegend":False,"visible":False,
        "hoverinfo":"text","text":["außerhalb der GML-Bounding-Box"]*len(_BO)})
for _be in bbox_check['envelopes']: _be.pop('out_pts', None)   # keep the result small

# --- surface overlays: facade / roof / shared interface / south-facing ---
# Ground (earth-contact) faces are deliberately NOT drawn.
for _vx,_vy,_vz,_ti,_tj,_tk,_oclr,_onm,_olg in (
        (_fas_vx,_fas_vy,_fas_vz,_fas_i,_fas_j,_fas_k,"deepskyblue","Fassadenfläche","srffas"),
        (_dch_vx,_dch_vy,_dch_vz,_dch_i,_dch_j,_dch_k,"seagreen","Dachfläche","srfdach"),
        (_shr_vx,_shr_vy,_shr_vz,_shr_i,_shr_j,_shr_k,"crimson","Gemeinsame Fläche","srfshared"),
        (_sth_vx,_sth_vy,_sth_vz,_sth_i,_sth_j,_sth_k,"orange","Süd-Fläche","srfsouth"),
        (_rek_vx,_rek_vy,_rek_vz,_rek_i,_rek_j,_rek_k,"#7b2cbf","Gemeinsame Fläche (Rekonstruktion)","srfrek")):
    if not _ti: continue
    _OP = np.round(np.column_stack([_vx,_vy,_vz]), 3)
    _OU, _OI = np.unique(_OP, axis=0, return_inverse=True)
    _OF = np.asarray(_OI).ravel()[np.column_stack([_ti,_tj,_tk])]
    traces.append({"type":"mesh3d","color":_oclr,"opacity":1.0,"flatshading":True,
        "lighting":{"ambient":0.8,"diffuse":0.0,"specular":0.0,"facenormalsepsilon":0.0},
        "name":_onm,"legendgroup":_olg,"showlegend":False,"visible":False,"hoverinfo":"skip",
        "_b":[base64.b64encode(_OU.T.astype('<f4').tobytes()).decode('ascii'),
              base64.b64encode(_OF.T.astype('<u4').tobytes()).decode('ascii'),
              int(len(_OU)), int(len(_OF))]})

# --- PART SELECTION (exclude a Teil) + KUBATUR-GML EXPORT ---
# _part_tr: trace index -> Teil it belongs to (building mesh, Quader, Dachform,
# reference edge, original wireframe). The JS hides every trace of an excluded
# Teil in all views. _part_meta carries what the browser needs to write the
# Kubatur GML of the remaining Teile (geometry is read from the traces).
_part_tr = {}
for _pti, _ptr in enumerate(traces):
    _pm = re.match(r'(kubatur|dachform|ref|origwf)(\d+)$', _ptr.get('legendgroup', ''))
    if _pm: _part_tr[_pti] = int(_pm.group(2))
for _pidx, _pti in _bm_idx.items(): _part_tr[_pti] = _pidx
_srs_name = None
for _el in root.iter():
    for _an, _av in _el.attrib.items():
        if (_an.split('}',1)[1] if '}' in _an else _an).lower() == 'srsname': _srs_name = _av; break
    if _srs_name: break
_part_meta = []
for i, cd in enumerate(cuboid_data):
    _u = _units[cd['part_idx'] - 1]; _par = _unit_parent.get(id(_u))
    _uid = None; _pid = None
    for _an, _av in _u.attrib.items():
        if (_an.split('}',1)[1] if '}' in _an else _an) == 'id': _uid = _av
    if _par is not None:
        for _an, _av in _par.attrib.items():
            if (_an.split('}',1)[1] if '}' in _an else _an) == 'id': _pid = _av
    _part_meta.append({"p":cd['part_idx'],"id":_uid,"pid":_pid,"kt":_kt_idx.get(cd['part_idx']),
        "kr":_kr_idx.get(cd['part_idx']),"clr":bcolors[(cd['part_idx']-1)%len(bcolors)],
        "l":round(float(cd['length']),3),"w":round(float(cd['width']),3),"h":round(float(cd['height']),3),
        "v":round(float(cd['volume']),2),"s":int(cd['storeys']),"rt":cd.get('roof_code'),
        "rh":round(float(cd['ridge_h']),3),"rf":cd.get('roof_faces') or None})
_export_meta = {"off":[float(v) for v in offset],"srs":_srs_name,"addr":_addresses[:1],"fms":FM_SCRIPT_NAME}
ptj = json.dumps({str(k): v for k, v in _part_tr.items()}, separators=(',',':'))
pmj = json.dumps(_part_meta, separators=(',',':')); exj = json.dumps(_export_meta, separators=(',',':'))

layout = {"scene":{"xaxis":{"title":"X [m]"},"yaxis":{"title":"Y [m]"},"zaxis":{"title":"Z [m]"},"aspectmode":"data","camera":{"eye":{"x":1.5,"y":1.5,"z":1.2}}},"margin":{"l":0,"r":0,"t":0,"b":0},"hovermode":"closest","legend":{"x":0.0,"y":1.0,"xanchor":"left","yanchor":"top","bgcolor":"rgba(255,255,255,0.95)","bordercolor":"rgba(0,0,0,0.3)","borderwidth":1,"font":{"size":11},"itemwidth":30,"tracegroupgap":2},"updatemenus":[{"type":"buttons","direction":"right","x":0.5,"y":1.02,"xanchor":"center","yanchor":"bottom","buttons":[{"label":"Top","method":"relayout","args":[{"scene.camera.eye":{"x":0,"y":0,"z":2.5}}]},{"label":"Front","method":"relayout","args":[{"scene.camera.eye":{"x":0,"y":-2.5,"z":0}}]},{"label":"Right","method":"relayout","args":[{"scene.camera.eye":{"x":2.5,"y":0,"z":0}}]},{"label":"Iso","method":"relayout","args":[{"scene.camera.eye":{"x":1.5,"y":1.5,"z":1.2}}]}],"pad":{"r":10,"t":10},"showactive":True,"bgcolor":"lightblue","font":{"size":11}}]}
layout["scene"]["annotations"] = scene_ann
tj = json.dumps(traces, separators=(',',':')); lj = json.dumps(layout, separators=(',',':'))
amj = json.dumps(_ann_meta, separators=(',',':')); rmj = json.dumps(_ref_meta, separators=(',',':'))

# --- title: address (bold) + model info ---
if _addresses:
    _addr_show = _addresses[:4]
    _addr_html = '<br>'.join([html.escape(_a) for _a in _addr_show])
    if len(_addresses) > 4:
        _addr_html += f"<br>(+{len(_addresses)-4} weitere Adressen)"
else:
    _addr_html = "Adresse: nicht im GML enthalten"
tt = f"3D Model - {len(building_data)} Parts · Version {VIEWER_VERSION}"

# --- bounding-box check panel (bottom left) ---
_fmt = (lambda v: f"{v:.7f}") if bbox_check['degrees'] else (lambda v: f"{v:.3f}")
if bbox_check['status'] == 'none':
    _bb_cls = 'bbnone'; _bb_head = 'GML-Bounding-Box: nicht vorhanden'
    _bb_body = ("Das GML enthält keine gml:Envelope / gml:Box für die Gebäude – "
                "es gibt nichts zu prüfen.<br>Tatsächliche Ausdehnung der Koordinaten:<br>"
                f"min ({', '.join(_fmt(v) for v in bbox_check['actual_min'])})<br>"
                f"max ({', '.join(_fmt(v) for v in bbox_check['actual_max'])})")
else:
    _nbad = sum(1 for e in bbox_check['envelopes'] if not e['ok'])
    if _nbad == 0:
        _bb_cls = 'bbok'; _bb_head = f"✓ GML-Bounding-Box enthält alle Gebäudekoordinaten"
    else:
        _bb_cls = 'bbfail'; _bb_head = f"✗ {_nbad} von {len(bbox_check['envelopes'])} Bounding-Box(en) enthalten NICHT alle Koordinaten"
    _bb_rows = []
    for _bi, _be in enumerate(bbox_check['envelopes']):
        _ax = 'XYZ'[:_be['dim']]
        _r = [f"<div class='bbrow {'ok' if _be['ok'] else 'bad'}'><b>{_bi+1}. {html.escape(_be['scope'])}</b>"
              f" <span class='mut'>({_be['dim']}D, Teil {', '.join(str(t) for t in _be['teile'])})</span><br>"]
        if _be['srs']: _r.append(f"<span class='mut'>SRS: {html.escape(_be['srs'])}</span><br>")
        _r.append(f"lower ({', '.join(_fmt(v) for v in _be['lower'])})<br>"
                  f"upper ({', '.join(_fmt(v) for v in _be['upper'])})<br>")
        if _be['ok']:
            _r.append(f"Alle {_be['n_pts']} Punkte innerhalb. Reserve zur Box: "
                      + ', '.join(f"{_ax[a]} {_fmt(min(_be['slack_lower'][a], _be['slack_upper'][a]))}"
                                  for a in range(_be['dim'])))
        else:
            _r.append(f"<b class='badt'>{_be['n_out']} von {_be['n_pts']} Punkten außerhalb</b><br>"
                      "max. Überschreitung: "
                      + ', '.join(f"{_ax[a]} {_fmt(_be['max_exceed'][a])}" for a in range(_be['dim'])))
            if _be['axis_swapped']:
                _r.append("<br><b class='badt'>Hinweis: mit vertauschten X/Y-Achsen würde die Box passen "
                          "(Achsenreihenfolge im GML falsch?)</b>")
        if not _be.get('drawn', True):
            _r.append("<br><span class='mut'>(zu groß / zu weit entfernt – nicht im 3D gezeichnet)</span>")
        _r.append("</div>")
        _bb_rows.append(''.join(_r))
    _bb_body = ''.join(_bb_rows) + (f"<div class='mut'>Toleranz: {bbox_check['tol']:g}"
                                    f"{'°' if bbox_check['degrees'] else ' m'}</div>")
_bb_html = (f"<div class='bbox {_bb_cls}'><details {'open' if _bb_cls == 'bbfail' else ''}>"
            f"<summary>{_bb_head}</summary><div class='bbbody'>{_bb_body}</div></details></div>")
eh = ("Fassadenfläche (netto): {0:.1f} m²<br>"
      "Dachfläche (netto): {1:.1f} m²<br>"
      "Bodenfläche (erdberührt): {2:.1f} m²<br>"
      "Hülle gesamt (F+D+B): {3:.1f} m²<br>"
      "Gemeinsame Fläche (einfach): {4:.1f} m²<br>"
      "Süd-projizierte Fläche: {5:.1f} m²").format(_exp_facade, _exp_roof, _exp_ground,
                                                   _total_exposed, _shared_once, _south_exposed)
if _adj_keys:
    eh += "<br><b style='margin-top:6px'>Gemeinsame Flächen (Original / Rekonstruktion)</b>"
    for _key in _adj_keys:
        _ao = _pair_area.get(_key, 0.0); _ar = _rek_pair.get(_key, 0.0)
        _mark = "" if (_ao >= 0.5) == (_ar >= 0.5) else (" ⚠ getrennt" if _ao >= 0.5 else " ⚠ neu")
        eh += f"Teil {_key[0]}–{_key[1]}: {_ao:.1f} / {_ar:.1f} m²{_mark}<br>"
html_tpl = """<!DOCTYPE html><html><head><meta charset="UTF-8">
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<style>*{margin:0;padding:0;box-sizing:border-box}html,body{width:100%%;height:100%%;overflow:hidden;background:#f8f9fa;font-family:Arial}#plotDiv{position:absolute;top:0;left:0;width:100%%;height:100%%}.title{position:fixed;bottom:8px;left:50%%;transform:translateX(-50%%);z-index:1000;background:rgba(255,255,255,0.92);padding:6px 14px;border-radius:6px;box-shadow:0 3px 10px rgba(0,0,0,0.18);pointer-events:none;text-align:center;max-width:34vw}.title .addr{font-size:14px;font-weight:bold;color:#1a1a1a;line-height:1.35}.title .sub{font-size:11px;color:#666;margin-top:2px}.cbox{position:fixed;right:16px;top:16px;z-index:1000;background:rgba(255,255,255,0.96);padding:14px;border-radius:8px;box-shadow:0 3px 10px rgba(0,0,0,0.2);min-width:230px;max-width:300px;max-height:90vh;overflow-y:auto}.ci{margin-bottom:8px;display:flex;align-items:center;cursor:pointer}.ci:last-child{margin-bottom:0}.ci input{width:18px;height:18px;margin-right:8px;cursor:pointer;flex-shrink:0}.ci label{font-size:13px;cursor:pointer}.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:middle}.sep{border-top:1px solid #ccc;margin:10px 0 8px 0}.hdr{font-size:11px;color:#666;font-weight:bold;text-transform:uppercase;margin-bottom:6px;letter-spacing:0.5px}.ebox{position:fixed;bottom:16px;right:16px;z-index:1000;background:rgba(255,255,255,0.95);padding:10px 14px;border-radius:8px;box-shadow:0 3px 10px rgba(0,0,0,0.2);font-size:12px;line-height:1.6;max-width:30vw}.ebox b{display:block;margin-bottom:4px;color:#1a5276}details>summary{list-style:none;cursor:pointer;user-select:none;font-weight:bold;font-size:13px;color:#1a5276;display:flex;align-items:center;gap:6px}details>summary::-webkit-details-marker{display:none}details>summary:before{content:'\\25B8';display:inline-block;transition:transform .15s;color:#888}details[open]>summary:before{transform:rotate(90deg)}details[open]>summary{margin-bottom:10px}.ebox .ebody{max-height:55vh;overflow-y:auto}.hint{font-size:11px;color:#888;margin:-2px 0 8px 26px}.bbox{position:fixed;bottom:16px;left:16px;z-index:1001;background:rgba(255,255,255,0.97);padding:10px 14px;border-radius:8px;box-shadow:0 3px 10px rgba(0,0,0,0.2);font-size:12px;line-height:1.5;max-width:30vw;border-left:6px solid #999}.bbox.bbok{border-left-color:#1e8449}.bbox.bbok summary{color:#1e8449}.bbox.bbfail{border-left-color:#c0392b}.bbox.bbfail summary{color:#c0392b}.bbox.bbnone{border-left-color:#b9770e}.bbox.bbnone summary{color:#9a6400}.bbox .bbbody{max-height:45vh;overflow-y:auto}.bbrow{padding:6px 0;border-top:1px solid #eee}.bbrow:first-child{border-top:0}.mut{color:#888;font-size:11px}.badt{color:#c0392b}.prow{display:flex;align-items:center;gap:6px;font-size:12px;margin-bottom:4px}.prow button{width:22px;height:22px;border:1px solid #999;border-radius:4px;background:#fff;cursor:pointer;font-weight:bold;font-size:14px;line-height:1;flex-shrink:0}.prow.off{opacity:.5}.prow.sel{background:#eaf2fb;outline:1px solid #9cc3e6;border-radius:4px}.prow .pn{cursor:pointer}.prow.off .pn{text-decoration:line-through}.prow .pd{color:#888;font-size:11px}@media (max-width:800px){.bbox,.ebox{max-width:calc(100vw - 32px)}.title{display:none}}</style></head><body>
<div class="title"><div class="addr">%s</div><div class="sub">%s</div></div><div id="plotDiv"></div>
<div class="cbox"><details open><summary>Ansicht</summary>
  <div class="hdr">Kubaturen</div>
  <div class="ci"><input type="radio" name="kubmode" id="kubOff" checked/><label for="kubOff">Aus</label></div>
  <div class="ci"><input type="radio" name="kubmode" id="kubPer"/><label for="kubPer">Pro Teil – Quader</label></div>
  <div class="ci"><input type="radio" name="kubmode" id="kubRoof"/><label for="kubRoof">Pro Teil – Dachform</label></div>
  <div class="ci"><input type="radio" name="kubmode" id="kubNet"/><label for="kubNet">Äquivalente Kubatur (NET)</label></div>
  <div class="ci"><input type="checkbox" id="showOrig"/><label for="showOrig"><span class="sw" style="background:#111"></span>Original-GML (Drahtmodell)</label></div>
  <div class="ci"><input type="checkbox" id="showBBox"/><label for="showBBox"><span class="sw" style="background:#1e8449"></span>GML-Bounding-Box prüfen</label></div>
  <div class="sep"></div>
  <div class="hdr">Beschriftung</div>
  <div class="ci"><input type="checkbox" id="showLbl"/><label for="showLbl">Abmessungen &amp; Dachtyp</label></div>
  <div class="ci"><input type="checkbox" id="showRef"/><label for="showRef"><span class="sw" style="background:magenta"></span>Referenzkanten</label></div>
  <div class="hint">gilt für die aktuelle Ansicht und alle in der Legende sichtbaren Teile; der zuletzt angeklickte Teil wird immer beschriftet</div>
  <div class="sep"></div>
  <div class="hdr">Flächen (3D)</div>
  <div class="ci"><input type="checkbox" id="showSrfFas"/><label for="showSrfFas"><span class="sw" style="background:deepskyblue"></span>Fassadenfläche</label></div>
  <div class="ci"><input type="checkbox" id="showSrfDach"/><label for="showSrfDach"><span class="sw" style="background:seagreen"></span>Dachfläche</label></div>
  <div class="ci"><input type="checkbox" id="showSrfShared"/><label for="showSrfShared"><span class="sw" style="background:crimson"></span>Gemeinsame Fläche (Original-GML)</label></div>
  <div class="ci"><input type="checkbox" id="showSrfRek"/><label for="showSrfRek"><span class="sw" style="background:#7b2cbf"></span>Gemeinsame Fläche (Rekonstruktion)</label></div>
  <div class="ci"><input type="checkbox" id="showSrfSouth"/><label for="showSrfSouth"><span class="sw" style="background:orange"></span>Süd-projizierte Fläche</label></div>
  <div class="sep"></div>
  <div class="hdr">Teile – Auswahl</div>
  <div id="partList"></div>
  <div class="hint" style="margin-left:0">Klick auf einen Teil im 3D-Modell (oder −) = nicht in die Kubatur übernehmen; nochmal klicken (oder +) = wieder aufnehmen. Ausgeschlossene Teile bleiben schwach sichtbar. Die NET-Kubatur und die Flächen bleiben auf alle Teile bezogen.</div>
  <div class="hdr" style="margin-top:8px">GML-Export (Kubatur)</div>
  <div class="ci"><select id="expGeom" style="font-size:12px;padding:2px;width:100%%"><option value="lod1">Quader (LoD1-Solid)</option><option value="lod2">Dachform (LoD2-Flächen)</option></select></div>
  <button id="expBtn" type="button" style="width:100%%;padding:6px;font-size:13px;cursor:pointer;background:#1a5276;color:#fff;border:0;border-radius:4px">Kubatur-GML exportieren</button>
  <div class="hint" id="expInfo" style="margin-left:0;margin-top:4px"></div>
</details></div>
<div class="ebox"><details><summary>Flächen / Energie</summary><div class="ebody">%s</div></details></div>
%s
<script>
var t=%s;var l=%s;var am=%s;var rmeta=%s;var ptr=%s;var pmeta=%s;var xmeta=%s;var excl={};
for(var q=0;q<t.length;q++){var o=t[q];
  if(o._bl){var s=atob(o._bl[0]),u=new Uint8Array(s.length),c;for(c=0;c<s.length;c++)u[c]=s.charCodeAt(c);
    var p=new Float32Array(u.buffer),n=o._bl[1];o.x=[];o.y=[];o.z=[];
    for(c=0;c<n;c++){var xv=p[c];if(xv!==xv){o.x.push(null);o.y.push(null);o.z.push(null);}
      else{o.x.push(xv);o.y.push(p[n+c]);o.z.push(p[2*n+c]);}}
    delete o._bl;continue;}
  if(!o._b)continue;
  var s=atob(o._b[0]),u=new Uint8Array(s.length),c;for(c=0;c<s.length;c++)u[c]=s.charCodeAt(c);var p=new Float32Array(u.buffer);
  s=atob(o._b[1]);u=new Uint8Array(s.length);for(c=0;c<s.length;c++)u[c]=s.charCodeAt(c);var f=new Uint32Array(u.buffer);
  var n=o._b[2],m=o._b[3];o.x=[];o.y=[];o.z=[];o.i=[];o.j=[];o.k=[];
  for(c=0;c<n;c++){o.x.push(p[c]);o.y.push(p[n+c]);o.z.push(p[2*n+c]);}
  for(c=0;c<m;c++){o.i.push(f[c]);o.j.push(f[m+c]);o.k.push(f[2*m+c]);}
  delete o._b;}
Plotly.newPlot('plotDiv',t,l,{responsive:true});
var gd=document.getElementById('plotDiv');
var gbb=[],srek=[],wf=[],kr=[],kt=[],ktnet=[],sfas=[],sdch=[],sshr=[],ssth=[],bmesh=[];
t.forEach(function(tr,i){
  if(tr.type==='mesh3d' && !tr.legendgroup){bmesh.push(i);}
  if(tr.legendgroup){
    if(tr.legendgroup.indexOf('netkubatur')===0){ktnet.push(i);}
    else if(tr.legendgroup.indexOf('kubatur')===0){kt.push(i);}
    else if(tr.legendgroup.indexOf('dachform')===0){kr.push(i);}
    else if(tr.legendgroup.indexOf('origwf')===0){wf.push(i);}
    else if(tr.legendgroup.indexOf('gmlbbox')===0){gbb.push(i);}
    else if(tr.legendgroup.indexOf('srffas')===0){sfas.push(i);}
    else if(tr.legendgroup.indexOf('srfdach')===0){sdch.push(i);}
    else if(tr.legendgroup.indexOf('srfshared')===0){sshr.push(i);}
    else if(tr.legendgroup.indexOf('srfrek')===0){srek.push(i);}
    else if(tr.legendgroup.indexOf('srfsouth')===0){ssth.push(i);}
  }
});
function curMode(){var md=document.querySelector('input[name=kubmode]:checked');return md?md.id:'kubOff';}
function isOn(i){if(i===undefined||i===null||!gd.data[i])return false;var v=gd.data[i].visible;return v===true||v===undefined;}
var busy=false;
// labels + reference edges follow: checkbox AND active view AND visibility of the described geometry
function updAnn(){
  if(busy)return; busy=true;
  try{
    var md=curMode(), lab=document.getElementById('showLbl').checked, rf=document.getElementById('showRef').checked;
    var an=gd.layout.scene.annotations||[], u={}, ch=false;
    for(var a=0;a<am.length;a++){
      var ap=ptr[am[a].tr];
      var v=am[a].md===md&&isOn(am[a].tr)&&((lab&&!exOf(am[a].tr))||(ap!==undefined&&ap===selP));
      if(!!an[a].visible!==v){u['scene.annotations['+a+'].visible']=v;ch=true;}
    }
    if(ch)Plotly.relayout(gd,u);
    var on=[],off=[];
    rmeta.forEach(function(r){var w=rf&&isOn(r.own[md])&&!exOf(r.tr);if(isOn(r.tr)!==w)(w?on:off).push(r.tr);});
    if(on.length)Plotly.restyle(gd,'visible',true,on);
    if(off.length)Plotly.restyle(gd,'visible',false,off);
  }finally{busy=false;}
}
gd.on('plotly_restyle',function(){setTimeout(updAnn,0);});
function updOrig(){
  var on=document.getElementById('showOrig').checked; setVis(wf,on);
  var sh=document.getElementById('showSrfShared').checked||document.getElementById('showSrfRek').checked;
  var md=document.querySelector('input[name=kubmode]:checked'); md=md?md.id:'kubOff';
  var op=((on||sh)&&(md==='kubPer'||md==='kubRoof'))?0.4:1.0;
  var rm=kt.concat(kr).filter(function(i){return t[i].type==='mesh3d';});
  if(rm.length)Plotly.restyle('plotDiv',{'opacity':rm.map(function(i){return exOf(i)?GHOST:op;})},rm);
  if(bmesh.length)Plotly.restyle('plotDiv',{'opacity':bmesh.map(function(i){return exOf(i)?GHOST:(sh?0.25:1.0);})},bmesh);
}
// an excluded Teil: its solids stay as a faint ghost (still clickable to take
// it back), its edges / wireframe / reference edge / label are hidden
var GHOST=0.12, selP=null, armed=false;
function exOf(i){var p=ptr[i];return p!==undefined&&!!excl[p];}
function setVis(idxs,vis){
  if(idxs.length===0)return;
  Plotly.restyle('plotDiv','visible',idxs.map(function(i){return vis&&!(exOf(i)&&t[i].type!=='mesh3d');}),idxs);
}
function applyMode(md,user){
  if(md==='kubOff'){setVis(kr,false);setVis(kt,false);setVis(ktnet,false);setVis(bmesh,true);}
  else if(md==='kubPer'){setVis(kr,false);setVis(kt,true);setVis(ktnet,false);setVis(bmesh,false);if(user)document.getElementById('showOrig').checked=true;}
  else if(md==='kubNet'){setVis(kr,false);setVis(kt,false);setVis(ktnet,true);setVis(bmesh,true);}
  else if(md==='kubRoof'){setVis(kt,false);setVis(ktnet,false);setVis(kr,true);setVis(bmesh,false);if(user)document.getElementById('showOrig').checked=true;}
  updOrig();updAnn();
}
document.getElementById('showLbl').addEventListener('change',updAnn);
document.getElementById('showRef').addEventListener('change',updAnn);
['kubOff','kubPer','kubNet','kubRoof'].forEach(function(id){
  document.getElementById(id).addEventListener('change',function(){if(this.checked)applyMode(id,true);});});
// ---- Teile: exclude / include ----
function nIncl(){return pmeta.filter(function(m){return !excl[m.p];}).length;}
function renderParts(){
  var el=document.getElementById('partList');el.innerHTML='';
  pmeta.forEach(function(m){
    var r=document.createElement('div');r.className='prow'+(excl[m.p]?' off':'')+(m.p===selP?' sel':'');
    var b=document.createElement('button');b.type='button';b.textContent=excl[m.p]?'+':'\u2212';
    b.title=excl[m.p]?'Teil wieder aufnehmen':'Teil ausschließen';
    b.addEventListener('click',function(){togglePart(m.p);});
    var sw=document.createElement('span');sw.className='sw';sw.style.background=m.clr;
    var n=document.createElement('span');n.className='pn';n.textContent='Teil '+m.p;n.title='Teil beschriften';
    n.addEventListener('click',function(){selP=(selP===m.p)?null:m.p;renderParts();updAnn();});
    var d=document.createElement('span');d.className='pd';
    d.textContent=m.l.toFixed(1)+'\u00d7'+m.w.toFixed(1)+'\u00d7'+m.h.toFixed(1)+' m';
    r.appendChild(b);r.appendChild(sw);r.appendChild(n);r.appendChild(d);el.appendChild(r);});
  var ex=pmeta.length-nIncl();
  document.getElementById('expInfo').textContent=nIncl()+' von '+pmeta.length+' Teilen im Export'+(ex?' ('+ex+' ausgeschlossen)':'');
}
function togglePart(p){
  excl[p]=!excl[p];selP=p;
  applyMode(curMode(),false);renderParts();
}
// click on a Teil in the 3D view (building, Quader or Dachform) = -/+
gd.on('plotly_click',function(ev){
  if(!ev||!ev.points||!ev.points.length)return;
  var p=ptr[ev.points[0].curveNumber];
  if(p===undefined||!pmeta.some(function(m){return m.p===p;}))return;
  if(!armed)return; armed=false;              // Plotly repeats the event while the button is held
  setTimeout(function(){togglePart(p);},0);   // not inside Plotly's render callback
});
gd.addEventListener('pointerdown',function(){armed=true;},true);
// ---- Kubatur GML (CityGML 2.0) of the included Teile ----
function xe(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
var off=xmeta.off,bmin=null,bmax=null;
function pos(q){var w=[q[0]+off[0],q[1]+off[1],q[2]+off[2]];
  if(!bmin){bmin=w.slice();bmax=w.slice();}else{for(var a=0;a<3;a++){if(w[a]<bmin[a])bmin[a]=w[a];if(w[a]>bmax[a])bmax[a]=w[a];}}
  return w[0].toFixed(3)+' '+w[1].toFixed(3)+' '+w[2].toFixed(3);}
function poly(pts){return '<gml:Polygon><gml:exterior><gml:LinearRing><gml:posList srsDimension="3">'+
  pts.concat([pts[0]]).map(pos).join(' ')+'</gml:posList></gml:LinearRing></gml:exterior></gml:Polygon>';}
function cuboidXml(m){
  var tr=gd.data[m.kt],c=[];for(var q=0;q<8;q++)c.push([tr.x[q],tr.y[q],tr.z[q]]);
  var f=[[c[0],c[3],c[2],c[1]],[c[4],c[5],c[6],c[7]]];
  for(var a=0;a<4;a++){var b=(a+1)%%4;f.push([c[a],c[b],c[b+4],c[a+4]]);}
  return '<bldg:lod1Solid><gml:Solid><gml:exterior><gml:CompositeSurface>'+
    f.map(function(p){return '<gml:surfaceMember>'+poly(p)+'</gml:surfaceMember>';}).join('')+
    '</gml:CompositeSurface></gml:exterior></gml:Solid></bldg:lod1Solid>';}
function roofXml(m){
  if(!m.rf||!m.rf.length)return '';
  var g={RoofSurface:[],WallSurface:[],GroundSurface:[]};
  m.rf.forEach(function(f){if(g[f[0]])g[f[0]].push(f[1]);});
  var s='';
  ['RoofSurface','WallSurface','GroundSurface'].forEach(function(ty){if(!g[ty].length)return;
    s+='<bldg:boundedBy><bldg:'+ty+'><bldg:lod2MultiSurface><gml:MultiSurface>'+
      g[ty].map(function(p){return '<gml:surfaceMember>'+poly(p)+'</gml:surfaceMember>';}).join('')+
      '</gml:MultiSurface></bldg:lod2MultiSurface></bldg:'+ty+'></bldg:boundedBy>';});
  return s;}
function partXml(m,tag,mode){
  var id=m.id||('Kubatur_Teil_'+m.p),lod2=(mode!=='lod1')&&!!(m.rf&&m.rf.length);
  var s='<bldg:'+tag+' gml:id="'+xe(id)+'"><gml:name>Kubatur Teil '+m.p+'</gml:name>'+
    '<gen:stringAttribute name="Kubatur_Teil"><gen:value>'+m.p+'</gen:value></gen:stringAttribute>'+
    '<gen:doubleAttribute name="Kubatur_Laenge"><gen:value>'+m.l+'</gen:value></gen:doubleAttribute>'+
    '<gen:doubleAttribute name="Kubatur_Breite"><gen:value>'+m.w+'</gen:value></gen:doubleAttribute>'+
    '<gen:doubleAttribute name="Kubatur_Hoehe"><gen:value>'+m.h+'</gen:value></gen:doubleAttribute>'+
    '<gen:doubleAttribute name="Kubatur_Volumen"><gen:value>'+m.v+'</gen:value></gen:doubleAttribute>';
  if(lod2&&m.rt)s+='<bldg:roofType>'+xe(m.rt)+'</bldg:roofType>';
  s+='<bldg:measuredHeight uom="m">'+(lod2?m.rh:m.h)+'</bldg:measuredHeight>'+
     '<bldg:storeysAboveGround>'+m.s+'</bldg:storeysAboveGround>';
  s+=lod2?roofXml(m):cuboidXml(m);   // Dachform missing -> Quader
  return s+'</bldg:'+tag+'>';}
function exportGml(){
  var mode=document.getElementById('expGeom').value,inc=pmeta.filter(function(m){return !excl[m.p];});
  if(!inc.length){alert('Alle Teile sind ausgeschlossen – nichts zu exportieren.');return;}
  bmin=null;bmax=null;var groups=[],byPid={};
  inc.forEach(function(m){if(m.pid){if(!byPid[m.pid]){byPid[m.pid]={pid:m.pid,parts:[]};groups.push(byPid[m.pid]);}byPid[m.pid].parts.push(m);}
    else groups.push({pid:null,parts:[m]});});
  var body=groups.map(function(gp){
    if(!gp.pid)return '<core:cityObjectMember>'+partXml(gp.parts[0],'Building',mode)+'</core:cityObjectMember>';
    return '<core:cityObjectMember><bldg:Building gml:id="'+xe(gp.pid)+'">'+gp.parts.map(function(m){
      return '<bldg:consistsOfBuildingPart>'+partXml(m,'BuildingPart',mode)+'</bldg:consistsOfBuildingPart>';}).join('')+
      '</bldg:Building></core:cityObjectMember>';}).join('\\n');
  var srs=xmeta.srs?' srsName="'+xe(xmeta.srs)+'"':'';
  var ex=pmeta.filter(function(m){return excl[m.p];}).map(function(m){return m.p;});
  var x='<?xml version="1.0" encoding="UTF-8"?>\\n'+
    '<core:CityModel xmlns:core="http://www.opengis.net/citygml/2.0" xmlns:bldg="http://www.opengis.net/citygml/building/2.0" '+
    'xmlns:gen="http://www.opengis.net/citygml/generics/2.0" xmlns:gml="http://www.opengis.net/gml" '+
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '+
    'xsi:schemaLocation="http://www.opengis.net/citygml/building/2.0 http://schemas.opengis.net/citygml/building/2.0/building.xsd '+
    'http://www.opengis.net/citygml/generics/2.0 http://schemas.opengis.net/citygml/generics/2.0/generics.xsd">\\n'+
    '<!-- Kubatur-Export: '+inc.length+' von '+pmeta.length+' Teilen'+(ex.length?', ausgeschlossen: Teil '+ex.join(', '):'')+
    ', Geometrie: '+mode+' -->\\n';
  var bb='';   // envelope needs the coordinates, so the body is written first
  x+='<gml:name>Kubatur'+(xmeta.addr.length?' '+xe(xmeta.addr[0]):'')+'</gml:name>\\n';
  bb='<gml:boundedBy><gml:Envelope'+srs+' srsDimension="3"><gml:lowerCorner>'+bmin.map(function(v){return v.toFixed(3);}).join(' ')+
     '</gml:lowerCorner><gml:upperCorner>'+bmax.map(function(v){return v.toFixed(3);}).join(' ')+'</gml:upperCorner></gml:Envelope></gml:boundedBy>\\n';
  x+=bb+body+'\\n</core:CityModel>\\n';
  var fn='Kubatur'+(xmeta.addr.length?'_'+xmeta.addr[0].replace(/[^A-Za-z0-9\\u00c0-\\u017f]+/g,'_').replace(/^_+|_+$/g,''):'')+'.gml';
  // inside a FileMaker Web Viewer: hand the GML text to a FileMaker script
  // (it stores it in a text field); anywhere else: download it as a file
  if(window.FileMaker&&typeof window.FileMaker.PerformScript==='function'){
    try{window.FileMaker.PerformScript(xmeta.fms,x);
      document.getElementById('expInfo').textContent='An FileMaker übergeben (Script \u201e'+xmeta.fms+'\u201c): '+inc.length+' Teile, '+Math.round(x.length/1024)+' kB';}
    catch(e){alert('FileMaker-Script \u201e'+xmeta.fms+'\u201c konnte nicht ausgeführt werden: '+e);}
    return;}
  var a=document.createElement('a');a.href=URL.createObjectURL(new Blob([x],{type:'application/gml+xml'}));a.download=fn;
  document.body.appendChild(a);a.click();setTimeout(function(){URL.revokeObjectURL(a.href);a.remove();},1000);
}
document.getElementById('expBtn').addEventListener('click',exportGml);
renderParts();
document.getElementById('showOrig').addEventListener('change',function(){updOrig();});
document.getElementById('showBBox').addEventListener('change',function(){setVis(gbb,this.checked);});
document.getElementById('showSrfFas').addEventListener('change',function(){setVis(sfas,this.checked);});
document.getElementById('showSrfDach').addEventListener('change',function(){setVis(sdch,this.checked);});
document.getElementById('showSrfShared').addEventListener('change',function(){setVis(sshr,this.checked);updOrig();});
document.getElementById('showSrfRek').addEventListener('change',function(){setVis(srek,this.checked);updOrig();});
document.getElementById('showSrfSouth').addEventListener('change',function(){setVis(ssth,this.checked);});
window.addEventListener('resize',function(){Plotly.Plots.resize('plotDiv')});
if(gbb.length&&document.querySelector('.bbox.bbfail')){document.getElementById('showBBox').checked=true;setVis(gbb,true);}
updAnn();
</script></body></html>"""
html_out = html_tpl % (_addr_html, tt, eh, _bb_html, tj, lj, amj, rmj, ptj, pmj, exj)
print(f"\nHTML generated: {len(html_out)/1e6:.2f} MB")


with open(out_path, 'w', encoding='utf-8') as f: f.write(html_out)
print(f"\nHTML: {out_path}")
webbrowser.open('file://' + os.path.abspath(out_path))
