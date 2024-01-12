from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class Level(Enum):
    # TODO this should be an open set instead of an enum
    note = "note"
    warning = "warning"
    error = "error"
    fatal_error = "fatal error"
    # ice = auto() # TODO


@dataclass
class SourceLocation:
    path: Path
    line: Optional[int] = None
    column: Optional[int] = None


@dataclass
class Diagnostic:
    message: str
    source_location: Optional[SourceLocation] = None
    error_code: Optional[str] = None  # MSVC specific

