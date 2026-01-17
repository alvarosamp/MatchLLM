from __future__ import annotations

import sqlite3
from pathlib import Path


def main() -> None:
    db_path = Path("data/matchllm.sqlite")
    print("sqlite exists:", db_path.exists())
    print("path:", db_path.resolve())

    if not db_path.exists():
        return

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    for table in ["document_cache", "match_cache", "editais", "produtos", "matches"]:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        row = cur.fetchone()
        print("\nTABLE", table, "exists:", bool(row))
        if not row:
            continue
        cur.execute(f"PRAGMA table_info({table})")
        for col in cur.fetchall():
            # cid,name,type,notnull,dflt_value,pk
            print(" ", col)

    conn.close()


if __name__ == "__main__":
    main()
