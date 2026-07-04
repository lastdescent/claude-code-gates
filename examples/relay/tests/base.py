import shutil
import tempfile
import unittest
from pathlib import Path

from relay import Queue, connect


class RelayTestCase(unittest.TestCase):
    """Fresh file-backed database per test (threads need a real file)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="relay-test-"))
        self.db_path = str(self.tmp / "relay.db")
        self.conn = connect(self.db_path)
        self.queue = Queue(self.conn)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(self.conn.close)
