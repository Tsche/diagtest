from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from diagtest.assertion import Assertion
from diagtest.compiler import Compiler, ProcessedResult


@dataclass
class RunResult:
    compiler: Compiler
    result: ProcessedResult | None
    assertions: dict[Assertion, bool | None]

Result = tuple[ProcessedResult | None, bool | None]

@dataclass
class TestResult:
    name: str
    runs: list[RunResult]

    def by_compiler(self):
        ret: dict[Compiler, dict[Assertion, list[Result]]] = defaultdict(lambda: defaultdict(list))
        for run in self.runs:
            for assertion, success in run.assertions.items():
                ret[run.compiler][assertion].append((run.result, success))
        return dict(ret)

    def by_assertion(self):
        ret: dict[Assertion, dict[Compiler, list[Result]]] = defaultdict(lambda: defaultdict(list))
        for run in self.runs:
            for assertion, success in run.assertions.items():
                ret[assertion][run.compiler].append((run.result, success))
        return dict(ret)

    def __bool__(self):
        return all(success if success is not None else True # count skipped as successful
                   for run in self.runs
                   for success in run.assertions.values())

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
        results = {compiler: list(compiler.run_test(source, self.identifier)) for compiler in self.compilers}

        def run_assertions():
            for compiler, assertions in self.assertions.items():
                if not compiler.available:
                    yield RunResult(compiler, None, {assertion: None for assertion in assertions})
                    continue

                for result in results[compiler]:
                    yield RunResult(compiler, result, {assertion: assertion.check(result) for assertion in assertions})

        return TestResult(self.name, runs=list(run_assertions()))

class TestSuiteResult(list[TestResult]):
    __slots__ = 'source_file'

    def __init__(self, *args, source_file: Optional[Path] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.source_file = source_file
