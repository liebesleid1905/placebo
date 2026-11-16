"""Builds the demo project, skill, checks and tasks for the Copilot A/B experiment."""
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent
PROJ = ROOT / "proj"
SKILL = ROOT / "skill" / "acme-conventions"
PY = sys.executable

TASKS = [
    ("slugify", "text", "Return a lowercase URL slug: runs of non-alphanumeric characters become a single '-', no leading or trailing '-'. Empty or whitespace-only input is invalid."),
    ("clamp", "value, low, high", "Return value limited to the range [low, high]. low greater than high is invalid."),
    ("chunk", "items, size", "Split a list into consecutive lists of at most `size` items. size below 1 is invalid."),
    ("parse_duration", "text", "Parse strings like '1h30m', '45s', '2h' into whole seconds (units h, m, s). Anything else is invalid."),
    ("is_palindrome", "text", "Return True if text reads the same forwards and backwards, ignoring case and non-alphanumeric characters. Empty input is invalid."),
    ("word_count", "text", "Return a dict mapping each lowercase word to how often it occurs. Empty or whitespace-only input is invalid."),
    ("median", "values", "Return the median of a list of numbers as a float. An empty list is invalid."),
    ("truncate", "text, width", "Return text unchanged if it fits in `width` characters, otherwise cut it so the result is exactly `width` long and ends with '...'. width below 4 is invalid."),
    ("roman", "n", "Convert an integer from 1 to 3999 to a Roman numeral string. Anything outside that range is invalid."),
    ("flatten", "nested", "Flatten an arbitrarily nested list of lists into one flat list. A non-list argument is invalid."),
]

# name -> list of (args, expected) ; invalid -> list of args that must raise AcmeError
CASES = {
    "slugify": ([(["Hello, World!"], "hello-world"), (["  A  b--c "], "a-b-c")], [[""], ["   "]]),
    "clamp": ([([5, 0, 3], 3), ([-1, 0, 3], 0), ([2, 0, 3], 2)], [[1, 5, 0]]),
    "chunk": ([([[1, 2, 3, 4, 5], 2], [[1, 2], [3, 4], [5]]), ([[], 3], [])], [[[1], 0]]),
    "parse_duration": ([(["1h30m"], 5400), (["45s"], 45), (["2h"], 7200)], [["abc"], [""]]),
    "is_palindrome": ([(["A man, a plan, a canal: Panama"], True), (["hello"], False)], [[""]]),
    "word_count": ([(["a b a"], {"a": 2, "b": 1}), (["Hi hi"], {"hi": 2})], [[""], ["  "]]),
    "median": ([([[3, 1, 2]], 2.0), ([[1, 2, 3, 4]], 2.5)], [[[]]]),
    "truncate": ([(["abcdefghij", 8], "abcde..."), (["abc", 8], "abc")], [["abc", 3]]),
    "roman": ([([1994], "MCMXCIV"), ([4], "IV"), ([3999], "MMMCMXCIX")], [[0], [4000]]),
    "flatten": ([([[1, [2, [3]]]], [1, 2, 3]), ([[]], [])], [["abc"], [5]]),
}

FUNC_CHECK = '''import importlib, json, os, sys
sys.path.insert(0, os.getcwd())
name = sys.argv[1]
cases, invalid = json.load(open(os.path.join(os.path.dirname(__file__), "cases.json")))[name]
from acme.errors import AcmeError
fn = getattr(importlib.import_module("acme." + name), name)
for args, expected in cases:
    got = fn(*args)
    if got != expected:
        sys.exit(f"{name}{tuple(args)} returned {got!r}, expected {expected!r}")
for args in invalid:
    try:
        fn(*args)
    except AcmeError:
        continue
    except Exception as e:
        sys.exit(f"{name}{tuple(args)} raised {type(e).__name__}, expected AcmeError")
    sys.exit(f"{name}{tuple(args)} should raise AcmeError")
'''

CONV_CHECK = '''import importlib, inspect, os, sys
sys.path.insert(0, os.getcwd())
name = sys.argv[1]
problems = []
path = os.path.join("acme", name + ".py")
if not os.path.isfile(path):
    sys.exit("missing " + path)
mod = importlib.import_module("acme." + name)
fn = getattr(mod, name, None)
if fn is None:
    sys.exit("no function " + name)
if getattr(mod, "__all__", None) != [name]:
    problems.append("__all__ must be exactly [%r]" % name)
sig = inspect.signature(fn)
if sig.return_annotation is inspect.Signature.empty or any(p.annotation is inspect.Parameter.empty for p in sig.parameters.values()):
    problems.append("missing type hints")
doc = inspect.getdoc(fn) or ""
if "Args:" not in doc or "Returns:" not in doc:
    problems.append("docstring needs Args: and Returns:")
t = os.path.join("tests", "test_" + name + ".py")
if not os.path.isfile(t) or not open(t, encoding="utf-8").read().strip():
    problems.append("missing " + t)
if problems:
    sys.exit("; ".join(problems))
'''

SKILL_MD = '''---
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
'''

EXISTING_ADD = '''"""Add two numbers."""

__all__ = ["add"]


def add(a: float, b: float) -> float:
    """Add two numbers.

    Args:
        a: First number.
        b: Second number.

    Returns:
        The sum.
    """
    return a + b
'''


def main() -> None:
    PROJ.mkdir(parents=True, exist_ok=True)
    (PROJ / "acme").mkdir(exist_ok=True)
    (PROJ / "tests").mkdir(exist_ok=True)
    (PROJ / "README.md").write_text("# acme\n\nSmall utility functions.\n", encoding="utf-8")
    (PROJ / "acme" / "__init__.py").write_text("", encoding="utf-8")
    (PROJ / "acme" / "errors.py").write_text(
        '"""Project exceptions."""\n\n__all__ = ["AcmeError"]\n\n\nclass AcmeError(Exception):\n    """Raised for invalid input."""\n',
        encoding="utf-8")
    (PROJ / "acme" / "add.py").write_text(EXISTING_ADD, encoding="utf-8")
    (PROJ / "tests" / "test_add.py").write_text(
        "from acme.add import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n", encoding="utf-8")
    (PROJ / ".gitignore").write_text("__pycache__/\n.placebo/\n.pytest_cache/\n", encoding="utf-8")

    SKILL.mkdir(parents=True, exist_ok=True)
    (SKILL / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")

    checks = ROOT / "checks"
    checks.mkdir(exist_ok=True)
    (checks / "func.py").write_text(FUNC_CHECK, encoding="utf-8")
    (checks / "conv.py").write_text(CONV_CHECK, encoding="utf-8")
    (checks / "cases.json").write_text(json.dumps(CASES), encoding="utf-8")

    tasks = []
    for name, params, desc in TASKS:
        prompt = f"Add a function `{name}({params})` to this project. {desc}"
        tasks.append({
            "id": name,
            "prompt": prompt,
            "checks": [f'"{PY}" "{checks / "func.py"}" {name}', f'"{PY}" "{checks / "conv.py"}" {name}'],
        })
    (ROOT / "tasks.yaml").write_text(yaml.safe_dump({"tasks": tasks}, sort_keys=False), encoding="utf-8")

    def git(*a):
        subprocess.run(["git", *a], cwd=PROJ, check=True, capture_output=True)

    if not (PROJ / ".git").exists():
        git("init", "-q", "-b", "main")
    git("config", "user.email", "exp@example.com")
    git("config", "user.name", "exp")
    git("add", "-A")
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=PROJ, capture_output=True)
    print("built", len(tasks), "tasks")


main()
