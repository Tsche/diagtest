from typing import Iterable, Protocol

from diagtest.test import TestSuiteResult

class Printer(Protocol):

    def print(self, report: Iterable[TestSuiteResult]):
        raise NotImplementedError
