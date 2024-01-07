import logging
from abc import abstractmethod
from pathlib import Path
from typing import Type

from diagtest.util import UniqueDict


class Language:
    languages: tuple[str, ...] | list[str]
    suffixes: tuple[str, ...] | list[str]

    @classmethod
    def __init_subclass__(cls):
        if not hasattr(cls, 'languages'):
            logging.warning("Language definition {cls.__name__} lacks the `languages` attribute.")
            return

        for language in getattr(cls, 'languages', []):
            languages[language] = cls

    @classmethod
    @abstractmethod
    def identifier(cls, name: str) -> str:
        ...

    @classmethod
    @abstractmethod
    def wrap_test(cls, name: str, code: str) -> str:
        ...


languages: dict[str, Type[Language]] = UniqueDict()


def detect_language(source_file: Path):
    return [language
            for language, definition in languages.items()
            if source_file.suffix in definition.suffixes]
