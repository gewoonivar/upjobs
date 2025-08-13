from __future__ import annotations

import json
import os
from typing import Any, Iterable

import gspread

from .. import config


def get_client() -> gspread.Client:
    """Authenticate via OAuth user credentials (no service account).

    Expects either env vars or config defaults for client and token files.
    - GOOGLE_OAUTH_CLIENT_FILE
    - GOOGLE_OAUTH_TOKEN_FILE
    """
    client_file = os.getenv("GOOGLE_OAUTH_CLIENT_FILE", str(config.GOOGLE_OAUTH_CLIENT_FILE))
    token_file = os.getenv("GOOGLE_OAUTH_TOKEN_FILE", str(config.GOOGLE_OAUTH_TOKEN_FILE))
    return gspread.oauth(
        credentials_filename=client_file,
        authorized_user_filename=token_file,
    )


def open_spreadsheet(client: gspread.Client, sheet_id: str):
    return client.open_by_key(sheet_id)


def ensure_worksheet(spreadsheet, title: str, cols: int = 50):
    try:
        return spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=1, cols=cols)


def ensure_headers(ws, headers: list[str]) -> None:
    cur = ws.row_values(1)
    if cur == headers:
        return
    if not cur:
        ws.update("1:1", [headers])
    else:
        ws.resize(rows=max(ws.row_count, 1))
        ws.update("1:1", [headers])


def read_index_by_key(ws, key_col_name: str) -> dict[str, int]:
    headers = ws.row_values(1)
    if key_col_name not in headers:
        return {}
    key_idx = headers.index(key_col_name) + 1
    column_values = ws.col_values(key_idx)[1:]  # skip header
    idx: dict[str, int] = {}
    for i, val in enumerate(column_values, start=2):
        if val:
            idx[val] = i
    return idx


def _normalize_row(headers: list[str], row: dict[str, Any]) -> list[Any]:
    normalized: list[Any] = []
    for h in headers:
        v = row.get(h)
        if isinstance(v, list):
            normalized.append(", ".join(str(x) for x in v))
        elif isinstance(v, dict):
            normalized.append(json.dumps(v, ensure_ascii=False))
        else:
            normalized.append(v)
    return normalized


def _col_letters(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def upsert_rows(
    ws, headers: list[str], rows: Iterable[dict[str, Any]], key: str, batch_size: int = 200
) -> None:
    ensure_headers(ws, headers)
    index = read_index_by_key(ws, key)

    updates: list[tuple[int, list[Any]]] = []
    appends = []

    for row in rows:
        if not row.get(key):
            continue
        target_row = index.get(str(row[key]))
        vals = _normalize_row(headers, row)
        if target_row:
            updates.append((target_row, vals))
        else:
            appends.append(vals)

    # Perform updates in chunks using A1 notation
    last_col = _col_letters(len(headers))
    for i in range(0, len(updates), batch_size):
        chunk = updates[i : i + batch_size]
        if not chunk:
            continue
        ws.batch_update(
            [
                {"range": f"A{row_num}:{last_col}{row_num}", "values": [vals]}
                for row_num, vals in chunk
            ],
            value_input_option="USER_ENTERED",
        )

    # Appends
    for i in range(0, len(appends), batch_size):
        ws.append_rows(appends[i : i + batch_size], value_input_option="USER_ENTERED")
