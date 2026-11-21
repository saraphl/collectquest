"""
Check every image the code names: it exists, ships with the add-on and is named the project's way.
Run after adding, renaming or moving an image. Exit 1 = a check failed.

    python3 tests/general/test_image_references.py
"""
import importlib
import pathlib
import re
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.parent))
for name in ("aqt", "aqt.qt", "aqt.utils", "aqt.theme", "anki", "anki.collection"):
    mod = types.ModuleType(name)
    mod.__getattr__ = lambda n: types.SimpleNamespace()
    sys.modules.setdefault(name, mod)
sys.modules["aqt"].mw = None
pkg = types.ModuleType("cq")
pkg.__path__ = [str(ROOT)]
sys.modules["cq"] = pkg

shop = importlib.import_module("cq.src.shop")

IMAGES = ROOT / "images"
# In the repository, but left out of the release (build.yml) and the deploy.
NOT_SHIPPED = {"screenshots", "unused"}
# Loaded by number, so no file name appears in the code.
BY_NUMBER = {"house"}

FAILS = []


def check(label, problems):
    print(f"  {'ok  ' if not problems else 'FAIL'} {label}")
    for problem in problems:
        print(f"       {problem}")
    FAILS.extend(problems)


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower().replace("'", "")).strip("_")


# Every quoted "folder/name.png" in the source, with the first place that names it.
named = {}
for path in sorted((ROOT / "src").rglob("*.py")):
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for ref in re.findall(r"""["']([^"'{}]+\.png)["']""", line):
            named.setdefault(ref, f"{path.relative_to(ROOT)}:{n}")

files = sorted(p.relative_to(IMAGES).as_posix() for p in IMAGES.rglob("*") if p.is_file())

print(f"{len(named)} images named in src/, {len(files)} files in images/")
check("every image the code names exists",
      [f"{where} names {ref}, which is not in images/" for ref, where in named.items()
       if not (IMAGES / ref).is_file()])
check("none of them is left out of the release",
      [f"{where} names {ref}, but images/{ref.split('/')[0]} does not ship" for ref, where in named.items()
       if ref.split("/")[0] in NOT_SHIPPED])
check("every file is folder/snake_case.png",
      [f"images/{f}" for f in files if not re.fullmatch(r"[a-z0-9_]+/[a-z0-9_]+\.png", f)])
check("every item's image carries the item's name",
      [f"{c['name']}: {c['image']} should be collectibles/{slug(c['name'])}.png" for c in shop.COLLECTIBLES
       if c["image"] != f"collectibles/{slug(c['name'])}.png"])
check("every shipped image is used",
      [f"images/{f} is named nowhere in src/; move it to images/unused" for f in files
       if f.split("/")[0] not in NOT_SHIPPED | BY_NUMBER and f not in named])

sys.exit(1 if FAILS else 0)
