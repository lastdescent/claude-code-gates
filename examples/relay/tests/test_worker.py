from relay import PermanentError, Worker, backoff
from tests.base import RelayTestCase

T0 = 1_000_000.0


class TestBackoff(RelayTestCase):
    def test_doubles_per_attempt_and_caps(self):
        self.assertEqual(backoff(1), 1.0)
        self.assertEqual(backoff(2), 2.0)
        self.assertEqual(backoff(3), 4.0)
        self.assertEqual(backoff(20), 300.0)
        self.assertEqual(backoff(3, base=5.0, cap=8.0), 8.0)


class TestWorker(RelayTestCase):
    def make_worker(self, **kwargs):
        return Worker(self.queue, "w1", lease_s=60, **kwargs)

    def test_success_acks(self):
        worker = self.make_worker()
        seen = []
        worker.register("email", lambda job: seen.append(job.payload))
        job_id = self.queue.enqueue("email", {"to": "a@example.com"}, now=T0)
        self.assertTrue(worker.run_once(now=T0))
        self.assertEqual(seen, [{"to": "a@example.com"}])
        self.assertEqual(self.queue.get(job_id).status, "done")

    def test_no_ready_job_returns_false(self):
        worker = self.make_worker()
        worker.register("email", lambda job: None)
        self.assertFalse(worker.run_once(now=T0))

    def test_handler_decorator_registers(self):
        worker = self.make_worker()

        @worker.handler("email")
        def send(job):
            pass

        job_id = self.queue.enqueue("email", now=T0)
        self.assertTrue(worker.run_once(now=T0))
        self.assertEqual(self.queue.get(job_id).status, "done")

    def test_unregistered_kind_is_left_alone(self):
        worker = self.make_worker()
        worker.register("email", lambda job: None)
        job_id = self.queue.enqueue("report", now=T0)
        self.assertFalse(worker.run_once(now=T0))
        self.assertEqual(self.queue.get(job_id).status, "queued")

    def test_failure_requeues_with_backoff(self):
        worker = self.make_worker(backoff_base=10.0)

        def explode(job):
            raise ValueError("smtp down")

        worker.register("email", explode)
        job_id = self.queue.enqueue("email", now=T0)
        worker.run_once(now=T0)
        job = self.queue.get(job_id)
        self.assertEqual(job.status, "queued")
        self.assertIn("smtp down", job.last_error)
        # first attempt -> backoff(1) = base
        self.assertEqual(job.not_before, T0 + 10.0)

    def test_attempts_exhausted_goes_dead(self):
        worker = self.make_worker(backoff_base=0.0)
        worker.register("email", lambda job: 1 / 0)
        job_id = self.queue.enqueue("email", max_attempts=3, now=T0)
        for i in range(3):
            self.assertTrue(worker.run_once(now=T0 + i))
        job = self.queue.get(job_id)
        self.assertEqual(job.status, "dead")
        self.assertEqual(job.attempts, 3)

    def test_permanent_error_buries_immediately(self):
        worker = self.make_worker()

        def reject(job):
            raise PermanentError("unknown recipient")

        worker.register("email", reject)
        job_id = self.queue.enqueue("email", max_attempts=5, now=T0)
        worker.run_once(now=T0)
        job = self.queue.get(job_id)
        self.assertEqual(job.status, "dead")
        self.assertEqual(job.attempts, 1)
        self.assertIn("unknown recipient", job.last_error)

    def test_lost_lease_discards_result(self):
        """A slow handler outlives its lease and the job is reclaimed; the
        first worker's ack must not overwrite the new owner's state."""
        worker = self.make_worker()

        def slow(job):
            # Simulates time passing beyond the lease: the reaper requeues
            # the job while this handler is still running.
            self.queue.release_expired(now=T0 + 61)

        worker.register("email", slow)
        job_id = self.queue.enqueue("email", now=T0)
        self.assertTrue(worker.run_once(now=T0))
        self.assertEqual(self.queue.get(job_id).status, "queued")

    def test_run_stops_after_max_jobs(self):
        worker = self.make_worker()
        worker.register("email", lambda job: None)
        for _ in range(3):
            self.queue.enqueue("email", now=T0)
        self.assertEqual(worker.run(max_jobs=2, poll_s=0), 2)
        self.assertEqual(self.queue.stats()["queued"], 1)
