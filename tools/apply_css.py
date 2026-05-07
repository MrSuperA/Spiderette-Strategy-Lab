#!/usr/bin/env python3
import re, sys
from pathlib import Path

INDEX = Path(__file__).resolve().parent.parent / "src" / "ui" / "static" / "index.html"

def main():
    if not INDEX.exists():
        print(f"ERROR: {INDEX} not found", file=sys.stderr)
        sys.exit(1)
    raw = INDEX.read_text(encoding="utf-8")
    m_open = re.search(r"<style[^>]*>", raw, re.IGNORECASE)
    m_close = re.search(r"</style>", raw, re.IGNORECASE)
    if not m_open or not m_close:
        print("ERROR: Could not locate style tags", file=sys.stderr)
        sys.exit(1)
    before = raw[: m_open.end()]
    after  = raw[m_close.start():]
    css_path = Path(__file__).resolve().parent / "new_theme.css"
    new_css = css_path.read_text(encoding="utf-8")
    output = before + chr(10) + new_css + chr(10) + after
    INDEX.write_text(output, encoding="utf-8")
    print(f"Updated {INDEX}")
    print(f"CSS length: {len(new_css)} chars")

if __name__ == "__main__":
    main()
