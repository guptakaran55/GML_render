"""
Bounding-box check over several GML files (no rendering, no Kubatur calculation).

The first file is the Kubatur file (the one shown in the 3D viewer). For every
file - the Kubatur file included - two things are checked:
  1) its own gml:Envelope / gml:Box against the coordinates of the buildings
     they describe (same rule as the check in gml_core.py)
  2) every building against the bounding box of the Kubatur file: its
     CityModel envelope, or - if it declares none - its real coordinate extent
Additionally, LBB numbers (we_nr / ge_nr) that are used by several different
building IDs across the files are reported.
"""
import re
import html
import xml.etree.ElementTree as ET
from collections import defaultdict

import numpy as np


def _ln(el):
    """Lower-case local name of an element or attribute name."""
    t = el if isinstance(el, str) else el.tag
    return (t.split('}', 1)[1] if '}' in t else t).lower()


def _parse(text):
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        pass
    # same last-resort fallback as gml_core.py: drop all namespace prefixes
    s = re.sub(r'\s+xmlns(:\w+)?="[^"]*"', '', text)
    s = re.sub(r'<(/?)(\w+):', r'<\1', s)
    s = re.sub(r'\s(\w+):(\w+)=', r' \2=', s)
    try:
        return ET.fromstring(s)
    except ET.ParseError as e:
        raise ValueError(f"kein lesbares GML/XML: {e}")


def _floats(text):
    return [float(v) for v in text.split()]


def _coords(el, id_index, skip):
    """All coordinates below el (following local xlink:hrefs), as an (n, 3) array."""
    pts = []
    stack, seen = [el], set()
    while stack:
        e = stack.pop()
        if id(e) in seen or id(e) in skip:
            continue
        seen.add(id(e))
        n = _ln(e)
        txt = e.text.strip() if e.text else ''
        if n in ('poslist', 'pos', 'coordinates'):
            if not txt:
                continue
            try:
                if n == 'coordinates':
                    rows = [[float(v) for v in tok.split(',')] for tok in txt.split()]
                else:
                    nums = _floats(txt)
                    dim = int(e.get('srsDimension') or 0) or (3 if len(nums) % 3 == 0 else 2)
                    if n == 'pos':
                        dim = len(nums)
                    if dim < 2 or len(nums) % dim:
                        continue
                    rows = [nums[i:i + dim] for i in range(0, len(nums), dim)]
            except ValueError:
                continue
            for r in rows:
                if len(r) >= 2:
                    pts.append((r + [0.0])[:3])
            continue
        for a, v in e.attrib.items():
            if _ln(a) == 'href' and v.startswith('#') and v[1:] in id_index:
                stack.append(id_index[v[1:]])
        stack.extend(e)
    return np.array(pts, dtype=float).reshape(-1, 3)


def _box_test(lo, hi, P, tol):
    """Which points of P lie outside the box lo..hi (2D or 3D)?"""
    d = len(lo)
    Q = P[:, :d]
    if not len(Q):
        return {'n_pts': 0, 'n_out': 0, 'ok': True, 'max_exceed': [0.0] * d, 'axis_swapped': False}
    exc = np.maximum(np.maximum(lo[None, :] - Q, Q - hi[None, :]), 0.0)
    out = np.any(exc > tol, axis=1)
    n_out = int(out.sum())
    swap = False
    if n_out and d >= 2:
        S = Q.copy()
        S[:, [0, 1]] = S[:, [1, 0]]
        swap = bool(np.all(S >= lo[None, :] - tol) and np.all(S <= hi[None, :] + tol))
    return {'n_pts': int(len(Q)), 'n_out': n_out, 'ok': n_out == 0,
            'max_exceed': exc.max(0).tolist(), 'axis_swapped': swap}


def _generic_attrs(el):
    d = {}
    for a in el:
        if not _ln(a).endswith('attribute') or not a.get('name'):
            continue
        for v in a:
            if _ln(v) == 'value' and v.text and v.text.strip():
                d[a.get('name')] = v.text.strip()
                break
    return d


def _epsg(srs):
    m = re.findall(r'\d{4,6}', srs or '')
    return m[-1] if m else None


def analyse(name, text):
    """Parse one GML file: buildings with their coordinates and all envelopes."""
    root = _parse(text)
    parent = {}
    id_index = {}
    skip = set()
    srs = None
    for e in root.iter():
        for c in e:
            parent[id(c)] = e
        for a, v in e.attrib.items():
            la = _ln(a)
            if la == 'id':
                id_index[v] = e
            elif la == 'srsname' and srs is None:
                srs = v
        if _ln(e) in ('envelope', 'box'):
            skip.add(id(e))

    buildings = []
    bpts = {}
    for e in root.iter():
        if _ln(e) != 'building':
            continue
        P = _coords(e, id_index, skip)
        bpts[id(e)] = P
        attrs = _generic_attrs(e)
        buildings.append({
            'el': e, 'pts': P, 'id': e.get('{http://www.opengis.net/gml}id') or e.get('id') or '',
            'alkis': attrs.get('alkis_oid'), 'we_nr': attrs.get('we_nr'), 'ge_nr': attrs.get('ge_nr'),
            'ge_bez': attrs.get('ge_bez'),
            'parts': sum(1 for x in e.iter() if _ln(x) == 'buildingpart'),
        })
    all_pts = [b['pts'] for b in buildings if len(b['pts'])]
    P_all = np.vstack(all_pts) if all_pts else np.zeros((0, 3))
    degrees = bool(len(P_all) and np.all(np.abs(P_all[:, :2]) <= 360.0))
    tol = 1e-7 if degrees else 0.01

    envelopes = []
    for env in root.iter():
        if id(env) not in skip:
            continue
        lo = hi = None
        poss = []
        for c in env:
            n = _ln(c)
            t = c.text.strip() if c.text else ''
            if not t:
                continue
            try:
                if n == 'lowercorner':
                    lo = _floats(t)
                elif n == 'uppercorner':
                    hi = _floats(t)
                elif n == 'pos':
                    poss.append(_floats(t))
                elif n == 'coordinates':
                    poss.extend([float(v) for v in tok.split(',')] for tok in t.split())
            except ValueError:
                pass
        if (lo is None or hi is None) and len(poss) >= 2:
            lo, hi = poss[0], poss[1]
        if lo is None or hi is None or len(lo) < 2 or len(hi) < 2:
            continue
        d = min(len(lo), len(hi), 3)
        lo, hi = np.array(lo[:d]), np.array(hi[:d])
        lo, hi = np.minimum(lo, hi), np.maximum(lo, hi)

        # scope: the element owning <gml:boundedBy><gml:Envelope>
        bby = parent.get(id(env))
        owner = parent.get(id(bby)) if bby is not None else None
        if owner is None:
            owner = root
        if _ln(owner) in ('building', 'buildingpart'):
            P = bpts.get(id(owner))
            if P is None:
                P = _coords(owner, id_index, skip)
        else:
            inside = [bpts[id(x)] for x in owner.iter() if id(x) in bpts and len(bpts[id(x)])]
            if not inside:
                continue                    # envelope of a non-building object
            P = np.vstack(inside)
        oid = owner.get('{http://www.opengis.net/gml}id') or owner.get('id') or ''
        otag = owner.tag.split('}', 1)[-1]
        scope = f"{otag} (gesamte Datei)" if owner is root else f"{otag} {oid}".strip()
        envelopes.append({'scope': scope, 'root': owner is root, 'srs': env.get('srsName') or srs,
                          'lower': lo, 'upper': hi, **_box_test(lo, hi, P, tol)})

    return {
        'name': name, 'error': None, 'srs': srs, 'epsg': _epsg(srs), 'degrees': degrees, 'tol': tol,
        'buildings': buildings, 'envelopes': envelopes,
        'own_status': 'none' if not envelopes else ('ok' if all(e['ok'] for e in envelopes) else 'fail'),
        'extent': (P_all.min(0), P_all.max(0)) if len(P_all) else None,
    }


def check_files(files, has_kubatur=True):
    """files: list of (filename, gml_text); the first one is the Kubatur file
    unless has_kubatur is False (then only each file's own bounding box is checked)."""
    results = []
    for name, text in files:
        try:
            results.append(analyse(name, text))
        except Exception as exc:
            results.append({'name': name, 'error': str(exc), 'buildings': [], 'envelopes': [],
                            'own_status': 'error', 'kub_status': 'error', 'notes': []})

    kub = results[0] if has_kubatur else None
    ref = None
    if kub and not kub['error']:
        root_env = [e for e in kub['envelopes'] if e['root']]
        if root_env:
            e = root_env[0]
            ref = {'lower': e['lower'], 'upper': e['upper'],
                   'source': 'CityModel-Envelope der Kubatur-Datei'}
        elif kub['extent'] is not None:
            ref = {'lower': kub['extent'][0], 'upper': kub['extent'][1],
                   'source': 'tatsächliche Ausdehnung der Kubatur-Datei (sie enthält keine CityModel-Envelope)'}
        if ref:
            ref.update(epsg=kub['epsg'], degrees=kub['degrees'], tol=kub['tol'])

    for r in results:
        if r['error']:
            continue
        r['notes'] = []
        if ref is None:
            r['kub_status'] = 'none'
            continue
        if r is not kub:
            if r['epsg'] and ref['epsg'] and r['epsg'] != ref['epsg']:
                r['notes'].append(f"anderes Koordinatensystem (EPSG {r['epsg']} statt {ref['epsg']}) - Vergleich nicht aussagekräftig")
            if r['degrees'] != ref['degrees']:
                r['notes'].append("Koordinaten in anderer Einheit (Grad / Meter) als die Kubatur-Datei")
        for b in r['buildings']:
            t = _box_test(ref['lower'], ref['upper'], b['pts'], ref['tol'])
            b['kub'] = t
            b['kub_status'] = ('leer' if not t['n_pts'] else 'innerhalb' if t['ok']
                               else 'außerhalb' if t['n_out'] == t['n_pts'] else 'teilweise')
        if not r['buildings']:
            r['kub_status'] = 'none'
        else:
            r['kub_status'] = 'ok' if all(b['kub']['ok'] for b in r['buildings']) else 'fail'

    # LBB number used by different building IDs (across all files)
    groups = defaultdict(list)
    for r in results:
        for b in r['buildings']:
            if b['we_nr'] and b['ge_nr']:
                groups[(b['we_nr'], b['ge_nr'])].append((r['name'], b['id']))
    lbb_dups = {k: v for k, v in groups.items() if len({i for _, i in v}) > 1}

    for r in results:                       # drop the heavy parts, keep the report data
        for b in r['buildings']:
            b.pop('el', None)
            b.pop('pts', None)
    return {'files': results, 'ref': ref, 'lbb_dups': lbb_dups, 'has_kubatur': has_kubatur,
            'status': 'fail' if any(r['own_status'] in ('fail', 'error') or r.get('kub_status') == 'fail'
                                    for r in results) else 'ok'}


# -------------------------------------------------------------------------
# report output
# -------------------------------------------------------------------------
def _fmt(v, deg):
    return f"{v:.7f}" if deg else f"{v:.3f}"


def _exceed(t, deg):
    return ' '.join(f"{'XYZ'[a]}+{_fmt(v, deg)}" for a, v in enumerate(t['max_exceed']) if v > 0)


_BADGE = {'ok': ('ok', 'OK'), 'fail': ('bad', 'FEHLER'), 'none': ('mut', 'keine'), 'error': ('bad', 'Lesefehler'),
          'innerhalb': ('ok', 'innerhalb'), 'teilweise': ('bad', 'teilweise außerhalb'),
          'außerhalb': ('bad', 'außerhalb'), 'leer': ('mut', 'keine Geometrie')}


def _badge(s):
    cls, txt = _BADGE.get(s, ('mut', s))
    return f"<span class='b {cls}'>{txt}</span>"


def report_html(rep):
    esc = html.escape
    ref = rep['ref']
    rows, details = [], []
    for i, r in enumerate(rep['files']):
        kub_cell = "<span class='mut'>Referenz</span>" if i == 0 and ref else _badge(r.get('kub_status', 'none'))
        if r['error']:
            rows.append(f"<tr><td>{esc(r['name'])}</td><td>–</td><td>{_badge('error')}</td><td>–</td>"
                        f"<td>{esc(r['error'])}</td></tr>")
            continue
        n_bad = sum(1 for b in r['buildings'] if 'kub' in b and not b['kub']['ok'])
        notes = list(r['notes'])
        if n_bad:
            notes.insert(0, f"{n_bad} von {len(r['buildings'])} Gebäuden nicht in der Kubatur-BBox")
        tag = " <span class='mut'>(Kubatur)</span>" if i == 0 and rep['has_kubatur'] else ''
        rows.append(f"<tr><td>{esc(r['name'])}{tag}</td>"
                    f"<td>{len(r['buildings'])}</td><td>{_badge(r['own_status'])}</td><td>{kub_cell}</td>"
                    f"<td>{'<br>'.join(esc(n) for n in notes)}</td></tr>")

        d = r['degrees']
        env_rows = ''.join(
            f"<tr><td>{esc(e['scope'])}</td><td>{_badge('ok' if e['ok'] else 'fail')}</td>"
            f"<td>{e['n_out']} / {e['n_pts']}</td><td>{_exceed(e, d) or '–'}"
            f"{'<br><b>passt mit vertauschten X/Y-Achsen</b>' if e['axis_swapped'] else ''}</td></tr>"
            for e in r['envelopes']) or "<tr><td colspan=4 class='mut'>keine gml:Envelope / gml:Box zu Gebäuden</td></tr>"
        b_rows = ''.join(
            f"<tr><td>{esc(b['id'] or '–')}</td><td>{esc(b['alkis'] or '–')}</td>"
            f"<td>{esc('-'.join(x for x in (b['we_nr'], b['ge_nr']) if x) or '–')} {esc(b['ge_bez'] or '')}</td>"
            f"<td>{b['parts']}</td>"
            + (f"<td>{_badge(b['kub_status'])}</td><td>{b['kub']['n_out']} / {b['kub']['n_pts']}</td>"
               f"<td>{_exceed(b['kub'], d) or '–'}</td>" if 'kub' in b else "<td colspan=3 class='mut'>–</td>")
            + "</tr>"
            for b in r['buildings'])
        details.append(f"""
<details{' open' if r['own_status'] == 'fail' or r.get('kub_status') == 'fail' else ''}>
  <summary>{esc(r['name'])}</summary>
  <p class='mut'>Koordinatensystem: {esc(r['srs'] or 'nicht angegeben')} · Toleranz {r['tol']:g}{'°' if d else ' m'}</p>
  <h3>Eigene Bounding-Box(en)</h3>
  <table><tr><th>Gilt für</th><th>Status</th><th>Punkte außerhalb</th><th>max. Überschreitung</th></tr>{env_rows}</table>
  <h3>Gebäude in der Kubatur-Bounding-Box</h3>
  <table><tr><th>Building-ID</th><th>ALKIS</th><th>LBB</th><th>Teile</th><th>Status</th><th>Punkte außerhalb</th><th>max. Überschreitung</th></tr>{b_rows}</table>
</details>""")

    if ref:
        dg = ref['degrees']
        ref_html = (f"<p><b>Kubatur-Bounding-Box</b> ({esc(ref['source'])}):<br>"
                    f"min ({', '.join(_fmt(v, dg) for v in ref['lower'])}) · "
                    f"max ({', '.join(_fmt(v, dg) for v in ref['upper'])})"
                    f"{' · nur X/Y (2D-Box)' if len(ref['lower']) == 2 else ''}</p>")
    elif not rep['has_kubatur']:
        ref_html = ("<p class='mut'>Keine Kubatur-Datei hochgeladen – geprüft wird nur die eigene Bounding Box "
                    "jeder Datei. Für den Vergleich mit der Kubatur-Bounding-Box zusätzlich die Kubatur-GML hochladen.</p>")
    else:
        ref_html = "<p class='bad'>Die Kubatur-Datei liefert keine Bounding-Box – der Vergleich ist nicht möglich.</p>"
    dup_html = ''.join(
        f"<div class='warn'><b>LBB {esc(we)}-{esc(ge)}</b> ist {len({i for _, i in v})} verschiedenen Building-IDs "
        f"zugeordnet: " + ', '.join(f"{esc(bid)} <span class='mut'>({esc(fn)})</span>" for fn, bid in v) + "</div>"
        for (we, ge), v in rep['lbb_dups'].items())
    head = ("✓ Alle Dateien bestanden" if rep['status'] == 'ok'
            else "✗ Mindestens eine Datei hat Bounding-Box-Fehler")

    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bounding-Box-Prüfung</title>
<style>
  :root{{--bg:#f4f5f2;--card:#fff;--ink:#1d2321;--mut:#6b726f;--line:#dfe2dc;--acc:#1f5f4a;--ok:#1e8449;--okbg:#e6f4ea;--bad:#b03a2e;--badbg:#fbeceb;--wbg:#fdf3dc}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 "Segoe UI",system-ui,-apple-system,Arial,sans-serif;padding:24px 16px}}
  .wrap{{max-width:1100px;margin:0 auto}}
  h1{{font-size:22px;margin:0 0 4px}} h3{{font-size:14px;margin:16px 0 6px}}
  .card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-top:16px;overflow-x:auto}}
  table{{border-collapse:collapse;width:100%}} th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}}
  th{{font-size:12px;color:var(--mut);font-weight:600}}
  .b{{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;font-weight:600;white-space:nowrap}}
  .b.ok{{background:var(--okbg);color:var(--ok)}} .b.bad{{background:var(--badbg);color:var(--bad)}} .b.mut{{background:#eee;color:var(--mut)}}
  .mut{{color:var(--mut)}} .bad{{color:var(--bad)}}
  .head{{font-size:16px;font-weight:600;color:{'var(--ok)' if rep['status'] == 'ok' else 'var(--bad)'}}}
  details{{border-top:1px solid var(--line);padding:10px 0}} summary{{cursor:pointer;font-weight:600}}
  .warn{{background:var(--wbg);border-radius:8px;padding:8px 12px;margin-top:8px}}
  a{{color:var(--acc)}}
</style></head><body><div class="wrap">
<h1>Bounding-Box-Prüfung · {len(rep['files'])} Dateien</h1>
<div class="head">{head}</div>
<div class="card">{ref_html}
<table><tr><th>Datei</th><th>Gebäude</th><th>eigene BBox</th><th>in Kubatur-BBox</th><th>Hinweise</th></tr>{''.join(rows)}</table>
{dup_html}</div>
<div class="card">{''.join(details)}</div>
<p class="mut">„eigene BBox“: enthalten die gml:Envelope / gml:Box der Datei alle Koordinaten der Gebäude, die sie beschreiben?
„in Kubatur-BBox“: liegen alle Koordinaten jedes Gebäudes innerhalb der Bounding-Box der Kubatur-Datei?
<br><a href="/pruefung">Neue Dateien prüfen</a> · <a href="/">3D-Kubatur</a></p>
</div></body></html>"""
