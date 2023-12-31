import subprocess
import platform as platform_info
import shutil
import re
import time


from pathlib import Path
from abc import ABC
from collections import UserList, defaultdict
from typing import Optional, Iterable
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache


class Collection(UserList):
    def __or__(self, other):
        if isinstance(other, (list, Collection)):
            self.extend(other)
        else:
            self.append(other)
        return self

    def compile(self, file: Path, args: Optional[list[str]] = None):
        for compiler in self.data:
            yield from compiler.compile(file, args)


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


@lru_cache(maxsize=None)
def which(name: str | None):
    if name is None:
        return

    result = shutil.which(name)
    if result is not None:
        return Path(result)


def find_executable(executable: Optional[Path | str] = None, default: Optional[str] = None):
    if isinstance(executable, Path):
        return executable
    return which(executable or default)


def run(command: list[str]):
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False
    )


class Compiler(ABC):
    def __init__(
        self,
        options: Optional[list[str]] = None,
        executable: Optional[Path | str] = None
    ):
        self.options = options or []
        self.compiler = find_executable(executable, getattr(self, 'executable'))
        self.diagnostic_pattern = getattr(self, 'diagnostic_pattern')  # hack to make mypy happy
        assert self.diagnostic_pattern is not None, "Compiler definition lacks a diagnostic pattern"

        if isinstance(self.diagnostic_pattern, str):
            # compile the pattern if it hasn't yet happened
            self.diagnostic_pattern = re.compile(self.diagnostic_pattern)

    def __call__(self, options: Optional[list[str]] = None, executable: Optional[Path | str] = None):
        return type(self)(options=options or self.options, executable=executable or self.compiler)

    @property
    def available(self):
        if (platform := getattr(self, 'platform', None)) is not None:
            if platform_info.system() != platform:
                return False
        return self.compiler is not None

    def extract_diagnostics(self, lines):
        for line in lines.splitlines():
            diagnostic = re.match(self.diagnostic_pattern, line)
            if not diagnostic:
                continue

            parts = diagnostic.groupdict()
            source_location = (
                SourceLocation(
                    parts["path"],
                    parts.get("line", None),
                    parts.get("column", None),
                )
                if "path" in parts
                else None
            )
            level = Level(parts["level"])
            yield level, Diagnostic(parts["message"], source_location, parts.get("error_code", None))

    def compile(self, file: Path | str, args: list[str]) -> Report:
        command = [str(self.compiler), *args, str(file)]

        start_time = time.monotonic_ns()
        raw_result = run(command)
        end_time = time.monotonic_ns()

        result = Report(
            command=' '.join(command),
            returncode=raw_result.returncode,
            stdout=raw_result.stdout,
            stderr=raw_result.stderr,
            start_time=start_time,
            end_time=end_time)
        result.extend(self.extract_diagnostics(result.stderr))
        result.extend(self.extract_diagnostics(result.stdout))
        return result

    def execute(self, file: Path, test_id: str):
        yield self.compile(file, [*(self.options or []), f"-D{test_id}"])

    def __or__(self, other):
        if isinstance(other, (list, Collection)):
            other.append(self)
            return other
        return Collection([self, other])

    def __str__(self):
        return type(self).__name__
