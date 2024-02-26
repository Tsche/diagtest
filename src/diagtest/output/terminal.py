from typing import Iterable
from click import echo, style

from diagtest.compiler import ProcessedResult
from diagtest.test import TestResult, TestSuiteResult
from diagtest.util import print_indent


def colored_result(success: bool | None):
    if success is None:
        return "SKIPPED"
    return style("PASS", fg="green") if success else style("FAIL", fg="red")

class TerminalPrinter:
    def __init__(self, brief: bool = False, assertion_first: bool = False):
        self.sort_function = TestResult.by_assertion if assertion_first else TestResult.by_compiler
        self.brief = brief

    def print_compiler_result(self, result: ProcessedResult):
        if self.brief:
            return
        print(result.command)
        print(f"{len(result.diagnostics)} diagnostic messages found. Return code: {result.returncode}")
        print("=== STDOUT ===")
        print(result.stdout)
        print("=== STDERR ===")
        print(result.stderr)
        print("----------------------------------------")

    def print_results(self, results):
        for result, success in results:
            if result is None:
                print_indent("SKIPPED", 4)
                continue

            print_indent(result.name, 4, end=' ')
            echo(colored_result(success), nl=False)

            if result.elapsed_s > 1.0:
                echo(f" in {result.elapsed_s:.3f}s")
            else:
                echo(f" in {result.elapsed_ms:.3f}ms")

            if success is False:
                self.print_compiler_result(result)

    def print_test(self, test: TestResult):
        print_indent(f"Test `{test.name}`", 1)
        for compiler, assertions in self.sort_function(test).items():
            print_indent(compiler, 2)
            for assertion, results in assertions.items():
                if len(results) == 1 and results[0] == (None, None):
                    print_indent(f"{assertion} - SKIPPED", 3)
                    continue
                print_indent(assertion, 3)
                self.print_results(results)
            print()

    def print_suite(self, suite: TestSuiteResult):
        print(f"File {suite.source_file.name}")
        for test in suite:
            self.print_test(test)

    def print(self, suites: Iterable[TestSuiteResult]):
        for suite in suites:
            self.print_suite(suite)
