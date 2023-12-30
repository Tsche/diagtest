@{
gcc = GCC(["c++17", "c++20", "c++23"], ["-xc++", "-lstdc++", "-shared-libgcc", "-lm"])
clang = Clang(["c++20", "c++23"], ["-xc++"])
}