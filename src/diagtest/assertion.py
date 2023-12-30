import re

from dataclasses import dataclass
from typing import Protocol, Optional
from diagtest.compiler import Result, Level


class Assertion(Protocol):
    def check(self, result: Result) -> bool:
        ...


@dataclass
class SimpleAssertion:
    level: Level
    text: str

    def check(self, result: Result):
        successful = any(diagnostic.message == self.text for diagnostic in result.diagnostics[self.level])
        if not successful:
            # print(result.diagnostics)
            print(result.stdout)
            print(result.stderr)
        return successful

    def __repr__(self):
        return f"REQUIRE {self.level.name}: {self.text}"


@dataclass
class RegexAssertion:
    level: Level
    pattern: re.Pattern

    def __post_init__(self):
        # compile patterns to speed up matching
        if isinstance(self.pattern, str):
            self.pattern = re.compile(self.pattern)

    def check(self, result: Result):
        successful = any(re.match(self.pattern, diagnostic.message) for diagnostic in result.diagnostics[self.level])
        if not successful:
            print(result.stdout)
            print(result.stderr)
        return successful

    def __repr__(self):
        return f"REQUIRE {self.level.name} MATCHES: {self.pattern!s}"
