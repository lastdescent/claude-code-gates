"""Worker: claims jobs it has handlers for, runs them, settles the outcome.

Outcome mapping: handler returns -> ack; handler raises PermanentError ->
bury (dead, no retries); handler raises anything else -> fail with
exponential backoff. A lease lost mid-run means the result is discarded and
the job runs again elsewhere - that is the at-least-once contract.
"""
import time
import uuid

from .queue import StaleLeaseError


class PermanentError(Exception):
    """Raise from a handler to send the job straight to 'dead'."""


def backoff(attempt, *, base=1.0, factor=2.0, cap=300.0):
    """Delay in seconds before retry number `attempt` (1-based), capped."""
    return min(cap, base * factor ** max(0, attempt - 1))


class Worker:
    def __init__(self, queue, worker_id=None, *, lease_s=60.0,
                 backoff_base=1.0, backoff_cap=300.0):
        self._queue = queue
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self._lease_s = lease_s
        self._backoff_base = backoff_base
        self._backoff_cap = backoff_cap
        self._handlers = {}

    def handler(self, kind):
        """Decorator: register the function as the handler for `kind`."""
        def register(fn):
            self._handlers[kind] = fn
            return fn
        return register

    def register(self, kind, fn):
        self._handlers[kind] = fn

    def run_once(self, *, now=None):
        """Claim and run one job. Returns True if a job was processed
        (even if its result had to be discarded), False if none was ready.

        Only kinds with a registered handler are claimed - jobs for other
        kinds stay queued for a worker that knows them.
        """
        now = time.time() if now is None else now
        job = self._queue.claim(self.worker_id, kinds=tuple(self._handlers),
                                lease_s=self._lease_s, now=now)
        if job is None:
            return False
        try:
            try:
                self._handlers[job.kind](job)
            except PermanentError as exc:
                self._queue.bury(job.id, self.worker_id,
                                 error=repr(exc), now=now)
            except Exception as exc:
                delay = backoff(job.attempts, base=self._backoff_base,
                                cap=self._backoff_cap)
                self._queue.fail(job.id, self.worker_id, error=repr(exc),
                                 retry_in=delay, now=now)
            else:
                self._queue.ack(job.id, self.worker_id, now=now)
        except StaleLeaseError:
            # Lease expired mid-run and someone else owns the job now; the
            # outcome of this run must not overwrite theirs.
            pass
        return True

    def run(self, *, max_jobs=None, poll_s=0.5, reap_every=20):
        """Blocking loop: reap expired leases periodically, process jobs,
        sleep briefly when the queue is empty. Stops after max_jobs."""
        done = 0
        ticks = 0
        while max_jobs is None or done < max_jobs:
            if ticks % reap_every == 0:
                self._queue.release_expired()
            ticks += 1
            if self.run_once():
                done += 1
            else:
                time.sleep(poll_s)
        return done
