import subprocess
import platform
import shutil
import re

from pathlib import Path
from abc import ABC
from collections import UserList, defaultdict
from typing import Optional, Iterable
from dataclasses import dataclass, field
from enum import Enum


class Collection(UserList):
    def __or__(self, other):
        if isinstance(other, (list, Collection)):
            self.extend(other)
        else:
            self.append(other)
        return self

    def compile(self, file: Path, args: list[str] = None):
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
class Result:
    returncode: int
    stdout: str
    stderr: str

    diagnostics: defaultdict[Level, list[Diagnostic]] = field(default_factory=lambda: defaultdict(list))

    def extend(self, diagnostics: Iterable[tuple[Level, Diagnostic]]):
        for level, diagnostic in diagnostics:
            self.diagnostics[level].append(diagnostic)


class Compiler(ABC):
    def __init__(
        self,
        standards: list[str],
        options: list[str] = None,
        executable: Optional[Path | str] = None,
    ):
        self.standards = standards
        self.options = options
        self.executable = Path(executable or shutil.which(self.default_executable))

        if isinstance(self.diagnostic_pattern, str):
            # compile the pattern if it hasn't yet happened
            self.diagnostic_pattern = re.compile(self.diagnostic_pattern)

    @property
    def configurations(self):
        return [[f"-std={standard}", *(self.options or [])] for standard in self.standards]

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
            diagnostic = Diagnostic(parts["message"], source_location, parts.get("error_code", None))
            yield level, diagnostic

    def compile(self, file: Path, args: list[str]) -> str:
        print(" ".join([str(self.executable), *args, str(file)]))
        return subprocess.run(
            [str(self.executable), *args, str(file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )

    def execute(self, file: Path, test_id: str):
        for config in self.configurations:
            result = self.compile(file, [*config, f"-D{test_id}"])
            result = Result(result.returncode, result.stdout, result.stderr)
            result.extend(self.extract_diagnostics(result.stderr))
            result.extend(self.extract_diagnostics(result.stdout))
            yield result

    def __or__(self, other):
        if isinstance(other, (list, Collection)):
            other.append(self)
            return other
        return Collection([self, other])

    def __str__(self):
        return type(self).__name__


class GCC(Compiler):
    default_executable = "gcc"
    diagnostic_pattern = "^((?P<path>[a-zA-Z0-9:\/\\\.]*?):((?P<line>[0-9]+):)?((?P<column>[0-9]+):)? )?((?P<level>error|warning|note): )(?P<message>.*)$"


class Clang(GCC):
    default_executable = "clang"


class MSVC(Compiler):
    diagnostic_pattern = "^((?P<path>[a-zA-Z0-9:\/\\\.]*?)\((?P<line>[0-9]+)\): )((?P<level>fatal error|error|warning) )((?P<error_code>[A-Z][0-9]+): )(?<message>.*)$"

    def do_compile(self, file: Path, args: list[str]) -> str:
        if platform.system() != "Windows":
            raise RuntimeError("Cannot compile. MSVC is only available on Windows")
