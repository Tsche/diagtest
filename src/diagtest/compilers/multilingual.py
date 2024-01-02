from typing import Optional
from pathlib import Path

from diagtest.compiler import VersionedCompiler

standard_query = str | int | list[int | str] | tuple[str, str]
class MultilingualCompiler(VersionedCompiler):
    def __init__(self, language: str, std: Optional[standard_query] = None, **kwargs):
        self.language = language
        super().__init__(**kwargs)
        self.standards: dict[str, list[tuple[str, ...]]] = self.get_supported_standards(self.compiler)
        assert language in self.standards, f"No supported standards for language {language.name}"
        self.selected_standards = self.get_standards(std)

    def __call__(self, language: Optional[str] = None, std: Optional[standard_query] = None,  # type: ignore[override]
                 options: Optional[list[str]] = None, executable: Optional[Path | str] = None):
        return type(self)(language=language or self.language,
                          std=std or self.selected_standards,
                          options=options or self.options,
                          executable=executable or self.compiler)

    def has_standard(self, standard: str):
        return any(standard in aliases for aliases in self.standards[self.language])

    def expand_standard(self, standard: str | int):
        if not isinstance(standard, int) and self.has_standard(standard):
            return standard

        expanded = f"{self.language}{standard}"
        if self.has_standard(expanded):
            return expanded

        raise RuntimeError(f"Standard {standard} not found in available standards")

    def filter_standards(self, query: str, standards=None):
        if standards is None:
            standards = self.standards[self.language]

        greater = query[0] == '>'
        include = query[1] == '='
        version = self.expand_standard(query[1 + include:])
        try:
            index = next(idx for idx, standard in enumerate(standards) if version in standard)
            index += include ^ greater
            return standards[index:] if greater else standards[:index]
        except StopIteration as e:
            raise RuntimeError(f"Could not find value {version} in {standards}") from e

    def get_standards(self, query: Optional[standard_query]=None):
        def unique(standards):
            return [*{standard: None for standard in standards}.keys()]

        def flatten(standards):
            return unique([standard[0] for standard in standards])

        if query is None:
            # get the primary version aliases
            return flatten(self.standards[self.language])

        if isinstance(query, list):
            return unique([self.expand_standard(standard) for standard in query])

        if isinstance(query, tuple):
            assert len(query) == 2, "Only a 2-tuple to specify range is allowed"
            assert query[0][0] == '>' and query[1][0] == '<', "Specify ranges as ('>minimum', '<maximum')"
            return flatten(self.filter_standards(query[1], self.filter_standards(query[0])))

        if isinstance(query, int):
            return [self.expand_standard(query)]

        if query.startswith(('>', '<')):
            return flatten(self.filter_standards(query))

        return [self.expand_standard(query)]
