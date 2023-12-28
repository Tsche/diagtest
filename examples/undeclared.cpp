@test("undeclared symbol") {
    undeclared;
    @error(gcc, "'undeclared' was not declared in this scope")
    @error(clang, "error: use of undeclared identifier 'undeclared'")
}