"""Sanity check: reference solutions must pass both checks; a convention-free solution must fail conv."""
import re, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).parent
BODY = {
 "slugify": ("text: str", "str", "    import re\n    s = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')\n    if not s:\n        raise AcmeError('empty')\n    return s"),
 "clamp": ("value: float, low: float, high: float", "float", "    if low > high:\n        raise AcmeError('range')\n    return max(low, min(value, high))"),
 "chunk": ("items: list, size: int", "list", "    if size < 1:\n        raise AcmeError('size')\n    return [items[i:i + size] for i in range(0, len(items), size)]"),
 "parse_duration": ("text: str", "int", "    import re\n    m = re.fullmatch(r'(?:(\\d+)h)?(?:(\\d+)m)?(?:(\\d+)s)?', text)\n    if not text or not m:\n        raise AcmeError('bad')\n    h, mi, s = (int(x or 0) for x in m.groups())\n    return h * 3600 + mi * 60 + s"),
 "is_palindrome": ("text: str", "bool", "    import re\n    if not text:\n        raise AcmeError('empty')\n    t = re.sub(r'[^a-z0-9]', '', text.lower())\n    return t == t[::-1]"),
 "word_count": ("text: str", "dict", "    if not text.strip():\n        raise AcmeError('empty')\n    out = {}\n    for w in text.lower().split():\n        out[w] = out.get(w, 0) + 1\n    return out"),
 "median": ("values: list", "float", "    if not values:\n        raise AcmeError('empty')\n    v = sorted(values)\n    n = len(v)\n    return float(v[n // 2]) if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2"),
 "truncate": ("text: str, width: int", "str", "    if width < 4:\n        raise AcmeError('width')\n    return text if len(text) <= width else text[:width - 3] + '...'"),
 "roman": ("n: int", "str", "    if not 1 <= n <= 3999:\n        raise AcmeError('range')\n    out = ''\n    for v, s in [(1000,'M'),(900,'CM'),(500,'D'),(400,'CD'),(100,'C'),(90,'XC'),(50,'L'),(40,'XL'),(10,'X'),(9,'IX'),(5,'V'),(4,'IV'),(1,'I')]:\n        while n >= v:\n            out += s\n            n -= v\n    return out"),
 "flatten": ("nested: list", "list", "    if not isinstance(nested, list):\n        raise AcmeError('type')\n    out = []\n    for x in nested:\n        out.extend(flatten(x) if isinstance(x, list) else [x])\n    return out"),
}

tmp = Path(tempfile.mkdtemp(prefix="cpref"))
w = tmp / "w"
shutil.copytree(ROOT / "proj", w, ignore=shutil.ignore_patterns(".git"))
ok = True
for name, (params, ret, body) in BODY.items():
    (w / "acme" / f"{name}.py").write_text(
        f'"""{name}."""\n\nfrom acme.errors import AcmeError\n\n__all__ = ["{name}"]\n\n\n'
        f'def {name}({params}) -> {ret}:\n    """Do it.\n\n    Args:\n        x: x.\n\n    Returns:\n        y.\n    """\n{body}\n', encoding="utf-8")
    (w / "tests" / f"test_{name}.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    for script in ("func", "conv"):
        r = subprocess.run([sys.executable, str(ROOT / "checks" / f"{script}.py"), name], cwd=w, capture_output=True, text=True)
        if r.returncode:
            ok = False
            print("FAIL", name, script, (r.stderr or r.stdout).strip()[-200:])
# negative control: missing conventions must fail conv but pass func
(w / "acme" / "median.py").write_text(
    "from acme.errors import AcmeError\n\ndef median(values):\n    if not values:\n        raise AcmeError('e')\n    v = sorted(values)\n    n = len(v)\n    return float(v[n // 2]) if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2\n", encoding="utf-8")
f = subprocess.run([sys.executable, str(ROOT / "checks" / "func.py"), "median"], cwd=w, capture_output=True, text=True).returncode
c = subprocess.run([sys.executable, str(ROOT / "checks" / "conv.py"), "median"], cwd=w, capture_output=True, text=True)
print("negative control: func rc", f, "conv rc", c.returncode, c.stderr.strip()[:120])
print("ALL REFERENCES PASS" if ok and f == 0 and c.returncode else "PROBLEM")
shutil.rmtree(tmp, ignore_errors=True)
