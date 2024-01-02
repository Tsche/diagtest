# TODO walk compilers directory instead

def get_defaults(language: str):
    if language in {'c', 'c++', 'gnu', 'gnu++'}:
        # TODO auto register
        from diagtest.compilers.gcc import GCC
        from diagtest.compilers.clang import Clang
        from diagtest.compilers.msvc import MSVC

        def wrap(cls):
            def inner(**kwargs):
                if 'language' not in kwargs:
                    kwargs['language'] = language
                return cls(**kwargs)
            return inner

        compilers = [GCC, Clang, MSVC]
        return {**{compiler.__name__: wrap(compiler)
                   for compiler in compilers},
                **{compiler.__name__.lower(): compiler(language=language)
                   for compiler in compilers}}
    return {}
