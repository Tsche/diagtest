import re
from pathlib import Path
from functools import cache
from collections import defaultdict
from contextlib import suppress

from diagtest.dialect import DialectCompiler, Dialect
from diagtest.util import run


class GCC(DialectCompiler):
    languages = 'c', 'c++', 'gnu', 'gnu++'
    diagnostic_pattern = r"^((?P<path>.*?):((?P<line>[0-9]+):)?((?P<column>[0-9]+):)? )?"\
                         r"((?P<level>error|warning|note): )(?P<message>.*)$"

    version_pattern = re.compile(r"((Target: (?P<target>.*))|(Thread model: (?P<thread_model>.*))|"
                                 r"((gcc|clang) version (?P<version>[0-9\.]+)))")

    gcc_pattern = r"^gcc(-[0-9]+)?(\.exe|\.EXE)?$"
    gcc_cpp_pattern = r"^g\+\+(-[0-9]+)?(\.exe|\.EXE)?$"

    executable_pattern: str | dict[str, str] = {
        'c': gcc_pattern,
        'gnu': gcc_pattern,
        'c++': gcc_cpp_pattern,
        'gnu++': gcc_cpp_pattern
        #'fortran': r"^gfortran(-[0-9]+)?(\.exe|\.EXE)?$" # TODO
    }

    @staticmethod
    def select_language(language: str):
        return None

    @staticmethod
    def select_dialect(dialect: str):
        return f"-std={dialect}"

    @staticmethod
    def select_test(test: str):
        return f"-D{test}"

    @staticmethod
    def include(directory: Path):
        return f"-I{directory.absolute()!s}"

    @staticmethod
    @cache
    def _query_version(path: Path) -> dict[str, str]:
        # invoke gcc -v --version
        result = run([str(path), "-v", "--version"])
        version: dict[str, str] = {}
        for source in result.stderr, result.stdout:
            for match in re.finditer(GCC.version_pattern, source):
                version |= {k: v for k, v in match.groupdict().items() if v}
        return version

    @staticmethod
    @cache
    def _get_supported_dialects(path: Path):
        search_pattern = re.compile(r"-std=(?P<standard>[^\s]+)[\s]*(Conform.*((C|C\+\+)( draft)? standard))"
                                    r"((.|(\n    )\s+)*Same.as(.|(\n    )\s+)*-std=(?P<alias>[^\. ]+))?")
        standards = defaultdict(list)
        # invoke gcc -v --help
        result = run([str(path), "-v", "--help"])
        for match in search_pattern.finditer(result.stdout):
            standard = match['standard']
            if alias := match['alias']:
                standards[alias].append(standard)
            else:
                standards[standard].append(standard)
        return [Dialect(standard, [alias for alias in aliases if alias != standard])
                for standard, aliases in standards.items()]

    @classmethod
    @cache
    def get_supported_dialects(cls, path: Path):
        result: dict[str, list[Dialect]] = defaultdict(list)
        for standard in cls._get_supported_dialects(path):
            is_gnu = any(name.startswith('gnu') for name in standard)
            is_cpp = any('++' in name for name in standard)
            suffix = '++' if is_cpp else ''
            result[f'gnu{suffix}' if is_gnu else f'c{suffix}'].append(standard)

        # GCC developers in their infinite wisdom decided to not list C standards in order
        # at least it is in order for both centuries, so do a little swapping here
        for language in 'c', 'gnu':
            standards = result[language]
            if not standards:
                continue

            idx = next(idx for idx, standard in enumerate(standards) if '9' in standard.name)
            last_century = standards[idx:]

            if language == 'c':
                with suppress(StopIteration):
                    # iso9899:199409 is discovered after c99, but 1994 was before 1999
                    index_iso94 = next(idx for idx, standard in enumerate(last_century) if 'iso9899:199409' in standard)
                    index_c99 = next(idx for idx, standard in enumerate(last_century) if 'c99' in standard)
                    assert index_iso94 > index_c99, "Standards discovered in order. Please open an issue!"
                    last_century[index_c99], last_century[index_iso94] = last_century[index_iso94], last_century[index_c99]
            result[language] = [*last_century, *standards[:idx]]

        return result

    @classmethod
    def get_version(cls, path: Path) -> str:
        info = cls._query_version(path)
        assert 'version' in info, "Automatic version detection failed"
        return info['version']

    @classmethod
    def get_target(cls, path: Path) -> str | None:
        info = cls._query_version(path)
        return info.get('target')

    alternative_needle = 'gcc'
    alternative_replacement = {'c': 'gcc', 'gnu': 'gcc', 'c++': 'g++', 'gnu++': 'g++'}

    def get_alternative(self, path: Path):
        if self.language not in self.alternative_replacement:
            return path

        replacement = path.with_name(path.name.replace(self.alternative_needle,
                                                       self.alternative_replacement[self.language]))
        return replacement if replacement.exists() else path

    def has_alternative(self) -> bool:
        return self.language not in self.alternative_replacement
