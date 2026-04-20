import sys

from admin import ensure_daemon, restart_daemon
from helpers import *

HELP = """Browser Harness (local-only)

Read SKILL.md for the default workflow and examples.

Typical usage:
  browser-harness <<'PY'
  ensure_real_tab()
  print(page_info())
  PY

Helpers are pre-imported. The daemon auto-starts and connects to your local Chrome.
Cloud/remote browser features have been removed for security.
"""


def main():
    if len(sys.argv) > 1 and sys.argv[1] in {"-h", "--help"}:
        print(HELP)
        return
    if sys.stdin.isatty():
        sys.exit(
            "browser-harness reads Python from stdin. Use:\n"
            "  browser-harness <<'PY'\n"
            "  print(page_info())\n"
            "  PY"
        )
    ensure_daemon()
    exec(sys.stdin.read())


if __name__ == "__main__":
    main()
