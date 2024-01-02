import re
import shutil
from pathlib import Path
from functools import cache

from diagtest.compilers.multilingual import MultilingualCompiler, Language
from diagtest.compilers.gcc import GCC
from diagtest.compiler import run

class Clang(MultilingualCompiler):
    executable = "clang"
    diagnostic_pattern = GCC.diagnostic_pattern

    def __init__(self, language: Language, *args, **kwargs):
        self.executable = "clang++" if language.is_cpp else "clang"
        super().__init__(language, *args, **kwargs)

    @staticmethod
    @cache
    def get_version(compiler: Path):
        # invoke clang --version
        result = run([str(compiler), "--version"])
        version: dict[str, str] = {}
        for match in re.finditer(GCC.version_pattern, result.stdout):
            version |= {k: v for k, v in match.groupdict().items() if v}
        return version

    standard_pattern = re.compile(r"use '(?P<standard>[^']+)'")
    standard_alias_pattern = re.compile(r"(( or|,) '(?P<alias>[^']+))")

    @staticmethod
    def get_standards_raw(compiler, language: str):
        result = run([str(compiler), f'-x{language}', '-std=dummy', '-'])
        for line in result.stderr.splitlines():
            standard_match = re.search(Clang.standard_pattern, line)
            if standard_match is None:
                continue
            standard = standard_match['standard']
            aliases = [match['alias'] for match in Clang.standard_alias_pattern.finditer(line)]
            yield standard, *aliases

    @staticmethod
    def filter_gnu(compiler, language: str):
        gnu_name = f'gnu{language[1:]}'
        result: dict[str, list[tuple[str, ...]]] = {gnu_name: [], language: []}
        for standard in Clang.get_standards_raw(compiler, language):
            is_gnu = any(name.startswith('gnu') for name in standard)
            result[gnu_name if is_gnu else language].append(standard)
        return result

    @staticmethod
    @cache
    def get_supported_standards(compiler: Path):
        return {Language(key): value
                for key, value in {
                    **Clang.filter_gnu(compiler, 'c'),
                    **Clang.filter_gnu(compiler, 'c++')}.items()}

    @staticmethod
    @cache
    def discover():
        default = shutil.which('clang')
        version = Clang.get_version(default)
        standards = Clang.get_supported_standards(default)
        return {default: {'version': version['version'], 'target': version['target'], 'standards': standards}}
