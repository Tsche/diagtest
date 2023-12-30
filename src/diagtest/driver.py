import em
import re

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from collections import defaultdict

from click import echo, style

from diagtest.assertion import Level, Assertion, SimpleAssertion, RegexAssertion
from diagtest.compiler import Compiler, GCC, Clang, MSVC
from diagtest.exceptions import UsageError


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
        for test in self.tests:
            test.run(self.source)


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
        print(f"Test {self.name}")
        for compiler, assertions in self.assertions.items():
            print(f"{compiler} {assertions}")
            for result in compiler.execute(source, self.identifier):
                for assertion in assertions:
                    result = assertion.check(result)
                    echo(style("PASS\n", fg="green") if result else style("FAIL\n", fg="red"))


class Parser:
    def __init__(self, source: Path):
        compilers = {"GCC": GCC, "Clang": Clang, "MSVC": MSVC}

        self.globals = {
            **compilers,
            "include": self.include,
            "test": self.test,
            "error": self.error,
        }
        self.interpreter = em.Interpreter(globals=self.globals)
        self.tests: list[Test] = []
        self.source = source

    def __enter__(self):
        content = self.source.read_text(encoding="utf-8")
        processed = self.interpreter.expand(content, name=self.source)
        return processed, self.tests

    def __exit__(self, type, value, traceback):
        self.interpreter.shutdown()

    def include(self, path: Path):
        if not isinstance(path, Path):
            path = Path(path)

        if not path.is_absolute():
            file, *_ = self.interpreter.identify()
            path = Path(file).parent / path

        self.interpreter.include(str(path.resolve()))

    def test(self, name: str):
        this_test = Test(name)
        self.tests.append(this_test)

        def report_usage_error():
            print()
            err = "Make sure to NOT place a space before the curly brace after @test(...)"
            raise UsageError(self.interpreter.identify(), err)
            return err

        @change_repr(report_usage_error)
        def wrap(code: str):
            nonlocal this_test
            return f"#ifdef {this_test.identifier}\n{code}\n#endif"

        return wrap

    def diagnostic(
        self,
        compiler: Compiler,
        level: Level,
        text: Optional[str] = None,
        regex: re.Pattern[str] | str | None = None,
    ):
        if text is not None:
            assertion = SimpleAssertion(level, text)
        elif regex is not None:
            assertion = RegexAssertion(level, regex)
        else:
            raise UsageError("Invalid assertion kind")

        self.tests[-1].add_assertion(compiler, assertion)

    def note(
        self,
        compiler: Compiler,
        text: Optional[str] = None,
        *,
        regex: re.Pattern[str] | str | None = None,
    ):
        self.diagnostic(compiler, Level.note, text, regex)

    def warning(
        self,
        compiler: Compiler,
        text: Optional[str] = None,
        *,
        regex: re.Pattern[str] | str | None = None,
    ):
        self.diagnostic(compiler, Level.warning, text, regex)

    def error(
        self,
        compiler: Compiler,
        text: Optional[str] = None,
        *,
        regex: re.Pattern[str] | str | None = None,
    ):
        self.diagnostic(compiler, Level.error, text, regex)

    def fatal_error(
        self,
        compiler: Compiler,
        text: Optional[str] = None,
        *,
        regex: re.Pattern[str] | str | None = None,
    ):
        self.diagnostic(compiler, Level.fatal_error, text, regex)
