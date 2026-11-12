"""
Run every test script at once and list which passed. Exit 1 = a test failed.

    python3 tests/run.py              # everything
    python3 tests/run.py shop streak  # only those folders
"""
import concurrent.futures
import os
import pathlib
import subprocess
import sys
import time

TESTS = pathlib.Path(__file__).resolve().parent
ROOT = TESTS.parent


def run(path):
    start = time.perf_counter()
    done = subprocess.run([sys.executable, str(path)], cwd=ROOT, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return path, done.returncode, time.perf_counter() - start, done.stdout


def main():
    folders = sys.argv[1:]
    unknown = [f for f in folders if not (TESTS / f).is_dir()]
    if unknown:
        print("no such test folder: " + ", ".join(unknown))
        return 2
    paths = sorted(p for p in TESTS.glob("*/test_*.py") if not folders or p.parent.name in folders)
    start = time.perf_counter()
    failed = []
    # The scripts are separate processes, so the threads only wait on them.
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count()) as pool:
        for path, code, took, output in pool.map(run, paths):
            name = path.relative_to(TESTS)
            print(f"  {'ok  ' if code == 0 else 'FAIL'} {took:5.1f}s  {name}")
            if code != 0:
                failed.append((name, output))
    for name, output in failed:
        print(f"\n--- {name} ---\n{output.rstrip()}")
    total = time.perf_counter() - start
    print(f"\n{len(paths) - len(failed)} of {len(paths)} passed in {total:.1f}s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
