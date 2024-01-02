import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any

import em
from click import style

from diagtest.assertion import Assertion, Message, ReturnCode, ErrorCode
from diagtest.compiler import Compiler, Level, Report
from diagtest.exceptions import UsageError
from diagtest.default import get_defaults

def change_repr(repr_fnc):
    class ReprWrapper:
        def __init__(self, fnc):
            self.fnc = fnc

        def __call__(self, *args, **kwargs):
            return self.fnc(*args, **kwargs)

        def __repr__(self):
            nonlocal repr_fnc
            return repr_fnc()

    return ReprWrapper

class Runner:
    def __init__(self, source: Path, out_path: Optional[Path] = None):
        if out_path is None:
            out_path = source.parent / "build"

        out_path.mkdir(exist_ok=True, parents=True)
        with Parser(source) as (processed, tests):
            self.tests = tests

            preprocessed_source = out_path / source.name
            preprocessed_source.write_text(processed)
            self.source = preprocessed_source

    def run(self):
        return all(test.run(self.source) for test in self.tests)


@dataclass
class Test:
    name: str
    assertions: defaultdict[Compiler, list[Assertion]] = field(default_factory=lambda: defaultdict(list))

    @property
    def identifier(self):
        return self.name.upper().replace(" ", "_")

    def add_assertion(self, compiler: Compiler, assertion: Assertion):
        self.assertions[compiler].append(assertion)

    def run(self, source: Path):
        print(f"Test '{self.name}'")
        failed = False
        for compiler, assertions in self.assertions.items():
            if not compiler.available:
                #logging.warning("Skipping %s because it is not available.", compiler)
                continue

            print(f"  Compiler group {compiler}")
            results: dict[Assertion, list[tuple[str, bool, Report]]] = defaultdict(list)
            for name, result in compiler.execute(source, self.identifier):
                for assertion in assertions:
                    success = assertion.check(result)
                    results[assertion].append((name, success, result))

            for assertion, runs in results.items():
                print(f"    {assertion}")
                for name, success, result in runs:
                    message = style("PASS", fg="green") if success else style("FAIL", fg="red")
                    print(f"      {name}: {message}")
                    if not success:
                        failed = True
                        logging.error(f"Command: {result.command}")
                        print("STDOUT\n",result.stdout)
                        print("STDERR\n", result.stderr)
                        print(result.diagnostics)
        return not failed


class Parser:
    def __init__(self, source: Path):
        self.globals = {
            "include": self.include,
            "update_globals": self.update_globals,
            "load_defaults": self.load_defaults,
            "test": self.test,
            "error_code": self.error_code,
            "return_code": self.return_code,
            "note": self.note,
            "warning": self.warning,
            "error": self.error,
            "fatal_error": self.fatal_error
        }
        self.interpreter = em.Interpreter(globals=self.globals)
        self.tests: list[Test] = []
        self.source = source

    def __enter__(self):
        content = self.source.read_text(encoding="utf-8")
        processed = self.interpreter.expand(content, name=self.source)
        return processed, self.tests

    def __exit__(self, type_, value, traceback):
        self.interpreter.shutdown()

    def include(self, path: Path | str):
        if not isinstance(path, Path):
            path = Path(path)

        if not path.is_absolute():
            file, *_ = self.interpreter.identify()
            path = Path(file).parent / path

        self.interpreter.include(str(path.resolve()))

    def load_defaults(self, language: str):
        language = language.lower()
        defaults = get_defaults(language)
        if not defaults:
            logging.warning("Could not find defaults for language %s", language)
            return
        self.update_globals(defaults)

    def update_globals(self, new_globals: dict[str, Any]):
        self.interpreter.updateGlobals(new_globals)

    def test(self, name: str):
        this_test = Test(name)
        self.tests.append(this_test)

        def report_usage_error():
            raise UsageError(self.interpreter.identify(),
                             "Make sure to NOT place a space before the curly brace after @test(...)")

        @change_repr(report_usage_error)
        def wrap(code: str):
            nonlocal this_test
            # TODO this is language dependent
            return f"\n#ifdef {this_test.identifier}\n{code}\n#endif"

        return wrap

    def return_code(self, compiler: Compiler, code: int):
        self.tests[-1].add_assertion(compiler, ReturnCode(code))

    def error_code(self, compiler: Compiler, code: str):
        self.tests[-1].add_assertion(compiler, ErrorCode(code))

    def note(
        self,
        compiler: Compiler,
        text: Optional[str] = None,
        *,
        regex: re.Pattern[str] | str | None = None,
    ):
        self.tests[-1].add_assertion(compiler, Message(Level.note, text, regex))

    def warning(
        self,
        compiler: Compiler,
        text: Optional[str] = None,
        *,
        regex: re.Pattern[str] | str | None = None,
    ):
        self.tests[-1].add_assertion(compiler, Message(Level.warning, text, regex))

    def error(
        self,
        compiler: Compiler,
        text: Optional[str] = None,
        *,
        regex: re.Pattern[str] | str | None = None,
    ):
        self.tests[-1].add_assertion(compiler, Message(Level.error, text, regex))

    def fatal_error(
        self,
        compiler: Compiler,
        text: Optional[str] = None,
        *,
        regex: re.Pattern[str] | str | None = None,
    ):
        self.tests[-1].add_assertion(compiler, Message(Level.fatal_error, text, regex))
