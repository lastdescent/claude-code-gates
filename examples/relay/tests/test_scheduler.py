from relay import Scheduler
from tests.base import RelayTestCase

T0 = 1_000_000.0


class TestScheduler(RelayTestCase):
    def setUp(self):
        super().setUp()
        self.scheduler = Scheduler(self.conn, self.queue)

    def test_fires_when_due(self):
        self.scheduler.add("digest", "email", {"kind": "digest"},
                           interval_s=60, now=T0)
        self.assertEqual(self.scheduler.tick(now=T0 + 59), 0)
        self.assertEqual(self.scheduler.tick(now=T0 + 60), 1)
        self.assertEqual(self.queue.stats(now=T0 + 60)["queued"], 1)
        job = self.queue.claim("w1", now=T0 + 60)
        self.assertEqual(job.kind, "email")
        self.assertEqual(job.payload, {"kind": "digest"})

    def test_start_at_overrides_first_run(self):
        self.scheduler.add("digest", "email", interval_s=60,
                           start_at=T0 + 5, now=T0)
        self.assertEqual(self.scheduler.tick(now=T0 + 5), 1)

    def test_missed_runs_are_not_backfilled(self):
        """After downtime spanning several intervals, exactly one job is
        enqueued and next_run lands in the future."""
        self.scheduler.add("digest", "email", interval_s=10,
                           start_at=T0, now=T0)
        self.assertEqual(self.scheduler.tick(now=T0 + 75), 1)
        self.assertEqual(self.queue.stats(now=T0 + 75)["queued"], 1)
        (schedule,) = self.scheduler.list()
        self.assertEqual(schedule["next_run"], T0 + 80)

    def test_refire_of_same_slot_deduplicates(self):
        """Two processes ticking the same due slot enqueue one job: the
        idempotency key is derived from the slot."""
        self.scheduler.add("digest", "email", interval_s=60,
                           start_at=T0, now=T0)
        self.assertEqual(self.scheduler.tick(now=T0), 1)
        # Second process saw the same due row before the first advanced it.
        self.conn.execute(
            "UPDATE schedules SET next_run = ? WHERE name = 'digest'", (T0,))
        self.assertEqual(self.scheduler.tick(now=T0), 1)
        self.assertEqual(self.queue.stats(now=T0)["queued"], 1)

    def test_disabled_schedule_does_not_fire(self):
        self.scheduler.add("digest", "email", interval_s=60,
                           start_at=T0, now=T0)
        self.scheduler.set_enabled("digest", False)
        self.assertEqual(self.scheduler.tick(now=T0 + 120), 0)
        self.scheduler.set_enabled("digest", True)
        self.assertEqual(self.scheduler.tick(now=T0 + 120), 1)

    def test_add_replaces_existing(self):
        self.scheduler.add("digest", "email", interval_s=60, now=T0)
        self.scheduler.add("digest", "report", interval_s=30, now=T0)
        (schedule,) = self.scheduler.list()
        self.assertEqual(schedule["kind"], "report")
        self.assertEqual(schedule["interval_s"], 30)

    def test_remove(self):
        self.scheduler.add("digest", "email", interval_s=60, now=T0)
        self.assertTrue(self.scheduler.remove("digest"))
        self.assertFalse(self.scheduler.remove("digest"))
        self.assertEqual(self.scheduler.list(), [])
