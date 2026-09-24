"""
Check that streak.py splits the revlog into scheduler days exactly as Anki does, across DST,
half-hour offsets and the date line. The Anki cutoff comparison is skipped without the anki package.

    python3 tests/test_streak_days.py
"""
import concurrent.futures, datetime, itertools, os, sqlite3, subprocess, sys, time, types, zoneinfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _n in ("aqt", "aqt.qt", "anki", "anki.collection"):
    sys.modules.setdefault(_n, types.ModuleType(_n))
from src import streak  # noqa: E402

TZS = ("Europe/Prague", "America/New_York", "America/Santiago", "America/Havana",
       "Australia/Lord_Howe", "Pacific/Chatham", "Asia/Kolkata", "Asia/Tehran", "Pacific/Apia", "UTC")
DAY = 86400
# A fixed start, so the span keeps covering Apia (2021) and Tehran (2022) dropping DST.
SPAN_START = datetime.date(2020, 9, 1)
MAX_SHOWN = 10


class _DB:
    def __init__(self, conn):
        self.conn = conn

    def all(self, sql, *args):
        return self.conn.execute(sql, args).fetchall()

    def scalar(self, sql, *args):
        row = self.conn.execute(sql, args).fetchone()
        return row[0] if row else None


class _Col:
    def __init__(self, stamps, rollover):
        self.conf = {"rollover": rollover}
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE revlog (id INTEGER PRIMARY KEY)")
        conn.executemany("INSERT OR IGNORE INTO revlog VALUES (?)", [(int(t * 1000),) for t in stamps])
        self.db = _DB(conn)


def _set_tz(tz):
    os.environ["TZ"] = tz
    time.tzset()


def _epoch(d):
    return streak._date_epoch(d)


def _test_days(tz):
    """Every day within two of an offset change since SPAN_START, plus every 13th day for the rest."""
    zone = zoneinfo.ZoneInfo(tz)
    today = datetime.datetime.now(zone).date()

    def offset(d):
        return datetime.datetime(d.year, d.month, d.day, 12, tzinfo=zone).utcoffset()

    days = set()
    for back in range((today - SPAN_START).days):
        d = today - datetime.timedelta(days=back)
        if back % 13 == 0:
            days.add(d)
        if offset(d) != offset(d - datetime.timedelta(days=1)):
            days.update(d + datetime.timedelta(days=k) for k in range(-2, 3))
    return sorted(d for d in days if d <= today)


def check_classification(tz, days):
    """Around each test day's edge, SQL and Python have to name the same scheduler day."""
    zone = zoneinfo.ZoneInfo(tz)
    failures, checked = [], 0
    for rollover in (0, 1, 2, 3, 4, 23):
        stamps = []
        for d in days:
            # fold=0 inside a DST gap still yields a real instant, which is all this needs
            edge = datetime.datetime(d.year, d.month, d.day, rollover, tzinfo=zone).timestamp()
            stamps += [edge + k * 900 for k in range(-8, 9)] + [edge - 1, edge + 1, edge + 12 * 3600]
        col = _Col(stamps, rollover)
        sql = "SELECT id, " + streak._day_of_sql("id", rollover) + " FROM revlog"
        for rid, day in col.db.all(sql):
            checked += 1
            want = _epoch(streak.scheduler_date(col, rid / 1000))
            if day != want:
                failures.append(f"CLASSIFY tz={tz} rollover={rollover} id={rid}: sql {day}, python {want}")
    return checked, failures


def check_day_starts(tz, days):
    """day_start_ms(d) is the first millisecond scheduler_date calls d."""
    failures, checked = [], 0
    for rollover in range(24):
        col = _Col([], rollover)
        for d in days:
            start = streak.day_start_ms(col, _epoch(d))
            checked += 1
            on = streak.scheduler_date(col, start / 1000)
            before = streak.scheduler_date(col, (start - 1) / 1000)
            if on != d or before >= d:
                failures.append(f"BOUNDARY tz={tz} rollover={rollover} {d}: start -> {on}, 1 ms earlier -> {before}")
    return checked, failures


def _stamps(tz, hour, gaps, days):
    zone = zoneinfo.ZoneInfo(tz)
    start = datetime.datetime.now(zone).date() - datetime.timedelta(days=days - 1)
    out = []
    for n in range(days):
        if n in gaps:
            continue
        d = start + datetime.timedelta(days=n)
        out.append(datetime.datetime(d.year, d.month, d.day, hour, 30, tzinfo=zone).timestamp())
    return out


def check_runs(tz):
    """_run_ending against the plain answer: classify every review, then walk the set of days."""
    days_back = 1200
    gaps = ((), (days_back - 1,), (1, 2, 3), (7, 400, 401), tuple(range(100, 140)), (1150,))
    failures, checked = [], 0
    for hour, g in itertools.product((0, 1, 2, 3, 12, 23), gaps):
        stamps = _stamps(tz, hour, g, days_back)
        for rollover in (0, 2, 3, 4):
            col = _Col(stamps, rollover)
            today = streak.today_epoch(col)
            days = {_epoch(streak.scheduler_date(col, t)) for t in stamps}
            for floor in (0, today - 300 * DAY, today - 1100 * DAY, today + DAY):
                recent = max((d for d in days if floor <= d <= today), default=0)
                first = recent
                while first - DAY in days and first - DAY >= floor:
                    first -= DAY
                want = (first, recent) if recent else (0, 0)
                got = streak._run_ending(col, streak.day_start_ms(col, today + DAY), floor)
                checked += 1
                if got != want:
                    failures.append(f"RUN tz={tz} hour={hour} rollover={rollover} gaps={g[:3]} "
                                    f"floor={floor}: got {got}, want {want}")
    return checked, failures


_ANKI_PROBE = """
import os, sys, tempfile
from anki.collection import Collection
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "c.anki2")
    col = Collection(path)
    col.set_config("rollover", int(sys.argv[1]))
    col.close()
    col = Collection(path)
    print((col.sched.day_cutoff - 86400) * 1000)
    col.close()
"""


def check_against_anki(tz):
    """Today's start as Anki's scheduler has it; one process per case, as the backend caches its
    day cutoff and timezone. Returns None when the anki package is unavailable."""
    failures, checked = [], 0
    for rollover in (0, 1, 2, 3, 4, 12, 23, 24):  # 24 is stored as is, and Anki caps it at 23
        res = subprocess.run([sys.executable, "-c", _ANKI_PROBE, str(rollover)],
                             env=dict(os.environ, TZ=tz), capture_output=True, text=True)
        if res.returncode:
            return None, res.stderr.strip().splitlines()[-1:]
        anki_start = int(res.stdout.split()[-1])
        ours = streak.day_start_ms(_Col([], rollover))
        checked += 1
        if ours != anki_start:
            failures.append(f"ANKI tz={tz} rollover={rollover}: ours {(ours - anki_start) / 3600000:+.2f}h from Anki's")
    return checked, failures


def _check_tz(tz):
    """Every check for one timezone, in its own process since TZ is process-wide. The Anki probes
    mostly wait on their subprocesses, so they run alongside the rest."""
    _set_tz(tz)
    days = _test_days(tz)
    with concurrent.futures.ThreadPoolExecutor(1) as probe:
        anki = probe.submit(check_against_anki, tz)
        return {"classified": check_classification(tz, days), "day starts": check_day_starts(tz, days),
                "runs": check_runs(tz), "anki": anki.result()}


def main():
    with concurrent.futures.ProcessPoolExecutor(max_workers=len(TZS)) as pool:
        results = list(pool.map(_check_tz, TZS))
    total = 0
    labels = {"classified": "classified {} timestamps", "day starts": "checked {} day starts",
              "runs": "compared {} runs", "anki": "compared {} day starts with Anki's"}
    for key, label in labels.items():
        parts = [r[key] for r in results]
        skipped = next((p for p in parts if p[0] is None), None)
        if skipped:
            print(f"anki probe failed, skipped: {skipped[1]}")
            continue
        failures = [f for _, fs in parts for f in fs]
        for line in failures[:MAX_SHOWN]:
            print(line)
        print(f"{label.format(sum(n for n, _ in parts))}, {len(failures)} mismatches")
        total += len(failures)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
