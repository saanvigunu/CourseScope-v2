# CourseScope-v2

A UC Berkeley schedule builder that runs on the **real Schedule of Classes**. It builds conflict-free course schedules (lecture + required discussions/labs per course), ranked by fewer days on campus and shorter idle gaps.

## Why a v2

[CourseScope](https://github.com/saanvigunu/CourseScope) (v1) proved out the scheduling engine, but its catalog was an illustrative sample of invented sections, as its own README admits. v2 keeps the idea and replaces the data: every section here was parsed out of snapshots of [classes.berkeley.edu](https://classes.berkeley.edu), Berkeley's official Schedule of Classes. The original v1 repo is untouched.

## The data is the point

- `data/spring2027/raw/` holds the actual HTML snapshots: search results and lecture detail pages for COMPSCI 61A, COMPSCI 61B, COMPSCI 70, DATA C8, MATH 54, and ECON 1, fetched 2026-11-18/19.
- `data/spring2027/MANIFEST.json` maps every snapshot to the exact URL it came from and when, so nothing in the catalog is unsourced.
- `coursescope2/catalog.py` parses the snapshots into `data/spring2027/catalog.json` (6 courses, 197 sections), linking each discussion/lab to its parent lecture by class number. Rerunning it against the snapshots reproduces the catalog byte for byte.

Honest caveats:

- Seat counts and times are what the site showed on the fetch dates. Sections change; regenerate the snapshots before relying on this for a real enrollment decision.
- As of the fetch date, **DATA C8 had no discussion sections published for Spring 2027** — only placeholder "999" labs. The engine treats placeholders (and any section with no published time) as TBA: they never conflict, and they rank below real scheduled sections because an unscheduled section can land anywhere once the department posts it.
- MATH 54's two lectures share one discussion pool; the catalog dedupes those by class number.
- This does not check enrollment, waitlists, or requisites, and it does not touch the live site at runtime.

## Usage

No dependencies beyond Python 3.10+.

```console
$ python3 -m coursescope2 list
COMPSCI 61A  The Structure and Interpretation of Computer Programs
             4 units, sections: 1 LEC, 33 DIS, 22 LAB
COMPSCI 61B  Data Structures
             4 units, sections: 1 LEC, 36 DIS, 33 LAB
...

$ python3 -m coursescope2 plan --courses "COMPSCI 61B,COMPSCI 70,MATH 54" --top 2
2 schedule option(s), 12 units total:

option 1  (days on campus: 5, idle gaps: 8 min)
  COMPSCI 61B  LEC 001   M/W/F 15:00-15:59      #28355
  COMPSCI 61B  DIS 119   Tu 18:00-18:59         #28389
  COMPSCI 61B  LAB 101l  W 13:00-14:59          #28536
  COMPSCI 70   LEC 001   Tu/Th 12:30-13:59      #28417
  COMPSCI 70   DIS 115   Tu/Th 17:00-17:59      #28432
  MATH 54      LEC 002   Tu/Th 15:30-16:59      #21850
  MATH 54      DIS 210   Tu/Th 14:00-15:29      #21873
```

`plan` options: `--max-units N`, `--no-before "9:00 am"`, `--no-after "6:00 pm"`, `--top N`.

## How the engine works

Each course expands into its legal combinations: one lecture plus one section of every other kind the course actually published (a course with no discussions posted yields lecture-only options, not invented ones). A backtracking search assembles cross-course schedules, pruning any combination with a time conflict. Survivors pass the hard bounds (unit cap, no-before/no-after) and are ranked: −20 per day on campus, −30 per TBA placeholder section, minus idle-gap time.

## Tests

```console
$ python3 -m unittest
Ran 20 tests in 0.570s

OK
```

`test_soc.py` runs the parser against the committed snapshots and asserts the real counts (e.g. 61B's 36 discussions and 33 labs, C8's placeholder-only labs), verbatim variable-unit text, and slug identity. `test_scheduler.py` covers conflict rules, combination building, unit/time bounds, placeholder ranking, and an end-to-end plan on the real catalog.

## Layout

```
coursescope2/        the package: soc.py (parser), catalog.py, models.py, scheduler.py, cli.py
data/spring2027/     raw snapshots, MANIFEST.json, generated catalog.json
test_soc.py          parser tests against the snapshots
test_scheduler.py    engine tests
```
