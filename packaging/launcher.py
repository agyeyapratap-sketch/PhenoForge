"""Entry point for the frozen Windows build: GUI by default, CLI when arguments name a command."""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from phenoforge.cli import main

    sys.exit(main() or 0)
