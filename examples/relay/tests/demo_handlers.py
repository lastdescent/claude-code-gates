"""Handler module used by test_cli.py via `relay work --handlers`."""
RECEIVED = []


def echo(job):
    RECEIVED.append(job.payload)


HANDLERS = {"echo": echo}
