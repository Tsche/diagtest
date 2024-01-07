import re
from pathlib import Path
from functools import cache

from diagtest.compilers.gcc import GCC
from diagtest.dialect import Dialect
from diagtest.util import run

class Clang(GCC):
    languages = 'c', 'c++', 'gnu', 'gnu++'
    executable_pattern = r"^clang(-[0-9]+)?(\.exe|\.EXE)?$"

    standard_pattern = re.compile(r"use '(?P<standard>[^']+)'")
    standard_alias_pattern = re.compile(r"(( or|,) '(?P<alias>[^']+))")

    @staticmethod
    @cache
    def _get_supported_dialects(compiler, language: str):
        result = run([str(compiler), f'-x{language}', '-std=dummy', '-'])
        for line in result.stderr.splitlines():
            standard_match = re.search(Clang.standard_pattern, line)
            if standard_match is None:
                continue
            standard = standard_match['standard']
            aliases = [match['alias'] for match in Clang.standard_alias_pattern.finditer(line)]
            yield Dialect(standard, aliases)

    @staticmethod
    def filter_gnu(compiler, language: str):
        gnu_name = f'gnu{language[1:]}'
        result: dict[str, list[tuple[str, ...]]] = {gnu_name: [], language: []}
        for standard in Clang._get_supported_dialects(compiler, language):
            is_gnu = any(name.startswith('gnu') for name in standard)
            result[gnu_name if is_gnu else language].append(standard)
        return result

    @staticmethod
    @cache
    def get_supported_dialects(compiler: Path):
        return {**Clang.filter_gnu(compiler, 'c'),
                **Clang.filter_gnu(compiler, 'c++')}
