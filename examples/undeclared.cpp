//! IMPORTANT: DO NOT PLACE A SPACE BEFORE {

@include("compilers.em")

int main() {
@test("undeclared symbol"){
    undeclared;
    @error(gcc, "‘undeclared’ was not declared in this scope")@
    @error(clang, "use of undeclared identifier 'undeclared'")@
}
}