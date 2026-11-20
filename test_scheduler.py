"""Engine tests: conflicts, combination building, bounds, ranking.

Synthetic sections keep these tests independent of the snapshots; one
integration test at the bottom runs the real catalog end to end.
"""

import os
import unittest

from coursescope2.models import Course, load_catalog
from coursescope2.scheduler import (Preferences, build_schedules,
                                    course_options, is_placeholder)
from coursescope2.soc import Meeting, Section


def make_section(ccn, course, kind, section, days, start, end):
    meeting = Meeting(days=tuple(days), start=start, end=end,
                      dates="Jan 19, 2027 - May 07, 2027", location=None)
    return Section(ccn=ccn, course=course, section=section, kind=kind,
                   title=f"{course} {kind}", units=4.0, units_text="4",
                   instructors=["Staff"], meetings=[meeting],
                   seats_text="10 Unreserved Seats",
                   instruction_mode="In Person", detail_path="/content/x",
                   term="Spring 2027")


def placeholder_section(ccn, course, kind):
    meeting = Meeting(days=("Su",), start=0, end=1,
                      dates="Jan 19, 2027 - May 07, 2027", location=None)
    return Section(ccn=ccn, course=course, section="999", kind=kind,
                   title=f"{course} {kind}", units=0.0, units_text="0",
                   instructors=[], meetings=[meeting],
                   seats_text=None, instruction_mode=None,
                   detail_path="/content/y", term="Spring 2027")


M = 9 * 60  # 9:00 in minutes


class TestConflicts(unittest.TestCase):
    def test_overlap_same_day(self):
        a = make_section("00001", "X 1", "LEC", "001", "MW", M, M + 60)
        b = make_section("00002", "Y 1", "DIS", "101", "M", M + 30, M + 90)
        self.assertTrue(a.conflicts_with(b))

    def test_adjacent_is_not_a_conflict(self):
        a = make_section("00001", "X 1", "LEC", "001", "MW", M, M + 60)
        b = make_section("00002", "Y 1", "DIS", "101", "M", M + 60, M + 120)
        self.assertFalse(a.conflicts_with(b))

    def test_different_days_do_not_conflict(self):
        a = make_section("00001", "X 1", "LEC", "001", "MW", M, M + 60)
        b = make_section("00002", "Y 1", "DIS", "101", "TuTh", M, M + 60)
        self.assertFalse(a.conflicts_with(b))

    def test_placeholder_never_conflicts(self):
        a = make_section("00001", "X 1", "LEC", "001", "Su", 0, 1)
        b = placeholder_section("00002", "Y 1", "LAB")
        self.assertTrue(is_placeholder(a))
        self.assertTrue(is_placeholder(b))
        self.assertFalse(a.conflicts_with(b))


class TestCourseOptions(unittest.TestCase):
    def test_one_lecture_plus_one_of_each_kind(self):
        lec = make_section("00001", "X 1", "LEC", "001", "MWF", M, M + 60)
        dis1 = make_section("00002", "X 1", "DIS", "101", "Tu", M, M + 60)
        dis2 = make_section("00003", "X 1", "DIS", "102", "W", M + 120, M + 180)
        lab = make_section("00004", "X 1", "LAB", "111l", "F", M + 120, M + 180)
        course = Course("X 1", "X", 4.0, [lec, dis1, dis2, lab])
        options = course_options(course)
        self.assertEqual(len(options), 2)  # 1 lec x 2 dis x 1 lab
        for combo in options:
            self.assertEqual([s.kind for s in combo], ["LEC", "DIS", "LAB"])

    def test_internally_conflicting_combos_are_dropped(self):
        lec = make_section("00001", "X 1", "LEC", "001", "MWF", M, M + 60)
        clashing = make_section("00002", "X 1", "DIS", "101", "M", M, M + 60)
        clean = make_section("00003", "X 1", "DIS", "102", "Tu", M, M + 60)
        course = Course("X 1", "X", 4.0, [lec, clashing, clean])
        options = course_options(course)
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0][1].ccn, "00003")


class TestBuildSchedules(unittest.TestCase):
    def setUp(self):
        self.a_lec = make_section("00001", "X 1", "LEC", "001", "MWF", M, M + 60)
        self.a_dis = make_section("00002", "X 1", "DIS", "101", "Tu", M, M + 60)
        self.b_lec = make_section("00003", "Y 1", "LEC", "001", "TuTh", M + 120, M + 180)
        self.b_clash = make_section("00004", "Y 1", "LEC", "002", "Tu", M, M + 90)
        self.course_a = Course("X 1", "X", 4.0, [self.a_lec, self.a_dis])
        self.course_b = Course("Y 1", "Y", 4.0, [self.b_lec, self.b_clash])

    def test_only_conflict_free_schedules_survive(self):
        schedules = build_schedules([self.course_a, self.course_b])
        self.assertEqual(len(schedules), 1)  # Y 1 LEC 002 clashes with X 1 DIS
        self.assertTrue(schedules[0].is_conflict_free())

    def test_max_units_cap(self):
        self.assertEqual(build_schedules([self.course_a, self.course_b], max_units=6), [])
        self.assertTrue(build_schedules([self.course_a, self.course_b], max_units=8))

    def test_no_before_bound(self):
        prefs = Preferences(no_before=M + 30)
        schedules = build_schedules([self.course_a], prefs=prefs)
        self.assertEqual(schedules, [])  # every X 1 meeting starts at 9:00

    def test_placeholder_ranked_below_real_sections(self):
        real_dis = make_section("00005", "Z 1", "DIS", "101", "F", M + 240, M + 300)
        fake_dis = placeholder_section("00006", "Z 1", "DIS")
        course_c = Course("Z 1", "Z", 4.0, [
            make_section("00007", "Z 1", "LEC", "001", "MW", M + 300, M + 360),
            real_dis, fake_dis])
        schedules = build_schedules([course_c], top=2)
        self.assertEqual(len(schedules), 2)
        self.assertEqual(schedules[0].sections[-1].ccn, "00005")  # real first
        self.assertEqual(schedules[1].sections[-1].ccn, "00006")


CATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "data", "spring2027", "catalog.json")


class TestRealCatalog(unittest.TestCase):
    def test_catalog_shape(self):
        catalog = load_catalog(CATALOG)
        self.assertEqual(sorted(catalog["courses"]),
                         ["COMPSCI 61A", "COMPSCI 61B", "COMPSCI 70",
                          "DATA C8", "ECON 1", "MATH 54"])
        total = sum(len(c.sections) for c in catalog["courses"].values())
        self.assertEqual(total, 197)

    def test_real_plan_is_conflict_free(self):
        catalog = load_catalog(CATALOG)
        courses = [catalog["courses"]["COMPSCI 61B"], catalog["courses"]["ECON 1"]]
        schedules = build_schedules(courses, top=3)
        self.assertTrue(schedules)
        for sched in schedules:
            self.assertTrue(sched.is_conflict_free())
            kinds = [s.kind for s in sched.sections]
            self.assertEqual(kinds.count("LEC"), 2)
            self.assertIn("DIS", kinds)
            self.assertIn("LAB", kinds)


if __name__ == "__main__":
    unittest.main()
