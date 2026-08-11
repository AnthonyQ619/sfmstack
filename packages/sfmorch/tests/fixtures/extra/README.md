# Extra fixture modules

Loaded only by the tests that need them, not by `fixtures/modules`.

`fixtures/modules` is a fixed set that several registry, service and MCP tests
assert over directly — module counts, which outputs are terminal, which types
have no consumer. Adding a module there to serve one unrelated test silently
changes what those assertions mean.

So a fixture that exists for one test's sake lives here and is loaded with a
second `load_dir` call beside the main set.
