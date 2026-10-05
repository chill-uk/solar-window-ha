"""Dependency-free solar window detection and validated daily records."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from copy import deepcopy
from zoneinfo import ZoneInfo


def parse_time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timestamps must include a timezone')
    return result.astimezone(timezone.utc)


class SolarEngine:
    """Use debounced hysteresis; keep all confirmed intervals, not just one pair."""

    def __init__(self, tz: str, start_w: float = 20, stop_w: float = 10,
                 start_seconds: float = 180, stop_seconds: float = 600,
                 data: dict | None = None):
        self.tz = ZoneInfo(tz)
        self.start_w, self.stop_w = start_w, stop_w
        self.start_seconds, self.stop_seconds = start_seconds, stop_seconds
        self.days = (data or {}).get('days', {})
        self.last_seen = (data or {}).get('last_seen')
        self.active = False
        self.pending: tuple[bool, datetime] | None = None
        self.previous_day: str | None = None
        self.initial = True
        self.start_unobserved = False

    def export(self) -> dict:
        return deepcopy({'days': self.days, 'last_seen': self.last_seen})

    def key(self, now: datetime) -> str:
        return now.astimezone(self.tz).date().isoformat()

    def row(self, key: str) -> dict:
        return self.days.setdefault(key, {'date': key, 'start': None, 'finish': None,
            'intervals': [], 'flags': [], 'source': 'live', 'resolution_minutes': 1})

    @staticmethod
    def flag(row: dict, name: str) -> None:
        if name not in row['flags']:
            row['flags'].append(name)

    def gap(self, now: datetime) -> None:
        """Close an unobserved continuation at last known observation, mark uncertainty."""
        for row in self.days.values():
            if row['source'] != 'live':
                continue
            for interval in row.get('intervals', []):
                if interval['end'] is None:
                    end = self.last_seen or interval['start']
                    interval['end'] = max(end, interval['start'])
                    row['finish'] = interval['end']
                    self.flag(row, 'recording_gap')
        if self.key(now) in self.days and self.days[self.key(now)]['source'] == 'live':
            self.flag(self.days[self.key(now)], 'recording_gap')
        self.active = False
        self.pending = None

    def sample(self, now: datetime, watts: float | None) -> None:
        now = now.astimezone(timezone.utc)
        key = self.key(now)
        if self.initial:
            self.gap(now)
        if watts is None or not math.isfinite(watts):
            self.gap(now)
            self.initial = True
            return
        if self.last_seen and now <= parse_time(self.last_seen):
            return
        if self.last_seen and (now - parse_time(self.last_seen)).total_seconds() > 180:
            self.gap(now)
            self.initial = True
        if self.previous_day and key != self.previous_day:
            midnight = datetime.combine(now.astimezone(self.tz).date(), datetime.min.time(), self.tz).astimezone(timezone.utc)
            if self.active:
                self._stop(midnight)
                self._start(midnight)
                self.flag(self.row(key), 'crosses_midnight')
            # A confirmation never spans two local calendar dates.
            self.pending = None
        target = self.active
        if watts > self.start_w:
            target = True
        elif watts < self.stop_w:
            target = False
        if self.initial:
            self.start_unobserved = target
        self.initial = False
        if target == self.active:
            self.pending = None
        else:
            if self.pending is None or self.pending[0] != target:
                self.pending = (target, now)
            seconds = self.start_seconds if target else self.stop_seconds
            if (now - self.pending[1]).total_seconds() >= seconds:
                at = self.pending[1]
                self._start(at) if target else self._stop(at)
                self.active = target
                self.pending = None
        self.last_seen = now.isoformat()
        self.previous_day = key

    def _start(self, at: datetime) -> None:
        row = self.row(self.key(at))
        if row['source'] != 'live':
            # Keep approximations separately when recording a partially observed day.
            prior = row.copy()
            row.update(start=None, finish=None, intervals=[], flags=[], source='live', resolution_minutes=1)
            row['backfill'] = prior
        if self.start_unobserved:
            self.flag(row, 'start_unobserved')
            self.start_unobserved = False
        row['start'] = row['start'] or at.isoformat()
        row['finish'] = None
        row['intervals'].append({'start': at.isoformat(), 'end': None})
        if len(row['intervals']) > 1:
            self.flag(row, 'interrupted')

    def _stop(self, at: datetime) -> None:
        # A midnight endpoint belongs to the interval's opening day.
        for row in reversed(list(self.days.values())):
            if row['intervals'] and row['intervals'][-1]['end'] is None:
                row['intervals'][-1]['end'] = at.isoformat()
                row['finish'] = at.isoformat()
                return

    def merge(self, records: list[dict]) -> int:
        """Validate the whole batch before merging; never overwrite better observations."""
        checked = []
        for supplied in records:
            key = supplied['date']
            datetime.strptime(key, '%Y-%m-%d')
            start = parse_time(supplied['start']) if supplied.get('start') else None
            finish = parse_time(supplied['finish']) if supplied.get('finish') else None
            if not start or self.key(start) != key:
                raise ValueError('Start must fall on record date in HA timezone')
            if finish and (finish < start or finish - start > timedelta(hours=26)):
                raise ValueError('Invalid finish')
            source = supplied.get('source', 'import')
            if source not in ('import', 'statistics'):
                raise ValueError('Invalid imported source')
            flags = supplied.get('flags', [])
            if not isinstance(flags, list) or not all(isinstance(f, str) and len(f) <= 64 for f in flags):
                raise ValueError('Invalid flags')
            intervals = supplied.get('intervals') or [{'start': start.isoformat(), 'end': finish.isoformat() if finish else None}]
            normalized = []
            previous_end = start
            for index, interval in enumerate(intervals):
                begin = parse_time(interval['start'])
                end = parse_time(interval['end']) if interval.get('end') else None
                if begin < previous_end or self.key(begin) != key or (end and (end < begin or end - start > timedelta(hours=26))):
                    raise ValueError('Invalid interval')
                if end is None and (index != len(intervals) - 1 or finish is not None):
                    raise ValueError('Only final open interval is allowed')
                normalized.append({'start': begin.isoformat(), 'end': end.isoformat() if end else None})
                previous_end = end or begin
            if normalized[0]['start'] != start.isoformat() or normalized[-1]['end'] != (finish.isoformat() if finish else None):
                raise ValueError('Intervals must match daily boundaries')
            checked.append({'date': key, 'start': start.isoformat(),
                'finish': finish.isoformat() if finish else None,
                'intervals': normalized,
                'flags': list(flags), 'source': source,
                'resolution_minutes': 60 if source == 'statistics' else 1})
        count = 0
        rank = {'statistics': 0, 'import': 1, 'live': 2}
        for row in checked:
            existing = self.days.get(row['date'])
            if existing and rank[existing['source']] >= rank[row['source']]:
                continue
            self.days[row['date']] = row
            count += 1
        return count
