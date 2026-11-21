"""Command line entry point: python -m browser_desktop --data-dir D --port P"""

from __future__ import annotations

import argparse
import sys

from .server import create_server
from .storage import StorageError


def _port(value: str) -> int:
    if not (value.isascii() and value.isdigit()):
        raise argparse.ArgumentTypeError("must be an integer from 0 to 65535")
    number = int(value)
    if not 0 <= number <= 65535:
        raise argparse.ArgumentTypeError("must be an integer from 0 to 65535")
    return number


def _one_line(message: object) -> str:
    return " ".join(str(message).split())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="browser_desktop",
        description="Local browser desktop simulator (binds 127.0.0.1 only).",
    )
    parser.add_argument("--data-dir", required=True, help="directory for desktop.sqlite3")
    parser.add_argument(
        "--port", required=True, type=_port, help="TCP port, 0-65535 (0 = ephemeral)"
    )
    args = parser.parse_args(argv)

    try:
        server, port = create_server(args.data_dir, args.port)
    except StorageError as exc:
        print(f"error: {_one_line(exc)}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: cannot listen on port {args.port}: {_one_line(exc)}", file=sys.stderr)
        return 1

    print(f"Serving on http://127.0.0.1:{port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
