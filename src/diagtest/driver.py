import logging
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any

import em

from diagtest.assertion import Message, ReturnCode, ErrorCode
from diagtest.test import Test, TestSuiteResult
from diagtest.compiler import Compiler
from diagtest.report import Level
from diagtest.exceptions import UsageError
from diagtest.util import change_repr
from diagtest.default import compilers, languages
from diagtest.language import Language, detect_language

@dataclass
class TestSuite:
    tests: list[Test]
    source: Path

    def run(self):
        return TestSuiteResult([test.run(self.source) for test in self.tests], source_file=self.source)

class Runner:
    def __init__(self, sources: Path | list[Path], out_path: Optional[Path] = None, language: str = ""):
        self.out_path = out_path
        self.language = language
        self.sources = sources if isinstance(sources, list) else [sources]

    def expand(self, source: Path):
        out_path = self.out_path or source.parent / "build"
        out_path = Path(out_path)
        out_path.mkdir(exist_ok=True, parents=True)
        with Parser(source, self.language) as (processed, tests):
            preprocessed_source = out_path / source.name
            preprocessed_source.write_text(processed)
            return TestSuite(tests, preprocessed_source)

    def run(self):
        for source in self.sources:
            try:
                suite = self.expand(source)
                yield suite.run()
            except Exception as exc: # TODO refine
                logging.exception("Running %s failed. Reason: %s", source, str(exc))


class Parser:
    def __init__(self, source: Path, language: str = ""):
        self.globals = {name: getattr(self, name)
                        for name in dir(type(self))
                        if not name.startswith('_')}

        self.interpreter = em.Interpreter(globals=self.globals)

        self.tests: list[Test] = []
        self.include_paths: list[Path] = []
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

    def _resolve_path(self, path: Path | str):
        if not isinstance(path, Path):
            path = Path(path)

        if not path.is_absolute():
            file, *_ = self.interpreter.identify()
            path = Path(file).parent / path
        return path.resolve()

    def include(self, path: Path | str):
        self.interpreter.include(str(self._resolve_path(path)))

    def include_path(self, path: Path | str):
        """
            Adds a directory to the include path. This may only be called before load_defaults!
        Args:
            path: Directory to add to the include path
        """
        path = self._resolve_path(path)
        assert path.exists(), "Include path does not exist"
        assert path.is_dir(), "Path does not point to a directory"
        self.include_paths.append(path)

    def set_language(self, language: str = ""):
        if not language:
            return

        self.language = language
        definition = languages.get(language)
        if self.language_definition != definition:
            self.language_definition = definition
            # TODO reload interpreter

    def load_defaults(self, language: str = "", dialect: str = ""):
        if language:
            self.set_language(language)
        assert self.language, "Must specify language to load defaults for"
        defaults: dict[str, Any] = {}

        def wrap(cls):
            def inner(**kwargs):
                if 'language' not in kwargs:
                    kwargs['language'] = self.language

                if self.include_paths:
                    if 'args' not in kwargs:
                        kwargs['args'] = []

                    assert hasattr(cls, "include"), f"Compiler {cls} cannot expand includes."
                    for path in self.include_paths:
                        kwargs['args'].append(cls.include(path))

                nonlocal dialect
                if dialect and 'dialect' not in kwargs:
                    kwargs['dialect'] = dialect

                return cls(**kwargs)
            return inner

        for compiler in compilers:
            if self.language not in getattr(compiler, 'languages', []):
                continue

            defaults[compiler.__name__] = wrap(compiler)
            defaults[compiler.__name__.lower()] = defaults[compiler.__name__]()

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
