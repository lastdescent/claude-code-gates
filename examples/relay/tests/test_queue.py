import threading

from relay import Queue, StaleLeaseError, connect
from tests.base import RelayTestCase

T0 = 1_000_000.0  # fixed wall-clock origin; every test passes now= explicitly


class TestLifecycle(RelayTestCase):
    def test_enqueue_claim_ack(self):
        job_id = self.queue.enqueue("email", {"to": "a@example.com"}, now=T0)
        job = self.queue.claim("w1", now=T0)
        self.assertEqual(job.id, job_id)
        self.assertEqual(job.status, "leased")
        self.assertEqual(job.payload, {"to": "a@example.com"})
        self.assertEqual(job.attempts, 1)
        self.queue.ack(job.id, "w1", now=T0 + 1)
        self.assertEqual(self.queue.get(job_id).status, "done")

    def test_claim_on_empty_queue_returns_none(self):
        self.assertIsNone(self.queue.claim("w1", now=T0))

    def test_fifo_within_same_priority(self):
        first = self.queue.enqueue("email", now=T0)
        second = self.queue.enqueue("email", now=T0)
        self.assertEqual(self.queue.claim("w1", now=T0).id, first)
        self.assertEqual(self.queue.claim("w1", now=T0).id, second)

    def test_higher_priority_claimed_first(self):
        self.queue.enqueue("email", now=T0, priority=0)
        urgent = self.queue.enqueue("email", now=T0, priority=10)
        self.assertEqual(self.queue.claim("w1", now=T0).id, urgent)

    def test_delay_holds_job_back(self):
        self.queue.enqueue("email", delay_s=30, now=T0)
        self.assertIsNone(self.queue.claim("w1", now=T0 + 29))
        self.assertIsNotNone(self.queue.claim("w1", now=T0 + 30))

    def test_kind_filter(self):
        self.queue.enqueue("email", now=T0)
        self.assertIsNone(self.queue.claim("w1", kinds=("report",), now=T0))
        self.assertIsNone(self.queue.claim("w1", kinds=(), now=T0))
        self.assertIsNotNone(
            self.queue.claim("w1", kinds=("report", "email"), now=T0))


class TestIdempotency(RelayTestCase):
    def test_same_key_returns_existing_job(self):
        a = self.queue.enqueue("email", {"n": 1}, idempotency_key="k1", now=T0)
        b = self.queue.enqueue("email", {"n": 2}, idempotency_key="k1", now=T0)
        self.assertEqual(a, b)
        self.assertEqual(self.queue.stats(now=T0)["queued"], 1)
        self.assertEqual(self.queue.get(a).payload, {"n": 1})

    def test_jobs_without_key_are_not_deduplicated(self):
        a = self.queue.enqueue("email", now=T0)
        b = self.queue.enqueue("email", now=T0)
        self.assertNotEqual(a, b)


class TestLeases(RelayTestCase):
    def test_ack_by_other_worker_rejected(self):
        job_id = self.queue.enqueue("email", now=T0)
        self.queue.claim("w1", lease_s=60, now=T0)
        with self.assertRaises(StaleLeaseError):
            self.queue.ack(job_id, "w2", now=T0 + 1)

    def test_ack_after_lease_expiry_rejected(self):
        job_id = self.queue.enqueue("email", now=T0)
        self.queue.claim("w1", lease_s=60, now=T0)
        with self.assertRaises(StaleLeaseError):
            self.queue.ack(job_id, "w1", now=T0 + 61)

    def test_extend_lease_keeps_job_ackable(self):
        job_id = self.queue.enqueue("email", now=T0)
        self.queue.claim("w1", lease_s=60, now=T0)
        self.queue.extend_lease(job_id, "w1", lease_s=60, now=T0 + 50)
        self.queue.ack(job_id, "w1", now=T0 + 100)
        self.assertEqual(self.queue.get(job_id).status, "done")

    def test_release_expired_requeues(self):
        job_id = self.queue.enqueue("email", now=T0)
        self.queue.claim("w1", lease_s=60, now=T0)
        self.assertEqual(self.queue.release_expired(now=T0 + 59), 0)
        self.assertEqual(self.queue.release_expired(now=T0 + 61), 1)
        job = self.queue.get(job_id)
        self.assertEqual(job.status, "queued")
        self.assertIsNone(job.worker_id)

    def test_release_expired_buries_exhausted_job(self):
        job_id = self.queue.enqueue("email", max_attempts=1, now=T0)
        self.queue.claim("w1", lease_s=60, now=T0)
        self.queue.release_expired(now=T0 + 61)
        job = self.queue.get(job_id)
        self.assertEqual(job.status, "dead")
        self.assertEqual(job.last_error, "lease expired")


class TestFailure(RelayTestCase):
    def test_fail_requeues_with_delay(self):
        job_id = self.queue.enqueue("email", now=T0)
        self.queue.claim("w1", now=T0)
        self.queue.fail(job_id, "w1", error="boom", retry_in=10, now=T0 + 1)
        job = self.queue.get(job_id)
        self.assertEqual(job.status, "queued")
        self.assertEqual(job.last_error, "boom")
        self.assertEqual(job.not_before, T0 + 11)
        self.assertIsNone(self.queue.claim("w1", now=T0 + 10))
        self.assertIsNotNone(self.queue.claim("w1", now=T0 + 11))

    def test_fail_on_last_attempt_goes_dead(self):
        job_id = self.queue.enqueue("email", max_attempts=2, now=T0)
        for i in range(2):
            self.queue.claim("w1", now=T0 + i)
            self.queue.fail(job_id, "w1", error=f"try {i}", now=T0 + i)
        self.assertEqual(self.queue.get(job_id).status, "dead")

    def test_bury_skips_remaining_retries(self):
        job_id = self.queue.enqueue("email", max_attempts=5, now=T0)
        self.queue.claim("w1", now=T0)
        self.queue.bury(job_id, "w1", error="unrecoverable", now=T0)
        job = self.queue.get(job_id)
        self.assertEqual(job.status, "dead")
        self.assertEqual(job.attempts, 1)

    def test_requeue_dead_resets_attempts(self):
        job_id = self.queue.enqueue("email", max_attempts=1, now=T0)
        self.queue.claim("w1", now=T0)
        self.queue.fail(job_id, "w1", error="boom", now=T0)
        self.assertEqual(self.queue.requeue_dead(now=T0 + 5), 1)
        job = self.queue.get(job_id)
        self.assertEqual((job.status, job.attempts), ("queued", 0))


class TestStats(RelayTestCase):
    def test_counts_per_status_and_ready(self):
        self.queue.enqueue("a", now=T0)
        self.queue.enqueue("b", delay_s=100, now=T0)
        done = self.queue.enqueue("c", now=T0)
        self.queue.claim("w1", kinds=("c",), now=T0)
        self.queue.ack(done, "w1", now=T0)
        stats = self.queue.stats(now=T0)
        self.assertEqual(stats["queued"], 2)
        self.assertEqual(stats["ready"], 1)
        self.assertEqual(stats["done"], 1)
        self.assertEqual(stats["leased"], 0)


class TestConcurrentClaim(RelayTestCase):
    def test_each_job_is_claimed_exactly_once(self):
        """Four workers on their own connections drain the queue; no job may
        be delivered to two of them. This is the invariant behind
        at-least-once delivery with exclusive leases."""
        n_jobs = 300
        for i in range(n_jobs):
            self.queue.enqueue("email", {"i": i}, now=T0)

        claimed, lock = [], threading.Lock()

        def drain(worker_id):
            conn = connect(self.db_path)
            queue = Queue(conn)
            try:
                while True:
                    job = queue.claim(worker_id, lease_s=300, now=T0)
                    if job is None:
                        return
                    with lock:
                        claimed.append(job.id)
            finally:
                conn.close()

        threads = [threading.Thread(target=drain, args=(f"w{i}",))
                   for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(claimed), n_jobs,
                         "every job delivered exactly once")
        self.assertEqual(len(set(claimed)), n_jobs,
                         f"duplicate deliveries: {len(claimed) - len(set(claimed))}")
