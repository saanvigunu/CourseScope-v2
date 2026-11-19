"""Backtracking schedule search over real Schedule of Classes data.

Each course expands into its legal combinations: one lecture plus one
section of every other kind the course published (discussion, lab, ...).
A combination with a time conflict is pruned immediately; full schedules
that survive the hard bounds are ranked so the first option is the one
most people would pick.

Placeholder sections (the '999' catch-alls Berkeley publishes as a one
minute Sunday meeting, 12:00am-12:01am) are treated as TBA: they never
conflict, because a one minute meeting at midnight is a data convention,
not a real commitment.
"""

DAY_ORDER = ["M", "Tu", "W", "Th", "F", "Sa", "Su"]


def is_placeholder(section):
    """True when a section carries no real meeting time yet.

    Two published forms: the '999' catch-all (Su 12:00-12:01am) and
    sections whose days/time the page simply has not filled in.
    """
    for m in section.meetings:
        if m.start is None or not m.days:
            return True
        if m.start == 0 and m.end == 1:
            return True
    return False


class Preferences:
    """Soft preferences and hard bounds for ranking schedules.

    no_before / no_after: minutes since midnight, hard bounds when set.
    """

    def __init__(self, no_before=None, no_after=None):
        self.no_before = no_before
        self.no_after = no_after


class Schedule:
    """One chosen lecture plus its required linked sections, per course."""

    def __init__(self, picks):
        # picks: list of (course_name, [Section, ...])
        self.picks = picks
        self.sections = [sec for _, secs in picks for sec in secs]

    def is_conflict_free(self):
        timed = [s for s in self.sections if not is_placeholder(s)]
        for i in range(len(timed)):
            for j in range(i + 1, len(timed)):
                if timed[i].conflicts_with(timed[j]):
                    return False
        return True

    def days_used(self):
        days = set()
        for sec in self.sections:
            if is_placeholder(sec):
                continue
            for m in sec.meetings:
                days.update(m.days)
        return days

    def respects_bounds(self, prefs):
        for sec in self.sections:
            if is_placeholder(sec):
                continue
            for m in sec.meetings:
                if m.start is None:
                    continue
                if prefs.no_before is not None and m.start < prefs.no_before:
                    return False
                if prefs.no_after is not None and m.end > prefs.no_after:
                    return False
        return True

    def idle_gap_minutes(self):
        """Total idle minutes between consecutive meetings on the same day."""
        gap = 0
        for day in DAY_ORDER:
            todays = []
            for sec in self.sections:
                if is_placeholder(sec):
                    continue
                for m in sec.meetings:
                    if day in m.days and m.start is not None:
                        todays.append((m.start, m.end))
            todays.sort()
            for (s1, e1), (s2, e2) in zip(todays, todays[1:]):
                gap += max(0, s2 - e1)
        return gap

    def placeholder_count(self):
        return sum(1 for s in self.sections if is_placeholder(s))

    def score(self):
        """Higher is better: fewer days on campus, shorter idle gaps.

        A placeholder (TBA) section costs 30: a fully timed schedule is
        worth more than one extra day on campus, because an unscheduled
        section could land anywhere once the department posts it.
        """
        return (-20.0 * len(self.days_used())
                - self.idle_gap_minutes() / 30.0
                - 30.0 * self.placeholder_count())


def course_options(course):
    """All legal section combinations for one course.

    One lecture, plus one pick from every other kind the course published.
    Combinations whose own sections conflict (a lab overlapping its lecture)
    are dropped here so the search never sees them.
    """
    from itertools import product

    kinds = course.required_kinds()
    options = []
    for lec in course.lectures:
        pools = [course.by_kind[k] for k in kinds]
        for extra in product(*pools) if pools else [()]:
            combo = [lec, *extra]
            timed = [s for s in combo if not is_placeholder(s)]
            ok = True
            for i in range(len(timed)):
                for j in range(i + 1, len(timed)):
                    if timed[i].conflicts_with(timed[j]):
                        ok = False
                        break
                if not ok:
                    break
            if ok:
                options.append(combo)
    return options


def build_schedules(courses, max_units=None, prefs=None, top=5):
    """Search all cross-course combinations; return the top-ranked schedules."""
    prefs = prefs or Preferences()
    option_lists = []
    total_units = 0.0
    for course in courses:
        opts = course_options(course)
        if not opts:
            return []  # a course with no published sections makes no schedule
        option_lists.append((course, opts))
        total_units += course.units

    if max_units is not None and total_units > max_units:
        return []

    results = []

    def search(idx, picked):
        if idx == len(option_lists):
            sched = Schedule(list(picked))
            if sched.is_conflict_free() and sched.respects_bounds(prefs):
                results.append(sched)
            return
        course, opts = option_lists[idx]
        for combo in opts:
            candidate = Schedule(list(picked) + [(course.course, combo)])
            if candidate.is_conflict_free() and candidate.respects_bounds(prefs):
                picked.append((course.course, combo))
                search(idx + 1, picked)
                picked.pop()

    search(0, [])
    results.sort(key=lambda s: s.score(), reverse=True)
    return results[:top]


def format_schedule(sched, rank):
    """Render one schedule option for the CLI."""
    lines = [f"option {rank}  (days on campus: {len(sched.days_used())}, idle gaps: {sched.idle_gap_minutes()} min)"]
    for course_name, secs in sched.picks:
        for sec in secs:
            if is_placeholder(sec):
                lines.append(f"  {sec.course:<12} {sec.kind} {sec.section:<5} {'time TBA':<22} #{sec.ccn}  (placeholder section - not scheduled yet)")
            else:
                lines.append(f"  {sec.course:<12} {sec.kind} {sec.section:<5} {sec.meetings[0].describe():<22} #{sec.ccn}")
    return "\n".join(lines)
