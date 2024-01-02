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

def dump_compilers():
    from diagtest.compilers.gcc import GCC
    from diagtest.compilers.clang import Clang
    from diagtest.compilers.msvc import MSVC

    compilers = [GCC, Clang, MSVC]
    for compiler in compilers:
        discovered = compiler.discover()
        if not discovered:
            continue

        for compiler_info in discovered:
            version = compiler.get_version(compiler_info.executable)
            print(f"{compiler.__name__} ({version['version']})")
            print(f"  Executable: {compiler_info.executable}")
            print(f"  Target:     {version['target']}")
            print( "  Languages:")
            standards = compiler.get_supported_standards(compiler_info.executable)
            for language, standard in standards.items():
                print(f"    {language:<6} {', '.join(', '.join(std) for std in standard)}")
            print()
