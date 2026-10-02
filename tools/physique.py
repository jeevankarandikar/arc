#!/usr/bin/env python3
"""Physique photos: from your videos and photos to aligned frames for the comparison view.

Everything here stays on your Mac. Photos and videos can live anywhere: point `add` at a folder or files and
they are read in place and never copied, moved or edited (the list goes in data/physique/originals-manifest.json).
Files you drop into data/physique/ also work. The output goes in physique/ at the repo root (gitignored).

    python3 tools/physique.py add PATH [PATH ...] register a folder or files from anywhere on the Mac
    python3 tools/physique.py scan [--all]       number new videos and make their contact sheets (--all redoes every one)
    python3 tools/physique.py strip N FROM TO    a closer sheet of video #N between two times, every 0.5 s
    python3 tools/physique.py refine [N ...]     move video picks to the held moment of their pose, within 2.5 s
    python3 tools/physique.py build              cut the picked frames, align them on the body, write physique/

Picks live in data/physique/picks.json, one per month and pose:
    {"n": 12, "t": 14.5, "pose": "front"}                  a numbered video from the scan
    {"src": "sent-sep-2026/IMG_9392.DNG", "pose": "front"}  a file under data/physique, or an id from the manifest
Optional keys: "manual" keeps refine away from a hand-checked time, "m" overrides the month, "rot" turns a sideways frame upright (degrees clockwise), "flip" mirrors the frame, "box" is a manual crop as fractions of
the frame [x, y, w, h] for when pose detection misses (usually back shots), "note" shows under the photo.
"""
import hashlib, json, os, re, subprocess, sys, tempfile
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'data', 'physique')
CACHE = os.path.join(SRC, '.cache')
MANIFEST = os.path.join(SRC, 'originals-manifest.json')
OUT = os.path.join(ROOT, 'physique')
TOOL = os.path.join(CACHE, 'pxtool')
VIDEO = {'.mov', '.mp4', '.m4v'}
PHOTO = {'.jpg', '.jpeg', '.png', '.heic', '.dng'}
W, H = 900, 1200          # output frame, 3:4
NECK_Y, TORSO = .32, .46  # neck sits 32% down the frame and neck to hips spans 46% of it: head to upper thigh
PAD = (237, 237, 241)     # --fill
PER_ROW, ROWS = 14, 6     # contact sheets: frames per video, videos per sheet


def font(size):
    for f in ('/System/Library/Fonts/Supplemental/Arial.ttf', '/System/Library/Fonts/Helvetica.ttc'):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def tool(*a):
    swift = os.path.join(ROOT, 'tools', 'pxtool.swift')
    if not os.path.exists(TOOL) or os.path.getmtime(TOOL) < os.path.getmtime(swift):
        os.makedirs(CACHE, exist_ok=True)
        subprocess.run(['swiftc', '-O', swift, '-o', TOOL], check=True)
    return subprocess.run([TOOL, *a], check=True, capture_output=True, text=True).stdout


def local_files():
    out = []
    for d, _, fs in os.walk(SRC):
        if d.startswith(CACHE):
            continue
        for f in sorted(fs):
            ext = os.path.splitext(f)[1].lower()
            if ext in VIDEO or ext in PHOTO:
                out.append(os.path.relpath(os.path.join(d, f), SRC))
    return sorted(out)


def file_date(rel, path):
    """The month you labeled in the path wins, then the file's own capture date, then its modified time."""
    m = re.search(r'(20(?:1[5-9]|2\d))[-_ .]?(0[1-9]|1[0-2])(?:[-_ .]?([0-3]\d))?', rel)
    if m:
        return '%s-%s-%s' % (m.group(1), m.group(2), m.group(3) or '15'), 'label'
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in VIDEO:
            d = json.loads(tool('info', path)).get('date')
            if d:
                return d, 'video'
        else:
            s = subprocess.run(['sips', '-g', 'creation', path], capture_output=True, text=True).stdout
            m = re.search(r'creation: (\d{4}):(\d\d):(\d\d)', s)
            if m:
                return '-'.join(m.groups()), 'photo'
    except subprocess.CalledProcessError:
        pass
    return datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d'), 'file'


def sources():
    """Every source as {key, path, date, how, video}. Library originals come from the manifest, read in place."""
    out = []
    for rel in local_files():
        path = os.path.join(SRC, rel)
        d, how = file_date(rel, path)
        out.append({'key': rel, 'path': path, 'date': d, 'how': how, 'video': os.path.splitext(rel)[1].lower() in VIDEO})
    if os.path.exists(MANIFEST):
        for r in json.load(open(MANIFEST)):
            path = os.path.expanduser(r['path'])
            out.append({'key': r['uuid'], 'path': path, 'date': r['date'][:10], 'how': 'library',
                        'video': os.path.splitext(path)[1].lower() in VIDEO, 'albums': r.get('albums', [])})
    return out


def numbered():
    """Videos in date order with a stable number, from the last scan."""
    p = os.path.join(CACHE, 'media.json')
    return {r['n']: r for r in json.load(open(p))} if os.path.exists(p) else {}


def resolve(pick):
    if 'n' in pick:
        r = numbered()[pick['n']]
        return r['path'], r['date']
    for s in sources():
        if s['key'] == pick['src']:
            return s['path'], s['date']
    raise SystemExit('no source %s' % pick.get('src'))


def upright(path, t, dest):
    """A full-size, upright JPEG with no metadata."""
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO:
        tool('frame', path, str(t or 0), dest)
        im = Image.open(dest)
    else:
        if ext in {'.heic', '.dng'}:
            subprocess.run(['sips', '-s', 'format', 'jpeg', path, '--out', dest], check=True, capture_output=True)
            im = Image.open(dest)
        else:
            im = Image.open(path)
        im = ImageOps.exif_transpose(im)
    im = im.convert('RGB')
    im.save(dest, quality=95)
    return im


def frames(path, every, h, t0=None, t1=None):
    with tempfile.TemporaryDirectory(dir=CACHE) as tmp:
        a = [path, str(every), tmp, str(h)] + ([str(t0), str(t1)] if t0 is not None else [])
        res = json.loads(tool('frames', *a))
        ims = [Image.open(os.path.join(tmp, f)).copy() for f in sorted(os.listdir(tmp))]
    return res, ims


def tag(d, x, y, text, f):
    w = d.textlength(text, font=f)
    d.rectangle((x, y, x + w + 8, y + f.size + 6), fill='white')
    d.text((x + 4, y + 2), text, fill='black', font=f)


def scan(everything=False):
    """Numbers stay put: a video already in media.json keeps its number, and new ones go on the end.
    Without --all only the new videos get sheets, named new-<month>.jpg."""
    os.makedirs(os.path.join(CACHE, 'sheets'), exist_ok=True)
    src = sorted(sources(), key=lambda s: (s['date'], s['key']))
    old = {} if everything else {r['key']: r for r in numbered().values()}
    vids = [s for s in src if s['video']]
    rows, months = sorted(old.values(), key=lambda r: r['n']), {}
    nxt = max([r['n'] for r in rows] or [0]) + 1
    small, big = font(13), font(15)
    todo = []
    for s in vids:
        if s['key'] in old:
            continue
        todo.append((nxt, s))
        nxt += 1
    for n, s in todo:
        dur = json.loads(tool('info', s['path']))['duration']
        res, ims = frames(s['path'], max(.25, dur / PER_ROW), 150)
        th = 150
        row = Image.new('RGB', (130 + PER_ROW * 86, th + 4), 'white')
        d = ImageDraw.Draw(row)
        d.text((6, 8), '#%d' % n, fill='black', font=font(22))
        d.text((6, 40), s['date'], fill='black', font=big)
        d.text((6, 60), '%d s' % round(dur), fill='black', font=big)
        x = 130
        for im, t in zip(ims[:PER_ROW], res['times']):
            im.thumbnail((84, th))
            row.paste(im, (x, 2))
            tag(d, x, th - 18, '%g' % t, small)
            x += 86
        months.setdefault(s['date'][:7], []).append(row)
        rows.append({'n': n, 'key': s['key'], 'path': s['path'], 'date': s['date'], 'dur': round(dur, 1)})
        print('#%d %s %ds' % (n, s['date'], round(dur)), flush=True)
    for mk, rs in months.items():
        for page in range(0, len(rs), ROWS):
            chunk = rs[page:page + ROWS]
            sheet = Image.new('RGB', (chunk[0].width, sum(r.height + 6 for r in chunk)), (200, 200, 205))
            y = 0
            for r in chunk:
                sheet.paste(r, (0, y))
                y += r.height + 6
            name = ('' if everything or not old else 'new-') + mk + ('' if page == 0 else '-%d' % (page // ROWS + 1)) + '.jpg'
            sheet.save(os.path.join(CACHE, 'sheets', name), quality=80)
    photos = [s for s in src if not s['video']]
    if photos:
        cols, cw, ch = 8, 200, 260
        sheet = Image.new('RGB', (cols * cw, -(-len(photos) // cols) * (ch + 18)), 'white')
        d = ImageDraw.Draw(sheet)
        for i, s in enumerate(photos):
            im = upright(s['path'], 0, os.path.join(CACHE, 'thumb.jpg'))
            im.thumbnail((cw - 4, ch))
            x, y = (i % cols) * cw, (i // cols) * (ch + 18)
            sheet.paste(im, (x, y))
            d.text((x + 2, y + ch + 3), '%s %s' % (os.path.basename(s['key'])[:18], s['date']), fill='black', font=small)
        sheet.save(os.path.join(CACHE, 'sheets', 'photos.jpg'), quality=80)
    with open(os.path.join(CACHE, 'media.json'), 'w') as f:
        json.dump(rows, f, indent=1)
    print('%d videos, %d photos. Sheets by month in %s' % (len(vids), len(photos), os.path.join(CACHE, 'sheets')))


def strip(n, t0, t1, step=.5):
    r = numbered()[n]
    res, ims = frames(r['path'], step, 300, t0, t1)
    cols = 10
    cw, ch = 170, 300
    sheet = Image.new('RGB', (cols * cw, -(-len(ims) // cols) * (ch + 4)), 'white')
    d = ImageDraw.Draw(sheet)
    for i, (im, t) in enumerate(zip(ims, res['times'])):
        im.thumbnail((cw - 4, ch))
        x, y = (i % cols) * cw, (i // cols) * (ch + 4)
        sheet.paste(im, (x, y))
        tag(d, x + 2, y + 2, '%g' % t, font(15))
    out = os.path.join(CACHE, 'sheets', 'strip-%d.jpg' % n)
    sheet.save(out, quality=82)
    print(out)


def held(kp, pose, iw, ih):
    """How well a frame's joints match the named pose, 0 to 1. Vision cannot tell front from back,
    so the nose decides: a front pose sees it and a back pose does not."""
    def pt(k):
        return (kp[k][0] * iw, kp[k][1] * ih, kp[k][2]) if k in kp else None
    ls, rs, le, re, lw, rw, nose = (pt(k) for k in ('ls', 'rs', 'le', 're', 'lw', 'rw', 'nose'))
    if not (ls and rs):
        return 0
    neck = pt('neck') or ((ls[0] + rs[0]) / 2, (ls[1] + rs[1]) / 2, 1)
    root = pt('root') or (pt('lh') and pt('rh') and ((pt('lh')[0] + pt('rh')[0]) / 2, (pt('lh')[1] + pt('rh')[1]) / 2, 1))
    torso = abs(root[1] - neck[1]) if root else 2.2 * abs(ls[0] - rs[0])
    if torso < 10:
        return 0
    sh_y, width = (ls[1] + rs[1]) / 2, abs(ls[0] - rs[0])
    facing = 1 if (nose and nose[2] > .5) else 0
    score = 0.0
    if pose in ('biceps', 'backbi'):
        if le and re and lw and rw:
            up = sum([lw[1] < sh_y, rw[1] < sh_y, le[1] < sh_y + .2 * torso, re[1] < sh_y + .2 * torso]) / 4
            wide = 1 if abs(le[0] - re[0]) > 1.3 * width else 0
            score = .7 * up + .3 * wide
    elif pose in ('front', 'back'):
        down = sum([bool(lw) and lw[1] > sh_y + .45 * torso, bool(rw) and rw[1] > sh_y + .45 * torso]) / 2
        square = min(1, width / (.55 * torso))
        score = .6 * down + .4 * square
    elif pose == 'side':
        score = max(0, 1 - width / (.5 * torso))
    if pose in ('front', 'biceps'):
        score *= .6 + .4 * facing
    elif pose in ('back', 'backbi'):
        score *= 1 - .4 * facing
    return score


def refine(only=None):
    """Move each video pick to the held moment of its pose within 2.5 s: joints in the pose, the body still, the frame sharp."""
    from PIL import ImageChops, ImageFilter, ImageStat
    path_p = os.path.join(SRC, 'picks.json')
    picks = json.load(open(path_p))
    media = numbered()
    before, after = [], []
    for i, p in enumerate(picks):
        if 'n' not in p or p.get('manual') or (only and p['n'] not in only):
            continue
        r = media[p['n']]
        t0 = p.get('t0', p['t'])
        a, b = max(0, t0 - 2.5), min(r['dur'], t0 + 2.5)
        with tempfile.TemporaryDirectory(dir=CACHE) as tmp:
            res = json.loads(tool('frames', r['path'], '0.2', tmp, '400', str(a), str(b)))
            files = sorted(os.path.join(tmp, f) for f in os.listdir(tmp))
            ims = [Image.open(f).convert('RGB') for f in files]
            if p.get('rot'):
                ims = [im.rotate(-p['rot'], expand=True) for im in ims]
                for im, f in zip(ims, files):
                    im.save(f)
            kps = {}
            for line in tool('pose', *files).splitlines():
                o = json.loads(line)
                kps[o['path']] = o
            small = [im.convert('L').resize((48, 64)) for im in ims]
            motion = []
            for k in range(len(small)):
                ds = [ImageStat.Stat(ImageChops.difference(small[k], small[j])).mean[0] for j in (k - 1, k + 1) if 0 <= j < len(small)]
                motion.append(sum(ds) / len(ds) if ds else 0)
            sharp = [ImageStat.Stat(im.convert('L').filter(ImageFilter.FIND_EDGES)).var[0] for im in ims]
            mmax, smax = max(motion) or 1, max(sharp) or 1
            best, best_s = None, -9
            for k, (f, t) in enumerate(zip(files, res['times'])):
                w, h = ims[k].size
                s = 3 * held(kps.get(f, {}), p['pose'], w, h) - motion[k] / mmax + .5 * sharp[k] / smax - .3 * abs(t - t0) / 2.5
                if s > best_s:
                    best, best_s = k, s
            before.append(ims[min(range(len(files)), key=lambda k: abs(res['times'][k] - t0))].copy())
            after.append(ims[best].copy())
        p['t0'] = t0
        p['t'] = res['times'][best]
        print('#%d %s %s: %.2f -> %.2f' % (p['n'], p.get('m', r['date'][:7]), p['pose'], t0, p['t']), flush=True)
    json.dump(picks, open(path_p, 'w'), indent=1)
    cols = 12
    sheet = Image.new('RGB', (cols * 120, -(-len(after) // (cols // 2)) * 164), 'white')
    for i, (x0, x1) in enumerate(zip(before, after)):
        x, y = (i % (cols // 2)) * 240, (i // (cols // 2)) * 164
        for j, im in enumerate((x0, x1)):
            im = im.copy()
            im.thumbnail((116, 160))
            sheet.paste(im, (x + j * 118, y))
    sheet.save(os.path.join(CACHE, 'refine.jpg'), quality=80)
    print('before and after pairs in', os.path.join(CACHE, 'refine.jpg'))


def estimate(kp, iw, ih):
    """Neck point, body center and neck-to-hips length in pixels, or None when the body is not found."""
    def pt(k):
        return (kp[k][0] * iw, kp[k][1] * ih) if k in kp else None
    def mid(a, b):
        a, b = pt(a), pt(b)
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) if a and b else None
    neck = pt('neck') or mid('ls', 'rs')
    root = pt('root') or mid('lh', 'rh')
    if neck and not root and pt('ls') and pt('rs'):
        # back shots often lose the hips; neck to hips runs about 1.4 shoulder widths
        sw = abs(pt('ls')[0] - pt('rs')[0])
        root = (neck[0], neck[1] + 1.4 * sw)
    if not neck or not root:
        return {'neck': neck} if neck else None
    torso = ((neck[0] - root[0]) ** 2 + (neck[1] - root[1]) ** 2) ** .5
    if torso < 20:
        return {'neck': neck}
    return {'neck': neck, 'cx': (neck[0] + root[0]) / 2, 'torso': torso}


def box_for(neck_y, cx, torso):
    """Source rectangle that puts the neck and hips at fixed spots in the output frame."""
    s = TORSO * H / torso
    return (cx - W / s / 2, neck_y - NECK_Y * H / s, W / s, H / s)


def median(v):
    v = sorted(v)
    return v[len(v) // 2]


def build():
    picks = json.load(open(os.path.join(SRC, 'picks.json')))
    work = os.path.join(CACHE, 'frames')
    os.makedirs(work, exist_ok=True)
    os.makedirs(os.path.join(OUT, 't'), exist_ok=True)
    cut = []
    for i, p in enumerate(picks):
        path, d = resolve(p)
        p['m'] = p.get('m') or d[:7]
        p['date'] = d if d[:7] == p['m'] else p['m'] + '-15'
        dest = os.path.join(work, hashlib.sha1(('%s|%s|%s' % (path, p.get('t'), p.get('rot'))).encode()).hexdigest()[:14] + '.jpg')
        if not os.path.exists(dest):
            im = upright(path, p.get('t'), dest)
            if p.get('rot'):
                # videos saved without their rotation flag come out sideways; rot is degrees clockwise to stand the person up
                im.rotate(-p['rot'], expand=True).save(dest, quality=95)
        cut.append(dest)
    poses = {}
    for line in tool('pose', *cut).splitlines():
        o = json.loads(line)
        poses[o['path']] = o
    est = []
    for p, f in zip(picks, cut):
        iw, ih = Image.open(f).size
        est.append(estimate(poses.get(f, {}), iw, ih))
    # The person stands in one spot through a video, so its front-facing picks set the scale for its side and back
    # picks, where Vision often misreads the torso. A pick more than 20% off the video's scale takes the scale.
    ref = {}
    for n in {p['n'] for p in picks if 'n' in p}:
        mine = [(p, e) for p, e in zip(picks, est) if p.get('n') == n and e and e.get('torso')]
        good = [e for p, e in mine if p['pose'] in ('front', 'biceps')] or [e for _, e in mine]
        if good:
            ref[n] = {'torso': median([e['torso'] for e in good]), 'cx': median([e['cx'] for e in good]),
                      'neck_y': median([e['neck'][1] for e in good])}
    items, checks = {}, []
    for p, f, e in zip(picks, cut, est):
        im = Image.open(f)
        iw, ih = im.size
        r = ref.get(p.get('n'))
        if p.get('box'):
            x, y, w, _ = p['box']
            box, how = (x * iw, y * ih, w * iw, w * iw * H / W), 'manual'
        elif e and e.get('torso') and (not r or abs(e['torso'] / r['torso'] - 1) <= .2):
            box, how = box_for(e['neck'][1], e['cx'], e['torso']), 'pose'
        elif r:
            neck = e['neck'] if e and e.get('neck') else (r['cx'], r['neck_y'])
            box, how = box_for(neck[1], neck[0] if e and e.get('neck') else r['cx'], r['torso']), 'pose'
        else:
            box, how = None, 'centered'
        if not box:
            w = ih * W / H
            box, how = ((iw - w) / 2, 0, w, ih), 'centered'
        x, y, w, h = box
        canvas = Image.new('RGB', (round(w), round(h)), PAD)
        x0, y0, x1, y1 = max(0, round(x)), max(0, round(y)), min(iw, round(x + w)), min(ih, round(y + h))
        canvas.paste(im.crop((x0, y0, x1, y1)), (x0 - round(x), y0 - round(y)))
        out = canvas.resize((W, H), Image.LANCZOS)
        if p.get('flip'):
            out = ImageOps.mirror(out)
        key = '%s-%s' % (p['m'], p['pose'])
        if key in items:
            print('two picks for %s, keeping the later one' % key)
        out.save(os.path.join(OUT, key + '.jpg'), quality=82, optimize=True, progressive=True)
        th = out.resize((180, 240), Image.LANCZOS)
        th.save(os.path.join(OUT, 't', key + '.jpg'), quality=76, optimize=True)
        items[key] = {'m': p['m'], 'date': p['date'], 'pose': p['pose'], 'src': 'physique/%s.jpg' % key,
                      'th': 'physique/t/%s.jpg' % key, 'note': p.get('note', '')}
        checks.append((key, how, th))
    rows = sorted(items.values(), key=lambda it: (it['m'], it['pose']))
    with open(os.path.join(OUT, 'index.js'), 'w') as f:
        f.write('// Built by tools/physique.py from data/physique. Personal, gitignored.\n')
        f.write('window.PHYSIQUE = ' + json.dumps(rows, indent=0) + ';\n')
    cols = 10
    sheet = Image.new('RGB', (cols * 180, -(-len(checks) // cols) * 262), 'white')
    d = ImageDraw.Draw(sheet)
    for i, (key, how, th) in enumerate(checks):
        x, y = (i % cols) * 180, (i // cols) * 262
        sheet.paste(th, (x, y))
        d.text((x + 2, y + 243), key + ('' if how == 'pose' else ' ' + how.upper()), fill='black' if how == 'pose' else 'red', font=font(13))
    sheet.save(os.path.join(CACHE, 'check.jpg'), quality=80)
    print('%d frames in %s. Check sheet: %s' % (len(rows), OUT, os.path.join(CACHE, 'check.jpg')))
    for key, how, _ in checks:
        if how != 'pose':
            print('  %s: %s crop, set a box if it looks off' % (key, how))


def add(paths):
    """Register photos and videos from anywhere on the Mac. Files are read in place, never copied or moved."""
    rows = {}
    if os.path.exists(MANIFEST):
        rows = {r['uuid']: r for r in json.load(open(MANIFEST))}
    n = 0
    for p in paths:
        p = os.path.abspath(os.path.expanduser(p))
        found = []
        if os.path.isdir(p):
            for d, ds, fs in os.walk(p):
                ds[:] = [x for x in ds if not x.startswith('.')]
                found += [os.path.join(d, f) for f in sorted(fs) if not f.startswith('.')]
        else:
            found = [p]
        for f in found:
            if os.path.splitext(f)[1].lower() not in VIDEO | PHOTO:
                continue
            key = hashlib.sha1(f.encode()).hexdigest()[:12]
            if key not in rows:
                n += 1
            rows[key] = {'uuid': key, 'path': f, 'date': file_date(f, f)[0], 'albums': []}
    os.makedirs(SRC, exist_ok=True)
    json.dump(sorted(rows.values(), key=lambda r: r['date']), open(MANIFEST, 'w'), indent=1)
    print('%d new files registered, %d in all. Next: python3 tools/physique.py scan' % (n, len(rows)))


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'add':
        add(sys.argv[2:])
    elif cmd == 'scan':
        scan('--all' in sys.argv)
    elif cmd == 'strip':
        strip(int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]) if len(sys.argv) > 5 else .5)
    elif cmd == 'refine':
        refine({int(a) for a in sys.argv[2:]} or None)
    elif cmd == 'build':
        build()
    else:
        print(__doc__)
