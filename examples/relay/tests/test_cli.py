import io
from contextlib import redirect_stdout

from relay.cli import main
from tests import demo_handlers
from tests.base import RelayTestCase


class TestCli(RelayTestCase):
    def relay(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["--db", self.db_path, *args])
        return code, out.getvalue()

    def test_enqueue_prints_job_id_and_stats_sees_it(self):
        code, out = self.relay("enqueue", "email", "--payload", '{"to": "a"}')
        self.assertEqual(code, 0)
        job = self.queue.get(int(out.strip()))
        self.assertEqual(job.payload, {"to": "a"})
        _, out = self.relay("stats")
        self.assertIn("queued", out)

    def test_enqueue_with_key_is_idempotent(self):
        _, first = self.relay("enqueue", "email", "--key", "k1")
        _, second = self.relay("enqueue", "email", "--key", "k1")
        self.assertEqual(first, second)

    def test_work_runs_handlers_from_module(self):
        demo_handlers.RECEIVED.clear()
        self.relay("enqueue", "echo", "--payload", '{"n": 1}')
        code, _ = self.relay("work", "--handlers", "tests.demo_handlers",
                             "--max", "1", "--poll", "0")
        self.assertEqual(code, 0)
        self.assertEqual(demo_handlers.RECEIVED, [{"n": 1}])

    def test_schedule_roundtrip_and_rm_unknown_fails(self):
        code, _ = self.relay("schedule", "add", "digest", "email",
                             "--interval", "60")
        self.assertEqual(code, 0)
        _, out = self.relay("schedule", "list")
        self.assertIn("digest", out)
        self.assertEqual(self.relay("schedule", "rm", "digest")[0], 0)
        self.assertEqual(self.relay("schedule", "rm", "digest")[0], 1)
