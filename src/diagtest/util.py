import os
import re
import subprocess
from pathlib import Path
from typing import Optional, TypeVar, Iterable, Any


def find_executables(query: re.Pattern | str):
    query = re.compile(query) if isinstance(query, str) else query
    env_path = os.environ.get('PATH', os.environ.get('Path', os.defpath))
    paths = [Path(path) for path in env_path.split(os.pathsep)]
    for path in paths:
        if not path.exists():
            continue

        for file in path.iterdir():
            if query.match(file.name):
                # resolving here should get rid of symlink aliases
                yield file.resolve()


def run(command: list[str] | str, env: Optional[dict[str, str]] = None):
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
        env=env
    )


def change_repr(repr_fnc):
    class ReprWrapper:
        def __init__(self, fnc):
            self.fnc = fnc

        def __call__(self, *args, **kwargs):
            return self.fnc(*args, **kwargs)

        def __repr__(self):
            nonlocal repr_fnc
            return repr_fnc()

    return ReprWrapper


K = TypeVar('K')
V = TypeVar('V')


class UniqueDict(dict[K, V]):
    def __setitem__(self, index, value):
        assert index not in self, f"Collection already contains {index}, cannot set to {value}"
        super().__setitem__(index, value)


Element = TypeVar('Element')


def remove_duplicates(data: Iterable[Element]) -> list[Element]:
    return [*{entry: None for entry in data}.keys()]

def print_dict(info: dict[str, Any], indent: int = 0, indent_level: int = 0):
    key_max_width = max(len(key) for key in info)
    indentation = ' ' * (indent * indent_level)
    def align_key(text: str, suffix: str = ""):
        nonlocal key_max_width
        diff = key_max_width - len(text)
        return f"{text}{suffix}{' '*diff}"

    for key, value in info.items():
        line = f"{indentation}{align_key(key, ': ')}"
        if isinstance(value, dict):
            print(line)
            print_dict(value, indent, indent_level + 1)
        elif isinstance(value, (list, tuple, set)):
            print(line + ', '.join(str(element) for element in value))
        else:
            print(line + str(value))
