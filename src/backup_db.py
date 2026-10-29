"""نسخة احتياطية عبر SQLite Backup API ثم integrity_check."""
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_db  # noqa: E402

BACKUP_DIR = Path(r"C:\Users\mesue\.maestro\backups")


def backup(db_path=None, out_dir=None):
    db_path = Path(db_path or usage_db.DB_PATH)
    out_dir = Path(out_dir or BACKUP_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / ("flow_usage_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".sqlite3")
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(dest))
    with dst:
        src.backup(dst)
    result = dst.execute("PRAGMA integrity_check").fetchone()[0]
    src.close()
    dst.close()
    if result != "ok":
        raise RuntimeError("فشل integrity_check على النسخة: " + result)
    return dest, result


if __name__ == "__main__":
    path, res = backup()
    print(str(path) + " integrity_check=" + res)
