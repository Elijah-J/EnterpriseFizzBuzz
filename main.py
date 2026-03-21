"""Backward-compatible re-export stub for main."""
from enterprise_fizzbuzz.__main__ import *  # noqa: F401,F403
from enterprise_fizzbuzz.__main__ import main, build_argument_parser, configure_logging, BANNER  # noqa: F401

if __name__ == "__main__":
    import sys
    sys.exit(main())
