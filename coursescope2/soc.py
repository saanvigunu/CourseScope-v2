"""Parser for UC Berkeley Schedule of Classes search pages (classes.berkeley.edu).

The Schedule of Classes publishes server-rendered HTML at
    https://classes.berkeley.edu/search/class?search=<query>&f[]=term:<term_id>

This module parses that HTML into plain section records. It never invents a
value: a field missing from the page comes out as None or an empty list, and
the raw snapshot files stay in the repo so every parsed value can be traced
back to what the site actually served (see data/spring2027/MANIFEST.json for
the source URL and fetch date of each snapshot).
"""

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

DAY_MAP = {
    "Mo": "M", "Tu": "Tu", "We": "W", "Th": "Th", "Fr": "F", "Sa": "Sa", "Su": "Su",
}


@dataclass
class Meeting:
    days: tuple          # subset of ("M","Tu","W","Th","F","Sa","Su")
    start: int | None    # minutes since midnight, None when the page has no time
    end: int | None
    dates: str           # e.g. "Jan 19, 2027 - May 07, 2027", verbatim
    location: str | None

    def describe(self):
        days = "/".join(self.days) if self.days else "TBA"
        if self.start is None or self.end is None:
            return f"{days} time TBA"
        return f"{days} {fmt_time(self.start)}-{fmt_time(self.end)}"


@dataclass
class Section:
    ccn: str                 # the 5-digit class number, e.g. "28320"
    course: str              # e.g. "COMPSCI 61A"
    section: str             # e.g. "001"
    kind: str                # "LEC", "DIS", "LAB", ...
    title: str
    units: float | None      # upper end when the page lists a range (see units_text)
    units_text: str | None   # verbatim from the page, e.g. "4" or "1to4"
    instructors: list
    meetings: list
    seats_text: str | None   # verbatim, e.g. "174 Unreserved Seats"
    instruction_mode: str | None
    detail_path: str         # e.g. "/content/2027-spring-compsci-61a-001-lec-001"
    term: str                # e.g. "Spring 2027", verbatim from the card

    def conflicts_with(self, other):
        for m in self.meetings:
            for n in other.meetings:
                if m.start is None or n.start is None:
                    continue  # cannot prove a conflict without times
                if not set(m.days) & set(n.days):
                    continue
                if m.start < n.end and n.start < m.end:
                    return True
        return False


def parse_time_text(text):
    """'01:00 pm' or '9:30 am' -> minutes since midnight. None if unparseable."""
    text = text.strip().lower()
    try:
        hm, ap = text.rsplit(None, 1)
        hours, minutes = hm.split(":")
        hours, minutes = int(hours), int(minutes)
    except ValueError:
        return None
    if ap.startswith("p") and hours != 12:
        hours += 12
    if ap.startswith("a") and hours == 12:
        hours = 0
    return hours * 60 + minutes


def fmt_time(minutes):
    return f"{minutes // 60}:{minutes % 60:02d}"


def parse_days_text(text):
    """'Mo, We, Fr' -> ('M', 'W', 'F'); unknown day names are dropped, not guessed."""
    days = []
    for part in text.split(","):
        d = DAY_MAP.get(part.strip())
        if d:
            days.append(d)
    return tuple(days)


def parse_time_range(text):
    """'01:00 pm  -  01:59 pm' -> (start, end) in minutes; (None, None) on failure."""
    if "-" not in text:
        return None, None
    left, right = text.split("-", 1)
    return parse_time_text(left), parse_time_text(right)


def _classes(attrs):
    for name, value in attrs:
        if name == "class":
            return set(value.split())
    return set()


class _PageParser(HTMLParser):
    """State machine over one search page, one .views-row card per section."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sections = []
        self._sec = None          # current section dict under construction
        self._meeting = None      # current meeting dict under construction
        self._capture = None      # name of the field currently collecting text
        self._depth = 0           # tag depth inside the captured element
        self._buf = []

    # -- helpers ---------------------------------------------------------
    def _start_capture(self, name):
        self._capture = name
        self._depth = 1
        self._buf = []

    def _store(self, text):
        text = " ".join(text.split())
        if not text or self._sec is None or self._capture is None:
            return
        target = self._capture
        if target.startswith("meeting.") and self._meeting is not None:
            self._meeting[target.split(".", 1)[1]] = text
        elif target == "instructors":
            # drop the icon alt text if the parser picked it up
            self._sec["instructors"] = text
        else:
            self._sec[target] = text

    # -- HTMLParser hooks --------------------------------------------------
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cl = _classes(list(attrs.items()))
        if self._capture is not None:
            self._depth += 1
        if "views-row" in cl:
            self._sec = {
                "term": None, "ccn": None, "course": None, "section": None,
                "kind": None, "title": None, "units": None, "instructors": None,
                "meetings": [], "seats_text": None, "instruction_mode": None,
                "detail_path": "",
            }
            self._meeting = None
            return
        if self._sec is None:
            return
        if attrs.get("aria-describedby", "").startswith("im-label-"):
            self._start_capture("instruction_mode")
        elif "st--term-year" in cl:
            self._start_capture("term")
        elif tag == "a" and self._sec["detail_path"] == "" and \
                attrs.get("href", "").startswith("/content/"):
            self._sec["detail_path"] = attrs["href"]
        elif "st--section-name" in cl:
            self._start_capture("course")
        elif "st--section-code" in cl:
            self._start_capture("kind")
        elif "st--title" in cl:
            self._start_capture("title")
        elif "st--instructors" in cl:
            self._start_capture("instructors")
        elif "st--meeting-details" in cl:
            self._meeting = {"dates": None, "days": None, "time": None, "location": None}
            self._sec["meetings"].append(self._meeting)
        elif "st--meeting-dates" in cl:
            self._start_capture("meeting.dates")
        elif "st--meeting-days" in cl:
            self._start_capture("meeting.days")
        elif "st--meeting-time" in cl:
            self._start_capture("meeting.time")
        elif "st--location" in cl:
            self._start_capture("meeting.location")
        elif "st--details-unit" in cl:
            self._start_capture("units")
        elif "st--seats" in cl:
            self._start_capture("seats_text")
        elif "st--section-number" in cl and self._sec["ccn"] is None and \
                self._sec["course"] is not None:
            # the header card shows "#28320"; the info wrapper repeats it as
            # "Class #: 28320" - either one is the CCN, take the first we see
            self._start_capture("ccn")

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if self._capture is not None:
            self._depth -= 1
            if self._depth <= 0:
                self._store("".join(self._buf))
                self._capture = None
                self._buf = []
        elif self._sec is not None and tag == "article":
            self.sections.append(self._sec)
            self._sec = None
            self._meeting = None

    def handle_data(self, data):
        if self._capture is not None:
            self._buf.append(data)


def _post_process(raw):
    """Turn the raw string fields into a Section record."""
    course = raw.get("course") or ""
    section_no = ""
    kind = raw.get("kind") or ""
    # the "001 - LEC 001" text lands partly around the captured spans; the
    # section number is the digits right after the course code in detail_path
    # e.g. /content/2027-spring-compsci-61a-001-lec-001
    parts = raw["detail_path"].strip("/").split("-")
    if len(parts) >= 6:
        section_no = parts[-3]
    ccn = (raw.get("ccn") or "").replace("#", "")
    ccn = "".join(ch for ch in ccn if ch.isdigit())
    units_text = None
    units = None
    if raw.get("units"):
        # the page renders fixed units as "4" and ranges as "1to4" (verbatim,
        # no separator in the markup); keep the text and take the upper end
        # so a unit cap never under-counts a variable-unit course
        u = raw["units"].replace("Units:", "").strip()
        m = re.fullmatch(r"(\d+(?:\.\d+)?)(?:to(\d+(?:\.\d+)?))?", u)
        if m:
            units_text = u
            units = float(m.group(2) or m.group(1))
    meetings = []
    for m in raw["meetings"]:
        start, end = parse_time_range(m.get("time") or "")
        location = m.get("location")
        if location:
            location = location.replace("(opens in a new window)", "").strip()
        meetings.append(Meeting(
            days=parse_days_text(m.get("days") or ""),
            start=start, end=end,
            dates=m.get("dates") or "",
            location=location or None,
        ))
    seats = raw.get("seats_text") or None
    if seats:
        if "No Open Seats" in seats:
            seats = "No Open Seats"
        else:
            seats = seats.replace("Open Seats", "", 1).strip() or None
    instructors = []
    if raw.get("instructors"):
        instructors = [i.strip() for i in raw["instructors"].split(",") if i.strip()]
    return Section(
        ccn=ccn, course=course, section=section_no, kind=kind,
        title=raw.get("title") or "", units=units, units_text=units_text,
        instructors=instructors,
        meetings=meetings, seats_text=seats,
        instruction_mode=raw.get("instruction_mode"),
        detail_path=raw["detail_path"], term=raw.get("term") or "",
    )


def parse_page(html_text):
    """Parse one search-results page into a list of Section records."""
    parser = _PageParser()
    parser.feed(html_text)
    parser.close()
    return [_post_process(raw) for raw in parser.sections]


def parse_files(paths):
    """Parse several snapshot files, in order, into one section list."""
    sections = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            sections.extend(parse_page(fh.read()))
    return sections


# ---------------------------------------------------------------------------
# Detail pages (/content/<term-slug>-<course-slug>-<sec>-<kind>-<sec>)
#
# A lecture's detail page lists its associated discussion/lab sections in
# .detail-class-associated-sections-flex blocks. Those blocks carry no units
# line: Berkeley attaches the course's units to the lecture, so associated
# sections are modeled as 0-unit add-ons of their parent lecture.
# ---------------------------------------------------------------------------

_ASSOC_KINDS = {"dis", "lab", "sem", "grp", "slf", "ind", "sup", "col", "lec"}


def identity_from_slug(slug):
    """'2027-spring-compsci-61a-103-dis-103' -> ('Spring 2027', 'COMPSCI 61A', '103', 'DIS').

    The slug is the section's canonical identifier on classes.berkeley.edu;
    parsing it never invents data, it reads the URL the site itself assigns.
    """
    slug = slug.strip("/").rsplit("/", 1)[-1]
    parts = slug.split("-")
    if len(parts) < 6:
        raise ValueError(f"not a section slug: {slug!r}")
    term = f"{parts[1].capitalize()} {parts[0]}"
    kind = parts[-2].upper()
    course = " ".join(parts[2:-3]).upper()
    return term, course, parts[-3], kind


class _AssocParser(HTMLParser):
    """Collects the associated-section blocks of a detail page.

    Each .detail-class-associated-sections-flex block becomes one dict with
    the section link, its heading text, the label:value fields (Days, Time,
    Place, Open Seats, ...) and the block's raw text (which carries the lines
    without label spans, like '103 DIS' and 'Class #: 28642').
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self._cur = None
        self._capture = None   # 'heading' | 'label' | 'value'
        self._depth = 0
        self._buf = []
        self._pending_label = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cl = _classes(list(attrs.items()))
        if "detail-class-associated-sections-flex" in cl:
            self.blocks.append({"href": "", "heading": "", "fields": {}, "raw": []})
            self._cur = self.blocks[-1]
            return
        if self._cur is None:
            return
        if self._capture is not None:
            self._depth += 1
        elif tag == "a" and self._cur["href"] == "" and \
                attrs.get("href", "").startswith("/content/"):
            self._cur["href"] = attrs["href"]
            self._capture = "heading"
            self._depth = 1
            self._buf = []
        elif "detail-label" in cl or "ls-label" in cl:
            self._capture = "label"
            self._depth = 1
            self._buf = []

    def handle_endtag(self, tag):
        if self._cur is None or self._capture is None:
            return
        self._depth -= 1
        if self._depth > 0:
            return
        text = " ".join("".join(self._buf).split())
        if self._capture == "heading":
            self._cur["heading"] = text
            self._capture = None
        elif self._capture == "label":
            self._pending_label = text.rstrip(":")
            self._capture = "value"
            self._depth = 1
            self._buf = []
        else:  # value
            self._cur["fields"][self._pending_label] = text
            self._capture = None

    def handle_data(self, data):
        if self._cur is None:
            return
        if self._capture is not None:
            self._buf.append(data)
        else:
            self._cur["raw"].append(data)


def _assoc_to_section(block):
    """Turn one associated-section block into a Section record."""
    href = block["href"]
    term, course, section_no, kind = identity_from_slug(href)
    fields = block["fields"]
    raw_text = " ".join("".join(block["raw"]).split())
    start, end = parse_time_range(fields.get("Time", ""))
    meeting = Meeting(
        days=parse_days_text(fields.get("Days", "")),
        start=start, end=end, dates="",
        location=fields.get("Place") or None,
    )
    seats = None
    if "Open Seats" in fields:
        seats = f"Open Seats: {fields['Open Seats']}"
    m = re.search(r"Class #:\s*(\d+)", raw_text)
    ccn = m.group(1) if m else ""
    return Section(
        ccn=ccn, course=course, section=section_no, kind=kind,
        title="",  # inherits the parent lecture's title at link time
        units=0.0,  # no units line on associated blocks; units live on the LEC
        units_text=None,
        instructors=[], meetings=[meeting], seats_text=seats,
        instruction_mode=fields.get("Instruction Mode"),
        detail_path=href, term=term,
    )


def parse_detail(html_text):
    """Parse one section detail page.

    Returns (primary_ccn, associated) where primary_ccn is the class number
    of the section the page belongs to and associated is the list of its
    linked sections (discussions, labs, ...) as Section records with
    parent_ccn set.
    """
    m = re.search(r'sf--section-number">\s*<span>Class #:</span>\s*(\d+)', html_text)
    primary_ccn = m.group(1) if m else None
    parser = _AssocParser()
    parser.feed(html_text)
    parser.close()
    associated = []
    for block in parser.blocks:
        if not block["href"]:
            continue
        try:
            associated.append(_assoc_to_section(block))
        except ValueError:
            continue  # a block without a section link is not a section
    return primary_ccn, associated
