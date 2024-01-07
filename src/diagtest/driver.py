import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any

import em
from click import style

from diagtest.assertion import Assertion, Message, ReturnCode, ErrorCode
from diagtest.compiler import Compiler, Level
from diagtest.exceptions import UsageError
from diagtest.util import change_repr
from diagtest.default import compilers, languages
from diagtest.language import Language, detect_language


class Runner:
    def __init__(self, source: Path, out_path: Optional[Path] = None, language: str = ""):
        if out_path is None:
            out_path = source.parent / "build"

        out_path.mkdir(exist_ok=True, parents=True)
        with Parser(source, language) as (processed, tests):
            self.tests = tests

            preprocessed_source = out_path / source.name
            preprocessed_source.write_text(processed)
            self.source = preprocessed_source

    def run(self):
        return all(test.run(self.source) for test in self.tests)


@dataclass
class Test:
    identifier: str
    name: str
    assertions: defaultdict[Compiler, list[Assertion]] = field(default_factory=lambda: defaultdict(list))

    @property
    def compilers(self):
        return self.assertions.keys()

    def add_assertion(self, compiler: Compiler, assertion: Assertion):
        self.assertions[compiler].append(assertion)

    def run(self, source: Path):
        print(f"Test '{self.name}'")
        results = {compiler: list(compiler.run_test(source, self.identifier)) for compiler in self.compilers}
        failed = False

        for compiler, assertions in self.assertions.items():
            if not compiler.available:
                print(f"  Compiler {compiler} - skipped")
                continue

            print(f"  Compiler {compiler}")
            for assertion in assertions:
                print(f"    {assertion}")
                for result in results[compiler]:
                    success = assertion.check(result)
                    message = style("PASS", fg="green") if success else style("FAIL", fg="red")
                    print(f"      {result.name}: {message}")
                    if not success:
                        failed = True
                        logging.error("Command failed: %s", result.command)
                        print("STDOUT\n", result.stdout)
                        print("STDERR\n", result.stderr)

        return not failed


class Parser:
    def __init__(self, source: Path, language: str = ""):
        self.globals = {name: getattr(self, name)
                        for name in dir(type(self))
                        if not name.startswith('_')}

        self.interpreter = em.Interpreter(globals=self.globals)

        self.tests: list[Test] = []
        self.source: Path = source
        self.language: str = language
        self.language_definition: Optional[type[Language]] = None

        if not self.language:
            candidates = detect_language(source)
            if len(candidates) > 1:
                logging.debug("Language for %s is ambiguous. Candidates: %s", source, candidates)
            elif len(candidates) == 1:
                self.language = candidates[0]
            else:
                logging.debug("Could not detect language for %s", source)

        self.set_language(language)


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

    def set_language(self, language: str = ""):
        if not language:
            return

        self.language = language
        definition = languages.get(language)
        if self.language_definition != definition:
            self.language_definition = definition
            # TODO reload interpreter

    def load_defaults(self, language: str = ""):
        if language:
            self.set_language(language)
        assert self.language, "Must specify language to load defaults for"
        defaults: dict[str, Any] = {}

        def wrap(cls):
            def inner(**kwargs):
                if 'language' not in kwargs:
                    kwargs['language'] = self.language
                return cls(**kwargs)
            return inner

        for compiler in compilers:
            if self.language not in getattr(compiler, 'languages', []):
                continue

            defaults[compiler.__name__] = wrap(compiler)
            defaults[compiler.__name__.lower()] = compiler(language=self.language)

        if not defaults:
            logging.warning("Could not find defaults for language %s", self.language)
            return
        self.update_globals(defaults)

    def update_globals(self, new_globals: dict[str, Any]):
        self.interpreter.updateGlobals(new_globals)

    def test(self, name: str):
        assert self.language, "Automatic language detection failed. "\
            "Specify it as command line argument or use set_language before the first test"
        assert self.language_definition is not None, "Missing language definition"
        self.tests.append(Test(self.language_definition.identifier(name), name))

        def report_usage_error():
            raise UsageError(self.interpreter.identify(),
                             "Make sure to NOT place a space before the curly brace after @test(...)")

        @change_repr(report_usage_error)
        def wrap(code: str):
            nonlocal name
            assert self.language_definition is not None, "Missing language definition"
            return self.language_definition.wrap_test(name, code)

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
