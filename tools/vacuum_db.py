"""VACUUM INTO + swap CLI for SQLite farm DB（WMOM-20260505-01）。

普通 ``VACUUM`` 需要約 2× DB size 暫時磁碟空間（41.9 GB DB → 84 GB free 才能跑），
``VACUUM INTO 'new.db'`` 只需 1× 但可指定路徑（如另一顆 SSD）+ 跑完手動 swap。

使用情境：
  WMOM-20260505-01 修補完 cleanup retention + broker dedupe 後，原本 41.9 GB 的
  彰化 farm DB 內 1081 萬 row snapshots 會被 cleanup 刪掉，但 SQLite 不會自動
  歸還磁碟。本工具把活的 page 寫到新檔再 swap，磁碟立刻釋放。

主要動作：
  1. 先跑 ``Storage.run_cleanup`` 清掉超過 retention 的 row（可選 ``--no-cleanup``）
  2. ``VACUUM INTO`` 寫到 sibling 路徑（``wind_farm.db.vacuumed``）
  3. 比對兩檔 size + 取得 row count 一致性
  4. （非 ``--dry-run``）原檔 rename → ``.bak``，新檔 rename → 原檔名

範例：
  # Dry run — 看會省多少不動
  python tools/vacuum_db.py "modules/monitoring/data/farms/彰化離岸風場台電/wind_farm.db" --dry-run

  # 實際做（會 cleanup + VACUUM + swap）
  python tools/vacuum_db.py "modules/monitoring/data/farms/彰化離岸風場台電/wind_farm.db"

  # 不要 cleanup，只 VACUUM（如已用其他方式清過）
  python tools/vacuum_db.py "modules/monitoring/data/farms/彰化離岸風場台電/wind_farm.db" --no-cleanup
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "modules" / "monitoring"))


def fmt_size(bytes_: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if bytes_ < 1024:
            return f"{bytes_:.2f} {unit}"
        bytes_ /= 1024  # type: ignore[assignment]
    return f"{bytes_:.2f} TB"  # type: ignore[str-format]


def get_table_counts(db_path: Path) -> dict:
    """取每個表的 row count（給比對用）。"""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = [
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    finally:
        con.close()


def _check_app_stopped(db_path: Path) -> str | None:
    """嘗試取得 EXCLUSIVE lock 確認沒有 app 持有 DB；回傳錯誤訊息或 None。

    WMOM-20260505-01 finding #6：避免 swap 中途 app 寫入造成資料漂移。
    """
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=rw", uri=True, timeout=2.0)
        try:
            con.execute("BEGIN EXCLUSIVE")
            con.execute("ROLLBACK")
        finally:
            con.close()
    except sqlite3.OperationalError as e:
        return f"DB 被鎖住，請先停止 app（FastAPI / data broker）：{e}"
    return None


def run(db_path: Path, *, do_cleanup: bool, dry_run: bool,
        snapshots_retention_days: int = 7) -> int:
    if not db_path.exists():
        print(f"❌ DB not found: {db_path}", file=sys.stderr)
        return 2

    print(f"=== VACUUM tool ===")
    print(f"Target DB:  {db_path}")
    print(f"Mode:       {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    # Pre-check: live mode 才強制要求 app 停機（dry-run 只讀，不會干擾）
    if not dry_run:
        err = _check_app_stopped(db_path)
        if err:
            print(f"❌ {err}", file=sys.stderr)
            print(f"   請停掉 python run.py / FastAPI server 後再試", file=sys.stderr)
            return 5

    size_before = db_path.stat().st_size
    print(f"Size before:  {fmt_size(size_before)} ({size_before:,} bytes)")

    counts_before = get_table_counts(db_path)
    print(f"Row counts before:")
    for t, n in counts_before.items():
        print(f"  {t:<30} {n:>15,}")
    print()

    # Step 1: cleanup
    if do_cleanup:
        print(f"--- Step 1/3: run_cleanup (snapshots_retention_days={snapshots_retention_days}) ---")
        if dry_run:
            print("  [dry-run] skip")
        else:
            from server.storage import Storage  # type: ignore
            s = Storage(db_path=str(db_path))
            res = s.run_cleanup(snapshots_retention_days=snapshots_retention_days)
            print(f"  removed: raw={res['deleted_raw']:,}  1m={res['deleted_1m']:,}  "
                  f"snapshots={res['deleted_snapshots']:,}")
            # close connection (Storage 用 thread-local)
            try:
                s._local.conn.close()  # type: ignore[attr-defined]
            except Exception:
                pass
        print()

    # Step 2: VACUUM INTO
    target = db_path.with_suffix(db_path.suffix + ".vacuumed")
    # 防呆：確認 target 在 source DB 同目錄、且尾碼為 .vacuumed（避免 path traversal）
    assert target.parent == db_path.parent
    assert target.name.endswith(".vacuumed")
    if target.exists():
        print(f"⚠ Removing stale {target.name}")
        target.unlink()

    print(f"--- Step 2/3: VACUUM INTO {target.name} ---")
    if dry_run:
        print("  [dry-run] skip — VACUUM 不執行，不產生 .vacuumed 檔")
    else:
        t0 = time.time()
        # 對 source DB 開「新 connection」做 VACUUM INTO（原 thread 的 connection 可能在 WAL）
        # SQLite 不支援 VACUUM INTO 的 parameter binding（？佔位）— 這裡用 single-quote
        # doubling escape，且本工具僅供本機 ops 使用，不暴露於 web 端。
        # （path 防呆見上方 assertion）
        con = sqlite3.connect(str(db_path))
        try:
            escaped = str(target).replace("'", "''")
            con.execute(f"VACUUM INTO '{escaped}'")
        finally:
            con.close()
        elapsed = time.time() - t0
        size_vacuumed = target.stat().st_size
        print(f"  done in {elapsed:.1f}s")
        print(f"  vacuumed size: {fmt_size(size_vacuumed)}")
        print(f"  saved:         {fmt_size(size_before - size_vacuumed)}  "
              f"({100 * (size_before - size_vacuumed) / size_before:.1f}%)")

        # 比對 row count
        counts_after = get_table_counts(target)
        diffs = []
        for t in counts_before:
            if counts_before[t] != counts_after.get(t, 0):
                diffs.append((t, counts_before[t], counts_after.get(t, 0)))
        if diffs and not do_cleanup:
            # 沒做 cleanup 卻 row 數變了 = 異常
            print(f"⚠ Row count mismatch (no cleanup but rows differ):")
            for t, before, after in diffs:
                print(f"  {t}: {before:,} → {after:,}")
            return 3
        print(f"  row counts after vacuum:")
        for t, n in counts_after.items():
            mark = "" if counts_before.get(t) == n else f"  (was {counts_before.get(t):,})"
            print(f"    {t:<30} {n:>15,}{mark}")
    print()

    # Step 3: swap
    print(f"--- Step 3/3: swap ---")
    if dry_run:
        print(f"  [dry-run] would: mv {db_path.name} → {db_path.name}.bak ; "
              f"mv {target.name} → {db_path.name}")
    else:
        backup = db_path.with_suffix(db_path.suffix + ".bak")
        if backup.exists():
            print(f"  ⚠ backup already exists: {backup} — please remove first")
            return 4

        # 同 farm 的 -wal / -shm 也要刪（VACUUM INTO 寫的是純 DB，新檔起跑時自動建 -wal）
        for sidecar in (db_path.with_name(db_path.name + "-wal"),
                        db_path.with_name(db_path.name + "-shm")):
            if sidecar.exists():
                print(f"  removing sidecar: {sidecar.name}")
                sidecar.unlink()

        print(f"  mv {db_path.name} → {backup.name}")
        shutil.move(str(db_path), str(backup))
        print(f"  mv {target.name} → {db_path.name}")
        shutil.move(str(target), str(db_path))

        size_after = db_path.stat().st_size
        print()
        print(f"✅ Done. {fmt_size(size_before)} → {fmt_size(size_after)}  "
              f"(saved {fmt_size(size_before - size_after)}, {100*(size_before-size_after)/size_before:.1f}%)")
        print(f"   Backup at: {backup}")
        print(f"   Verify the app works，then 'rm {backup.name}' to release backup space.")

    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("db_path", type=Path, help="Path to wind_farm.db")
    p.add_argument("--no-cleanup", action="store_true",
                   help="Skip run_cleanup before VACUUM (default: do cleanup)")
    p.add_argument("--snapshots-retention-days", type=int, default=7,
                   help="Cleanup retention for turbine_snapshots (default: 7)")
    p.add_argument("--dry-run", action="store_true",
                   help="Estimate savings without modifying anything")
    args = p.parse_args()

    return run(
        args.db_path,
        do_cleanup=not args.no_cleanup,
        dry_run=args.dry_run,
        snapshots_retention_days=args.snapshots_retention_days,
    )


if __name__ == "__main__":
    sys.exit(main())
