from diagtest.language import Language

class C(Language):
    languages = 'c', 'gnu'
    suffixes = ['.c', '.h', '.i']
    @classmethod
    def identifier(cls, name: str):
        return f"TEST_{''.join(c if c.isalnum() else '_' for c in name.upper())}"

    @classmethod
    def wrap_test(cls, name: str, code: str):
        return f"\n#ifdef {cls.identifier(name)}\n{code}\n#endif"

class CPP(C):
    languages = 'c++', 'gnu++'
    suffixes = [*C.suffixes, '.C', '.cc', '.cpp', '.CPP', '.c++', '.cp', '.cxx', '.hh', '.hpp', '.H', '.tcc', '.ii']
