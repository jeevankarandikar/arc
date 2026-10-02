#!/usr/bin/env python3
"""Your Notes app lift logs (Oct 2021 to Mar 2024, before Strong) to best e1RM per session.

    python3 tools/liftlog.py            print the LIFTLOG array
    python3 tools/liftlog.py --write    replace the LIFTLOG block in index.html

Reads data/lifting-log.txt (personal, gitignored). Only the lifts the page charts are kept:
bench, back squat, deadlift, and the dumbbell shoulder press (one dumbbell's weight, the ohp line).
e1RM is Brzycki, weight * 36 / (37 - reps). Sets of 10 reps or fewer win; longer sets count as 10 and only
when they are all there is. Failed sets are dropped and half reps round down.
"""
import os, re, sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, 'data', 'lifting-log.txt')
SECTIONS = {'bench press': 'bench', 'barbell squat': 'squat', 'deadlift (5 min rest)': 'deadlift',
            'dumbbell shoulder press': 'ohp'}
DATE = re.compile(r'\((\d{1,2})/(\d{1,2})/(\d{1,4})\)')
SET = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*(kg)?\s*s?\s*x\s*(\d+(?:\.\d+)?)', re.I)
REP = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*(?:pause)?\s*$', re.I)


def e1rm(w, r):
    r = int(r)
    return w * 36 / (37 - min(r, 10)) if r >= 1 else None


def parse():
    out, lift, prev = [], None, None
    for line in open(LOG):
        line = line.strip()
        if not line:
            continue
        m = DATE.search(line)
        if not m and ' x ' not in line:
            lift, prev = SECTIONS.get(line.lower()), None
            continue
        if not lift or not m:
            continue
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 100 else y
        when = date(y, mo, d)
        if prev and when < prev:
            # typos like 10/19/12 or 2/23/22 inside a 2023 run: take the year that keeps the log in order
            for yy in (prev.year, prev.year + 1):
                if date(yy, mo, d) >= prev:
                    when = date(yy, mo, d)
                    break
        prev = when
        body = re.sub(r'(\d)\.(\d{3})', r'\1, \2', line[:m.start()]).replace(' / ', ' | ')
        best, best_rank, w = None, None, None
        for part in body.split('|'):
            for tok in part.split(','):
                if 'fail' in tok.lower():
                    continue
                s = SET.match(tok)
                if s:
                    w = float(s.group(1)) * (2.2046 if s.group(2) else 1)
                    r = float(s.group(3))
                else:
                    t = REP.match(tok)
                    if not (t and w and float(t.group(1)) <= 30):
                        continue
                    r = float(t.group(1))
                v = e1rm(w, r)
                # sets past 10 reps overstate the max, so they only count when nothing heavier was logged
                rank = (r <= 10, v or 0)
                if v and (best is None or rank > best_rank):
                    best, best_rank = v, rank
        if best:
            out.append((lift, when.isoformat(), round(best, 1)))
    return out


def js(rows):
    lines = ['var LIFTLOG = [']
    for lift in ('bench', 'squat', 'deadlift', 'ohp'):
        mine = ["['%s', '%s', %g]" % r for r in rows if r[0] == lift]
        for i in range(0, len(mine), 5):
            lines.append('  ' + ', '.join(mine[i:i + 5]) + ',')
    lines[-1] = lines[-1].rstrip(',')
    lines.append('];')
    return '\n'.join(lines)


if __name__ == '__main__':
    block = js(parse())
    if '--write' in sys.argv:
        p = os.path.join(ROOT, 'index.html')
        s = open(p).read()
        a, b = s.index('var LIFTLOG = ['), s.index('];', s.index('var LIFTLOG = [')) + 2
        open(p, 'w').write(s[:a] + block + s[b:])
        print('wrote %d entries' % block.count("['"))
    else:
        print(block)
