"""Download the live Consignee master database CSV into memory with pandas."""

from __future__ import annotations

import pandas as pd

from config import MASTER_DB_CSV_URL, MASTER_DB_SOURCE_NAME

MAX_EXCERPT_CHARS = 80_000


def load_master_database_excerpt() -> str:
    """Fetch the published Google Sheets CSV and serialize Name / Address rows.

    The DataFrame stays in memory only long enough to build the Gemini prompt
    excerpt. No local Excel file is read.
    """
    try:
        frame = pd.read_csv(MASTER_DB_CSV_URL)
    except Exception as exc:
        raise RuntimeError(
            "Could not download the live Consignee database CSV. "
            "Check the network connection and that the Google Sheet is still "
            f"published.\n{exc}"
        ) from exc

    frame = frame.dropna(how="all")
    frame = frame.dropna(how="all", axis=1)
    if frame.empty:
        return (
            "[Master Database CSV downloaded but contained no rows. "
            "Use 'Unrecognized Consignee'.]"
        )

    if not _has_name_address_columns(frame):
        frame = pd.read_csv(MASTER_DB_CSV_URL, header=1)
        frame = frame.dropna(how="all")
        frame = frame.dropna(how="all", axis=1)

    name_col, address_col = _resolve_name_address_columns(frame)
    lines = [
        f"Source: {MASTER_DB_SOURCE_NAME}",
        f"URL: {MASTER_DB_CSV_URL}",
        "Name | Address",
    ]

    for _, row in frame.iterrows():
        name = _cell_text(row.get(name_col) if name_col else None)
        address = _cell_text(row.get(address_col) if address_col else None)
        if not name and not address:
            continue
        if not name:
            name = "Unrecognized Consignee"
        lines.append(f"{name} | {address}")
        if sum(len(line) for line in lines) > MAX_EXCERPT_CHARS:
            lines.append("[Master Database truncated for prompt size.]")
            break

    if len(lines) <= 3:
        return (
            "[Master Database CSV had no Name/Address records. "
            "Use 'Unrecognized Consignee'.]"
        )
    return "\n".join(lines)


def _has_name_address_columns(frame: pd.DataFrame) -> bool:
    labels = [_normalize_header(col) for col in frame.columns]
    return "name" in labels and "address" in labels


def _resolve_name_address_columns(frame: pd.DataFrame) -> tuple[object | None, object | None]:
    name_col = address_col = None
    for col in frame.columns:
        label = _normalize_header(col)
        if label == "name":
            name_col = col
        elif label == "address":
            address_col = col
    if name_col is None or address_col is None:
        non_unnamed = [col for col in frame.columns if not str(col).startswith("Unnamed")]
        if len(non_unnamed) >= 2:
            name_col, address_col = non_unnamed[0], non_unnamed[1]
        elif len(frame.columns) >= 2:
            name_col, address_col = frame.columns[0], frame.columns[1]
    return name_col, address_col


def _normalize_header(value: object) -> str:
    return str(value).strip().lower()


def _cell_text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none"}:
        return ""
    return " ".join(text.split())
