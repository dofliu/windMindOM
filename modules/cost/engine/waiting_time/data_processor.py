"""Metocean data preprocessing for the waiting time calculation engine."""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class ProcessedData:
    """Container for cleaned metocean data and metadata."""

    df: pd.DataFrame
    time_step_hours: float
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    record_count: int
    statistics: dict = field(default_factory=dict)


def process_metocean_data(df: pd.DataFrame) -> ProcessedData:
    """Load and clean metocean data from a DataFrame.

    Args:
        df: DataFrame with columns [timestamp, vw, hs, hsd_max, hsd_min].

    Returns:
        ProcessedData with cleaned DataFrame and metadata.
    """
    required_cols = ["timestamp", "vw", "hs", "hsd_max", "hsd_min"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Detect time step from first two records
    if len(df) < 2:
        raise ValueError("Need at least 2 records to determine time step")
    time_step = df["timestamp"].iloc[1] - df["timestamp"].iloc[0]
    time_step_hours = time_step.total_seconds() / 3600.0

    # Forward-fill small gaps (up to 1 missing step)
    value_cols = ["vw", "hs", "hsd_max", "hsd_min"]
    df[value_cols] = df[value_cols].ffill(limit=1)

    # Drop any remaining NaN rows
    df = df.dropna(subset=value_cols).reset_index(drop=True)

    statistics = {
        "vw_mean": float(df["vw"].mean()),
        "vw_max": float(df["vw"].max()),
        "hs_mean": float(df["hs"].mean()),
        "hs_max": float(df["hs"].max()),
    }

    return ProcessedData(
        df=df,
        time_step_hours=time_step_hours,
        start_date=df["timestamp"].iloc[0],
        end_date=df["timestamp"].iloc[-1],
        record_count=len(df),
        statistics=statistics,
    )


def preprocess_metocean_data(dataset_id: int, db) -> pd.DataFrame:
    """[ECN-specific] Load metocean records from SQLAlchemy DB.

    windMindOM 移植時 stub 掉：engine 層保持與 storage 解耦，從 DB 載入由
    adapter 層做（modules/cost/adapter.py，待 WMOM-20260504-06）。
    Engine 內部與 K13 test 都從 CSV 讀，不會走到這個 path。
    """
    raise NotImplementedError(
        "preprocess_metocean_data() 是 ECN 的 SQLAlchemy 便利函數，"
        "windMindOM engine 層不直接依賴 ORM。請從 CSV 載入後 call "
        "process_metocean_data(df) 或在 modules/cost/adapter.py 實作載入邏輯。"
    )
