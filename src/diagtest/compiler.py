import subprocess
import re
import time
import logging

from pathlib import Path
from abc import ABC, abstractmethod
from collections import UserList, defaultdict
from typing import Optional, Iterable, Type
from dataclasses import dataclass, field
from enum import Enum
from functools import cache

from packaging.version import Version
from packaging.specifiers import SpecifierSet

from diagtest.util import find_executables

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

    def execute(self, file: Path, test_id: str):
        for compiler in self.data:
            yield from compiler.execute(file, test_id)

    @property
    def available(self):
        return len(self.data) != 0

    def __hash__(self):
        return hash(iter(self))

    def __str__(self):
        if len(self.data) == 1:
            return str(self.data[0])

        compilers = ', '.join(str(data) for data in self.data)
        return f"[{compilers}]"

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

def run(command: list[str]|str, env: Optional[dict[str, str]] = None):
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
        env=env
    )


class Compiler(ABC):
    def __init__(
        self,
        executable: Path,
        options: Optional[list[str]] = None,
        **_ # ignore excess keyword arguments
    ):
        self.options = options or []
        self.compiler = executable
        self.diagnostic_pattern = getattr(self, 'diagnostic_pattern')  # hack to make mypy happy
        assert self.diagnostic_pattern is not None, "Compiler definition lacks a diagnostic pattern"

        if isinstance(self.diagnostic_pattern, str):
            # compile the pattern if it hasn't yet happened
            self.diagnostic_pattern = re.compile(self.diagnostic_pattern)

    def __call__(self, options: Optional[list[str]] = None, executable: Optional[Path] = None):
        return type(self)(options=options or self.options, executable=executable or self.compiler)

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
        raise NotImplementedError()

    def __or__(self, other):
        if isinstance(other, (list, Collection)):
            other.append(self)
            return other
        return Collection([self, other])

    def __str__(self):
        return type(self).__name__

    @property
    def available(self):
        return True

@dataclass
class CompilerInfo:
    executable: Path
    version: Version
    target: str

class CompilerCollection(UserList[CompilerInfo]):
    def by_version(self, specifier: SpecifierSet):
        for compiler in self.data:
            if compiler.version in specifier:
                yield compiler

    def by_target(self, target: str | re.Pattern):
        def matches(compiler):
            if isinstance(target, str):
                return compiler.target == target
            elif isinstance(target, re.Pattern):
                return re.match(target, compiler.target)
            raise RuntimeError("Target must be string or regex pattern")

        for compiler in self.data:
            if matches(compiler):
                yield compiler

    def by_executable(self, executable: Path):
        for compiler in self.data:
            if compiler.executable == executable:
                yield compiler

class VersionedCompiler(Compiler):
    def __new__(cls: Type['VersionedCompiler'],
                executable: Optional[Path] = None,
                options: Optional[list[str]] = None,
                version: Optional[SpecifierSet | str] = None,
                target: Optional[str | re.Pattern] = None,
                **kwargs):
        def init(binary: Path):
            nonlocal options
            obj = object.__new__(cls)
            cls.__init__(obj, executable=binary, options=options, **kwargs)
            return obj

        if executable is not None:
            return init(executable)

        compilers = CompilerCollection(cls.discover())
        if version is not None:
            version = SpecifierSet(version) if isinstance(version, str) else version
            compilers = CompilerCollection(compilers.by_version(version))
        if target is not None:
            compilers = CompilerCollection(compilers.by_target(target))

        return Collection([init(compiler.executable) for compiler in compilers])

    @classmethod
    @cache
    def discover(cls):
        assert hasattr(cls, 'executable_pattern')
        assert hasattr(cls, 'get_version')
        compilers: list[CompilerInfo] = []
        for executable in find_executables(getattr(cls, 'executable_pattern')):
            version = getattr(cls, 'get_version')(executable)
            if 'version' not in version or 'target' not in version:
                logging.warning("Invalid compiler: %s", executable)
                continue
            compilers.append(CompilerInfo(executable, version['version'], version['target']))

        return compilers

    @staticmethod
    @abstractmethod
    def get_version(path: Path):
        raise NotImplementedError()

    def __str__(self):
        version = self.get_version(self.compiler)
        return f"{super().__str__()} ({version['version']}, {version['target']})"
