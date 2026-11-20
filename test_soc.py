"""Parser tests, run against the committed raw snapshots.

These are the project's guard rails: if classes.berkeley.edu changes its
markup and the parser starts inventing or dropping sections, these counts
move and the tests say so. The expected numbers come from the snapshots
themselves (Spring 2027, fetched 2026-11-18/19), not from assumptions.
"""

import glob
import os
import unittest

from coursescope2.soc import identity_from_slug, parse_detail, parse_files
from coursescope2.scheduler import is_placeholder

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "data", "spring2027", "raw")


def search_sections(prefix, course_name):
    files = sorted(glob.glob(os.path.join(RAW, f"{prefix}_search_p*.html")))
    assert files, f"no snapshots for {prefix}"
    return [s for s in parse_files(files) if s.course == course_name]


class TestSearchPages(unittest.TestCase):
    # The keyword search is relevance-sorted, so each course's search pages
    # list that course's lecture(s) among other departments' sections.
    def test_target_lecture_counts(self):
        expected = {
            "COMPSCI_61A": ("COMPSCI 61A", 1),
            "COMPSCI_61B": ("COMPSCI 61B", 1),
            "COMPSCI_70": ("COMPSCI 70", 1),
            "DATA_C8": ("DATA C8", 2),
            "MATH_54": ("MATH 54", 2),
            "ECON_1": ("ECON 1", 1),
        }
        for prefix, (name, count) in expected.items():
            secs = search_sections(prefix, name)
            self.assertEqual(len(secs), count, prefix)
            self.assertTrue(all(s.kind == "LEC" for s in secs), prefix)

    def test_every_section_has_a_five_digit_ccn(self):
        for path in glob.glob(os.path.join(RAW, "*_search_p*.html")):
            for sec in parse_files([path]):
                self.assertRegex(sec.ccn, r"^\d{5}$", f"{sec.course} {sec.section}")

    def test_variable_units_keep_verbatim_text(self):
        # XMBA 296 appears on the MATH 54 search page (relevance noise) and
        # lists units as "1to3"; the parser keeps the text verbatim and takes
        # the upper end as the numeric value.
        secs = parse_files([os.path.join(RAW, "MATH_54_search_p0.html")])
        var = [s for s in secs if s.units_text and "to" in s.units_text]
        self.assertTrue(var, "expected at least one variable-units section")
        for s in var:
            upper = float(s.units_text.split("to")[-1])
            self.assertEqual(s.units, upper)

    def test_no_incomplete_records(self):
        # every parsed section carries a day/time or is explicitly time-less
        for path in glob.glob(os.path.join(RAW, "*_search_p*.html")):
            for sec in parse_files([path]):
                self.assertTrue(sec.meetings, f"{sec.course} {sec.section} has no meeting")
                for m in sec.meetings:
                    self.assertEqual((m.start is None), (m.end is None),
                                     f"{sec.course} {sec.section} half-parsed time")


class TestDetailPages(unittest.TestCase):
    def test_61b_associated_sections(self):
        with open(os.path.join(RAW, "COMPSCI_61B_001_detail.html"), encoding="utf-8") as fh:
            primary, assoc = parse_detail(fh.read())
        self.assertEqual(primary, "28355")
        self.assertEqual(len(assoc), 69)
        self.assertEqual(sum(1 for s in assoc if s.kind == "DIS"), 36)
        self.assertEqual(sum(1 for s in assoc if s.kind == "LAB"), 33)
        self.assertTrue(all(s.course == "COMPSCI 61B" for s in assoc))

    def test_c8_detail_shows_only_placeholder_labs(self):
        # As of the fetch date, DATA C8 discussions were genuinely not
        # published: the detail pages list only "999" placeholder labs.
        with open(os.path.join(RAW, "DATA_C8_001_detail.html"), encoding="utf-8") as fh:
            _, assoc = parse_detail(fh.read())
        self.assertEqual(len(assoc), 1)
        self.assertEqual(assoc[0].kind, "LAB")
        self.assertTrue(is_placeholder(assoc[0]))

    def test_placeholder_vs_real_section(self):
        with open(os.path.join(RAW, "MATH_54_001_detail.html"), encoding="utf-8") as fh:
            _, assoc = parse_detail(fh.read())
        real = [s for s in assoc if not is_placeholder(s)]
        self.assertTrue(len(real) > 10)
        for s in real:
            self.assertTrue(all(m.start is not None and m.days for m in s.meetings))


class TestSlugIdentity(unittest.TestCase):
    def test_identity_from_slug(self):
        self.assertEqual(
            identity_from_slug("2027-spring-compsci-61a-103-dis-103"),
            ("Spring 2027", "COMPSCI 61A", "103", "DIS"))
        self.assertEqual(
            identity_from_slug("/content/2027-spring-data-c8-001-lec-001/"),
            ("Spring 2027", "DATA C8", "001", "LEC"))
        with self.assertRaises(ValueError):
            identity_from_slug("not-a-section")


if __name__ == "__main__":
    unittest.main()
