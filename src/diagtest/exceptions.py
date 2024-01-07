from pathlib import Path

class InterpreterError(Exception):
    ...

class UsageError(InterpreterError):
    def __init__(self, context: tuple[Path, int, int, int], message: str):
        # context[3] is the number of characters processed - we don't care
        self.file, self.line, self.column, *_ = context
        super().__init__(message)
