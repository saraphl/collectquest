"""
Check that a save written by another add-on version loads with the shop stock and the rolled next
craft cleared, and that a save from the same version keeps both. Exit 1 = something is off.

    python3 tests/test_version_reset.py
"""
import importlib, pathlib, sys, tempfile, types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))
for name in ("aqt", "aqt.qt", "aqt.utils", "aqt.theme", "anki", "anki.collection"):
    mod = types.ModuleType(name)
    mod.__getattr__ = lambda n: types.SimpleNamespace()
    sys.modules.setdefault(name, mod)
sys.modules["aqt"].mw = None
pkg = types.ModuleType("cq")
pkg.__path__ = [str(ROOT)]
sys.modules["cq"] = pkg

storage = importlib.import_module("cq.src.storage")
shop = importlib.import_module("cq.src.shop")

FAILS = []
SLOTS = [{"type": "collectible", "id": "potion_blue_4"}]


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: {got}" + ("" if ok else f" (want {want})"))
    if not ok:
        FAILS.append(label)


def write_save(saved_with):
    d = storage._default_state()
    d["shop_daily_slots"] = list(SLOTS)
    d["next_craft_id"] = "potion_blue_2"
    storage._version_cache = saved_with or "x"  # save() stamps whatever get_version() returns
    storage.save(d)
    if not saved_with:  # an older save that predates the version stamp
        raw = storage.decode_from_hashsave(open(storage._path()).read())
        raw["saved_with_version"] = ""
        raw["_hash"] = storage.compute_hash(raw)
        open(storage._path(), "w").write(storage.encode_to_hashsave(raw))


with tempfile.TemporaryDirectory() as tmp:
    storage.set_profile_folder(tmp)

    print("a save from an older version")
    write_save("2.4.1")
    storage._version_cache = "2.4.2"
    d = storage.load()
    check("stock cleared", d["shop_daily_slots"], [])
    check("next craft cleared", d["next_craft_id"], None)
    d["shop_daily_slots"] = shop.get_daily_slots(d, 80)
    storage.save(d)
    again = storage.load()
    check("fresh stock survives the next load", again["shop_daily_slots"], d["shop_daily_slots"])
    check("and the save now carries the new version", again["saved_with_version"], "2.4.2")

    print("\na save from the same version")
    write_save("2.4.2")
    d = storage.load()
    check("stock kept", d["shop_daily_slots"], SLOTS)
    check("next craft kept", d["next_craft_id"], "potion_blue_2")

    print("\na save with no version stamp")
    write_save("")
    storage._version_cache = "2.4.2"
    d = storage.load()
    check("stock kept", d["shop_daily_slots"], SLOTS)
    check("and the hash still checks out", d.get("_hash_invalid", False), False)

if FAILS:
    print(f"\n{len(FAILS)} FAILED: {', '.join(FAILS)}")
    sys.exit(1)
print("\nall version reset checks passed")
