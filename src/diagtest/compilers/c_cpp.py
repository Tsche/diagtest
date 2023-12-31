import re

from enum import Enum
from typing import Optional
from pathlib import Path
from diagtest.compiler import Compiler, run


class Language(Enum):
    C = 'c'
    GNU_C = 'gnu'
    CPP = 'c++'
    GNU_CPP = 'gnu++'

    @property
    def is_cpp(self):
        return self in (Language.CPP, Language.GNU_CPP)


def filter_standards(standards, query: str):
    greater = query[0] == '>'
    include = query[1] == '='
    version = query[1 + include:]

    index = standards.index(int(version) if version.isnumeric() else version)
    index += include ^ greater
    return standards[index:] if greater else standards[:index]


standard_query = str | int | list[int | str] | tuple[str, str]


class MultilingualCompiler(Compiler):
    def __init__(self, language: Language, *args, std: Optional[standard_query] = None, **kwargs):
        self.language = language
        self.standards: dict[Language, list[int | str]] = getattr(self, "standards", {})  # make mypy happy
        self.selected_standards = self.standards[self.language] if std is None else self.get_standards(std)
        super().__init__(*args, **kwargs)

    def __call__(self, language: Optional[Language] = None, std: Optional[standard_query] = None, # type: ignore[override]
                 options: Optional[list[str]] = None, executable: Optional[Path | str] = None):
        return type(self)(language=language or self.language,
                          std=std or self.selected_standards,
                          options=options or self.options,
                          executable=executable or self.compiler)

    def get_standards(self, query: standard_query):
        if isinstance(query, list):
            return query

        if isinstance(query, tuple):
            assert len(query) == 2, "Only a 2-tuple to specify range is allowed"
            assert query[0][0] == '>' and query[1][0] == '<', "Specify ranges as ('>minimum', '<maximum')"
            return filter_standards(filter_standards(self.standards[self.language], query[0]), query[1])

        if isinstance(query, int):
            return [query]

        if query.startswith(('>', '<')):
            return filter_standards(self.standards[self.language], query)

        return [query]

    def execute(self, file: Path, test_id: str):
        for standard in self.selected_standards:
            print(f"    Standard {self.language.value}{standard}", end='')
            yield self.compile(file, [f"-std={self.language.value}{standard}", *(self.options or []), f"-D{test_id}"])


class GCC(MultilingualCompiler):
    diagnostic_pattern = r"^((?P<path>[a-zA-Z0-9:\/\\\.]*?):((?P<line>[0-9]+):)?((?P<column>[0-9]+):)? )"\
                         r"?((?P<level>error|warning|note): )(?P<message>.*)$"

    standards = {
        Language.C: [89, 99, 11, 17, 23],
        Language.GNU_C: [89, 99, 11, 17, 23],
        Language.CPP: [98, '03', 11, 14, 17, 20, 23, 26],
        Language.GNU_CPP: [98, '03', 11, 14, 17, 20, 23, 26]
    }

    def __init__(self, language: Language, *args, **kwargs):
        self.executable = "g++" if language.is_cpp else "gcc"
        super().__init__(language, *args, **kwargs)

    def get_version(self):
        ...

    @staticmethod
    def get_standards_raw():
        search_pattern = re.compile(r"^\s+-std=(?P<standard>[^\s]+)[\s]*(Conform.*((C|C\+\+)( draft)? standard)).*?((-std=(?P<alias>[^\s\.]+))|\.$)")
        # invoke gcc -v --help
        result = run(["gcc", "-v", "--help"])
        for line in result.stdout.splitlines():
            match = re.match(search_pattern, line)
            if match is None:
                continue
            standard = match['standard']
            if alias := match['alias']:
                yield standard, alias
            else:
                yield (standard,)

    @staticmethod
    def get_supported_standards():
        result: dict[str, list[tuple[str, ...]]] = {'c': [], 'c++': [], 'gnu': [], 'gnu++': []}
        for standard in GCC.get_standards_raw():
            is_gnu = any(name.startswith('gnu') for name in standard)
            is_cpp =  any('++' in name for name in standard)
            suffix = '++' if is_cpp else ''
            result[f'gnu{suffix}' if is_gnu else f'c{suffix}'].append(standard)

        return result

class Clang(MultilingualCompiler):
    executable = "clang"
    diagnostic_pattern = GCC.diagnostic_pattern

    standards = {
        Language.C: [89, 99, 11, 17, 23],
        Language.GNU_C: [89, 99, 11, 17, 23],
        Language.CPP: [98, '03', 11, 14, 17, 20, 23, '2c'],
        Language.GNU_CPP: [98, '03', 11, 14, 17, 20, 23, '2c']
    }

    def __init__(self, language: Language, *args, **kwargs):
        self.executable = "clang++" if language.is_cpp else "clang"
        super().__init__(language, *args, **kwargs)

    def get_version(self):
        ...

    standard_pattern = re.compile(r"use '(?P<standard>[^']+)'")
    standard_alias_pattern = re.compile(r"(( or|,) '(?P<alias>[^']+))")

    @staticmethod
    def get_standards_raw(language: str):
        result = run(['clang', f'-x{language}', '-std=dummy', '-'])
        for line in result.stderr.splitlines():
            standard_match = re.search(Clang.standard_pattern, line)
            if standard_match is None:
                continue
            standard = standard_match['standard']
            aliases = [match['alias'] for match in Clang.standard_alias_pattern.finditer(line)]
            yield standard, *aliases

    @staticmethod
    def filter_gnu(language: str):
        gnu_name = f'gnu{language[1:]}'
        result: dict[str, list[tuple[str, ...]]] = {gnu_name: [], language: []}
        for standard in Clang.get_standards_raw(language):
            is_gnu = any(name.startswith('gnu') for name in standard)
            result[gnu_name if is_gnu else language].append(standard)
        return result


    @staticmethod
    def get_supported_standards():
        return {**Clang.filter_gnu('c'),
                **Clang.filter_gnu('c++')}
        # invoke clang -xc -std=dummy -
        # invoke clang -xc++ -std=dummy -

class MSVC(MultilingualCompiler):
    platform = "Windows"
    executable = "cl"
    diagnostic_pattern = r"^((?P<path>[a-zA-Z0-9:\/\\\.]*?)\((?P<line>[0-9]+)\): )"\
                         r"((?P<level>fatal error|error|warning) )((?P<error_code>[A-Z][0-9]+): )(?P<message>.*)$"
    standards = {
        Language.C: [11, 17, 'latest'],
        Language.CPP: [14, 17, 20, 'latest']
    }


defaults = {
    'c': {'gcc': GCC(Language.C), 'clang': Clang(Language.C), 'msvc': MSVC(Language.C)},
    'c++': {'gcc': GCC(Language.CPP), 'clang': Clang(Language.CPP), 'msvc': MSVC(Language.CPP)}
}

if __name__ == "__main__":
    print(GCC.get_supported_standards())
