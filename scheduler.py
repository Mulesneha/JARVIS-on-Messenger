"""Thin wrapper around APScheduler so the service can be tested with a fake."""


class APSchedulerBackend:
    def __init__(self):
        from apscheduler.schedulers.background import BackgroundScheduler
        self._sched = BackgroundScheduler()

    def start(self):
        if not self._sched.running:
            self._sched.start()

    def shutdown(self):
        if self._sched.running:
            self._sched.shutdown(wait=False)

    def schedule(self, rid, run_at, callback):
        from apscheduler.triggers.date import DateTrigger
        self._sched.add_job(callback, DateTrigger(run_date=run_at), args=[rid],
                            id='reminder-%d' % rid, replace_existing=True,
                            misfire_grace_time=3600)

    def cancel(self, rid):
        try:
            self._sched.remove_job('reminder-%d' % rid)
        except Exception:  # job already ran / never existed
            pass
