"""Natural-language parsing for reminder commands (no external deps)."""
import calendar
import re
from datetime import datetime, timedelta

WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
UNITS = {'minute': 'minutes', 'min': 'minutes', 'hour': 'hours', 'hr': 'hours',
         'day': 'days', 'week': 'weeks'}
_WD = '|'.join(WEEKDAYS)

RECUR_RE = re.compile(
    r'\bevery\s+(day|week|month|hour|weekday|' + _WD + r')\b|\b(daily|weekly|monthly|hourly)\b', re.I)
IN_RE = re.compile(r'\bin\s+(\d+)\s*(minutes?|mins?|hours?|hrs?|days?|weeks?)\b', re.I)
AT_RE = re.compile(r'\b(?:at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?|(\d{1,2})(?::(\d{2}))?\s*(am|pm))\b', re.I)
DAY_RE = re.compile(r'\b(?:on\s+|next\s+)?(today|tonight|tomorrow|' + _WD + r')\b', re.I)


class ParseError(ValueError):
    pass


def add_months(dt, n=1):
    month = dt.month - 1 + n
    year, month = dt.year + month // 12, month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def next_occurrence(due, recurrence, after):
    """Next due time strictly after `after` for a recurring reminder."""
    step = {'hourly': lambda d: d + timedelta(hours=1),
            'daily': lambda d: d + timedelta(days=1),
            'weekly': lambda d: d + timedelta(weeks=1),
            'monthly': lambda d: add_months(d, 1)}
    if recurrence == 'weekdays':
        def fn(d):
            d += timedelta(days=1)
            while d.weekday() >= 5:
                d += timedelta(days=1)
            return d
    else:
        fn = step[recurrence]
    nxt = fn(due)
    while nxt <= after:
        nxt = fn(nxt)
    return nxt


def _to_24h(hour, minute, ampm):
    if ampm:
        if not 1 <= hour <= 12:
            raise ParseError('Invalid hour.')
        hour = hour % 12 + (12 if ampm.lower() == 'pm' else 0)
    if hour > 23 or minute > 59:
        raise ParseError('Invalid time.')
    return hour, minute


def extract_time(text, now):
    """Return (remaining_text, due_datetime | None, recurrence | None)."""
    recurrence, weekday_name = None, None
    m = RECUR_RE.search(text)
    if m:
        word = (m.group(1) or m.group(2)).lower()
        if word in WEEKDAYS:
            recurrence, weekday_name = 'weekly', word
        else:
            recurrence = {'day': 'daily', 'week': 'weekly', 'month': 'monthly', 'hour': 'hourly',
                          'weekday': 'weekdays'}.get(word, word)
        text = text[:m.start()] + ' ' + text[m.end():]

    m = IN_RE.search(text)
    if m:
        unit = UNITS[m.group(2).lower().rstrip('s')]
        due = now + timedelta(**{unit: int(m.group(1))})
        text = text[:m.start()] + ' ' + text[m.end():]
        return _clean(text), due.replace(second=0, microsecond=0), recurrence

    hour = minute = None
    m = AT_RE.search(text)
    if m:
        g = m.groups()
        h, mi, ap = (g[0], g[1], g[2]) if g[0] else (g[3], g[4], g[5])
        hour, minute = _to_24h(int(h), int(mi or 0), ap)
        text = text[:m.start()] + ' ' + text[m.end():]

    day = weekday_name
    m = DAY_RE.search(text)
    if m:
        day = m.group(1).lower()
        text = text[:m.start()] + ' ' + text[m.end():]

    if hour is None and day is None and recurrence not in ('hourly',):
        return _clean(text), None, recurrence
    if recurrence == 'hourly' and hour is None and day is None:
        return _clean(text), (now + timedelta(hours=1)).replace(second=0, microsecond=0), recurrence

    base = now.replace(second=0, microsecond=0)
    if hour is None:
        hour, minute = (20, 0) if day == 'tonight' else (9, 0)
    due = base.replace(hour=hour, minute=minute)
    if day == 'tomorrow':
        due += timedelta(days=1)
    elif day in WEEKDAYS:
        ahead = (WEEKDAYS.index(day) - now.weekday()) % 7
        due += timedelta(days=ahead)
        if due <= now:
            due += timedelta(days=7)
    elif due <= now:  # "at 7 PM" already passed today -> tomorrow
        due += timedelta(days=1)
    return _clean(text), due, recurrence


def _clean(text):
    text = re.sub(r'\s+', ' ', text).strip(' ,.')
    return re.sub(r'^(to|that)\s+', '', text, flags=re.I)


def parse(text, now=None):
    """Parse a user message into an intent dict, or None if it isn't reminder-related."""
    now = now or datetime.now()
    t = text.strip()
    low = t.lower()

    if re.match(r'^(show|list|view|display|what are)\b.*\breminders?\b', low):
        return {'intent': 'list'}

    m = re.match(r'^(?:delete|remove|cancel)\s+(?:my\s+)?reminder\s+#?(\d+)$', low)
    if m:
        return {'intent': 'delete', 'id': int(m.group(1))}
    m = re.match(r'^(?:delete|remove|cancel)\s+(?:my\s+)?(.+?)\s+reminders?$', low)
    if m:
        return {'intent': 'delete', 'keyword': m.group(1)}

    m = re.match(r'^(?:edit|change|reschedule|update)\s+reminder\s+#?(\d+)\s+(?:to\s+)?(.+)$', t, re.I)
    if m:
        rest, due, rec = extract_time(m.group(2), now)
        if due is None:
            raise ParseError("I couldn't find a new time. Try: 'change reminder 2 to 8 PM'.")
        return {'intent': 'edit', 'id': int(m.group(1)), 'due': due, 'recurrence': rec,
                'text': rest or None}

    m = re.match(r'^remind me\s+(.+)$', t, re.I)
    if m:
        rest, due, rec = extract_time(m.group(1), now)
        if not rest:
            raise ParseError('What should I remind you about?')
        if due is None:
            raise ParseError("When should I remind you? e.g. 'at 7 PM', 'in 10 minutes', 'tomorrow'.")
        return {'intent': 'create', 'text': rest, 'due': due, 'recurrence': rec}
    return None
