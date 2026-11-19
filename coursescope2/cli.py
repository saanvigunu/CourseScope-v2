"""Command line interface: list the catalog, plan a schedule."""

import argparse
import os
import sys

from .models import load_catalog
from .scheduler import Preferences, build_schedules, format_schedule, is_placeholder
from .soc import parse_time_text

DEFAULT_CATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               os.pardir, "data", "spring2027", "catalog.json")


def _provenance_footer(catalog):
    return (f"source: UC Berkeley Schedule of Classes (classes.berkeley.edu), "
            f"{catalog['term']}, fetched {catalog['fetched_at']}\n"
            f"seat counts and times are what the site showed on that date; "
            f"sections marked TBA are placeholders the department has not scheduled yet.")


def cmd_list(catalog, args):
    for name, course in catalog["courses"].items():
        kinds = {k: len(v) for k, v in course.by_kind.items()}
        lec = len(course.lectures)
        summary = ", ".join([f"{lec} LEC"] + [f"{n} {k}" for k, n in sorted(kinds.items())])
        units = course.units
        unit_note = f"{units:g} units"
        for sec in course.sections:
            if sec.units_text and "to" in sec.units_text:
                unit_note += f" (listed as {sec.units_text.replace('to', ' to ')})"
                break
        print(f"{name:<12} {course.title}")
        print(f"{'':12} {unit_note}, sections: {summary}")
        if not kinds:
            print(f"{'':12} note: no discussion/lab sections published in this snapshot")
    print()
    print(_provenance_footer(catalog))


def cmd_plan(catalog, args):
    wanted = [c.strip().upper() for c in args.courses.split(",") if c.strip()]
    courses = []
    for name in wanted:
        course = catalog["courses"].get(name)
        if course is None:
            known = ", ".join(sorted(catalog["courses"]))
            print(f"no catalog entry for {name!r} (snapshot covers: {known})")
            return 1
        courses.append(course)

    prefs = Preferences()
    if args.no_before:
        prefs.no_before = parse_time_text(args.no_before)
        if prefs.no_before is None:
            print(f"could not parse --no-before {args.no_before!r} (try '9:00 am')")
            return 1
    if args.no_after:
        prefs.no_after = parse_time_text(args.no_after)
        if prefs.no_after is None:
            print(f"could not parse --no-after {args.no_after!r} (try '6:00 pm')")
            return 1

    total_units = sum(c.units for c in courses)
    if args.max_units is not None and total_units > args.max_units:
        print(f"these courses total {total_units:g} units, over the {args.max_units:g} unit cap")
        return 1

    schedules = build_schedules(courses, max_units=args.max_units, prefs=prefs, top=args.top)
    if not schedules:
        print("no conflict-free schedule exists for that combination and those bounds.")
        return 1
    print(f"{len(schedules)} schedule option(s), {total_units:g} units total:\n")
    for i, sched in enumerate(schedules, 1):
        print(format_schedule(sched, i))
        print()
    print(_provenance_footer(catalog))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="coursescope2",
        description="Build conflict-free UC Berkeley schedules from the real Schedule of Classes snapshot.")
    parser.add_argument("--catalog", default=DEFAULT_CATALOG,
                        help="path to catalog.json (defaults to the bundled Spring 2027 snapshot)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show the courses in the catalog")

    plan = sub.add_parser("plan", help="find conflict-free schedules")
    plan.add_argument("--courses", required=True,
                      help="comma-separated course codes, e.g. 'COMPSCI 61B,COMPSCI 70'")
    plan.add_argument("--max-units", type=float, default=None)
    plan.add_argument("--no-before", default=None, help="nothing starting before, e.g. '9:00 am'")
    plan.add_argument("--no-after", default=None, help="nothing ending after, e.g. '7:00 pm'")
    plan.add_argument("--top", type=int, default=3)

    args = parser.parse_args(argv)
    catalog = load_catalog(args.catalog)
    if args.command == "list":
        cmd_list(catalog, args)
        return 0
    return cmd_plan(catalog, args)


if __name__ == "__main__":
    sys.exit(main())
