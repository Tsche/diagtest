@load_defaults('c++')

int main() {
//! IMPORTANT: DO NOT PLACE A SPACE BEFORE {
@test("undeclared symbol"){
    undeclared;
    //unavailable compilers will be skipped
    @error(gcc, regex=".* was not declared in this scope")
    @error(clang, "use of undeclared identifier 'undeclared'")
    @error(msvc, "'undeclared': undeclared identifier")
    @error_code(msvc, 'C2065')
}

@test("test only some versions"){
    undeclared;
    @error(GCC(std='>11', version="<12.0"), regex=".* was not declared in this scope")
    @error(MSVC(std='>14', target='x64'), "'undeclared': undeclared identifier")
}
}