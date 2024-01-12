import re

from dataclasses import dataclass
from typing import Protocol, Optional
from diagtest.report import Level
from diagtest.util import Result

from diagtest.compiler import ProcessedResult


class Assertion(Protocol):
    def check(self, result: Result) -> bool:
        ...


class Message:
    def __init__(self, level: Level, text: Optional[str] = None, regex: Optional[str | re.Pattern] = None):
        self.regex = regex is not None
        self.text = re.compile(regex) if regex is not None else text
        self.level = level

    def check(self, result: ProcessedResult):
        def check_one(message):
            if self.regex:
                assert self.text is not None
                return re.match(self.text, message) is not None
            return self.text == message

        return any(check_one(diagnostic.message) for diagnostic in result.diagnostics[self.level])

    def __repr__(self):
        require = f"REQUIRE {self.level.name}"
        if self.regex:
            return f"{require} MATCHES {self.text.pattern if isinstance(self.text, re.Pattern) else str(self.text)}"
        return f"{require}: {str(self.text)}"

@dataclass(frozen=True)
class ReturnCode:
    expected: int

    def check(self, result: Result):
        return result.returncode == self.expected

    def __repr__(self):
        return f"RETURNS {self.expected}"

@dataclass(frozen=True)
class ErrorCode:
    expected: str

    def check(self, result: Result):
        return any(diagnostic.error_code is not None and diagnostic.error_code == self.expected
                    for diagnostics in result.diagnostics.values()
                    for diagnostic in diagnostics)

    def __repr__(self):
        return f"RAISES {self.expected}"
