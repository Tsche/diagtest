# @load_defaults('python')
#import os

# @test("undeclared symbol"){
#if os.environ.get("UNDECLARED_SYMBOL", False):
undeclared
# @error(python, "NameError: name 'undeclared' is not defined")
# }

# @test("assertion"){
#if os.environ.get("ASSERTION", False):
assert False, "Message"
# @error(python, "AssertionError: Message")
# }
