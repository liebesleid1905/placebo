---
name: acme-conventions
description: Use when adding or changing Python functions in the acme package, to follow the project's module, typing, docstring, error and test conventions.
---

# acme conventions

When you add a function to the `acme` package:

1. Put it in its own module `acme/<function_name>.py` (module name equals function name).
2. Define `__all__ = ["<function_name>"]` in that module, listing only that function.
3. Give every parameter and the return value a type hint.
4. Write a Google-style docstring with `Args:` and `Returns:` sections.
5. Report invalid input by raising `AcmeError` (from `acme.errors`), never `ValueError` or `TypeError`.
6. Add `tests/test_<function_name>.py` with pytest tests covering normal use and the error case.
