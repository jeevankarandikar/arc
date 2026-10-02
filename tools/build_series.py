#!/usr/bin/env python3
"""Build series.js, the daily history the dashboard charts read.

    python3 tools/build_series.py

series.js holds your daily history and is personal data, so keep your copy of this repo private. Its inputs stay in data/ (gitignored):
  --health   Apple Health export.zip                  weight, body fat, steps, meals logged in apps,
                                                        Whoop sleep and resting HR after the Whoop export ends
  --whoop    Whoop export zip                         sleep, consistency, resting HR, HRV, recovery, energy burned
  --eufy     eufy scale CSV                           weight and body fat, 2021 to 2025
  --strong   Strong CSV                               top set per lift per day as a Brzycki e1RM, sessions per day
  --weighins data/weighins.csv (date,lb,when)         hand-logged weigh-ins, including the dosing log
  --base     an earlier series.js                     keeps its days wherever this build has none

Inputs that are missing are skipped. With --base, a session that has only a new Health export (the
cloud session, say) can top up the published series.js without the Mac-only Whoop, eufy and Strong files:

    python3 tools/build_series.py --health data/export.zip --base series.js

Output: window.SERIES = {built, epoch, d: {metric: [[dayNumber, value], ...]}}
dayNumber counts days from epoch (2017-01-01). Every value is per calendar day.
"""
import argparse
import collections
import csv
import io
import json
import os
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime

HOME = os.path.expanduser("~")
EPOCH = date(2017, 1, 1)
FMT = "%Y-%m-%d %H:%M:%S %z"
ASLEEP = {"AsleepUnspecified", "AsleepCore", "AsleepDeep", "AsleepREM", "Asleep"}
PHONES = ("17ProMax", "iPhone")
LIFTS = {
    "bench": ["Bench Press (Barbell)"],
    "squat": ["Squat (Barbell)"],
    "deadlift": ["Deadlift (Barbell)"],
    "press": ["Shoulder Press (Plate Loaded)"],
    "ohp": ["Overhead Press (Dumbbell)"],
    "lateral": ["Lateral Raise (Dumbbell)"],
    "curl": ["Bicep Curl (Cable)"],
    "pushdown": ["Triceps Pushdown (Cable - Straight Bar)"],
}


def dn(s):
    return (date.fromisoformat(s[:10]) - EPOCH).days


def mean(v):
    return sum(v) / len(v)


def brzycki(w, r):
    return w * 36 / (37 - r)


def health(path, out):
    weight, fat = collections.defaultdict(list), collections.defaultdict(list)
    steps = collections.defaultdict(dict)
    kcal, prot = collections.defaultdict(float), collections.defaultdict(float)
    rhr, sleep = {}, collections.defaultdict(float)
    with zipfile.ZipFile(path) as z, z.open("apple_health_export/export.xml") as f:
        for _, el in ET.iterparse(f, events=("end",)):
            if el.tag != "Record":
                if el.tag == "Workout":
                    el.clear()
                continue
            t, src, sd = el.get("type", ""), el.get("sourceName") or "", el.get("startDate") or ""
            try:
                v = float(el.get("value"))
            except (TypeError, ValueError):
                v = None
            if t == "HKQuantityTypeIdentifierBodyMass" and v:
                weight[sd[:10]].append(v)
            elif t == "HKQuantityTypeIdentifierBodyFatPercentage" and v:
                fat[sd[:10]].append(v * 100)
            elif t == "HKQuantityTypeIdentifierStepCount" and v:
                who = "phone" if src in PHONES else ("watch" if "Watch" in src else ("whoop" if src == "WHOOP" else "other"))
                steps[sd[:10]][who] = steps[sd[:10]].get(who, 0) + v
            elif t == "HKQuantityTypeIdentifierDietaryEnergyConsumed" and v:
                kcal[sd[:10]] += v
            elif t == "HKQuantityTypeIdentifierDietaryProtein" and v:
                prot[sd[:10]] += v
            elif t == "HKQuantityTypeIdentifierRestingHeartRate" and src == "WHOOP" and v:
                rhr[sd[:10]] = v
            elif t == "HKCategoryTypeIdentifierSleepAnalysis" and src == "WHOOP":
                if (el.get("value") or "").replace("HKCategoryValueSleepAnalysis", "") in ASLEEP:
                    a, b = datetime.strptime(sd, FMT), datetime.strptime(el.get("endDate"), FMT)
                    sleep[el.get("endDate")[:10]] += (b - a).total_seconds() / 3600
            el.clear()
    for d, v in weight.items():
        out["weight"][d].append(mean(v))
    for d, v in fat.items():
        out["bodyfat"][d].append(mean(v))
    for d, s in steps.items():
        # The phone misses steps taken while it sits on a desk and the wrist misses some too, so the day
        # takes whichever source counted more, close to what the Health app shows after merging them.
        n = max(s.values()) if s else 0
        if n >= 50:
            out["steps"][d] = [n]
    for d, v in kcal.items():
        out["kcal"][d] = [v]
        if prot.get(d):
            out["protein"][d] = [prot[d]]
    return rhr, sleep


def whoop(path, out):
    with zipfile.ZipFile(path) as z, z.open("physiological_cycles.csv") as f:
        for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8")):
            wake, start = (r.get("Wake onset") or "")[:10], (r.get("Cycle start time") or "")[:10]
            def num(k):
                try:
                    return float(r[k])
                except (KeyError, TypeError, ValueError):
                    return None
            if wake:
                for key, col, scale in (("sleep", "Asleep duration (min)", 1 / 60), ("cons", "Sleep consistency %", 1),
                                        ("rhr", "Resting heart rate (bpm)", 1), ("hrv", "Heart rate variability (ms)", 1),
                                        ("recovery", "Recovery score %", 1)):
                    v = num(col)
                    if v is not None:
                        out[key][wake] = [v * scale]
            e = num("Energy burned (cal)")
            if start and e and r.get("Cycle end time"):
                out["energy"][start] = [e]
    return max(out["sleep"]) if out["sleep"] else ""


def eufy(path, out):
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            d = r["Time"][:10]
            try:
                w = float(r["WEIGHT (lbs)"])
                out["weight"][d].append(w)
            except ValueError:
                pass
            try:
                bf = float(r["BODY FAT %"])
                if bf > 0:
                    out["bodyfat"][d].append(bf)
            except ValueError:
                pass


def strong(path, out, titles):
    best = collections.defaultdict(dict)
    workouts = collections.defaultdict(set)
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            d = r["Date"][:10]
            workouts[d].add(r["Date"])
            if r.get("Workout Name"):
                titles[d].add(r["Workout Name"].strip())
            order = (r.get("Set Order") or "").strip()
            if order in ("W", "Rest Timer") or not r.get("Weight"):
                continue
            try:
                w, reps = float(r["Weight"]), float(r["Reps"])
            except ValueError:
                continue
            if w <= 0 or reps < 1 or reps > 12:
                continue
            for key, names in LIFTS.items():
                if r["Exercise Name"] in names:
                    e = brzycki(w, reps)
                    if e > best[key].get(d, 0):
                        best[key][d] = e
    for key, days in best.items():
        for d, e in days.items():
            out[key][d] = [e]
    for d, ids in workouts.items():
        out["sessions"][d] = [len(ids)]


def weighins(path, out):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for r in csv.DictReader(f):
            out["weight"][r["date"]].append(float(r["lb"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--health", default="data/export.zip")
    ap.add_argument("--whoop", default="data/whoop.zip")
    ap.add_argument("--eufy", default="data/scale.csv")
    ap.add_argument("--strong", default="data/strong_workouts.csv")
    ap.add_argument("--weighins", default="data/weighins.csv")
    ap.add_argument("--out", default="series.js")
    ap.add_argument("--base")
    a = ap.parse_args()

    def have(path, name):
        if path and os.path.exists(path):
            return True
        print("skipping", name, "(not found:", path, ")")
        return False

    base = None
    if a.base:
        t = open(a.base).read()
        base = json.loads(t[t.index("=") + 1:].strip().rstrip(";"))

    out = collections.defaultdict(lambda: collections.defaultdict(list))
    rhr_h, sleep_h = health(a.health, out) if have(a.health, "Health") else ({}, {})
    last_whoop = whoop(a.whoop, out) if have(a.whoop, "Whoop") else ""
    if not last_whoop and base and base["d"].get("hrv"):
        # HRV only ever comes from the Whoop export, so its last day marks where that export ended.
        last_whoop = (EPOCH.fromordinal(EPOCH.toordinal() + base["d"]["hrv"][-1][0])).isoformat()
    for d, v in rhr_h.items():
        if d > last_whoop:
            out["rhr"][d] = [v]
    for d, v in sleep_h.items():
        if d > last_whoop:
            out["sleep"][d] = [v]
    if have(a.eufy, "eufy"):
        eufy(a.eufy, out)
    titles = collections.defaultdict(set)
    if have(a.strong, "Strong"):
        strong(a.strong, out, titles)
    weighins(a.weighins, out)
    if base:
        for key, pts in base["d"].items():
            for n, v in pts:
                day = date.fromordinal(EPOCH.toordinal() + n).isoformat()
                if not out[key].get(day):
                    out[key][day] = [v]
        for n, names in (base.get("workouts") or {}).items():
            day = date.fromordinal(EPOCH.toordinal() + int(n)).isoformat()
            if not titles[day]:
                titles[day] = set(x.strip() for x in names.split(","))

    digits = {"weight": 1, "bodyfat": 1, "sleep": 2, "steps": 0, "kcal": 0, "protein": 0, "energy": 0}
    d = {}
    for key, days in out.items():
        pts = []
        for day, vals in days.items():
            if not vals:
                continue
            v = mean(vals)
            nd = digits.get(key, 1)
            pts.append([dn(day), round(v, nd) if nd else int(round(v))])
        pts.sort()
        d[key] = pts
    workouts = {str(dn(day)): ", ".join(sorted(n)) for day, n in titles.items() if n}
    payload = {"built": date.today().isoformat(), "epoch": EPOCH.isoformat(), "d": d, "workouts": workouts}
    with open(a.out, "w") as f:
        f.write("window.SERIES=" + json.dumps(payload, separators=(",", ":")) + ";\n")
    print("wrote", a.out, os.path.getsize(a.out) // 1024, "KB")
    for key in sorted(d):
        p = d[key]
        first = (EPOCH.toordinal() + p[0][0]) if p else None
        last = (EPOCH.toordinal() + p[-1][0]) if p else None
        print(f"  {key:9} {len(p):5} days  {date.fromordinal(first) if first else '-'} to {date.fromordinal(last) if last else '-'}")


if __name__ == "__main__":
    main()
