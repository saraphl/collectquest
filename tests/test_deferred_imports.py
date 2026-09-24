"""
Resolve every function-scope relative import under src/ and flag any that shadows a module-level
one. Run after any module move or rename. Exit 1 = something is broken.

    python3 tests/test_deferred_imports.py
"""
import ast, pathlib, sys

root = pathlib.Path(__file__).resolve().parent.parent

fails = []
checked = 0
for p in sorted((root/"src").rglob("*.py")):
    tree = ast.parse(p.read_text(encoding="utf-8"))
    for top in tree.body:
        if not isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for n in ast.walk(top):
            if not isinstance(n, ast.ImportFrom) or not n.level:
                continue
            here = list(p.relative_to(root).parts[:-1])          # e.g. ['src','ui']
            base = here[:len(here) - (n.level - 1)] if n.level > 1 else here
            mod_parts = base + (n.module.split(".") if n.module else [])
            checked += 1
            target_pkg = root.joinpath(*mod_parts)
            target_mod = root.joinpath(*mod_parts).with_suffix(".py")
            if target_mod.exists():
                names = set()
                for x in ast.parse(target_mod.read_text(encoding="utf-8")).body:
                    if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)): names.add(x.name)
                    elif isinstance(x,ast.Assign):
                        names |= {t.id for t in x.targets if isinstance(t,ast.Name)}
                    elif isinstance(x,ast.AnnAssign) and isinstance(x.target,ast.Name): names.add(x.target.id)
                    elif isinstance(x,(ast.Import,ast.ImportFrom)):
                        names |= {(a.asname or a.name).split(".")[0] for a in x.names}
                missing = [a.name for a in n.names if a.name not in names]
                if missing:
                    fails.append(f"{p.relative_to(root)}:{n.lineno}  {'.'.join(mod_parts)} has no {missing}")
            elif (target_pkg/"__init__.py").exists():
                names = {a.name for a in n.names}
                have = {x.stem for x in target_pkg.glob("*.py")}
                init = ast.parse((target_pkg/"__init__.py").read_text(encoding="utf-8"))
                for x in init.body:
                    if isinstance(x,(ast.Import,ast.ImportFrom)):
                        have |= {(a.asname or a.name).split(".")[0] for a in x.names}
                missing = sorted(names - have)
                if missing:
                    fails.append(f"{p.relative_to(root)}:{n.lineno}  package {'.'.join(mod_parts)} has no {missing}")
            else:
                fails.append(f"{p.relative_to(root)}:{n.lineno}  no module {'.'.join(mod_parts)}")


# A function-scope import rebinding a top-level name to a different module resolves fine but
# shadows it, failing later as an AttributeError far from the import.
shadow = []
for p2 in sorted((root/"src").rglob("*.py")):
    tree2 = ast.parse(p2.read_text(encoding="utf-8"))
    top_binds = {}
    for x in tree2.body:
        if isinstance(x, ast.ImportFrom):
            for a in x.names:
                top_binds[a.asname or a.name] = ("." * x.level) + (x.module or "") + "/" + a.name
    for top in tree2.body:
        if not isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for n in ast.walk(top):
            if not isinstance(n, ast.ImportFrom) or not n.level:
                continue
            for a in n.names:
                nm = a.asname or a.name
                origin = ("." * n.level) + (n.module or "") + "/" + a.name
                if nm in top_binds and top_binds[nm] != origin:
                    shadow.append(f"{p2.relative_to(root)}:{n.lineno}  {nm!r} shadows module-level "
                                  f"{top_binds[nm]} with {origin}")
for s in shadow: print("  SHADOWS:", s)
fails += shadow

print(f"checked {checked} function-scope relative imports")
for f in fails: print("  BROKEN:", f)
sys.exit(1 if fails else 0)
