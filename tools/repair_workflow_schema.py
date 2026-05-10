"""Dev tool — 偵測 + 修復 farm DB 中過時的 workflow schema。

問題背景：
    digiWindTurbine 早期 (M0) 的 ``work_orders`` 表 schema 與 windMindOM M3+ 完全不
    相容（舊：10 欄 turbine_id/turbine_name/technician_id/fault_description；
    新：41 欄 business_key/type/priority/... etc）。SQLAlchemy ``Base.metadata.
    create_all`` 是「create if not exists」不做 ALTER，所以遺留的舊表卡住新版查詢
    （sqlite3.OperationalError: no such column: work_orders.business_key）。

使用：
    python tools/repair_workflow_schema.py                    # dry-run 列出問題 farm
    python tools/repair_workflow_schema.py --apply            # 實際修復
    python tools/repair_workflow_schema.py --apply --farm 台中港曲風場   # 限定 farm

修復動作（only when --apply）：
    - DROP TABLE work_orders / work_order_event_log / work_order_progress_notes（若 schema 不符且為空）
    - DELETE 孤兒 signoff_chains / signoff_steps / signoff_history（subject 指向不存在的 work_order）
    - 結束後讓 backend 啟動時 ``Base.metadata.create_all`` 自動建新表
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Iterable

# 期望（M3+）work_orders 必備欄位 — 任一缺失即視為舊 schema
_EXPECTED_WO_COLS = {
    "business_key", "type", "priority", "dispatched_at", "finished_at",
    "actual_hours", "followup_kind",
}
# 對應的支援表（同樣可能 schema drift；表存在就一併 drop 重建）
_WO_DEPENDENT_TABLES = ("work_order_event_log", "work_order_progress_notes")


def _get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _row_count(conn: sqlite3.Connection, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _scan_orphan_signoff_chains(conn: sqlite3.Connection) -> int:
    """簽核 chain subject_type='work_order' 但 subject_id 不存在 → 孤兒。

    Edge case：若 work_orders 表已被 drop（前次 repair 半途中斷的狀態），
    所有 subject_type='work_order' 的 chain 都是孤兒。
    """
    if not _table_exists(conn, "signoff_chains"):
        return 0
    if not _table_exists(conn, "work_orders"):
        # work_orders 不存在 → 所有 work_order subject_type 的 chain 都是孤兒
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM signoff_chains WHERE subject_type='work_order'"
            ).fetchone()[0]
        )
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM signoff_chains sc
            WHERE sc.subject_type = 'work_order'
              AND sc.subject_id NOT IN (SELECT id FROM work_orders)
            """
        ).fetchone()[0]
    )


def diagnose_db(db_path: Path) -> dict:
    """回傳 farm DB 的修復需求 dict。"""
    conn = sqlite3.connect(str(db_path))
    try:
        wo_exists = _table_exists(conn, "work_orders")
        wo_cols = _get_columns(conn, "work_orders") if wo_exists else set()
        missing = _EXPECTED_WO_COLS - wo_cols
        wo_outdated = wo_exists and bool(missing)
        wo_rows = _row_count(conn, "work_orders") if wo_exists else 0

        dependent_state = {
            t: {"exists": _table_exists(conn, t), "rows": _row_count(conn, t)}
            for t in _WO_DEPENDENT_TABLES
        }
        orphan_chains = _scan_orphan_signoff_chains(conn)

        return {
            "db_path": str(db_path),
            "wo_table_outdated": wo_outdated,
            "wo_missing_cols": sorted(missing),
            "wo_rows": wo_rows,
            "dependent": dependent_state,
            "orphan_signoff_chains": orphan_chains,
            "needs_repair": wo_outdated or orphan_chains > 0,
        }
    finally:
        conn.close()


def repair_db(db_path: Path, *, dry_run: bool = True) -> list[str]:
    """執行修復；dry_run=True 只列動作不執行。回傳動作 log 字串列表。"""
    actions: list[str] = []
    conn = sqlite3.connect(str(db_path))
    try:
        info = diagnose_db(db_path)
        if not info["needs_repair"]:
            return ["（無需修復）"]

        if info["wo_table_outdated"]:
            wo_rows = info["wo_rows"]
            if wo_rows > 0:
                actions.append(
                    f"❌ work_orders 有 {wo_rows} 筆資料 + 舊 schema → 需手動處理（拒絕自動 drop）"
                )
                # 不繼續，讓 caller 看到警告
                return actions
            actions.append("DROP TABLE work_orders（0 rows，舊 schema）")
            for dep in _WO_DEPENDENT_TABLES:
                if info["dependent"][dep]["exists"]:
                    rows = info["dependent"][dep]["rows"]
                    actions.append(f"DROP TABLE {dep}（{rows} rows）")

        if info["orphan_signoff_chains"] > 0:
            n = info["orphan_signoff_chains"]
            actions.append(
                f"DELETE {n} 筆孤兒 signoff_chains（subject_type='work_order' 指向不存在的 work_order）"
            )
            actions.append(
                "DELETE 連帶的 signoff_steps + signoff_history（FK cascade）"
            )

        if dry_run:
            return actions

        # ── Apply ──
        # 先抓孤兒 chain ids（在 DROP work_orders 之前，否則 NOT IN 查不到）。
        # 若 work_orders 已不存在（前次 repair 半途中斷），所有 work_order subject 都是孤兒。
        orphan_ids: list[str] = []
        if info["orphan_signoff_chains"] > 0:
            if _table_exists(conn, "work_orders"):
                cur = conn.execute(
                    """
                    SELECT sc.id FROM signoff_chains sc
                    WHERE sc.subject_type='work_order'
                      AND sc.subject_id NOT IN (SELECT id FROM work_orders)
                    """
                )
            else:
                cur = conn.execute(
                    "SELECT id FROM signoff_chains WHERE subject_type='work_order'"
                )
            orphan_ids = [r[0] for r in cur.fetchall()]

        if info["wo_table_outdated"] and info["wo_rows"] == 0:
            for dep in _WO_DEPENDENT_TABLES:
                if info["dependent"][dep]["exists"]:
                    conn.execute(f"DROP TABLE {dep}")
            conn.execute("DROP TABLE work_orders")
        if orphan_ids:
            qmarks = ",".join("?" * len(orphan_ids))
            # signoff_history → signoff_steps → signoff_chains（依 FK 順序刪）
            if _table_exists(conn, "signoff_history"):
                conn.execute(
                    f"DELETE FROM signoff_history WHERE chain_id IN ({qmarks})",
                    orphan_ids,
                )
            if _table_exists(conn, "signoff_steps"):
                conn.execute(
                    f"DELETE FROM signoff_steps WHERE chain_id IN ({qmarks})",
                    orphan_ids,
                )
            conn.execute(
                f"DELETE FROM signoff_chains WHERE id IN ({qmarks})",
                orphan_ids,
            )
        conn.commit()
        actions.append("✅ 已 commit")
    finally:
        conn.close()
    return actions


def find_farm_dbs(base_dir: Path, only_farm: str | None = None) -> Iterable[Path]:
    farms_dir = base_dir / "modules" / "monitoring" / "data" / "farms"
    if not farms_dir.is_dir():
        return []
    paths: list[Path] = []
    for p in sorted(farms_dir.iterdir()):
        if not p.is_dir():
            continue
        if only_farm and p.name != only_farm:
            continue
        db = p / "wind_farm.db"
        if db.exists():
            paths.append(db)
    return paths


def main() -> int:
    # Windows console 預設 cp950 (Big5)，不支援 emoji + 中文 farm 名 → 強制 UTF-8
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="實際執行修復（預設 dry-run）")
    parser.add_argument("--farm", type=str, default=None,
                        help="只處理指定 farm_id（預設掃所有）")
    parser.add_argument("--root", type=str, default=".",
                        help="windMindOM repo 根目錄（預設當下）")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    dbs = list(find_farm_dbs(root, only_farm=args.farm))
    if not dbs:
        print(f"找不到 farm DB（root={root}, farm={args.farm}）", file=sys.stderr)
        return 1

    print(f"==== Workflow schema repair {'[APPLY]' if args.apply else '[DRY-RUN]'} ====")
    any_repair_needed = False
    for db in dbs:
        # farm 名稱在某些 console 顯示為亂碼但 Path 操作 OK
        rel = db.relative_to(root)
        print(f"\n→ {rel}")
        info = diagnose_db(db)
        print(f"   wo_table_outdated={info['wo_table_outdated']}, "
              f"wo_rows={info['wo_rows']}, "
              f"missing_cols={info['wo_missing_cols']}, "
              f"orphan_chains={info['orphan_signoff_chains']}")
        if not info["needs_repair"]:
            print("   (skip)")
            continue
        any_repair_needed = True
        actions = repair_db(db, dry_run=not args.apply)
        for a in actions:
            print(f"   - {a}")

    if not any_repair_needed:
        print("\n✅ 所有 farm DB schema 都對得上，無需修復")
        return 0
    if not args.apply:
        print("\n⚠ 上述為 dry-run。確認後加 --apply 實際執行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
