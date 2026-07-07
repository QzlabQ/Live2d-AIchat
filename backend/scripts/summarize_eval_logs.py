from __future__ import annotations

import argparse
import re
from pathlib import Path


def parse_log(path: Path) -> dict[int, dict[str, object]]:
    rows: dict[int, dict[str, object]] = {}
    current: int | None = None

    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\[(\d+)\] Q: (.*)", line)
        if match:
            current = int(match.group(1))
            rows[current] = {"question": match.group(2), "passed": None}
            continue

        if current is None:
            continue

        if "result: PASS" in line:
            rows[current]["passed"] = True
        elif "result: FAIL" in line:
            rows[current]["passed"] = False

    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-log", required=True)
    parser.add_argument("--compare-log", required=True)
    args = parser.parse_args()

    base_rows = parse_log(Path(args.base_log))
    compare_rows = parse_log(Path(args.compare_log))

    print("BASE_FAILS")
    for index in sorted(key for key, row in base_rows.items() if row["passed"] is False):
        print(f"{index}\t{base_rows[index]['question']}")

    print("COMPARE_FAILS")
    for index in sorted(key for key, row in compare_rows.items() if row["passed"] is False):
        print(f"{index}\t{compare_rows[index]['question']}")

    print("COMPARE_WORSE_THAN_BASE")
    for index in sorted(set(base_rows) | set(compare_rows)):
        base_pass = base_rows.get(index, {}).get("passed")
        compare_pass = compare_rows.get(index, {}).get("passed")
        if base_pass and compare_pass is False:
            print(f"{index}\t{base_rows[index]['question']}")

    print("COMPARE_BETTER_THAN_BASE")
    for index in sorted(set(base_rows) | set(compare_rows)):
        base_pass = base_rows.get(index, {}).get("passed")
        compare_pass = compare_rows.get(index, {}).get("passed")
        if base_pass is False and compare_pass:
            print(f"{index}\t{base_rows[index]['question']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
