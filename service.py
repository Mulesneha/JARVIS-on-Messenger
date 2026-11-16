"""High-level reminder service: parse -> store -> schedule -> notify."""
from datetime import datetime, timedelta

from .parser import ParseError, next_occurrence, parse
from .scheduler import APSchedulerBackend
from .storage import ReminderStore


def fmt_due(dt):
    return dt.strftime('%a %d %b, %I:%M %p').replace(' 0', ' ')


class ReminderService:
    def __init__(self, send_fn, db_path='reminders.db', backend=None, clock=datetime.now):
        """send_fn(user_id, message) delivers a message (e.g. the Messenger send API)."""
        self.send, self.store, self.clock = send_fn, ReminderStore(db_path), clock
        self.backend = backend or APSchedulerBackend()

    # -- lifecycle ---------------------------------------------------------
    def start(self):
        """Start the scheduler and re-schedule everything persisted in SQLite."""
        self.backend.start()
        now = self.clock()
        for r in self.store.all_active():
            run_at = r['due_at'] if r['due_at'] > now else now + timedelta(seconds=2)
            self.backend.schedule(r['id'], run_at, self._fire)

    def stop(self):
        self.backend.shutdown()

    # -- scheduler callback --------------------------------------------------
    def _fire(self, rid):
        r = self.store.get(rid)
        if not r:
            return
        self.send(r['user_id'], u'\u23f0 Reminder: %s' % r['text'])
        if r['recurrence']:
            nxt = next_occurrence(r['due_at'], r['recurrence'], self.clock())
            self.store.update(rid, due=nxt)
            self.backend.schedule(rid, nxt, self._fire)
        else:
            self.store.deactivate(rid)

    # -- user commands -------------------------------------------------------
    def handle(self, user_id, text):
        """Return a reply string, or None if the message isn't a reminder command."""
        try:
            cmd = parse(text, self.clock())
        except ParseError as e:
            return str(e)
        if cmd is None:
            return None
        return getattr(self, '_' + cmd['intent'])(user_id, cmd)

    def _create(self, user_id, c):
        rid = self.store.add(user_id, c['text'], c['due'], c['recurrence'])
        self.backend.schedule(rid, c['due'], self._fire)
        rec = ' (repeats %s)' % c['recurrence'] if c['recurrence'] else ''
        return u'Got it! I\u2019ll remind you to %s on %s%s. [#%d]' % (c['text'], fmt_due(c['due']), rec, rid)

    def _list(self, user_id, c):
        items = self.store.list_for_user(user_id)
        if not items:
            return 'You have no reminders.'
        return 'Your reminders:\n' + '\n'.join(
            '#%d  %s \u2014 %s%s' % (r['id'], r['text'], fmt_due(r['due_at']),
                                    ' (%s)' % r['recurrence'] if r['recurrence'] else '')
            for r in items)

    def _delete(self, user_id, c):
        if 'id' in c:
            r = self.store.get(c['id'], user_id)
            matches = [r] if r else []
        else:
            matches = self.store.search(user_id, c['keyword'])
        if not matches:
            return "I couldn't find a matching reminder."
        if len(matches) > 1:
            return ('Multiple matches, say "delete reminder <id>":\n' +
                    '\n'.join('#%d  %s' % (r['id'], r['text']) for r in matches))
        r = matches[0]
        self.store.deactivate(r['id'])
        self.backend.cancel(r['id'])
        return 'Deleted reminder: %s' % r['text']

    def _edit(self, user_id, c):
        r = self.store.get(c['id'], user_id)
        if not r:
            return "I couldn't find that reminder."
        self.store.update(r['id'], due=c['due'], text=c['text'], recurrence=c['recurrence'])
        self.backend.schedule(r['id'], c['due'], self._fire)
        return 'Updated reminder #%d: %s on %s' % (r['id'], c['text'] or r['text'], fmt_due(c['due']))
