import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Iterable, Optional, TypeVar


@dataclass
class Result:
    command: str
    returncode: int
    stdout: str
    stderr: str
    start_time: int
    end_time: int

    @property
    def elapsed(self):
        assert self.end_time >= self.start_time, "Invalid time measurements"
        return self.end_time - self.start_time

    @property
    def elapsed_ms(self):
        return self.elapsed / 1e6

    @property
    def elapsed_s(self):
        return self.elapsed / 1e9


def run(command: list[str] | str, env: Optional[dict[str, str]] = None):
    command_str = command if isinstance(command, str) else ' '.join(command)
    logging.debug(command_str)
    start_time = time.monotonic_ns()
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
        env=env
    )
    end_time = time.monotonic_ns()

    return Result(command_str,
                  result.returncode,
                  result.stdout,
                  result.stderr,
                  start_time,
                  end_time)


def which(query: re.Pattern | str):
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

def format_dict(item: dict,
                indent_amount: int = 4,
                indent_level: int = 0,
                dict_separator: str = ": ",
                list_separator: str = ", ",
                break_list: bool = False,
                right_align: bool = False) -> Iterable[str]:
    max_width = max(len(str(key)) for key in item)

    def align(inner_key: Any, prefix: str = "", suffix: str = ""):
        nonlocal max_width, right_align
        diff = ' ' * (max_width - len(str(inner_key)))
        wrapped = f"{prefix}{inner_key}{suffix}"
        return diff + wrapped if right_align else wrapped + diff

    for key, value in item.items():
        line = f"{align(key, suffix=dict_separator)}"
        if isinstance(value, dict):
            yield from indent(line, indent_level, indent_amount)
            yield from format_dict(value, indent_amount, indent_level + 1, dict_separator, list_separator, break_list, right_align)

        elif isinstance(value, (list, tuple, set)):
            if break_list:
                yield from indent(line, indent_level, indent_amount)
                for element in value:
                    yield from indent(str(element), indent_level + 1, indent_amount)
            else:
                yield from indent(line + list_separator.join(str(element) for element in value), indent_level, indent_amount)

        else:
            yield from indent(line + str(value), indent_level, indent_amount)


def print_dict(item: dict, *args, **kwargs):
    for line in format_dict(item, *args, **kwargs):
        print(line)

def indent(element: Any, indent_level: int = 1, indent_amount: int = 4):
    indentation = ' ' * (indent_amount * indent_level)
    for line in str(element).splitlines():
        yield f"{indentation}{line}"

def print_indent(what: Any, indent_level: int = 0, indent_amount: int = 4, **kwargs):
    for line in indent(what, indent_level, indent_amount):
        print(line, **kwargs)
