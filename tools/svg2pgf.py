#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Alain Matthes
# SPDX-License-Identifier: LPPL-1.3c
# Maintainer: Alain Matthes
"""
svg2pgf.py -- convert SVG drawings into ornament files for pgfornament.

Output format (the short macros defined by \\pgfornament@shortcuts):
    \\m x y            moveto            \\l x y         lineto
    \\c x1 y1 x2 y2 x y  curveto           \\o             closepath
    \\s                fill and stroke   \\k             stroke only
    \\pgfusepathqfill  fill only (svg elements without stroke: thin gaps stay open)
    \\r 0 0 W H + \\ubb  exact bounding box (first lines of each file)
Coordinates are in bp, origin at the lower left corner of the drawing.

Usage
-----
  A sheet with several ornaments (eps, pdf or svg):
      python3 svg2pgf.py --family celtic --split pack.eps
      -> look at build/test-celtic.pdf, then e.g. --skip 1,2 to drop texts
  One file:
      python3 svg2pgf.py ornament.svg -o pgfornament-myfam1.pgf --height 60
  A whole family (all SVG files of a folder, in alphabetical order):
      python3 svg2pgf.py --family myfam --out-dir build svgs/*.svg --height 60
    -> build/generic/myfam/pgfornament-myfam1.pgf, pgfornament-myfam2.pgf, ...
       build/latex/pgfornament-lib-myfam.code.tex  (table \\@pgfornamentDim)
       build/test-myfam.tex                   (catalogue to check the result)

Options
-------
  --width W / --height H   scale the drawing to this width / height (bp)
  --scale S                otherwise: 1 SVG unit = S bp (default 0.75 : 1px = 0.75bp,
                           1 for eps/pdf files)
  --digits N               decimals in the output (default 2)
  --source TEXT            text written in the header (origin, licence)
  --split                  the svg is a sheet with several ornaments (needs --family):
                           one file per group of overlapping shapes, in reading
                           order; small groups (texts, logos) are dropped
  --min-size F             with --split: minimal size relative to the largest
                           ornament (default 0.25)
  --skip 1,2               leave out these parts (numbers shown by a first run)
  --keep-white             keep white elements (by default they are ignored:
                           pgfornament draws with only one colour, so a white
                           background would become a black rectangle)

Input: .svg files, or .eps / .ps / .pdf files (first page) if ghostscript
and pdftocairo are installed (TeX Live provides neither; MacTeX includes gs,
pdftocairo comes with poppler: brew install poppler).

Supported: <path> (all commands, arcs included), <rect> (rounded corners),
<circle>, <ellipse>, <line>, <polyline>, <polygon>, <g>, <use>, nested
transform attributes, fill-rule evenodd, fill="none" (stroke only).
CSS: style attribute and simple <style> rules (.class, #id, tag) are read.
Ignored: <defs> content (except through <use>), <clipPath>, <mask>, text,
images, gradients (a gradient fill is treated as a plain fill),
display:none / visibility:hidden elements.

Licence: LPPL 1.3c -- Alain Matthes (pgfornament).
"""
import argparse
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

SVGNS = '{http://www.w3.org/2000/svg}'
XLINK = '{http://www.w3.org/1999/xlink}href'

# --------------------------------------------------------------------------
#  affine transforms  (a b c d e f) : x' = a x + c y + e ; y' = b x + d y + f
# --------------------------------------------------------------------------
IDENT = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def mul(m, n):
    """m o n (apply n first, then m)"""
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return (a * A + c * B, b * A + d * B,
            a * C + c * D, b * C + d * D,
            a * E + c * F + e, b * E + d * F + f)


def apply(m, p):
    a, b, c, d, e, f = m
    x, y = p
    return (a * x + c * y + e, b * x + d * y + f)


NUM = r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?'


def parse_transform(s):
    m = IDENT
    if not s:
        return m
    for name, args in re.findall(r'(\w+)\s*\(([^)]*)\)', s):
        v = [float(x) for x in re.findall(NUM, args)]
        if name == 'matrix' and len(v) == 6:
            t = tuple(v)
        elif name == 'translate':
            t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == 'scale':
            sx = v[0]
            sy = v[1] if len(v) > 1 else sx
            t = (sx, 0, 0, sy, 0, 0)
        elif name == 'rotate':
            r = math.radians(v[0])
            co, si = math.cos(r), math.sin(r)
            t = (co, si, -si, co, 0, 0)
            if len(v) == 3:
                cx, cy = v[1], v[2]
                t = mul((1, 0, 0, 1, cx, cy), mul(t, (1, 0, 0, 1, -cx, -cy)))
        elif name == 'skewX':
            t = (1, 0, math.tan(math.radians(v[0])), 1, 0, 0)
        elif name == 'skewY':
            t = (1, math.tan(math.radians(v[0])), 0, 1, 0, 0)
        else:
            continue
        m = mul(m, t)
    return m


# --------------------------------------------------------------------------
#  geometry : a path = list of subpaths ; subpath = [start, [segments], closed]
#  segment = ('L', p) or ('C', p1, p2, p)
# --------------------------------------------------------------------------
def arc_to_cubics(p0, rx, ry, phi, large, sweep, p):
    """SVG elliptical arc -> list of ('C', c1, c2, end)  (SVG 1.1 F.6)"""
    x1, y1 = p0
    x2, y2 = p
    if (x1, y1) == (x2, y2):
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [('L', p)]
    ph = math.radians(phi)
    cp, sp = math.cos(ph), math.sin(ph)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p = cp * dx + sp * dy
    y1p = -sp * dx + cp * dy
    lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        co = -co
    cxp = co * rx * y1p / ry
    cyp = -co * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (x1 + x2) / 2
    cy = sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a
    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry,
             (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    n = max(1, int(math.ceil(abs(dt) / (math.pi / 2) - 1e-9)))
    d = dt / n
    k = 4 / 3 * math.tan(d / 4)
    out = []

    def pt(t):
        return (cx + rx * math.cos(t) * cp - ry * math.sin(t) * sp,
                cy + rx * math.cos(t) * sp + ry * math.sin(t) * cp)

    def der(t):
        return (-rx * math.sin(t) * cp - ry * math.cos(t) * sp,
                -rx * math.sin(t) * sp + ry * math.cos(t) * cp)
    t = t1
    for i in range(n):
        a, b = t, t + d
        pa, pb = pt(a), pt(b)
        da, db = der(a), der(b)
        c1 = (pa[0] + k * da[0], pa[1] + k * da[1])
        c2 = (pb[0] - k * db[0], pb[1] - k * db[1])
        if i == n - 1:
            pb = p
        out.append(('C', c1, c2, pb))
        t = b
    return out


def parse_path(d):
    toks = re.findall(r'[MmZzLlHhVvCcSsQqTtAa]|' + NUM, d)
    i = 0
    subs = []
    cur = (0.0, 0.0)
    start = (0.0, 0.0)
    sub = None
    cmd = None
    last_c = None   # last cubic control point (for S)
    last_q = None   # last quadratic control point (for T)

    def num():
        nonlocal i
        v = float(toks[i])
        i += 1
        return v

    def flag():
        # flags may be written without separators: "a10 10 0 0110 10"
        nonlocal i
        t = toks[i]
        if t in ('0', '1'):
            i += 1
            return int(t)
        # glued flags, e.g. "01" or "110" : split first char
        toks[i] = t[1:]
        return int(t[0])

    while i < len(toks):
        t = toks[i]
        if re.match(r'[A-Za-z]', t):
            cmd = t
            i += 1
            if cmd in 'Zz':
                if sub is not None:
                    sub[2] = True
                    cur = start
                    sub = None
                last_c = last_q = None
                continue
        elif cmd is None:
            raise ValueError('path data does not start with a command')
        rel = cmd.islower()
        C = cmd.upper()
        ox, oy = cur if rel else (0.0, 0.0)
        if C == 'M':
            p = (num() + ox, num() + oy)
            sub = [p, [], False]
            subs.append(sub)
            cur = start = p
            cmd = 'l' if rel else 'L'   # following pairs are lineto
            last_c = last_q = None
            continue
        if sub is None:            # drawing after Z without M
            sub = [cur, [], False]
            subs.append(sub)
            start = cur
        if C == 'L':
            p = (num() + ox, num() + oy)
            sub[1].append(('L', p))
            last_c = last_q = None
        elif C == 'H':
            p = (num() + ox, cur[1])
            sub[1].append(('L', p))
            last_c = last_q = None
        elif C == 'V':
            p = (cur[0], num() + oy)
            sub[1].append(('L', p))
            last_c = last_q = None
        elif C == 'C':
            c1 = (num() + ox, num() + oy)
            c2 = (num() + ox, num() + oy)
            p = (num() + ox, num() + oy)
            sub[1].append(('C', c1, c2, p))
            last_c, last_q = c2, None
        elif C == 'S':
            c1 = (2 * cur[0] - last_c[0], 2 * cur[1] - last_c[1]) if last_c else cur
            c2 = (num() + ox, num() + oy)
            p = (num() + ox, num() + oy)
            sub[1].append(('C', c1, c2, p))
            last_c, last_q = c2, None
        elif C in 'QT':
            if C == 'Q':
                q = (num() + ox, num() + oy)
            else:
                q = (2 * cur[0] - last_q[0], 2 * cur[1] - last_q[1]) if last_q else cur
            p = (num() + ox, num() + oy)
            c1 = (cur[0] + 2 / 3 * (q[0] - cur[0]), cur[1] + 2 / 3 * (q[1] - cur[1]))
            c2 = (p[0] + 2 / 3 * (q[0] - p[0]), p[1] + 2 / 3 * (q[1] - p[1]))
            sub[1].append(('C', c1, c2, p))
            last_c, last_q = None, q
        elif C == 'A':
            rx, ry, phi = num(), num(), num()
            la, sw = flag(), flag()
            p = (num() + ox, num() + oy)
            sub[1].extend(arc_to_cubics(cur, rx, ry, phi, la, sw, p))
            last_c = last_q = None
        else:
            raise ValueError('unknown command ' + cmd)
        cur = p
    return subs


def ellipse_path(cx, cy, rx, ry):
    k = 0.5522847498
    return [[(cx + rx, cy), [
        ('C', (cx + rx, cy + k * ry), (cx + k * rx, cy + ry), (cx, cy + ry)),
        ('C', (cx - k * rx, cy + ry), (cx - rx, cy + k * ry), (cx - rx, cy)),
        ('C', (cx - rx, cy - k * ry), (cx - k * rx, cy - ry), (cx, cy - ry)),
        ('C', (cx + k * rx, cy - ry), (cx + rx, cy - k * ry), (cx + rx, cy)),
    ], True]]


def rect_path(x, y, w, h, rx, ry):
    if rx == 0 and ry == 0:
        return [[(x, y), [('L', (x + w, y)), ('L', (x + w, y + h)),
                          ('L', (x, y + h))], True]]
    rx = min(rx, w / 2)
    ry = min(ry, h / 2)
    d = ('M{0},{1} H{2} A{3},{4} 0 0 1 {5},{6} V{7} A{3},{4} 0 0 1 {2},{8} '
         'H{0} A{3},{4} 0 0 1 {9},{7} V{6} A{3},{4} 0 0 1 {0},{1} Z').format(
        x + rx, y, x + w - rx, rx, ry, x + w, y + ry, y + h - ry, y + h, x)
    return parse_path(d)


# --------------------------------------------------------------------------
#  styles
# --------------------------------------------------------------------------
INHERITED = ('fill', 'stroke', 'fill-rule', 'display', 'visibility')


CSS = {}   # simple stylesheet : '.class' / '#id' / 'tag' -> {prop: value}


def read_css(root):
    CSS.clear()
    for el in root.iter(SVGNS + 'style'):
        txt = re.sub(r'/\*.*?\*/', '', el.text or '', flags=re.S)
        for sels, body in re.findall(r'([^{}]+)\{([^}]*)\}', txt):
            decl = {}
            for d in body.split(';'):
                if ':' in d:
                    k, v = d.split(':', 1)
                    decl[k.strip()] = v.strip()
            for sel in sels.split(','):
                CSS.setdefault(sel.strip(), {}).update(decl)


def style_of(el, parent):
    st = dict(parent)
    for k in INHERITED:
        if el.get(k) is not None:
            st[k] = el.get(k).strip()
    tag = el.tag.replace(SVGNS, '')
    sels = [tag] + ['.' + c for c in (el.get('class') or '').split()]
    if el.get('id'):
        sels.append('#' + el.get('id'))
    for sel in sels:
        for k, v in CSS.get(sel, {}).items():
            if k in INHERITED:
                st[k] = v
    for decl in (el.get('style') or '').split(';'):
        if ':' in decl:
            k, v = decl.split(':', 1)
            k = k.strip()
            if k in INHERITED:
                st[k] = v.strip()
    return st


def flen(s, default=0.0):
    if s is None:
        return default
    m = re.match(NUM, s.strip())
    return float(m.group(0)) if m else default


# --------------------------------------------------------------------------
#  reading the svg
# --------------------------------------------------------------------------
def collect(root):
    ids = {}
    for el in root.iter():
        if el.get('id'):
            ids[el.get('id')] = el
    shapes = []   # (subpaths transformed, style)
    warn = set()

    def walk(el, m, st, depth=0):
        if depth > 50:
            return
        tag = el.tag.replace(SVGNS, '')
        if tag in ('defs', 'clipPath', 'mask', 'symbol', 'metadata', 'title',
                   'desc', 'style', 'linearGradient', 'radialGradient',
                   'pattern', 'marker', 'filter'):
            return
        if tag in ('text', 'image', 'foreignObject'):
            warn.add(tag)
            return
        st = style_of(el, st)
        if st.get('display') == 'none' or st.get('visibility') == 'hidden':
            return
        m = mul(m, parse_transform(el.get('transform')))
        subs = None
        if tag == 'path':
            d = el.get('d')
            if d:
                subs = parse_path(d)
        elif tag == 'rect':
            subs = rect_path(flen(el.get('x')), flen(el.get('y')),
                             flen(el.get('width')), flen(el.get('height')),
                             flen(el.get('rx'), flen(el.get('ry'))),
                             flen(el.get('ry'), flen(el.get('rx'))))
        elif tag == 'circle':
            r = flen(el.get('r'))
            subs = ellipse_path(flen(el.get('cx')), flen(el.get('cy')), r, r)
        elif tag == 'ellipse':
            subs = ellipse_path(flen(el.get('cx')), flen(el.get('cy')),
                                flen(el.get('rx')), flen(el.get('ry')))
        elif tag == 'line':
            subs = [[(flen(el.get('x1')), flen(el.get('y1'))),
                     [('L', (flen(el.get('x2')), flen(el.get('y2'))))], False]]
        elif tag in ('polyline', 'polygon'):
            v = [float(x) for x in re.findall(NUM, el.get('points') or '')]
            pts = list(zip(v[0::2], v[1::2]))
            if pts:
                subs = [[pts[0], [('L', q) for q in pts[1:]], tag == 'polygon']]
        elif tag == 'use':
            ref = (el.get(XLINK) or el.get('href') or '').lstrip('#')
            target = ids.get(ref)
            if target is not None:
                mm = mul(m, (1, 0, 0, 1, flen(el.get('x')), flen(el.get('y'))))
                if target.tag.replace(SVGNS, '') == 'symbol':
                    for ch in target:
                        walk(ch, mm, st, depth + 1)
                else:
                    walk(target, mm, st, depth + 1)
            return
        if subs:
            tsubs = []
            for s0, segs, closed in subs:
                tsegs = [(sg[0],) + tuple(apply(m, q) for q in sg[1:]) for sg in segs]
                tsubs.append([apply(m, s0), tsegs, closed])
            shapes.append((tsubs, st))
        for ch in el:
            walk(ch, m, st, depth + 1)

    walk(root, IDENT, {'fill': 'black', 'stroke': 'none', 'fill-rule': 'nonzero'})
    return shapes, warn


# --------------------------------------------------------------------------
#  bounding box (exact for cubics)
# --------------------------------------------------------------------------
def cubic_extrema(a, b, c, d):
    # derivative coefficients of the Bezier on one axis
    A = -a + 3 * b - 3 * c + d
    B = 2 * (a - 2 * b + c)
    C = b - a
    ts = []
    if abs(A) < 1e-12:
        if abs(B) > 1e-12:
            ts.append(-C / B)
    else:
        disc = B * B - 4 * A * C
        if disc >= 0:
            r = math.sqrt(disc)
            ts += [(-B + r) / (2 * A), (-B - r) / (2 * A)]
    vals = []
    for t in ts:
        if 0 < t < 1:
            u = 1 - t
            vals.append(u ** 3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t ** 3 * d)
    return vals


def bbox(shapes):
    xs, ys = [], []
    for subs, st in shapes:
        for s0, segs, closed in subs:
            cur = s0
            xs.append(cur[0])
            ys.append(cur[1])
            for sg in segs:
                p = sg[-1]
                xs.append(p[0])
                ys.append(p[1])
                if sg[0] == 'C':
                    xs += cubic_extrema(cur[0], sg[1][0], sg[2][0], p[0])
                    ys += cubic_extrema(cur[1], sg[1][1], sg[2][1], p[1])
                cur = p
    return min(xs), min(ys), max(xs), max(ys)


# --------------------------------------------------------------------------
#  writing
# --------------------------------------------------------------------------
def fmt(v, digits):
    s = ('%.' + str(digits) + 'f') % v
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    if s in ('-0', ''):
        s = '0'
    return s


def is_white(v):
    if v is None:
        return False
    v = v.strip().lower().replace(' ', '')
    return v in ('white', '#fff', '#ffffff', 'rgb(255,255,255)', 'rgb(100%,100%,100%)')


def is_none(v):
    return v is None or v.strip().lower() in ('none', 'transparent')


def to_svg(path):
    """.eps / .ps / .pdf -> temporary svg (needs ghostscript and pdftocairo)"""
    import shutil
    import subprocess
    import tempfile
    ext = os.path.splitext(path)[1].lower()
    if ext not in ('.eps', '.ps', '.pdf'):
        return path
    tmp = tempfile.mkdtemp(prefix='svg2pgf')
    pdf = path
    if ext != '.pdf':
        if not shutil.which('gs'):
            sys.exit('ghostscript (gs) is needed to read ' + path)
        pdf = os.path.join(tmp, 'in.pdf')
        subprocess.run(['gs', '-q', '-dNOPAUSE', '-dBATCH', '-dSAFER', '-dEPSCrop',
                        '-sDEVICE=pdfwrite', '-sOutputFile=' + pdf, path], check=True)
    if not shutil.which('pdftocairo'):
        sys.exit('pdftocairo (poppler) is needed to read ' + path)
    svg = os.path.join(tmp, 'in.svg')
    subprocess.run(['pdftocairo', '-svg', '-f', '1', '-l', '1', pdf, svg], check=True)
    return svg


def load_shapes(svgfile, keep_white=False):
    root = ET.parse(to_svg(svgfile)).getroot()
    read_css(root)
    shapes, warn = collect(root)
    for t in sorted(warn):
        sys.stderr.write('warning: %s: <%s> ignored\n' % (svgfile, t))
    shapes = [(s, st) for s, st in shapes
              if not (is_none(st.get('fill')) and is_none(st.get('stroke')))]
    if not keep_white:
        nw = len(shapes)
        shapes = [(s, st) for s, st in shapes
                  if not (is_white(st.get('fill')) or
                          (is_none(st.get('fill')) and is_white(st.get('stroke'))))]
        if len(shapes) < nw:
            sys.stderr.write('warning: %s: %d white element(s) ignored '
                             '(use --keep-white)\n' % (svgfile, nw - len(shapes)))
    if not shapes:
        raise ValueError('no drawable element in ' + svgfile)
    return shapes


def split_shapes(shapes, min_size=0.25, gap=1.0):
    """Split a sheet into separate ornaments : groups of shapes whose
    bounding boxes overlap (or are closer than gap). Groups smaller than
    min_size x (largest group) are dropped (texts, logos...).
    Result sorted by rows (top to bottom) then columns."""
    boxes = [bbox([sh]) for sh in shapes]
    n = len(shapes)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    order = sorted(range(n), key=lambda i: boxes[i][0])
    for ii, i in enumerate(order):        # sweep on x
        bi = boxes[i]
        for j in order[ii + 1:]:
            bj = boxes[j]
            if bj[0] > bi[2] + gap:
                break
            if bj[1] <= bi[3] + gap and bi[1] <= bj[3] + gap:
                parent[find(i)] = find(j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    groups = [[shapes[i] for i in sorted(g)] for g in groups.values()]
    # merge again on the group boxes (union of shapes may create new overlaps)
    changed = True
    while changed:
        changed = False
        gb = [bbox(g) for g in groups]
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                a, b = gb[i], gb[j]
                if a[0] <= b[2] + gap and b[0] <= a[2] + gap and \
                   a[1] <= b[3] + gap and b[1] <= a[3] + gap:
                    groups[i] += groups.pop(j)
                    changed = True
                    break
            if changed:
                break
    gb = [bbox(g) for g in groups]
    big = max(max(b[2] - b[0], b[3] - b[1]) for b in gb)
    keep = [(g, b) for g, b in zip(groups, gb)
            if max(b[2] - b[0], b[3] - b[1]) >= min_size * big]
    # rows : sort by top, a new row when the top is below the previous centre
    keep.sort(key=lambda gb_: gb_[1][1])
    rows, cur = [], []
    for g, b in keep:
        if cur and b[1] > max(c[1][3] for c in cur) - 0.5 * (cur[0][1][3] - cur[0][1][1]):
            rows.append(cur)
            cur = []
        cur.append((g, b))
    if cur:
        rows.append(cur)
    out = []
    for r in rows:
        out += [g for g, b in sorted(r, key=lambda gb_: gb_[1][0])]
    return out


def render(shapes, width=None, height=None, scale=0.75, digits=2, source=None,
           name='ornament.pgf', origin=''):
    x0, y0, x1, y1 = bbox(shapes)
    w, h = x1 - x0, y1 - y0
    if width:
        k = width / w
    elif height:
        k = height / h
    else:
        k = scale
    W, H = w * k, h * k

    def P(p):  # svg (y down) -> pgf (y up), origin lower left, bp
        return fmt((p[0] - x0) * k, digits) + ' ' + fmt((y1 - p[1]) * k, digits)

    out = ['%% %s' % name]
    out.append('%% converted by svg2pgf.py from %s' % origin)
    if source:
        for line in source.splitlines():
            out.append('% ' + line)
    out.append('%% size: %s x %s bp' % (fmt(W, 1), fmt(H, 1)))
    # exact bounding box (pgf would include the control points of the curves)
    out.append('\\r 0 0 %s %s' % (fmt(W, digits), fmt(H, digits)))
    out.append('\\ubb')
    rule = False
    for subs, st in shapes:
        filled = not is_none(st.get('fill'))
        eo = st.get('fill-rule') == 'evenodd'
        if filled and eo != rule:
            out.append('\\pgfseteorule' if eo else '\\pgfsetnonzerorule')
            rule = eo
        for s0, segs, closed in subs:
            out.append('\\m ' + P(s0))
            for sg in segs:
                if sg[0] == 'L':
                    out.append('\\l ' + P(sg[1]))
                else:
                    out.append('\\c ' + P(sg[1]) + ' ' + P(sg[2]) + ' ' + P(sg[3]))
            if closed:
                out.append('\\o')
        stroked = not is_none(st.get('stroke'))
        if filled and stroked:
            out.append('\\s')                    # fill and stroke
        elif filled:
            out.append('\\pgfusepathqfill')      # fill only (as in the svg)
        else:
            out.append('\\k')                    # stroke only
    if rule:
        out.append('\\pgfsetnonzerorule')
    out.append('\\endinput')
    return '\n'.join(out) + '\n', W, H


def convert(svgfile, width=None, height=None, scale=0.75, digits=2, source=None,
            name=None, keep_white=False):
    shapes = load_shapes(svgfile, keep_white)
    return render(shapes, width, height, scale, digits, source,
                  name or os.path.splitext(os.path.basename(svgfile))[0] + '.pgf',
                  os.path.basename(svgfile))


def write_library(family, dims, path):
    lines = ['%% pgfornament-lib-%s.code.tex (utf8 encoding)' % family,
             '% generated by svg2pgf.py',
             '% This work may be distributed and/or modified under the',
             '% conditions of the LaTeX Project Public License, either version 1.3c',
             '% of this license or (at your option) any later version.',
             '\\typeout{pgfornament-lib-%s.code.tex}%%' % family,
             '\\expandafter\\edef\\csname pgfornament@restoreat\\endcsname'
             '{\\catcode`\\noexpand\\@=\\the\\catcode`\\@\\relax}%',
             '\\catcode`\\@=11\\relax',
             '% dimensions des motifs (en bp)',
             '\\def\\@pgfornamentDim#1{%',
             '\\ifcase#1\\relax%']
    for i, (W, H) in enumerate(dims, 1):
        lines.append('\\or\\def\\@pgfornamentX{%s}\\def\\@pgfornamentY{%s}%% %d'
                     % (fmt(W, 1), fmt(H, 1), i))
    lines += ['\\fi%', '}%', '\\pgfornament@restoreat', '\\endinput', '']
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def write_test(family, names, path):
    rows = []
    for i, n in enumerate(names, 1):
        rows.append('\\fbox{\\pgfornament[height=1.5cm]{%d}}\\ \\textbf{%d} '
                    '{\\tiny %s}\\par\\medskip' % (i, i, n.replace('_', '\\_')))
    doc = ('\\documentclass{article}\n\\usepackage[margin=1.5cm]{geometry}\n'
           '\\usepackage[object=%s]{pgfornament}\n\\setlength\\fboxsep{0pt}\n'
           '\\begin{document}\n\\begin{multicols}{3}\n' % family)
    doc = doc.replace('\\begin{document}', '\\usepackage{multicol}\n\\begin{document}')
    doc += '\n'.join(rows) + '\n\\end{multicols}\n\\end{document}\n'
    with open(path, 'w', encoding='utf-8') as f:
        f.write(doc)


def main():
    ap = argparse.ArgumentParser(description='SVG -> pgfornament .pgf')
    ap.add_argument('svg', nargs='+')
    ap.add_argument('-o', '--output', help='output file (one svg only)')
    ap.add_argument('--family', help='build a whole family with this name')
    ap.add_argument('--out-dir', default='build', help='output folder for --family (default build)')
    ap.add_argument('--width', type=float)
    ap.add_argument('--height', type=float)
    ap.add_argument('--scale', type=float, default=None)
    ap.add_argument('--digits', type=int, default=2)
    ap.add_argument('--source', help='origin / licence written in the header')
    ap.add_argument('--split', action='store_true',
                    help='the svg is a sheet with several ornaments: one file per ornament')
    ap.add_argument('--min-size', type=float, default=0.25,
                    help='with --split: drop groups smaller than this fraction '
                         'of the largest one (texts, logos), default 0.25')
    ap.add_argument('--skip', help='numbers of the parts to leave out, e.g. 1,2')
    ap.add_argument('--keep-white', action='store_true',
                    help='keep white elements (ignored by default: background, highlights)')
    a = ap.parse_args()
    if a.scale is None:   # svg: 1px = 0.75bp ; eps/pdf (via pdftocairo): 1pt = 1bp
        a.scale = 1.0 if os.path.splitext(a.svg[0])[1].lower() in ('.eps', '.ps', '.pdf') \
            else 0.75
    if a.family:
        if not re.fullmatch(r'[a-zA-Z]+', a.family):
            sys.exit('the family name must contain only letters')
        gdir = os.path.join(a.out_dir, 'generic', a.family)
        ldir = os.path.join(a.out_dir, 'latex')
        os.makedirs(gdir, exist_ok=True)
        os.makedirs(ldir, exist_ok=True)
        items = []          # (shapes, origin)
        for f in sorted(a.svg):
            shapes = load_shapes(f, a.keep_white)
            if a.split:
                parts = split_shapes(shapes, a.min_size)
                print('%s : %d ornament(s) found' % (f, len(parts)))
                items += [(p, '%s (part %d)' % (os.path.basename(f), j))
                          for j, p in enumerate(parts, 1)]
            else:
                items.append((shapes, os.path.basename(f)))
        if a.skip:
            sk = set(int(x) for x in a.skip.split(','))
            items = [it for j, it in enumerate(items, 1) if j not in sk]
        dims = []
        for i, (shapes, origin) in enumerate(items, 1):
            name = 'pgfornament-%s%d.pgf' % (a.family, i)
            txt, W, H = render(shapes, a.width, a.height, a.scale, a.digits,
                               a.source, name, origin)
            with open(os.path.join(gdir, name), 'w', encoding='utf-8') as g:
                g.write(txt)
            dims.append((W, H))
            print('%s  <-  %s   (%s x %s bp)' % (name, origin, fmt(W, 1), fmt(H, 1)))
        write_library(a.family, dims,
                      os.path.join(ldir, 'pgfornament-lib-%s.code.tex' % a.family))
        write_test(a.family, [o for sh, o in items],
                   os.path.join(a.out_dir, 'test-%s.tex' % a.family))
    else:
        for f in a.svg:
            txt, W, H = convert(f, a.width, a.height, a.scale, a.digits, a.source,
                                None, a.keep_white)
            out = a.output if (a.output and len(a.svg) == 1) else \
                os.path.splitext(f)[0] + '.pgf'
            with open(out, 'w', encoding='utf-8') as g:
                g.write(txt)
            print('%s  ->  %s   (%s x %s bp)' % (f, out, fmt(W, 1), fmt(H, 1)))


if __name__ == '__main__':
    main()
