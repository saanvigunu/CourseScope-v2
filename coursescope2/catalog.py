"""Build catalog.json from the raw Schedule of Classes snapshots.

Reads the trimmed HTML snapshots under data/spring2027/raw/, keeps the six
target courses, links each lecture's associated discussion/lab sections
(deduplicated across lectures of the same course - multi-lecture courses
like MATH 54 share one discussion pool), and writes one normalized JSON
catalog. Every value in the catalog traces back to a snapshot file; the
manifest records where each file came from and when it was fetched.
"""

import json
import os
from dataclasses import asdict

from .soc import parse_page, parse_detail

TARGET_COURSES = ["COMPSCI 61A", "COMPSCI 61B", "COMPSCI 70", "DATA C8", "MATH 54", "ECON 1"]


def build_catalog(raw_dir, manifest, out_path):
    """Parse every snapshot in raw_dir and write the normalized catalog."""
    lectures = {}   # ccn -> Section
    assoc = {}      # ccn -> Section (with parent ccn noted separately)
    parents = {}    # assoc ccn -> parent lecture ccn

    for name in sorted(os.listdir(raw_dir)):
        if not name.endswith(".html"):
            continue
        with open(os.path.join(raw_dir, name), encoding="utf-8") as fh:
            html = fh.read()
        if name.endswith("_detail.html"):
            primary_ccn, associated = parse_detail(html)
            for sec in associated:
                if sec.course not in TARGET_COURSES:
                    continue
                if sec.ccn in assoc:
                    continue  # shared discussion pool seen from another lecture
                assoc[sec.ccn] = sec
                parents[sec.ccn] = primary_ccn
        else:
            for sec in parse_page(html):
                if sec.course not in TARGET_COURSES or sec.kind != "LEC":
                    continue
                lectures[sec.ccn] = sec

    courses = {}
    for ccn, lec in lectures.items():
        courses.setdefault(lec.course, {"title": lec.title, "units": lec.units,
                                        "lecture_ccns": [], "sections": []})
        courses[lec.course]["lecture_ccns"].append(ccn)
    for ccn, sec in assoc.items():
        entry = courses.get(sec.course)
        if entry is None:
            continue  # associated section whose lecture was not a target (should not happen)
        sec.title = entry["title"]

    catalog = {
        "term": manifest["term"],
        "source": manifest["source"],
        "fetched_at": manifest["fetched_at"],
        "courses": [],
    }
    for course in TARGET_COURSES:
        entry = courses.get(course)
        if entry is None:
            continue
        secs = []
        for ccn in entry["lecture_ccns"]:
            secs.append(_record(lectures[ccn], parent_ccn=None))
        for ccn, sec in assoc.items():
            if sec.course == course:
                secs.append(_record(sec, parent_ccn=parents[ccn]))
        catalog["courses"].append({
            "course": course,
            "title": entry["title"],
            "units": entry["units"],
            "sections": secs,
        })

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, indent=2, sort_keys=False)
        fh.write("\n")
    return catalog


def _record(sec, parent_ccn):
    rec = asdict(sec)
    rec["parent_ccn"] = parent_ccn
    return rec


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    base = os.path.join(here, os.pardir, "data", "spring2027")
    with open(os.path.join(base, "MANIFEST.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    catalog = build_catalog(os.path.join(base, "raw"), manifest,
                            os.path.join(base, "catalog.json"))
    total = sum(len(c["sections"]) for c in catalog["courses"])
    print(f"catalog.json: {len(catalog['courses'])} courses, {total} sections")


if __name__ == "__main__":
    main()
