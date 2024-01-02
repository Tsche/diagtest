// Include our compiler definitions. You probably want to reuse these
@include("compilers.em")

int main() {
//! IMPORTANT: DO NOT PLACE A SPACE BEFORE {
@test("undeclared symbol"){
    undeclared;
    //unavailable compilers will be skipped
    @error(gcc, "‘undeclared’ was not declared in this scope")@
    @error(clang, "use of undeclared identifier 'undeclared'")@
    @#error(msvc, "use of undeclared identifier 'undeclared'")@
    
    //Also compile this test with GCC instead of G++
    @#error(c_gcc, "‘undeclared’ was not declared in this scope")@
}
}