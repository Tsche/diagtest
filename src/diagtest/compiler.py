from collections import defaultdict
import re

from abc import ABC, abstractmethod
from functools import cache
from operator import attrgetter
from pathlib import Path
from typing import Any, Iterable, Optional, Type

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from diagtest.report import Diagnostic, Level, SourceLocation
from diagtest.util import Result, which, remove_duplicates, run


class CompilerInfo:
    __slots__ = "executable", "languages", "version", "target"

    def __init__(self, executable: Path, languages: list[str], version: str | Version, target: Optional[str] = None):
        self.executable: Path = executable
        self.languages: list[str] = languages
        self.version = version if isinstance(version, Version) else Version(version)
        self.target: Optional[str] = target

    def dump(self) -> dict[str, Any]:
        info = {'executable': self.executable,
                'version': self.version}
        if self.target:
            info['target'] = self.target

        info['languages'] = self.languages
        return info

    def __str__(self):
        return str(self.dump())

    @property
    def version_string(self):
        ret = str(self.version)
        if self.target:
            ret += f" {self.target}"
        return ret

    def has_executable(self, executable: Path):
        return self.executable == executable

    def has_language(self, language: str):
        return language in self.languages

    def has_version(self, specifier: SpecifierSet):
        return self.version in specifier

    def has_target(self, query: str | re.Pattern):
        if self.target is None:
            return False

        if isinstance(query, str):
            return query == self.target
        elif isinstance(query, re.Pattern):
            return re.match(query, self.target)
        raise RuntimeError("Query must be string or regex pattern")


class CompilerCollection(list[CompilerInfo]):
    def __getattr__(self, attr: str):
        """ Filter by arbitrary attribute.
        This assumes CompilerInfo has been subclassed and provides a method prefixed with has_
        to determine if any compilers match the search query
        """
        if not attr.startswith('by_'):
            # Ignore other unknown attributes
            return None

        def apply_filter(query: Any):
            nonlocal attr
            filtered_compilers: list[CompilerInfo] = []
            for compiler in self:
                check = getattr(compiler, attr.replace('by_', 'has_'), None)
                if not check:
                    continue

                if check(query):
                    filtered_compilers.append(compiler)

            return CompilerCollection(filtered_compilers)

        return apply_filter

    @property
    def executables(self):
        return [compiler.executable for compiler in self]


class ProcessedResult(Result):
    def __init__(self, result: Result, name: str, compiler: CompilerInfo):
        super().__init__(result.command, result.returncode, result.stdout, result.stderr, result.start_time, result.end_time)
        self.name = name
        self.compiler = compiler
        # TODO Level should be an open set. Replace with str
        self.diagnostics: dict[Level, list[Diagnostic]] = defaultdict(list)

    def extend(self, diagnostics: Iterable[tuple[Level, Diagnostic]]):
        for level, diagnostic in diagnostics:
            self.diagnostics[level].append(diagnostic)


class Compiler(ABC):
    def __init__(
        self,
        /, *,
        language: str = "",
        executable: Optional[Path] = None,
        version: Optional[SpecifierSet | str] = None,
        target: Optional[str | re.Pattern] = None,
        args: Optional[list[str]] = None
    ):
        self.options = args or []

        assert hasattr(type(self), "languages"), "Compiler definition lacks languages attribute"
        if language not in getattr(self, "languages", []):
            raise RuntimeError(f"Cannot run compiler {self!s} in language mode {language}")
        self.language = language

        assert hasattr(self, "diagnostic_pattern"), "Compiler definition lacks a diagnostic pattern"
        self.diagnostic_pattern = getattr(self, 'diagnostic_pattern')  # hack to make mypy happy
        if isinstance(self.diagnostic_pattern, str):
            # compile the pattern if it hasn't yet happened
            self.diagnostic_pattern = re.compile(self.diagnostic_pattern)

        if executable:
            self.compilers = CompilerCollection([self.get_info(executable)])
        else:
            discovered_paths = self.discover()
            compiler_paths = discovered_paths[self.language] if isinstance(discovered_paths, dict) else discovered_paths
            self.compilers = CompilerCollection(self.get_info(path) for path in compiler_paths)

        if version is not None:
            version = SpecifierSet(version) if isinstance(version, str) else version
            self.compilers = self.compilers.by_version(version)

        if target is not None:
            self.compilers = self.compilers.by_target(target)

    def __call__(self, language: Optional[str] = None, args: Optional[list[str]] = None, **kwargs):
        return type(self)(language=language or self.language, args=args or self.options, **kwargs)

    @classmethod
    def __init_subclass__(cls, **kwargs):
        if cls not in compilers and hasattr(cls, 'languages'):
            compilers.append(cls)
        super().__init_subclass__(**kwargs)

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

    def get_name(self, info: CompilerInfo):
        name = type(self).__name__
        target_str = f"{info.target} " if info.target else ""
        return f"{target_str}{name} ({info.version})"

    def execute(self, name: str, compiler: CompilerInfo, source_file: Path,
                extra_args: Optional[list[str]] = None, env: Optional[dict[str, str]] = None) -> ProcessedResult:

        result = run([str(compiler.executable.resolve()),
                      # TODO select language if needed
                      *self.get_compile_options(),
                      *(extra_args or []),
                      str(source_file.resolve())], env=env)

        processed = ProcessedResult(result, name, compiler)
        processed.extend(self.extract_diagnostics(result.stderr))
        processed.extend(self.extract_diagnostics(result.stdout))
        return processed

    def run_test(self, source_file: Path, test: str):
        for compiler in self.compilers:
            yield self.execute(self.get_name(compiler), compiler, source_file, [self.select_test(test)])

    @classmethod
    @cache
    def discover(cls) -> list[Path] | dict[str | tuple[str, ...], list[Path]]:
        assert hasattr(cls, 'executable_pattern'), "Auto discovery failed. Compiler definition lacks executable_pattern"
        executable_pattern = getattr(cls, 'executable_pattern')
        if isinstance(executable_pattern, dict):
            # alternatives for various languages
            return {language: remove_duplicates(which(pattern))
                    for language, pattern in executable_pattern.items()}
        return remove_duplicates(which(executable_pattern))

    @staticmethod
    @abstractmethod
    def select_language(language: str):
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def select_test(test: str):
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def get_version(path: Path) -> Version | str:
        raise NotImplementedError()

    @staticmethod
    def get_target(path: Path) -> Optional[str]:
        return None

    @classmethod
    def get_info(cls, path: Path) -> CompilerInfo:
        assert hasattr(cls, "languages"), "Compiler definition lacks languages attribute"
        return CompilerInfo(executable=path,
                            languages=getattr(cls, "languages"),
                            version=cls.get_version(path),
                            target=cls.get_target(path))

    def get_compile_options(self):
        options = self.options or []
        if language := self.select_language(self.language):
            options.append(language)
        return options

    def get_alternative(self, path: Path) -> Path:
        return path

    def __str__(self):
        name = type(self).__name__
        versions = ", ".join(str(compiler.version) for compiler in sorted(self.compilers, key=attrgetter('version')))
        return f"{name} ({versions})" if versions else name

    def __or__(self, other):
        if isinstance(other, (list, Collection)):
            other.append(self)
            return other
        return Collection([self, other])

    @property
    def available(self):
        return len(self.compilers) != 0


class Collection(list[Compiler]):
    def __or__(self, other):
        if isinstance(other, (list, Collection)):
            self.extend(other)
        else:
            self.append(other)
        return self

    def run_test(self, file: Path, test_id: str):
        for compiler in self:
            yield compiler.run_test(file, test_id)

    @property
    def available(self):
        return len(self) != 0

    def __hash__(self):
        return hash(iter(self))

    def __str__(self):
        if len(self) == 1:
            return str(self[0])

        return f"[{', '.join(str(data) for data in self)}]"


compilers: list[Type[Compiler]] = []
