@{
from diagtest.compilers.c_cpp import GCC, Language

# compile C++ code with GCC instead of G++
# to do this we need to grab GCC in C mode and reconfigure it
c_gcc = GCC(language=Language.C)(
            language=Language.CPP, std='>17', 
            options=["-xc++", "-lstdc++", "-shared-libgcc", "-lm"])

# alternatively we configure for C++ and could set the executable 
# to the one GCC configured for C uses
# c_gcc = GCC(language=Language.CPP, std='>17', 
#             options=["-xc++", "-lstdc++", "-shared-libgcc", "-lm"]
#             executable=GCC(language=Language.C).compiler)
}

@load_defaults('c++')
