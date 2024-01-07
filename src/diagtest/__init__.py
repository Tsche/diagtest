import logging
from typing import Optional
from pathlib import Path
import click

from diagtest.log import setup_logger
from diagtest.default import load_compilers, load_languages
from diagtest.driver import Runner

setup_logger()


@click.command()
@click.option("--list-compilers", type=bool, is_flag=True, default=False, help="Print discovered compilers and exit.")
@click.option("--output", type=Optional[Path], default=None, help="Path to build directory")
@click.option("--verbose", type=bool, is_flag=True, default=False, help="Be more verbose")
@click.option("--language", "-l", type=str, default="", help="Target language")
@click.argument("files", type=Path, nargs=-1)
def main(files: list[Path], list_compilers=False, verbose=False, output: Optional[Path] = None, language: str = ""):
    # assert filename.exists(), "Please provide a valid path"
    if verbose:
        logging.root.setLevel(logging.DEBUG)

    load_languages()
    load_compilers()

    if list_compilers:
        from diagtest.default import dump_compilers
        dump_compilers()
        return

    if not files:
        raise RuntimeError("Input files missing")

    raise SystemExit(not all(Runner(path, output, language).run() for path in files))
