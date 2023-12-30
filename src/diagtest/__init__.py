from typing import Optional
from pathlib import Path
import click

from diagtest.driver import Runner


@click.command()
@click.option("--output", type=Optional[Path], default=None, help="Path to build directory")
@click.argument("filename", type=Path)
def main(filename: Path, output: Optional[Path] = None):
    assert filename.exists(), "Please provide a valid path"
    Runner(filename, output).run()
