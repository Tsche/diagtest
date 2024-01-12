from dataclasses import dataclass
from typing import Optional, Any
from pathlib import Path
from abc import abstractmethod

from diagtest.compiler import Compiler, CompilerInfo
from diagtest.util import remove_duplicates


DialectQuery = str | int | list[int | str] | tuple[str, str]

@dataclass
class Dialect:
    name: str
    aliases: Optional[list[str]] = None

    def __str__(self):
        name = self.name
        if self.aliases:
            name += f" ({', '.join(self.aliases)})"
        return name

    def __iter__(self):
        yield self.name
        if self.aliases is not None:
            yield from self.aliases

class DialectInfo(CompilerInfo):
    __slots__ = ["dialects"]

    def __init__(self, dialects: dict[str, Dialect], **kwargs):
        # map of language -> list of supported dialects (and their aliases)
        self.dialects: dict[str, Dialect] = dialects
        super().__init__(**kwargs)

    def dump(self) -> dict[str, Any]:
        info = super().dump()
        info['dialects'] = self.dialects
        return info

    def expand_dialect(self, language: str, dialect: str | int):
        if isinstance(dialect, str) and self.has_dialect(dialect):
            return dialect

        expanded = f"{language}{dialect}"
        if self.has_dialect(expanded):
            return expanded

        raise RuntimeError(f"Standard {expanded} not found in available dialects")

    def filter_dialects(self, language: str, query: str, dialects=None):
        if dialects is None:
            dialects = self.dialects[language]

        greater = query[0] == '>'
        include = query[1] == '='
        version = self.expand_dialect(language, query[1 + include:])
        try:
            index = next(idx for idx, dialect in enumerate(dialects) if version in dialect)
            index += include ^ greater
            return dialects[index:] if greater else dialects[:index]
        except StopIteration as e:
            raise RuntimeError(f"Could not find value {version} in {dialects}") from e

    def get_dialects(self, language: str, query: Optional[DialectQuery] = None):
        def flatten(dialects):
            return remove_duplicates([dialect.name for dialect in dialects])

        if query is None:
            # get the primary version aliases
            return flatten(self.dialects[language])

        if isinstance(query, list):
            return remove_duplicates([self.expand_dialect(language, dialect) for dialect in query])

        if isinstance(query, tuple):
            assert len(query) == 2, "Only a 2-tuple to specify range is allowed"
            assert query[0][0] == '>' and query[1][0] == '<', "Specify ranges as ('>minimum', '<maximum')"
            return flatten(self.filter_dialects(language, query[1], self.filter_dialects(language, query[0])))

        if isinstance(query, int):
            return [self.expand_dialect(language, query)]

        if query.startswith(('>', '<')):
            return flatten(self.filter_dialects(language, query))

        query = self.expand_dialect(language, query)
        if any(query in aliases for aliases in self.dialects[language]):
            return [query]
        return []

    def has_dialect(self, query: str):
        return any(query in dialect
        for dialects in self.dialects.values()
        for dialect in dialects)


class DialectCompiler(Compiler):
    def __init__(self, language: str, dialect: Optional[dict[CompilerInfo, list[str]] | DialectQuery] = None, **kwargs):
        super().__init__(language=language, **kwargs)
        if isinstance(dialect, dict):
            self.dialects = dialect
        else:
            self.dialects = {}
            for compiler in self.compilers:
                assert isinstance(compiler, DialectInfo)
                self.dialects[compiler] = compiler.get_dialects(language, dialect)

    def __call__(self, language: Optional[str] = None, dialect: Optional[dict[CompilerInfo, list[str]] | DialectQuery] = None,  # type: ignore[override]
                 options: Optional[list[str]] = None, executable: Optional[Path | str] = None):
        return type(self)(language=language or self.language,
                          dialect=dialect or self.dialects,
                          options=options or self.options,
                          executable=executable or self.compilers)

    def has_dialect(self, path: Path, dialect: str):
        info = self.get_info(path)
        return info.has_dialect(dialect)

    def get_dialects(self, path: Path, query: Optional[DialectQuery] = None):
        info = self.get_info(path)
        return info.get_dialects(self.language, query)

    @staticmethod
    @abstractmethod
    def select_dialect(dialect: str):
        raise NotImplementedError

    def run_test(self, source_file: Path, test: str):
        for compiler, dialects in self.dialects.items():
            for dialect in dialects:
                name = f"{self.get_name(compiler)} ({dialect})"
                yield self.execute(name, compiler, source_file, [self.select_dialect(dialect), self.select_test(test)])

    @staticmethod
    @abstractmethod
    def get_supported_dialects(path: Path):
        raise NotImplementedError()

    @classmethod
    def get_info(cls, path: Path) -> DialectInfo:
        dialects = cls.get_supported_dialects(path)
        supported_languages = remove_duplicates([*getattr(cls, "languages", []), *dialects.keys()])
        return DialectInfo(dialects=dialects,
                           executable=path,
                           languages=supported_languages,
                           version=cls.get_version(path),
                           target=cls.get_target(path))
