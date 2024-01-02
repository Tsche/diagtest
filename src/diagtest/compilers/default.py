from functools import cache

from diagtest.compilers.gcc import GCC
from diagtest.compilers.clang import Clang
from diagtest.compilers.msvc import MSVC

def discover():
    compilers = [GCC, Clang, MSVC]
    for compiler in compilers:
        name = compiler.__name__.lower()
        print(compiler.discover())

if __name__ == "__main__":
    discover()
