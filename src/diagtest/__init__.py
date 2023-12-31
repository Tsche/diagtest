import logging
from typing import Optional
from pathlib import Path
import click

from diagtest.log import setup_logger
from diagtest.driver import Runner

setup_logger()

@click.command()
@click.option("--output", type=Optional[Path], default=None, help="Path to build directory")
@click.option("--verbose", type=bool, is_flag=True, default=False, help="Be more verbose")
@click.argument("filename", type=Path)
def main(filename: Path, verbose = False, output: Optional[Path] = None):
    assert filename.exists(), "Please provide a valid path"
    if verbose:
        logging.root.setLevel(logging.DEBUG)
    Runner(filename, output).run()
