"""Validate API names and kwargs in skill markdown against the live deephaven modules.

Static phase (this process):
    Walk every *.md in the skill, extract fenced ```python``` blocks AND inline
    `code` spans, AST-parse each, collect (file, line, chain, kwargs) tuples for
    every Call/Attribute rooted at a known module name (`ui`, `dx`, `dht`, `agg`,
    `deephaven`) or known instance type (`t`, `table`, `source`, `filtered` → Table).

Dynamic phase (via `dh exec`):
    Pass the collected chains as JSON to a probe script. The probe imports each
    module, resolves each chain via getattr, and validates kwargs against
    inspect.signature. Returns JSON.

Report phase (this process):
    Print failures with file:line context.

Usage:
    uv run check-apis                # check all skill files
    uv run check-apis ui.md          # check one reference
    uv run check-apis -v             # show OK lines too
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import textwrap
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from config import REFERENCES_DIR, SKILL_DIR, SKILL_MD

# Module-rooted names: chain[0] -> module to import.
ROOTS: dict[str, str] = {
    "ui": "deephaven.ui",
    "dx": "deephaven.plot.express",
    "dht": "deephaven.dtypes",
    "agg": "deephaven.agg",
    "deephaven": "deephaven",
}

# Variable names that always denote a Deephaven Table — chain[0] is replaced by
# the bound type, so `t.where(...)` validates against `Table.where`.
INSTANCE_TYPES: dict[str, tuple[str, str]] = {
    "t": ("deephaven.table", "Table"),
    "table": ("deephaven.table", "Table"),
    "source": ("deephaven.table", "Table"),
    "filtered": ("deephaven.table", "Table"),
}

FENCED_RE = re.compile(r"^```python\s*\n(.*?)^```", re.MULTILINE | re.DOTALL)
INLINE_RE = re.compile(r"`([^`\n]+)`")


@dataclass(frozen=True)
class Chain:
    file: str
    line: int
    parts: tuple[str, ...]
    kwargs: tuple[str, ...]


def find_markdown_files(filter_name: str | None = None) -> list[Path]:
    files = [SKILL_MD] + sorted(REFERENCES_DIR.glob("*.md"))
    if filter_name:
        files = [f for f in files if f.name == filter_name]
    return files


def extract_fenced_blocks(text: str) -> list[tuple[int, str]]:
    out = []
    for m in FENCED_RE.finditer(text):
        line = text[: m.start()].count("\n") + 2  # +2 for ```python line
        out.append((line, textwrap.dedent(m.group(1))))
    return out


def extract_inline_spans(text: str) -> list[tuple[int, str]]:
    out = []
    # Strip fenced blocks before scanning for inline so we don't double-count.
    stripped = FENCED_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    for m in INLINE_RE.finditer(stripped):
        line = stripped[: m.start()].count("\n") + 1
        out.append((line, m.group(1)))
    return out


def try_parse(snippet: str) -> ast.AST | None:
    """Best-effort parse. Tries exec then eval; strips a few common doc-fragment
    decorations (trailing `, ...`, leading `.`)."""
    s = snippet.strip()
    if not s:
        return None
    # Skip obvious non-Python single-line fragments: shell commands, URLs, paths.
    # (Multi-line snippets may legitimately start with `#` for comments or `@`
    # for decorators — only apply these filters to single-line fragments.)
    if "\n" not in s:
        if any(s.startswith(p) for p in ("http", "/", "$", "!")):
            return None
        if "://" in s or s.startswith("```"):
            return None
        # File-path-like fragments: `references/ui.md`, `path/to/foo.csv`. They
        # parse as `references / ui.md` (BinOp) but yield bogus attribute chains.
        if re.fullmatch(r"[\w./\-]+\.(md|py|csv|txt|json|ya?ml|html|toml|sh)", s):
            return None
    # Trim trailing ellipses that show up in inline call signatures.
    s = re.sub(r",\s*\.\.\.\s*\)?\s*$", ")", s)
    s = s.removesuffix("...").rstrip()
    for mode in ("exec", "eval"):
        try:
            return ast.parse(s, mode=mode)
        except (SyntaxError, ValueError):
            continue
    return None


def chain_of(node: ast.AST) -> tuple[str, ...] | None:
    """Walk an Attribute/Name spine into ('root', 'a', 'b', ...). None if non-pure."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return tuple(reversed(parts))
    return None


def collect_chains(tree: ast.AST, file: str, base_line: int) -> list[Chain]:
    """Walk AST collecting chains rooted at known names. Calls capture kwargs."""
    out: list[Chain] = []

    # Mark Attribute nodes that are the .func of a Call so we don't double-count.
    in_call_func: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            in_call_func.add(id(node.func))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            ch = chain_of(node.func)
            if ch is None or ch[0] not in ROOTS and ch[0] not in INSTANCE_TYPES:
                continue
            kwargs = tuple(sorted({kw.arg for kw in node.keywords if kw.arg}))
            line = base_line + (getattr(node, "lineno", 1) - 1)
            out.append(Chain(file, line, ch, kwargs))
        elif isinstance(node, ast.Attribute):
            if id(node) in in_call_func:
                continue
            ch = chain_of(node)
            if ch is None or ch[0] not in ROOTS and ch[0] not in INSTANCE_TYPES:
                continue
            line = base_line + (getattr(node, "lineno", 1) - 1)
            out.append(Chain(file, line, ch, ()))

    return out


def collect_all(files: list[Path]) -> list[Chain]:
    chains: list[Chain] = []
    for f in files:
        text = f.read_text()
        rel = str(f.relative_to(SKILL_DIR))
        for line, code in extract_fenced_blocks(text):
            tree = try_parse(code)
            if tree is not None:
                chains.extend(collect_chains(tree, rel, line))
        for line, code in extract_inline_spans(text):
            tree = try_parse(code)
            if tree is not None:
                chains.extend(collect_chains(tree, rel, line))
    return chains


PROBE_TEMPLATE = '''
import importlib
import inspect
import json
import sys

ROOTS = {roots!r}
INSTANCE_TYPES = {instance_types!r}
QUERIES = {queries!r}

modules = {{}}
import_errors = {{}}
for root, modname in ROOTS.items():
    try:
        modules[root] = importlib.import_module(modname)
    except Exception as e:
        import_errors[root] = f"{{type(e).__name__}}: {{e}}"

instances = {{}}
for name, (modname, cls) in INSTANCE_TYPES.items():
    try:
        m = importlib.import_module(modname)
        instances[name] = getattr(m, cls)
    except Exception as e:
        import_errors[name] = f"{{type(e).__name__}}: {{e}}"


def instance_attrs_from_init(cls):
    """Return names assigned to self.X inside cls.__init__ (and parents)."""
    import ast as _ast, inspect as _inspect
    found = set()
    for klass in cls.__mro__:
        try:
            src = _inspect.getsource(klass)
        except (OSError, TypeError):
            continue
        try:
            tree = _ast.parse(src)
        except SyntaxError:
            continue
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Assign):
                for target in node.targets:
                    if (isinstance(target, _ast.Attribute)
                            and isinstance(target.value, _ast.Name)
                            and target.value.id == "self"):
                        found.add(target.attr)
    return found


def resolve(parts):
    """Return (obj, error). obj=None if any attr is missing."""
    head = parts[0]
    if head in modules:
        obj = modules[head]
    elif head in instances:
        obj = instances[head]
    else:
        return None, f"unknown root '{{head}}'"
    seen = [head]
    for attr in parts[1:]:
        # Try direct attribute access first.
        if hasattr(obj, attr):
            obj = getattr(obj, attr)
            seen.append(attr)
            continue
        # If obj is a module, the missing attr might be an unimported submodule.
        if inspect.ismodule(obj):
            full = obj.__name__ + "." + attr
            try:
                sub = importlib.import_module(full)
                obj = sub
                seen.append(attr)
                continue
            except ImportError:
                pass
        # If obj is a class, the missing attr might be an instance attribute set
        # in __init__ (e.g. Table.j_table). Walk __init__ source.
        if inspect.isclass(obj):
            init_attrs = instance_attrs_from_init(obj)
            if attr in init_attrs:
                # Instance attr exists; we can't traverse further without a real
                # instance, so report success but stop chain validation here.
                return None, None  # noqa: special "ok, untraversable" sentinel
        # Suggest closest match before failing.
        import difflib
        candidates = [n for n in dir(obj) if not n.startswith('_')]
        close = difflib.get_close_matches(attr, candidates, n=1)
        hint = f" (did you mean {{close[0]!r}}?)" if close else ""
        return None, f"no attribute '{{attr}}' on {{'.'.join(seen)}}{{hint}}"
    return obj, None


def check_kwargs(obj, kwargs):
    if not kwargs:
        return None
    try:
        sig = inspect.signature(obj)
    except (ValueError, TypeError):
        return None  # unintrospectable; pass
    params = sig.parameters
    has_var_kw = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
    )
    if has_var_kw:
        return None
    bad = [k for k in kwargs if k not in params]
    if bad:
        valid = [n for n, p in params.items()
                 if p.kind != inspect.Parameter.VAR_POSITIONAL][:15]
        return f"unknown kwargs {{bad}} on {{obj!r}}; valid: {{valid}}"
    return None


results = []
for q in QUERIES:
    parts = tuple(q["parts"])
    kwargs = tuple(q["kwargs"])
    if parts[0] in import_errors:
        results.append({{"parts": list(parts), "kwargs": list(kwargs),
                        "error": f"import failed: {{import_errors[parts[0]]}}"}})
        continue
    obj, err = resolve(parts)
    if err:
        results.append({{"parts": list(parts), "kwargs": list(kwargs), "error": err}})
        continue
    if obj is None:
        # Instance attribute resolved via __init__ inspection — accept.
        results.append({{"parts": list(parts), "kwargs": list(kwargs), "ok": True}})
        continue
    err = check_kwargs(obj, kwargs)
    if err:
        results.append({{"parts": list(parts), "kwargs": list(kwargs), "error": err}})
        continue
    results.append({{"parts": list(parts), "kwargs": list(kwargs), "ok": True}})

print("__API_PROBE_BEGIN__")
print(json.dumps(results))
print("__API_PROBE_END__")
'''


QueryKey = tuple[tuple[str, ...], tuple[str, ...]]


def run_probe(chains: list[Chain]) -> dict[QueryKey, dict]:
    """Dedupe queries and run the probe via dh exec.

    Returns map (parts, kwargs) -> result.
    """
    queries: list[dict] = []
    seen: set[QueryKey] = set()
    for c in chains:
        key = (c.parts, c.kwargs)
        if key in seen:
            continue
        seen.add(key)
        queries.append({"parts": list(c.parts), "kwargs": list(c.kwargs)})

    if not queries:
        return {}

    probe = PROBE_TEMPLATE.format(
        roots=ROOTS,
        instance_types=INSTANCE_TYPES,
        queries=queries,
    )

    if not shutil.which("dh"):
        print("Error: 'dh' CLI not found on PATH", file=sys.stderr)
        sys.exit(2)

    proc = subprocess.run(
        ["dh", "exec", "-c", probe, "--no-show-tables", "--no-table-meta"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        print("Probe failed:", file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        sys.exit(2)

    out = proc.stdout
    try:
        after_begin = out.split("__API_PROBE_BEGIN__", 1)[1]
        body = after_begin.split("__API_PROBE_END__", 1)[0].strip()
    except IndexError:
        print("Could not find probe markers in output:", file=sys.stderr)
        print(out, file=sys.stderr)
        sys.exit(2)

    results = json.loads(body)
    return {(tuple(r["parts"]), tuple(r["kwargs"])): r for r in results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?", help="Single reference file (e.g. ui.md)")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show OK chains too"
    )
    args = parser.parse_args()

    files = find_markdown_files(args.file)
    if not files:
        print(f"No markdown files matched (filter: {args.file!r})", file=sys.stderr)
        sys.exit(2)

    chains = collect_all(files)
    results = run_probe(chains)

    failures: list[tuple[Chain, dict]] = []
    ok_count = 0
    for c in chains:
        r = results.get((c.parts, c.kwargs))
        if r is None:
            continue
        if "error" in r:
            failures.append((c, r))
        else:
            ok_count += 1

    # Group failures by file
    by_file: dict[str, list[tuple[Chain, dict]]] = defaultdict(list)
    for c, r in failures:
        by_file[c.file].append((c, r))

    if failures:
        for file, entries in sorted(by_file.items()):
            print(f"\n{file}:")
            for c, r in sorted(entries, key=lambda x: x[0].line):
                chain_repr = ".".join(c.parts)
                kw_repr = f"({', '.join(c.kwargs)})" if c.kwargs else ""
                print(f"  L{c.line}  {chain_repr}{kw_repr}")
                print(f"          → {r['error']}")
        unique_failures = len({(c.parts, c.kwargs) for c, _ in failures})
        print(
            f"\nFAIL: {unique_failures} unique chain(s) failed across "
            f"{len(failures)} reference(s) in {len(by_file)} file(s). "
            f"{ok_count} OK."
        )
        sys.exit(1)

    if args.verbose:
        for c in chains:
            r = results.get((c.parts, c.kwargs))
            if r and r.get("ok"):
                chain_repr = ".".join(c.parts)
                kw_repr = f"({', '.join(c.kwargs)})" if c.kwargs else ""
                print(f"OK  {c.file}:{c.line}  {chain_repr}{kw_repr}")

    print(f"OK: {ok_count} chain reference(s) validated across {len(files)} file(s).")
    sys.exit(0)


if __name__ == "__main__":
    main()
