import logging
from typing import Optional
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import nullcontext
import click

from diagtest.log import setup_logger
from diagtest.default import load_compilers, load_languages
from diagtest.driver import Runner
from diagtest.output.terminal import TerminalPrinter
from diagtest.printer import Printer

setup_logger()


@click.command()
@click.option("--list-compilers", type=bool, is_flag=True, default=False, help="Print discovered compilers and exit.")
@click.option("--output", type=Path, default=None, help="Path to build directory")
@click.option("--verbose", type=bool, is_flag=True, default=False, help="Be more verbose")
@click.option("--language", "-l", type=str, default="", help="Target language")
@click.option("--sort-by-assertion", type=bool, default=False, is_flag=True, help="Sort results by assertion, not by compiler")
@click.option("--junit-xml", type=Path, default=None, help="Path to output JUnit style XML test report to")
#@click.option("--json", type=Path, default=None, help="Path to output JSON test report to")
@click.option("--brief", type=bool, default=False, is_flag=True, help="Do not output extra info for failed assertions")
@click.argument("files", type=Path, nargs=-1)
def main(files: list[Path], sort_by_assertion: bool, list_compilers: bool = False, verbose: bool = False, brief: bool = False,
         output: Optional[Path] = None, language: str = "", junit_xml: Optional[Path] = None, json: Optional[Path] = None):
    assert all(file.exists() for file in files), "Please provide valid file paths"
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

    printers: list[Printer] = [TerminalPrinter(brief=brief, assertion_first=sort_by_assertion)]
    if junit_xml:
        from diagtest.output.junit import JUnitPrinter
        printers.append(JUnitPrinter(junit_xml, assertion_first=sort_by_assertion))

    #if json:
    #    from diagtest.output.json import JSONPrinter
    #    printers.append(JSONPrinter(json))

    with nullcontext(output) if output is not None else TemporaryDirectory() as out_path:
        runner = Runner(list(files), Path(out_path), language)
        results = list(runner.run())

    for printer in printers:
        printer.print(results)

    # raise SystemExit(not all(Runner(path, output, language).run() for path in files))
