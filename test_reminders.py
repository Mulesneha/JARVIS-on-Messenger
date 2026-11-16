import os
import tempfile
from datetime import datetime

import pytest

from reminders.parser import ParseError, next_occurrence, parse
from reminders.service import ReminderService

NOW = datetime(2026, 11, 16, 10, 0)  # Monday


class FakeBackend:
    def __init__(self):
        self.jobs = {}
    def start(self): pass
    def shutdown(self): pass
    def schedule(self, rid, run_at, cb): self.jobs[rid] = (run_at, cb)
    def cancel(self, rid): self.jobs.pop(rid, None)


@pytest.fixture
def env():
    d = tempfile.mkdtemp()
    sent, clock = [], {'now': NOW}
    def make(backend=None):
        return ReminderService(lambda u, m: sent.append((u, m)), os.path.join(d, 'r.db'),
                               backend or FakeBackend(), lambda: clock['now'])
    return make, sent, clock


def test_parse_at_time_today_and_rollover():
    c = parse('Remind me to study at 7 PM', NOW)
    assert c['text'] == 'study' and c['due'] == datetime(2026, 11, 16, 19, 0)
    assert parse('remind me to run at 8 am', NOW)['due'] == datetime(2026, 11, 17, 8, 0)


def test_parse_relative_and_tomorrow():
    assert parse('remind me to call mom in 30 minutes', NOW)['due'] == datetime(2026, 11, 16, 10, 30)
    c = parse('remind me to pay rent tomorrow at 9:30am', NOW)
    assert c['due'] == datetime(2026, 11, 17, 9, 30) and c['text'] == 'pay rent'


def test_parse_recurring():
    c = parse('remind me to meditate every day at 6 am', NOW)
    assert c['recurrence'] == 'daily' and c['due'] == datetime(2026, 11, 17, 6, 0)
    c = parse('remind me to take out trash every friday at 8pm', NOW)
    assert c['recurrence'] == 'weekly' and c['due'] == datetime(2026, 11, 20, 20, 0)


def test_parse_errors_and_non_commands():
    with pytest.raises(ParseError):
        parse('remind me to study', NOW)
    assert parse('hello there', NOW) is None


def test_next_occurrence():
    fri = datetime(2026, 11, 20, 9, 0)
    assert next_occurrence(fri, 'weekdays', fri) == datetime(2026, 11, 23, 9, 0)
    assert next_occurrence(datetime(2026, 1, 31, 9), 'monthly', datetime(2026, 1, 31, 9)) == datetime(2026, 2, 28, 9)


def test_create_list_delete(env):
    make, _, _ = env
    s = make()
    assert 'study' in s.handle('u1', 'Remind me to study at 7 PM')
    s.handle('u1', 'remind me to attend meeting at 5 pm')
    assert s.handle('u2', 'show my reminders') == 'You have no reminders.'
    assert 'study' in s.handle('u1', 'show my reminders')
    assert s.handle('u1', 'delete my meeting reminder').startswith('Deleted')
    assert 'meeting' not in s.handle('u1', 'show my reminders')


def test_edit(env):
    make, _, _ = env
    s = make()
    s.handle('u1', 'remind me to study at 7 PM')
    assert 'Updated' in s.handle('u1', 'change reminder 1 to 8 PM')
    assert s.store.get(1)['due_at'] == datetime(2026, 11, 16, 20, 0)
    assert "couldn't" in s.handle('u2', 'change reminder 1 to 9 PM')  # other user's reminder


def test_fire_one_shot_and_recurring(env):
    make, sent, clock = env
    s = make()
    s.handle('u1', 'remind me to stretch at 11 am')
    s.handle('u1', 'remind me to meditate every day at 11 am')
    clock['now'] = datetime(2026, 11, 16, 11, 0)
    s._fire(1); s._fire(2)
    assert len(sent) == 2 and 'stretch' in sent[0][1]
    assert s.store.get(1) is None                                  # one-shot finished
    assert s.store.get(2)['due_at'] == datetime(2026, 11, 17, 11, 0)  # recurring rescheduled
    assert s.backend.jobs[2][0] == datetime(2026, 11, 17, 11, 0)


def test_persistence_across_restart(env):
    make, _, _ = env
    make().handle('u1', 'remind me to study at 7 PM')
    backend = FakeBackend()
    make(backend).start()                  # "restart": new service, same DB file
    assert backend.jobs[1][0] == datetime(2026, 11, 16, 19, 0)
