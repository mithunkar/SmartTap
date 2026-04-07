from __future__ import annotations

import json
import sys

from smarttap_service import process_query


def main() -> int:
    if len(sys.argv) != 2:
        print('Usage: python smarttap.py "Show temperature in Corvallis for July 2024"')
        return 1

    query = sys.argv[1]
    result = process_query(query)

    if not result["success"]:
        print(f"Error: {result['error']}")
        return 1

    print(f"Task: {result['spec']['task']}")
    print(json.dumps(result["summary"], indent=2, default=str))
    print(f"Chart: {result['files']['png']}")
    if result["files"].get("vega"):
        print(f"Vega: {result['files']['vega']}")
    if result["files"].get("validation"):
        print(f"Validation: {result['files']['validation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
