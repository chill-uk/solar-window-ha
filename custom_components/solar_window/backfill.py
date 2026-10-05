"""Convert energy statistics to explicitly approximate, local calendar windows."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def month_ranges(year, tz):
    zone = ZoneInfo(tz)
    for month in range(1, 13):
        start = datetime(year, month, 1, tzinfo=zone)
        end = datetime(year + (month == 12), 1 if month == 12 else month + 1, 1, tzinfo=zone)
        yield start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def bins_to_days(rows, tz):
    zone = ZoneInfo(tz)
    days = {}
    for row in sorted(rows, key=lambda r: r['start']):
        change = row.get('change')
        if change is None or change <= 0:
            continue
        start = datetime.fromtimestamp(row['start'], timezone.utc)
        end = datetime.fromtimestamp(row.get('end', row['start'] + 3600), timezone.utc)
        # Split a bin at local midnight rather than grouping by UTC date.
        cursor = start
        while cursor < end:
            local = cursor.astimezone(zone)
            midnight = datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), zone).astimezone(timezone.utc)
            finish = min(midnight, end)
            key = local.date().isoformat()
            record = days.setdefault(key, {'date': key, 'start': cursor.isoformat(),
                'finish': finish.isoformat(), 'source': 'statistics', 'flags': ['approximate']})
            record['finish'] = finish.isoformat()
            cursor = finish
    return list(days.values())
