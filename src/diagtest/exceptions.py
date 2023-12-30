import sys
from pathlib import Path


class UsageError(Exception):
    def __init__(self, context: tuple[Path, int, int, int], message: str):
        # context[3] is the number of characters processed - we don't care
        self.file, self.line, self.column, *_ = context
        super().__init__(message)


def exception_hook(kind, exception, traceback):
    if kind is UsageError:
        print("Traceback:")
        print(f'  File: "{exception.file}", line {exception.line}')
        print(f"{kind.__name__}: {exception!s}")
    else:
        sys.__excepthook__(kind, exception, traceback)


sys.excepthook = exception_hook
