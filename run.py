#!/usr/bin/env python3
"""AdjScope-Tx public command-line entry point."""
import sys
sys.dont_write_bytecode = True
from adjscope_tx.cli import entrypoint

if __name__ == '__main__':
    raise SystemExit(entrypoint())
