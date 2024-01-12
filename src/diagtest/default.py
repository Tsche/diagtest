import logging
from pathlib import Path
from itertools import groupby
from functools import partial

from diagtest.compiler import compilers
from diagtest.language import languages
from diagtest.util import remove_duplicates, print_dict
__all__ = ['compilers', 'languages', 'load_compilers', 'load_languages']

def dump_compilers():
    def key_function(compiler, path: Path):
        return compiler.get_version(path), compiler.get_target(path)

    for compiler in compilers:
        print(f"Compiler `{compiler.__name__}`")
        discovered = compiler.discover()
        if not discovered:
            # print("    not found")
            continue
        if isinstance(discovered, dict):
            discovered = remove_duplicates([compiler
                                            for compiler_list in discovered.values()
                                            for compiler in compiler_list])

            for _, group in groupby(discovered, partial(key_function, compiler)):
                executables = list(group)
                assert executables, "Empty group in compilers listed by version. How?"
                info = compiler.get_info(executables[0]).dump()
                info['executable'] = executables
                print_dict(info, indent_amount=4, indent_level=1)
            continue

        for compiler_path in discovered:
            info = compiler.get_info(compiler_path).dump()
            print_dict(info, indent_amount=4, indent_level=1)


def load_compilers():
    # TODO load all files in compilers directory instead
    import diagtest.compilers.gcc
    import diagtest.compilers.msvc
    import diagtest.compilers.clang


def load_languages():
    import diagtest.languages.cfamily
