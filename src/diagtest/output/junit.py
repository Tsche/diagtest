from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from xml.etree.ElementTree import Element, ElementTree, SubElement, indent

from diagtest.compiler import ProcessedResult
from diagtest.test import TestResult, TestSuiteResult

from diagtest.util import remove_duplicates


def add_property(properties: Element, name, value):
    SubElement(properties, "property", name=str(name), value=str(value))


class Meta:
    def __init__(self):
        self.results: list[ProcessedResult] = []

    @property
    def versions(self):
        return remove_duplicates(str(result.compiler.version) for result in self.results)

    @property
    def compiler_paths(self):
        return remove_duplicates(str(result.compiler.executable) for result in self.results)

    @property
    def compiler_names(self):
        return remove_duplicates(result.name for result in self.results)

    @property
    def compiler_targets(self):
        return remove_duplicates(result.compiler.target for result in self.results)

    @property
    def times(self):
        return [result.elapsed_s for result in self.results]


class JUnitPrinter:
    def __init__(self, out_path: Path, assertion_first: bool = False):
        self.out_path = out_path
        self.sort_function = TestResult.by_assertion if assertion_first else TestResult.by_compiler
        self.assertion_first = assertion_first

    def print_testcase(self, testsuite: Element, outer_key, assertions):
        testcase = SubElement(testsuite, "testcase", name=str(outer_key))
        properties = SubElement(testcase, "properties")
        add_property(properties, "compiler" if self.assertion_first else "assertions",
                     "\n".join(str(assertion) for assertion in assertions))
        add_property(properties, "assertions" if self.assertion_first else "compiler", str(outer_key))

        meta = Meta()
        assertion_count = 0
        has_failures = False
        for inner_key, results in assertions.items():
            if len(results) == 1 and results[0] == (None, None):
                continue

            for result, success in results:
                if success is not None:
                    assertion_count += 1
                if success is False:
                    has_failures = True
                    failure = SubElement(testcase, "failure", message=f"{result.name} failed",
                                         type=str(outer_key) if self.assertion_first else str(inner_key))
                    failure.text = f"""\
{result.command}
{len(result.diagnostics)} diagnostic messages found. Return code: {result.returncode}
=== STDOUT ===
{result.stdout}
=== STDERR ===
{result.stderr}"""
                meta.results.append(result)

        total_time = sum(meta.times)
        testcase.attrib['assertions'] = str(assertion_count)
        testcase.attrib['time'] = str(total_time)
        if assertion_count == 0:
            SubElement(testcase, "skipped", message="No assertions were executed")
            return 0, None, 0

        add_property(properties, "compiler_versions", ";".join(meta.versions))
        add_property(properties, "compiler_paths", ";".join(meta.compiler_paths))
        add_property(properties, "compiler_targets", ";".join(meta.compiler_targets))
        add_property(properties, "compiler_names", "\n".join(meta.compiler_names))
        add_property(properties, "compile_times", ";".join(str(time) for time in meta.times))

        return total_time, not has_failures, assertion_count

    def print_suite(self, root: Element, suite: TestSuiteResult):
        for test in suite:
            testsuite = SubElement(root, "testsuite", name=test.name)
            total_time = 0
            skipped = 0
            failures = 0
            tests = 0
            total_assertions = 0
            for outer_key, assertions in self.sort_function(test).items():
                time, success, assertion_count = self.print_testcase(testsuite, outer_key, assertions)
                total_assertions += assertion_count
                total_time += time
                tests += 1
                if success is None:
                    skipped += 1
                if success is False:
                    failures += 1

            testsuite.attrib["time"] = str(total_time)
            testsuite.attrib["tests"] = str(tests)
            testsuite.attrib["skipped"] = str(skipped)
            testsuite.attrib["failures"] = str(failures)
            testsuite.attrib["assertions"] = str(total_assertions)
            testsuite.attrib["timestamp"] = str(datetime.now(timezone.utc).isoformat())
            testsuite.attrib["file"] = str(suite.source_file)
            yield total_time, tests, failures, skipped, total_assertions

    def print(self, suites: Iterable[TestSuiteResult]):
        root = Element("testsuites")
        timestamp = str(datetime.now(timezone.utc).isoformat())

        results = [[sum(x) for x in zip(*self.print_suite(root, suite))] for suite in suites]
        total_time, tests, failures, skipped, total_assertions = [sum(x) for x in zip(*results)]
        root.attrib["time"] = str(total_time)
        root.attrib["tests"] = str(tests)
        root.attrib["skipped"] = str(skipped)
        root.attrib["failures"] = str(failures)
        root.attrib["assertions"] = str(total_assertions)
        root.attrib["timestamp"] = timestamp

        tree = ElementTree(root)
        indent(tree, space="    ", level=0)
        self.out_path.parent.mkdir(exist_ok=True, parents=True)
        tree.write(self.out_path, encoding="utf-8")
