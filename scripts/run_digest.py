"""Convenience entry point for running the default daily digest once."""

import sys

from multiscribe_agent.cli import main

if __name__ == "__main__":
    main(["digest", *sys.argv[1:]])
