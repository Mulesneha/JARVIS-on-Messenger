"""Wire the reminder service into JARVIS's Flask webhook (adapt names to your handler)."""
from reminders import ReminderService


def send_text(user_id, message):
    # Reuse JARVIS's existing Messenger send helper here, e.g.:
    # from app.messenger import send_message; send_message(user_id, message)
    print('->', user_id, message)


reminders = ReminderService(send_fn=send_text, db_path='reminders.db')
reminders.start()  # call once at app startup; reloads pending reminders from SQLite


def on_message(user_id, text):
    """Call this BEFORE the Wit.ai / other-module fallback in your webhook."""
    reply = reminders.handle(user_id, text)
    if reply is not None:
        send_text(user_id, reply)
        return True
    return False  # not a reminder command -> let existing modules handle it
