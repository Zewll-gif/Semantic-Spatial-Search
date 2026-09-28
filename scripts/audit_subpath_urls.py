"""Fail when first-party frontend URLs escape the configured document base."""
from __future__ import annotations

import re
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = APP_ROOT / "frontend"
TEXT_SUFFIXES = {".html", ".js", ".css", ".json"}
ROOT_APP_LITERAL = re.compile(
    r"(?P<quote>[\"'`])/(?P<prefix>api|assets|aoi|analysis-assets|terrain|vendor|static|styles|app|favicon)"
    r"(?:/|\.|\?|`|[\"'])"
)


def main() -> int:
    violations: list[str] = []
    for path in FRONTEND_ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES or "vendor" in path.parts:
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if ROOT_APP_LITERAL.search(line):
                violations.append(f"{path.relative_to(APP_ROOT)}:{line_number}: {line.strip()}")

    index = (FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
    if '<base href="./"/>' not in index:
        violations.append("frontend/index.html: missing portable <base href=\"./\"/>")
    if 'src="app-base.js?' not in index:
        violations.append("frontend/index.html: app-base.js must load before application scripts")

    if violations:
        print("SUBPATH URL AUDIT: FAIL")
        print("\n".join(violations))
        return 1
    print("SUBPATH URL AUDIT: PASS (no first-party root-absolute frontend URLs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
