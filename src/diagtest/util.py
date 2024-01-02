import re
import os

from pathlib import Path

def find_executables(query: re.Pattern | str):
    query = re.compile(query) if isinstance(query, str) else query
    env_path = os.environ.get('PATH', os.environ.get('Path', os.defpath))
    paths = [Path(path) for path in env_path.split(os.pathsep)]

    for path in paths:
        if not path.exists():
            continue

        for file in path.iterdir():
            if query.match(file.name):
                yield file.resolve()
