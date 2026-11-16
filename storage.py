"""SQLite persistence for reminders."""
import sqlite3
from contextlib import closing
from datetime import datetime

FMT = '%Y-%m-%d %H:%M:%S'

SCHEMA = """CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    text TEXT NOT NULL,
    due_at TEXT NOT NULL,
    recurrence TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id, active);"""


class ReminderStore:
    def __init__(self, path='reminders.db'):
        self.path = path
        with closing(self._conn()) as c, c:
            c.executescript(SCHEMA)

    def _conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    @staticmethod
    def _row(r):
        if r is None:
            return None
        d = dict(r)
        d['due_at'] = datetime.strptime(d['due_at'], FMT)
        return d

    def add(self, user_id, text, due, recurrence=None):
        with closing(self._conn()) as c, c:
            cur = c.execute(
                'INSERT INTO reminders (user_id, text, due_at, recurrence, created_at) VALUES (?,?,?,?,?)',
                (str(user_id), text, due.strftime(FMT), recurrence, datetime.now().strftime(FMT)))
            return cur.lastrowid

    def get(self, rid, user_id=None):
        q, args = 'SELECT * FROM reminders WHERE id=? AND active=1', [rid]
        if user_id is not None:
            q += ' AND user_id=?'
            args.append(str(user_id))
        with closing(self._conn()) as c:
            return self._row(c.execute(q, args).fetchone())

    def list_for_user(self, user_id):
        with closing(self._conn()) as c:
            rows = c.execute('SELECT * FROM reminders WHERE user_id=? AND active=1 ORDER BY due_at',
                             (str(user_id),)).fetchall()
        return [self._row(r) for r in rows]

    def all_active(self):
        with closing(self._conn()) as c:
            return [self._row(r) for r in c.execute('SELECT * FROM reminders WHERE active=1')]

    def search(self, user_id, keyword):
        with closing(self._conn()) as c:
            rows = c.execute('SELECT * FROM reminders WHERE user_id=? AND active=1 AND text LIKE ? '
                             'ORDER BY due_at', (str(user_id), '%' + keyword + '%')).fetchall()
        return [self._row(r) for r in rows]

    def update(self, rid, due=None, text=None, recurrence=None):
        sets, args = [], []
        if due is not None:
            sets.append('due_at=?'); args.append(due.strftime(FMT))
        if text is not None:
            sets.append('text=?'); args.append(text)
        if recurrence is not None:
            sets.append('recurrence=?'); args.append(recurrence)
        if sets:
            with closing(self._conn()) as c, c:
                c.execute('UPDATE reminders SET %s WHERE id=?' % ', '.join(sets), args + [rid])

    def deactivate(self, rid):
        with closing(self._conn()) as c, c:
            c.execute('UPDATE reminders SET active=0 WHERE id=?', (rid,))
