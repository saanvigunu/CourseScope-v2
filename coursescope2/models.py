"""Load the normalized catalog into Course and Section objects."""

import json

from .soc import Meeting, Section


class Course:
    """One catalog course: identity plus every published section."""

    def __init__(self, course, title, units, sections):
        self.course = course          # e.g. "COMPSCI 61A"
        self.title = title
        self.units = units or 0.0
        self.sections = sections      # list of Section
        self.lectures = [s for s in sections if s.kind == "LEC"]
        self.by_kind = {}
        for sec in sections:
            if sec.kind == "LEC":
                continue
            self.by_kind.setdefault(sec.kind, []).append(sec)

    def required_kinds(self):
        """Section kinds a schedule must pick for this course, beyond the LEC.

        Only kinds the course actually published sections for are required:
        if the department has not posted discussions yet, the honest answer
        is a lecture-only schedule, not an invented one.
        """
        return sorted(self.by_kind)


def _section_from_record(rec):
    meetings = [Meeting(days=tuple(m["days"]), start=m["start"], end=m["end"],
                        dates=m["dates"], location=m["location"])
                for m in rec["meetings"]]
    return Section(
        ccn=rec["ccn"], course=rec["course"], section=rec["section"],
        kind=rec["kind"], title=rec["title"], units=rec["units"],
        units_text=rec.get("units_text"), instructors=rec["instructors"],
        meetings=meetings, seats_text=rec["seats_text"],
        instruction_mode=rec["instruction_mode"],
        detail_path=rec["detail_path"], term=rec["term"],
    )


def load_catalog(path):
    """Read catalog.json into a dict of course name -> Course."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    courses = {}
    for entry in data["courses"]:
        sections = [_section_from_record(r) for r in entry["sections"]]
        courses[entry["course"]] = Course(entry["course"], entry["title"],
                                          entry["units"], sections)
    return {"term": data["term"], "source": data["source"],
            "fetched_at": data["fetched_at"], "courses": courses}
