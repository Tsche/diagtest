import shutil
import os
import re
import logging
import platform
from functools import cache
from pathlib import Path
from enum import Enum

from diagtest.dialect import DialectCompiler, Dialect
from diagtest.compiler import CompilerInfo
from diagtest.util import run


class VsArch(Enum):
    x86 = 'x86'
    x64 = 'amd64'


class MSVC(DialectCompiler):
    languages = 'c', 'c++'
    diagnostic_pattern = r"^((?P<path>[a-zA-Z0-9:\/\\\._-]*?)\((?P<line>[0-9]+)\): )"\
                         r"((?P<level>fatal error|error|warning) )((?P<error_code>[A-Z][0-9]+): )(?P<message>.*)$"

    '''def execute(self, file: Path, test_id: str):
        # TODO
        env = self.get_env(VsArch[self.get_version(self.compiler)['target']])
        for standard in self.selected_standards:
            name = f"{str(self)} ({standard})"
            yield name, self.compile(file, [f"/std:{standard}", *(self.options or []), f"/D{test_id}"], env=env)'''

    @staticmethod
    def select_language(language: str):
        return None

    @staticmethod
    def select_dialect(dialect: str):
        return f"/std:{dialect}"

    @staticmethod
    def select_test(test: str):
        return f"/D{test}"

    @staticmethod
    def include(directory: Path):
        return f"/I{directory.absolute()!s}"

    @staticmethod
    @cache
    def get_help_text(compiler: Path):
        return run([str(compiler), '/help'])

    @staticmethod
    @cache
    def _query_version(compiler: Path) -> dict[str, str]:
        help_text = MSVC.get_help_text(compiler)
        version_pattern = re.compile(r"Version (?P<version>[0-9\.]+) for (?P<target>.*)")
        result = re.search(version_pattern, help_text.stderr)
        assert result is not None, "Querying compiler version failed"
        return result.groupdict()

    @classmethod
    def get_version(cls, path: Path) -> str:
        info = cls._query_version(path)
        assert 'version' in info, "Automatic version detection failed"
        return info['version']

    @classmethod
    def get_target(cls, path: Path) -> str | None:
        info = cls._query_version(path)
        return info.get('target')

    @staticmethod
    @cache
    def get_supported_dialects(compiler: Path):
        help_text = MSVC.get_help_text(compiler)
        standard_pattern = r"\/std:<(?P<standards>.*)> (?P<language>[^ ]+)"
        standards: dict[str, list[Dialect]] = {}
        for match in re.finditer(standard_pattern, help_text.stdout):
            language = match['language'].lower()
            standards[language] = [Dialect(standard) for standard in match["standards"].split('|')]
        return standards

    @staticmethod
    @cache
    def vswhere():
        # this is a stable path
        vswhere_exe = Path(os.environ["PROGRAMFILES(X86)"]) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
        result = run([str(vswhere_exe)])
        assert result.returncode == 0, "Could not run vswhere"

        def search(fields: list[str]):
            for line in result.stdout.splitlines():
                for field in fields:
                    if not line.startswith(field):
                        continue
                    yield field, line.split(f"{field}: ", maxsplit=1)[1]

        return dict(search(['installationPath', 'installationVersion', 'displayName']))

    @staticmethod
    @cache
    def get_env(arch: VsArch):
        if os.environ.get('VSCMD_ARG_HOST_ARCH', None) == arch.name:
            # environment already configured properly
            return None

        installation_info = MSVC.vswhere()
        setup_env = Path(installation_info['installationPath']) / "Common7" / "Tools" / "VsDevCmd.bat"
        cmd = f'cmd.exe /s /c "\"{setup_env}\" -arch={arch.value} >nul 2>&1 && set"'

        result = run(cmd)
        assert result.returncode == 0, "Setting up environment failed"
        return dict([line.split("=", maxsplit=1) for line in result.stdout.splitlines()])

    @classmethod
    @cache
    def discover(cls):
        if platform.system() != "Windows":
            # This compiler is not available on UNIX systems
            return []

        if 'VSCMD_VER' in os.environ:
            logging.debug("Developer VS Shell environment variables found. Skipping discovery.")
            compiler = shutil.which("cl")
            return [] if compiler is None else [Path(compiler)]

        installation_info = MSVC.vswhere()
        if not installation_info:
            # MSVC isn't installed
            return []

        logging.debug("Discovered %s version %s",
                      installation_info['displayName'],
                      installation_info['installationVersion'])

        compilers: list[Path] = []
        for arch in VsArch:
            env = MSVC.get_env(arch)
            compiler = shutil.which("cl", path=env['Path'])
            if compiler is None:
                continue
            compilers.append(Path(compiler))
        return compilers
