from __future__ import annotations

import json
import sys
from pathlib import Path

from research_agent.repo_hygiene import scan_repo_hygiene


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    issues = scan_repo_hygiene(root)
    print(json.dumps({"root": str(root), "issues": issues}, ensure_ascii=False, indent=2))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
