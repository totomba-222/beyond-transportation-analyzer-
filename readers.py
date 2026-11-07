"""File readers. One public entry point: read_report().

Every parsed record keeps src_file / src_sheet / src_row (the 1-based row number
in the original sheet), so any number on any report can be traced to its source.
Rows that are not trips (Total, sub-total, blank-driver rows) are never dropped
silently: they go to `excluded` and, when they carry numbers, to `control_totals`
so they can be checked against the recomputed detail sums.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from normalization import (file_hash, is_total_label, norm_name, norm_trip,
                           norm_trip_id, parse_date, to_number)

# header synonyms, matched on the header with all non-alphanumerics removed
SYN = {
    "driver": {"drivername", "driver", "drivers"},
    "trip_id": {"tripcode", "tripid", "tripnumber", "tripno", "tripnum", "trip", "runid", "confirmation", "confirmationnumber"},
    "date": {"date", "tripdate", "servicedate", "pickupdate"},
    "trip_name": {"tripname", "school", "tripdescription", "description", "route", "routename"},
    "miles": {"totalmiles", "miles", "mileage", "totalmileage"},
    "net_pay": {"netpay"},
    "gross_pay": {"grosspay"},
    "deduction": {"deduction", "deductions"},
    "spiff": {"spiff"},
    "revenue": {"revenue", "contract", "contractprice", "contractrevenue", "tripprice", "price", "totalrevenue"},
    "driver_pay": {"payment", "pay", "driverpay", "driverpayment", "driverpayments"},
    "cancel": {"cancellationreason", "cancelreason"},
}
CANON_COLS = ["src_file", "src_sheet", "src_row", "provider", "role", "state_hint",
              "driver_disp", "driver", "trip_id", "date", "trip_name", "trip_key",
              "miles", "main_amount", "revenue", "driver_pay", "gross_pay",
              "cancelled", "flags"]


def _key(h) -> str:
    return re.sub(r"[^a-z0-9]", "", str(h).lower())


@dataclass
class ParsedReport:
    filename: str
    sha256: str
    role: str                      # 'main' | 'state'
    provider: str                  # FIRST | EVERDRIVEN | STATE | UNKNOWN
    records: pd.DataFrame
    excluded: pd.DataFrame
    control_totals: pd.DataFrame
    mapping: dict = field(default_factory=dict)      # canonical field -> source header (what was assumed)
    warnings: list = field(default_factory=list)
    needs_mapping: list = field(default_factory=list)  # fields the user must map


def _find_header(raw: pd.DataFrame, max_scan=25):
    for i in range(min(max_scan, len(raw))):
        keys = [_key(v) for v in raw.iloc[i].tolist()]
        if any(k in SYN["driver"] for k in keys) and sum(any(k in s for s in SYN.values()) for k in keys) >= 2:
            return i
    return None


def _map_columns(cols, overrides=None):
    m = {}
    for c in cols:
        k = _key(c)
        for canon, syns in SYN.items():
            if k in syns and canon not in m:
                m[canon] = c
    tm = [c for c in cols if _key(c) == "totalmiles"]
    if tm:
        m["miles"] = tm[0]          # TOTAL MILES (incl. return miles) wins over MILES
    for canon, col in (overrides or {}).items():
        if col in cols:
            m[canon] = col
    return m


def _sheets_from_bytes(data: bytes, filename: str):
    low = filename.lower()
    if low.endswith(".csv"):
        yield "csv", pd.read_csv(io.BytesIO(data), header=None, dtype=object, keep_default_na=False, na_values=[""])
        return
    xl = pd.ExcelFile(io.BytesIO(data))
    for sh in xl.sheet_names:
        yield sh, xl.parse(sh, header=None, dtype=object)


def read_report(data: bytes, filename: str, role: str = "main", overrides: dict | None = None,
                state_hint: str | None = None, first_revenue_col: str = "net_pay") -> ParsedReport:
    """Parse one uploaded report. `overrides` = {canonical_field: source_header}
    is the manual column mapping supplied by the user."""
    sha = file_hash(data)
    low = filename.lower()
    if low.endswith(".pdf"):
        from pdf_reader import pdf_to_sheets
        sheets, pdf_warn = pdf_to_sheets(data)
    else:
        sheets, pdf_warn = list(_sheets_from_bytes(data, filename)), []
    recs, excl, ctrl, warns = [], [], [], list(pdf_warn)
    used_map, provider = {}, "UNKNOWN"
    ocr_used = any("OCR" in w for w in pdf_warn)

    for sheet, raw in sheets:
        raw = raw.reset_index(drop=True)
        h = _find_header(raw)
        if h is None:
            warns.append(f"Sheet '{sheet}': no recognisable header row (needs a DRIVER NAME column) - skipped.")
            continue
        cols = [str(c).strip() if not pd.isna(c) else f"unnamed_{j}" for j, c in enumerate(raw.iloc[h].tolist())]
        body = raw.iloc[h + 1:].copy()
        body.columns = cols
        m = _map_columns(cols, overrides)
        if role == "main" and "trip_id" not in m and "date" not in m:
            warns.append(f"Sheet '{sheet}': summary sheet (no trip id / date) not imported as trips - used only as reference.")
            continue
        # --- decide provider / meaning of money columns (never assume NET PAY = revenue blindly)
        is_first_layout = "net_pay" in m and "gross_pay" in m and "trip_id" in m and "revenue" not in m
        if role == "main":
            if is_first_layout:
                provider = "FIRST"
                m["main_amount"] = m.get(first_revenue_col, m["net_pay"])
            else:
                provider = "EVERDRIVEN" if "everdriven" in low or "ever driven" in low else "UNKNOWN"
                cand = m.get("revenue") or m.get("net_pay")
                if cand is None:
                    return ParsedReport(filename, sha, role, provider, pd.DataFrame(columns=CANON_COLS),
                                        pd.DataFrame(), pd.DataFrame(), m, warns + [
                                            f"Sheet '{sheet}': cannot tell which column is the company revenue."],
                                        ["main_amount"])
                m["main_amount"] = cand
                warns.append(f"Sheet '{sheet}': main revenue taken from '{cand}' (layout not a known First report) - confirm in the mapping panel.")
        else:
            provider = "STATE"
            rev = m.get("revenue") or m.get("net_pay")
            pay = m.get("driver_pay")
            if rev is None or pay is None:
                return ParsedReport(filename, sha, role, provider, pd.DataFrame(columns=CANON_COLS),
                                    pd.DataFrame(), pd.DataFrame(), m, warns,
                                    [f for f, v in (("revenue", rev), ("driver_pay", pay)) if v is None])
            m["revenue"], m["driver_pay"] = rev, pay
            if "revenue" in SYN and _key(rev) != "revenue":
                warns.append(f"'{filename}': no 'Revenue' column - using '{rev}' as state revenue.")
        used_map.update(m)
        unmapped = [c for c in cols if c not in m.values() and not c.startswith("unnamed_")
                    and body[c].map(to_number).notna().any() and _key(c) not in ("batchid", "drivecode", "returnmiles")]
        if unmapped:
            warns.append(f"'{filename}' / '{sheet}': numeric columns ignored: {unmapped}")
        stray = [c for c in cols if c.startswith("unnamed_") and body[c].notna().any()]
        if stray:
            warns.append(f"'{filename}' / '{sheet}': unlabeled column(s) contain data and were not imported ({len(stray)}) - review source.")

        num = lambda c: body[m[c]].map(to_number) if c in m else pd.Series(np.nan, index=body.index)
        drv_raw = body[m["driver"]]
        has_driver = drv_raw.notna() & ~drv_raw.astype(str).str.strip().isin(["", "nan", "None"])
        is_tot = drv_raw.map(is_total_label) & has_driver
        money_cols = [m[c] for c in ("main_amount", "revenue", "driver_pay") if c in m]
        any_money = pd.concat([body[c].map(to_number).notna() for c in money_cols], axis=1).any(axis=1) if money_cols else pd.Series(False, index=body.index)

        # control totals + exclusions (never silent)
        for idx in body.index[is_tot | (~has_driver & any_money)]:
            kind = "TOTAL" if is_tot[idx] else "SUBTOTAL/UNLABELED"
            ctrl.append({"src_file": filename, "src_sheet": sheet, "src_row": idx + 1, "kind": kind,
                         "declared_revenue": to_number(body.at[idx, m.get("main_amount") or m.get("revenue")]) if (m.get("main_amount") or m.get("revenue")) else np.nan,
                         "declared_driver_pay": to_number(body.at[idx, m["driver_pay"]]) if "driver_pay" in m else np.nan,
                         "declared_miles": to_number(body.at[idx, m["miles"]]) if "miles" in m else np.nan,
                         "block_start_row": None})
        for idx in body.index[~has_driver | is_tot]:
            if body.loc[idx].notna().any():
                excl.append({"src_file": filename, "src_sheet": sheet, "src_row": idx + 1,
                             "reason": "total row" if is_tot[idx] else ("subtotal / unlabeled numbers (no driver)" if any_money[idx] else "stray text, no driver")})

        det = body[has_driver & ~is_tot].copy()
        # block ids so per-driver subtotals (S.CA style) can be verified later
        sub_pos = [i for i in body.index if (not has_driver[i]) and any_money[i]]
        blk_of = {}
        start = body.index[0] if len(body) else 0
        for sp in sub_pos:
            for i in det.index[(det.index >= start) & (det.index < sp)]:
                blk_of[i] = sp + 1
            start = sp + 1
        for c in ctrl:
            if c["src_file"] == filename and c["src_sheet"] == sheet and c["kind"] == "SUBTOTAL/UNLABELED":
                rows = [i for i, b in blk_of.items() if b == c["src_row"]]
                c["block_start_row"] = (min(rows) + 1) if rows else None
                c["block_end_row"] = (max(rows) + 1) if rows else None

        out = pd.DataFrame(index=det.index)
        out["src_file"], out["src_sheet"], out["src_row"] = filename, sheet, det.index + 1
        out["provider"], out["role"], out["state_hint"] = provider, role, state_hint
        out["driver_disp"] = det[m["driver"]].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
        out["driver"] = det[m["driver"]].map(norm_name)
        out["trip_id"] = det[m["trip_id"]].map(norm_trip_id) if "trip_id" in m else ""
        out["date"] = det[m["date"]].map(parse_date) if "date" in m else pd.NaT
        out["trip_name"] = det[m["trip_name"]].astype(str).str.strip().where(det[m["trip_name"]].notna(), "") if "trip_name" in m else ""
        out["trip_key"] = out["trip_name"].map(norm_trip)
        out["miles"] = num("miles").loc[det.index]
        out["main_amount"] = num("main_amount").loc[det.index] if role == "main" else np.nan
        out["revenue"] = num("revenue").loc[det.index] if role == "state" else np.nan
        out["driver_pay"] = num("driver_pay").loc[det.index] if role == "state" else np.nan
        out["gross_pay"] = num("gross_pay").loc[det.index] if "gross_pay" in m else np.nan
        out["cancelled"] = det[m["cancel"]].notna() if "cancel" in m else False
        # row-level data-quality flags (kept, never dropped)
        fl = pd.Series("", index=det.index)
        def add(mask, text):
            nonlocal fl
            fl = fl.where(~mask, fl + text + "; ")
        if role == "main":
            add(out["main_amount"].isna(), "MISSING AMOUNT")
        else:
            add(out["revenue"].isna(), "MISSING REVENUE"); add(out["driver_pay"].isna(), "MISSING DRIVER PAYMENT")
        if "date" in m:
            raw_has = det[m["date"]].notna()
            add(raw_has & out["date"].isna(), "UNPARSEABLE DATE"); add(~raw_has, "MISSING DATE")
        if role == "main" and "trip_id" in m:
            add(out["trip_id"].eq(""), "MISSING TRIP ID")
        if role == "main" and "gross_pay" in m and "deduction" in m:
            ded = num("deduction").loc[det.index].fillna(0); sp = num("spiff").loc[det.index].fillna(0)
            diff = (out["gross_pay"] - ded + sp - out["main_amount"]).abs() > 0.005
            add(diff.fillna(False), "NET != GROSS-DEDUCTION+SPIFF")
        if ocr_used:
            add(pd.Series(True, index=det.index), "OCR SOURCE - VERIFY")
        out["flags"] = fl.str.strip("; ")
        recs.append(out)

    records = pd.concat(recs, ignore_index=True) if recs else pd.DataFrame(columns=CANON_COLS)
    return ParsedReport(filename, sha, role, provider, records, pd.DataFrame(excl),
                        pd.DataFrame(ctrl), used_map, warns, [])


def validate_control_totals(p: ParsedReport) -> pd.DataFrame:
    """Compare each declared Total / sub-total against the recomputed detail sum."""
    rows = []
    r, c = p.records, p.control_totals
    if c.empty:
        return pd.DataFrame(columns=["src_file", "src_row", "kind", "field", "declared", "computed", "difference"])
    for _, t in c.iterrows():
        for fld, col, dcol in (("revenue", "main_amount" if p.role == "main" else "revenue", "declared_revenue"),
                               ("driver_pay", "driver_pay", "declared_driver_pay"), ("miles", "miles", "declared_miles")):
            decl = t[dcol]
            if pd.isna(decl) or (fld == "driver_pay" and p.role == "main"):
                continue
            sub = r[(r.src_sheet == t.src_sheet)]
            if t.kind == "SUBTOTAL/UNLABELED" and pd.notna(t.get("block_start_row")):
                sub = sub[(sub.src_row >= t.block_start_row) & (sub.src_row <= t.block_end_row)]
            elif t.kind == "SUBTOTAL/UNLABELED":
                continue
            comp = sub[col].sum(min_count=1)
            rows.append({"src_file": t.src_file, "src_row": t.src_row, "kind": t.kind, "field": fld,
                         "declared": decl, "computed": comp, "difference": round(decl - comp, 4) if pd.notna(comp) else np.nan})
    out = pd.DataFrame(rows)
    return out
