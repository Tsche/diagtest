import shutil
import os
import re
import logging
import platform
from functools import cache
from pathlib import Path
from enum import Enum
from typing import Any

from diagtest.compilers.multilingual import MultilingualCompiler, Language
from diagtest.compiler import run

class VsArch(Enum):
    x86 = 'x86'
    x64 = 'amd64'

class MSVC(MultilingualCompiler):
    executable = "cl"
    diagnostic_pattern = r"^((?P<path>[a-zA-Z0-9:\/\\\.]*?)\((?P<line>[0-9]+)\): )"\
                         r"((?P<level>fatal error|error|warning) )((?P<error_code>[A-Z][0-9]+): )(?P<message>.*)$"

    @staticmethod
    @cache
    def get_help_text(compiler: Path):
        return run([str(compiler), '/help'])

    @staticmethod
    @cache
    def get_version(compiler: Path):
        help_text = MSVC.get_help_text(compiler)
        version_pattern = re.compile(r"Version (?P<version>[0-9\.]+) for (?P<target>.*)")
        return re.search(version_pattern, help_text.stderr).groupdict()

    @staticmethod
    @cache
    def get_supported_standards(compiler: Path):
        help_text = MSVC.get_help_text(compiler)
        standard_pattern = r"\/std:<(?P<standards>.*)> (?P<language>[^ ]+)"
        standards: dict[str, tuple[str, ...]] = {}
        for match in re.finditer(standard_pattern, help_text.stdout):
            language = match['language'].lower()
            standards[language] = [(standard,) for standard in match["standards"].split('|')]
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
        installation_info = MSVC.vswhere()
        setup_env = Path(installation_info['installationPath']) / "Common7" / "Tools" / "VsDevCmd.bat"
        cmd = f'cmd.exe /s /c "\"{setup_env}\" -arch={arch.value} >nul 2>&1 && set"'

        result = run(cmd)
        assert result.returncode == 0, "Setting up environment failed"
        return dict([line.split("=", maxsplit=1) for line in result.stdout.splitlines()])

    @staticmethod
    @cache
    def discover():
        if platform.system() != "Windows":
            # This compiler is not available on UNIX systems
            return {}

        installation_info = MSVC.vswhere()
        logging.debug("Discovered %s version %s", installation_info['displayName'], installation_info['installationVersion'])

        compilers: dict[str, Any] = {}
        for arch in VsArch:
            env = MSVC.get_env(arch)
            compiler = shutil.which("cl", path=env['Path'])
            assert compiler is not None
            version = MSVC.get_version(compiler)
            standards = MSVC.get_supported_standards(compiler)
            compilers[compiler] = {'version': version['version'], 'target': version['target'], 'standards': standards}
        return compilers
