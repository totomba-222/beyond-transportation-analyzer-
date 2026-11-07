"""EverDriven 'Cashiering Receipt' PDF adapter (text-layer PDFs).
Details table: Person | Code | Date | Key | Name | Miles | Gross | Net Pay  (person/date only on the first row of a group -> forward-filled).
Main revenue = Net Pay (what EverDriven pays Beyond; Gross minus RAD/WUD deductions) - confirmed by the user.
Adjustments (e.g. drug test) are NOT trips: kept in `adjustments`; every declared subtotal is checked against the detail rows."""
import io
import numpy as np
import pandas as pd
from normalization import file_hash, norm_name, norm_trip, parse_date, to_number

DET = ["person", "code", "date", "key", "name", "miles", "gross", "netpay"]


def _hdr(row):
    return [str(c).strip().lower().replace(" ", "") if c else "" for c in row]


def read_everdriven(data: bytes, filename: str, state_hint=None):
    import pdfplumber
    from readers import CANON_COLS, ParsedReport
    det, summ, adj, warns = [], [], [], []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        first = (pdf.pages[0].extract_text() or "")
        if "cashiering" not in first.lower() and "everdriven" not in first.lower():
            return None
        for pno, page in enumerate(pdf.pages, 1):
            for tbl in page.extract_tables() or []:
                h = _hdr(tbl[0])
                if h == DET:
                    det += [(pno, i + 1, r) for i, r in enumerate(tbl) if i > 0]
                elif h[:3] == ["person", "code", "activebetween"]:
                    summ += [(pno, i + 1, r) for i, r in enumerate(tbl) if i > 0]
                elif h[:5] == ["person", "code", "date", "type", "comments"]:
                    adj += [(pno, i + 1, r) for i, r in enumerate(tbl) if i > 0]
    sha = file_hash(data)
    recs, person, code, date, sub = [], None, None, None, None
    for pno, ri, r in det:
        if r[0] and str(r[0]).strip().lower() == "subtotal":
            sub = (pno, ri, r); continue
        person = (r[0] or person); code = (r[1] or code); date = (r[2] or date)
        if not r[3]:
            warns.append(f"page {pno} row {ri}: detail row without a trip key skipped"); continue
        name = str(r[4] or "").replace("\n", " ").strip()
        recs.append({"src_file": filename, "src_sheet": f"p{pno}", "src_row": ri, "provider": "EVERDRIVEN", "role": "main", "state_hint": state_hint,
                     "driver_disp": " ".join(str(person).split()), "driver": norm_name(person), "trip_id": str(r[3]).strip(), "date": parse_date(date),
                     "trip_name": name, "trip_key": norm_trip(name), "miles": to_number(r[5]), "main_amount": to_number(r[7]), "revenue": np.nan,
                     "driver_pay": np.nan, "gross_pay": to_number(r[6]), "cancelled": False,
                     "flags": "" if pd.notna(to_number(r[7])) else "MISSING AMOUNT"})
    R = pd.DataFrame(recs, columns=CANON_COLS)
    if R["trip_id"].duplicated().any(): warns.append("duplicate trip keys inside the EverDriven receipt")
    A = pd.DataFrame([{"Date": parse_date(r[2]), "Type": r[3], "Comments": r[4], "Amount": to_number(r[5]), "Source": f"{filename}#p{p}!{i}"}
                      for p, i, r in adj if r[0] is None or str(r[0]).strip().lower() != "subtotal"
                      if r[5] and str(r[0] or "").strip().lower() != "subtotal" and (r[3] or r[4])])
    checks = []
    def chk(src, kind, field, declared, computed):
        checks.append({"src_file": filename, "src_row": src, "kind": kind, "field": field, "declared": declared, "computed": computed,
                       "difference": round(declared - computed, 4) if pd.notna(declared) and pd.notna(computed) else np.nan})
    if sub:
        chk(f"p{sub[0]}!{sub[1]}", "Details subtotal", "revenue", to_number(sub[2][7]), R.main_amount.sum())
        chk(f"p{sub[0]}!{sub[1]}", "Details subtotal", "miles", to_number(sub[2][5]), R.miles.sum())
    by = R.groupby("driver").agg(n=("main_amount", "size"), net=("main_amount", "sum"), mi=("miles", "sum"))
    adj_total = A.Amount.sum() if len(A) else 0.0
    for p, i, r in summ:
        lab = str(r[0] or "").strip()
        if lab.lower() == "subtotal":
            chk(f"p{p}!{i}", "Summary subtotal", "revenue", to_number(r[9]), R.main_amount.sum() + adj_total); continue
        if lab.lower() == "accounting adjustment": continue
        k = norm_name(lab)
        if k in by.index:
            chk(f"p{p}!{i}", f"Summary: {lab}", "revenue", to_number(r[9]), by.loc[k, "net"])
            chk(f"p{p}!{i}", f"Summary: {lab}", "trips", to_number(r[4]), float(by.loc[k, "n"]))
        else:
            warns.append(f"Summary driver '{lab}' has no detail rows")
    missing = set(by.index) - {norm_name(str(r[0])) for _, _, r in summ}
    if missing: warns.append(f"drivers in details but not in summary: {sorted(missing)}")
    P = ParsedReport(filename, sha, "main", "EVERDRIVEN", R, pd.DataFrame(), pd.DataFrame(), {"main_amount": "Net Pay", "gross_pay": "Gross"}, warns, [])
    P.adjustments = A; P.precomputed_checks = pd.DataFrame(checks)
    return P
