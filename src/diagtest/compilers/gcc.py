import re
from pathlib import Path
from functools import cache
from collections import defaultdict
from contextlib import suppress

from diagtest.compilers.multilingual import MultilingualCompiler
from diagtest.compiler import run


class GCC(MultilingualCompiler):
    diagnostic_pattern = r"^((?P<path>[^:]*?):((?P<line>[0-9]+):)?((?P<column>[0-9]+):)? )"\
                         r"?((?P<level>error|warning|note): )(?P<message>.*)$"

    version_pattern = re.compile(r"((Target: (?P<target>.*))|(Thread model: (?P<thread_model>.*))|"
                                 r"((gcc|clang) version (?P<version>[0-9\.]+)))")
    executable_pattern = r"^gcc(-[0-9]+)?(\.exe|\.EXE)?$"

    def execute(self, file: Path, test_id: str):
        for standard in self.selected_standards:
            name = f"{str(self)} ({standard})"
            yield name, self.compile(file, [f"-std={standard}", *(self.options or []), f"-D{test_id}"])

    @staticmethod
    @cache
    def get_version(compiler: Path):
        # invoke gcc -v --version
        env = os.environ.copy()
        env['COLUMNS'] = 1024
        result = run([str(compiler), "-v", "--version"], env=env)
        version: dict[str, str] = {}
        for match in re.finditer(GCC.version_pattern, result.stderr):
            version |= {k: v for k, v in match.groupdict().items() if v}
        return version

    @staticmethod
    def get_standards_raw(compiler):
        search_pattern = re.compile(r"^\s+-std=(?P<standard>[^\s]+)[\s]*(Conform.*((C|C\+\+)( draft)? standard))"
                                    r".*?((-std=(?P<alias>[^\s\.]+))|(\.$))")
        standards = defaultdict(list)
        # invoke gcc -v --help
        result = run([str(compiler), "-v", "--help"])
        logging.error(result.stdout) #! TODO remove
        for line in result.stdout.splitlines():
            match = re.match(search_pattern, line)
            if match is None:
                continue
            standard = match['standard']
            if alias := match['alias']:
                standards[alias].append(standard)
            else:
                standards[standard].append(standard)
        return [(standard, *[alias for alias in aliases if alias != standard])
                for standard, aliases in standards.items()]

    @staticmethod
    @cache
    def get_supported_standards(compiler: Path):
        result: dict[str, list[tuple[str, ...]]] = defaultdict(list)
        for standard in GCC.get_standards_raw(compiler):
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

            idx = next(idx for idx, standard in enumerate(standards) if '9' in standard[0])
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
