from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional


class Level(Enum):
    note = "note"
    warning = "warning"
    error = "error"
    fatal_error = "fatal error"
    # ice = auto() # TODO


@dataclass
class SourceLocation:
    path: Path
    line: Optional[int] = None
    column: Optional[int] = None


@dataclass
class Diagnostic:
    message: str
    source_location: Optional[SourceLocation] = None
    error_code: Optional[str] = None  # MSVC specific


@dataclass
class Report:
    name: str
    command: str
    returncode: int
    stdout: str
    stderr: str
    start_time: int
    end_time: int

    diagnostics: defaultdict[Level, list[Diagnostic]] = field(default_factory=lambda: defaultdict(list))

    def extend(self, diagnostics: Iterable[tuple[Level, Diagnostic]]):
        for level, diagnostic in diagnostics:
            self.diagnostics[level].append(diagnostic)

    @property
    def elapsed(self):
        return self.end_time - self.start_time

    @property
    def elapsed_ms(self):
        return self.elapsed / 1e6

    @property
    def elapsed_s(self):
        return self.elapsed / 1e9
