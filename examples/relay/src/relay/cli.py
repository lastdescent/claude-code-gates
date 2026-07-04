"""Command-line interface: relay <command> against a database file.

The CLI is a thin shell over queue.py / scheduler.py / worker.py - it parses
arguments, calls exactly one API function, prints the result. Handler code
for `relay work` comes from a user module exposing HANDLERS = {kind: fn}.
"""
import argparse
import importlib
import json
import sys

from .queue import Queue
from .scheduler import Scheduler
from .store import connect
from .worker import Worker


def build_parser():
    p = argparse.ArgumentParser(prog="relay",
                                description="SQLite-backed job queue")
    p.add_argument("--db", default="relay.db", help="database file")
    sub = p.add_subparsers(dest="command", required=True)

    enq = sub.add_parser("enqueue", help="add a job")
    enq.add_argument("kind")
    enq.add_argument("--payload", default="{}", help="JSON object")
    enq.add_argument("--priority", type=int, default=0)
    enq.add_argument("--max-attempts", type=int, default=5)
    enq.add_argument("--delay", type=float, default=0.0, metavar="SECONDS")
    enq.add_argument("--key", help="idempotency key")

    sub.add_parser("stats", help="job counts per status")
    sub.add_parser("reap", help="requeue jobs with expired leases")

    dead = sub.add_parser("dead", help="inspect or requeue dead jobs")
    dead_sub = dead.add_subparsers(dest="dead_command", required=True)
    dead_sub.add_parser("list")
    req = dead_sub.add_parser("requeue")
    req.add_argument("job_id", nargs="?", type=int,
                     help="one job id; omit to requeue all dead jobs")

    sched = sub.add_parser("schedule", help="manage recurring jobs")
    sched_sub = sched.add_subparsers(dest="schedule_command", required=True)
    add = sched_sub.add_parser("add")
    add.add_argument("name")
    add.add_argument("kind")
    add.add_argument("--interval", type=float, required=True, metavar="SECONDS")
    add.add_argument("--payload", default="{}", help="JSON object")
    sched_sub.add_parser("list")
    rm = sched_sub.add_parser("rm")
    rm.add_argument("name")
    sched_sub.add_parser("tick")

    work = sub.add_parser("work", help="run a worker loop")
    work.add_argument("--handlers", required=True,
                      help="importable module with HANDLERS = {kind: fn}")
    work.add_argument("--max", type=int, default=None,
                      help="stop after N jobs (default: run forever)")
    work.add_argument("--poll", type=float, default=0.5, metavar="SECONDS")
    work.add_argument("--lease", type=float, default=60.0, metavar="SECONDS")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    conn = connect(args.db)
    queue = Queue(conn)

    if args.command == "enqueue":
        job_id = queue.enqueue(args.kind, json.loads(args.payload),
                               priority=args.priority,
                               max_attempts=args.max_attempts,
                               delay_s=args.delay, idempotency_key=args.key)
        print(job_id)
    elif args.command == "stats":
        for status, n in queue.stats().items():
            print(f"{status:>7}  {n}")
    elif args.command == "reap":
        print(queue.release_expired())
    elif args.command == "dead":
        if args.dead_command == "list":
            rows = conn.execute(
                "SELECT id, kind, attempts, last_error FROM jobs"
                " WHERE status = 'dead' ORDER BY id")
            for row in rows:
                print(f"{row['id']}  {row['kind']}  attempts={row['attempts']}"
                      f"  {row['last_error']}")
        else:
            print(queue.requeue_dead(args.job_id))
    elif args.command == "schedule":
        scheduler = Scheduler(conn, queue)
        if args.schedule_command == "add":
            scheduler.add(args.name, args.kind, json.loads(args.payload),
                          interval_s=args.interval)
        elif args.schedule_command == "list":
            for s in scheduler.list():
                state = "on" if s["enabled"] else "off"
                print(f"{s['name']}  {s['kind']}  every {s['interval_s']}s"
                      f"  [{state}]")
        elif args.schedule_command == "rm":
            if not scheduler.remove(args.name):
                print(f"no schedule named {args.name!r}", file=sys.stderr)
                return 1
        else:
            print(scheduler.tick())
    elif args.command == "work":
        module = importlib.import_module(args.handlers)
        worker = Worker(queue, lease_s=args.lease)
        for kind, fn in module.HANDLERS.items():
            worker.register(kind, fn)
        worker.run(max_jobs=args.max, poll_s=args.poll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
