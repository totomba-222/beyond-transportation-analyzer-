"""Beyond Transportation trip analyzer.

Supports:
- First SP ITEMIZED REPORT Excel files
- EverDriven Cashiering Receipt PDFs exported with pdftotext
- Pricing comparisons by state, region, vehicle type, driver, and city
- Cross Border as the Alaska revenue label for Beyond
- Excel report export

Run UI: streamlit run beyond_trip_analyzer_new.py
Run batch mode: python beyond_trip_analyzer_new.py --first FILE.xlsx --everdriven FILE.pdf --out OUTPUT_DIR
"""
from __future__ import annotations

import argparse
import io
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import pandas as pd

# ----------------------------- Pricing policies -----------------------------
# Rates supplied by the user / retained from the original code.
POLICIES = [
    # Oregon
    {"State": "OR", "Vehicle": "Any", "Min_Miles": 0, "Max_Miles": 8, "Base_Price": 35.0, "Per_Mile_Rate": 0.0, "Extra_Mile_Base": 0.0},
    {"State": "OR", "Vehicle": "Any", "Min_Miles": 8.01, "Max_Miles": 16, "Base_Price": 40.0, "Per_Mile_Rate": 0.0, "Extra_Mile_Base": 0.0},
    {"State": "OR", "Vehicle": "Any", "Min_Miles": 16.01, "Max_Miles": 9999, "Base_Price": 37.0, "Per_Mile_Rate": 1.75, "Extra_Mile_Base": 0.0},
    # Northern California
    {"State": "N.CA", "Vehicle": "Any", "Min_Miles": 0, "Max_Miles": 6, "Base_Price": 38.0, "Per_Mile_Rate": 0.0, "Extra_Mile_Base": 0.0},
    {"State": "N.CA", "Vehicle": "Any", "Min_Miles": 6.01, "Max_Miles": 16, "Base_Price": 42.0, "Per_Mile_Rate": 0.0, "Extra_Mile_Base": 0.0},
    # Southern California retained from supplied code
    {"State": "S.CA", "Vehicle": "Any", "Min_Miles": 0, "Max_Miles": 4, "Base_Price": 38.0, "Per_Mile_Rate": 0.0, "Extra_Mile_Base": 0.0},
    {"State": "S.CA", "Vehicle": "Any", "Min_Miles": 4.01, "Max_Miles": 8, "Base_Price": 40.0, "Per_Mile_Rate": 0.0, "Extra_Mile_Base": 0.0},
    {"State": "S.CA", "Vehicle": "Any", "Min_Miles": 8.01, "Max_Miles": 15, "Base_Price": 43.0, "Per_Mile_Rate": 0.0, "Extra_Mile_Base": 0.0},
    # Alaska: user's updated rates, vehicle-specific
    {"State": "AK", "Vehicle": "Sedan", "Min_Miles": 0, "Max_Miles": 8, "Base_Price": 35.0, "Per_Mile_Rate": 0.0, "Extra_Mile_Base": 0.0},
    {"State": "AK", "Vehicle": "Sedan", "Min_Miles": 8.01, "Max_Miles": 16, "Base_Price": 37.0, "Per_Mile_Rate": 0.0, "Extra_Mile_Base": 0.0},
    {"State": "AK", "Vehicle": "Minivan", "Min_Miles": 0, "Max_Miles": 8, "Base_Price": 40.0, "Per_Mile_Rate": 0.0, "Extra_Mile_Base": 0.0},
    {"State": "AK", "Vehicle": "Minivan", "Min_Miles": 8.01, "Max_Miles": 16, "Base_Price": 42.0, "Per_Mile_Rate": 0.0, "Extra_Mile_Base": 0.0},
    # Alaska trips over 16 miles need the vehicle/extra-mile rule confirmed; mark as unresolved.
    {"State": "AK", "Vehicle": "Any", "Min_Miles": 16.01, "Max_Miles": 9999, "Base_Price": 0.0, "Per_Mile_Rate": 0.0, "Extra_Mile_Base": 0.0},
    # Nebraska: $30 through 16 miles, then +$1.50 per mile above 16.
    {"State": "NE", "Vehicle": "Any", "Min_Miles": 0, "Max_Miles": 16, "Base_Price": 30.0, "Per_Mile_Rate": 0.0, "Extra_Mile_Base": 0.0},
    {"State": "NE", "Vehicle": "Any", "Min_Miles": 16.01, "Max_Miles": 9999, "Base_Price": 30.0, "Per_Mile_Rate": 1.50, "Extra_Mile_Base": 0.0},
]
POLICY_DF = pd.DataFrame(POLICIES)


def money(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(r"[$,()]", "", regex=True).str.replace("-", "-", regex=False), errors="coerce").fillna(0.0)


def infer_city(name: str) -> str:
    s = str(name).upper()
    if any(x in s for x in ["LINC ", "LINCOLN "]):
        return "Lincoln"
    if "BRYAN" in s:
        return "Lincoln"
    if "ELGIN" in s:
        return "Elgin"
    if "CAROL STREAM" in s:
        return "Carol Stream"
    if "RICHMOND" in s:
        return "Richmond"
    if "BERKELEY" in s:
        return "Berkeley"
    if "PORTLAND" in s:
        return "Portland"
    return "Unknown"


def infer_state(name: str, source_company: str = "") -> str:
    s = f"{name} {source_company}".upper()
    if any(x in s for x in ["ALASKA", "ANCHORAGE", "CROSS BORDER"]):
        return "AK"
    if any(x in s for x in ["NEBRASKA", "LINCOLN", "LINC ", "BRYAN"]):
        return "NE"
    if any(x in s for x in ["OREGON", "PORTLAND", "GRESHAM", "SALEM"]):
        return "OR"
    if any(x in s for x in ["CALIFORNIA", "RICHMOND", "BERKELEY", "SAN LEANDRO"]):
        return "N.CA"
    if "ILLINOIS" in s or " IL" in s:
        return "IL"
    return "Unknown"


def policy_price(state: str, miles: float, vehicle: str = "Unknown") -> tuple[float, str]:
    state = str(state).upper().strip()
    miles = float(miles or 0)
    vehicle = str(vehicle or "Unknown").strip().title()
    candidates = POLICY_DF[(POLICY_DF.State == state) & (POLICY_DF.Min_Miles <= miles) & (POLICY_DF.Max_Miles >= miles)]
    if state == "AK" and vehicle in {"Sedan", "Minivan"}:
        exact = candidates[candidates.Vehicle == vehicle]
        if not exact.empty:
            candidates = exact
    if candidates.empty:
        return 0.0, "No policy"
    rule = candidates.iloc[0]
    if state == "AK" and miles > 16:
        return 0.0, "Needs Alaska >16-mile rule"
    if float(rule.Per_Mile_Rate) > 0:
        return round(float(rule.Base_Price) + (miles - 16.0) * float(rule.Per_Mile_Rate), 2), "Matched"
    return round(float(rule.Base_Price), 2), "Matched"


def finalize(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    for c in ["Miles", "Gross", "Net Pay", "Driver Pay", "Vehicle Cost"]:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    if "State" not in df:
        df["State"] = df.apply(lambda r: infer_state(r.get("Trip Name", ""), r.get("Source Company", "")), axis=1)
    if "City" not in df:
        df["City"] = df.get("Trip Name", pd.Series(index=df.index, dtype=str)).map(infer_city)
    if "Vehicle" not in df:
        df["Vehicle"] = "Unknown"
    prices = df.apply(lambda r: policy_price(r.State, r.Miles, r.Vehicle), axis=1)
    df["Policy Price"] = prices.map(lambda x: x[0])
    df["Policy Status"] = prices.map(lambda x: x[1])
    df["Revenue"] = df["Gross"]
    df["Cost"] = df["Driver Pay"] + df["Vehicle Cost"]
    df["Profit"] = df["Revenue"] - df["Cost"]
    df["Price Variance"] = df["Revenue"] - df["Policy Price"]
    df["Is Violation"] = (df["Policy Status"] == "Matched") & (df["Price Variance"] < 0)
    df["Profit Margin"] = (df["Profit"] / df["Revenue"].where(df["Revenue"] != 0)).fillna(0.0)
    return df


def read_first_excel(path_or_buffer) -> pd.DataFrame:
    book = pd.ExcelFile(path_or_buffer, engine="openpyxl")
    sheet = "SP ITEMIZED REPORT" if "SP ITEMIZED REPORT" in book.sheet_names else book.sheet_names[0]
    raw = pd.read_excel(path_or_buffer, sheet_name=sheet, engine="openpyxl")
    raw.columns = [str(c).strip() for c in raw.columns]
    out = pd.DataFrame(index=raw.index)
    out["Source Company"] = raw.get("SP COMPANY", "")
    out["Driver"] = raw.get("DRIVER NAME", "Unknown")
    out["Trip Date"] = pd.to_datetime(raw.get("DATE"), errors="coerce")
    out["Trip ID"] = raw.get("TRIP CODE", "")
    out["Trip Name"] = raw.get("TRIP NAME", "")
    out["Miles"] = raw.get("TOTAL MILES", raw.get("MILES", 0))
    out["Gross"] = raw.get("GROSS PAY", 0)
    out["Net Pay"] = raw.get("NET PAY", 0)
    out["Driver Pay"] = raw.get("NET PAY", 0)
    out["Vehicle Cost"] = 0.0
    out["State"] = out.apply(lambda r: infer_state(r["Trip Name"], r["Source Company"]), axis=1)
    out["City"] = out["Trip Name"].map(infer_city)
    out["Vehicle"] = "Unknown"
    out["Source"] = "First"
    return finalize(out)


def extract_pdf_text(path_or_bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        if hasattr(path_or_bytes, "read"):
            f.write(path_or_bytes.read())
        else:
            f.write(Path(path_or_bytes).read_bytes())
        pdf_path = f.name
    try:
        result = subprocess.run(["pdftotext", "-layout", pdf_path, "-"], capture_output=True, text=True, check=True)
        return result.stdout
    finally:
        Path(pdf_path).unlink(missing_ok=True)


def read_everdriven_pdf(path_or_bytes) -> pd.DataFrame:
    text = extract_pdf_text(path_or_bytes)
    rows = []
    # Detail rows contain an 8-digit key, a trip name, miles, gross, and net pay.
    rx = re.compile(r"^\s*(?:(?P<driver>[A-Za-z][A-Za-z .'-]+)\s+\d{5,}\s+)?(?:(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+)?(?P<key>\d{6,})\s+(?P<name>.+?)\s+(?P<miles>\d+(?:\.\d+)?)\s+\$(?P<gross>[\d,]+\.\d{2})\s+\$(?P<net>[\d,]+\.\d{2})\s*$")
    current_driver = "Unknown"
    current_date = pd.NaT
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Cashiering") or stripped.startswith("Person"):
            continue
        # Driver names occur at the start of detail sections; retain the previous driver when date is omitted.
        m = rx.match(line)
        if not m:
            continue
        gd = m.groupdict()
        driver = gd.get("driver") or current_driver
        if gd.get("driver"):
            current_driver = gd["driver"].strip()
        if gd.get("date"):
            current_date = pd.to_datetime(gd["date"], format="%m/%d/%Y", errors="coerce")
        rows.append({
            "Source": "EverDriven",
            "Source Company": "Beyond Transportation (IL)",
            "Driver": driver,
            "Trip Date": current_date,
            "Trip ID": gd["key"],
            "Trip Name": gd["name"].strip(),
            "Miles": float(gd["miles"]),
            "Gross": float(gd["gross"].replace(",", "")),
            "Net Pay": float(gd["net"].replace(",", "")),
            "Driver Pay": float(gd["net"].replace(",", "")),
            "Vehicle Cost": 0.0,
            "State": infer_state(gd["name"], "Beyond Transportation (IL)"),
            "City": infer_city(gd["name"]),
            "Vehicle": "Unknown",
        })
    # If text extraction misses detail rows, retain an auditable empty result rather than inventing trips.
    return finalize(pd.DataFrame(rows))


def summary_table(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=group_cols + ["Trips", "Miles", "Revenue", "Net Pay", "Policy Violations", "Profit"])
    s = df.groupby(group_cols, dropna=False).agg(
        Trips=("Trip ID", "count"), Miles=("Miles", "sum"), Revenue=("Revenue", "sum"),
        Net_Pay=("Net Pay", "sum"), Policy_Violations=("Is Violation", "sum"), Profit=("Profit", "sum")
    ).reset_index()
    return s.rename(columns={"Net_Pay": "Net Pay", "Policy_Violations": "Policy Violations"})


def write_reports(first_path: Optional[str], ever_path: Optional[str], out_dir: str) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    frames = []
    if first_path:
        frames.append(read_first_excel(first_path))
    if ever_path:
        frames.append(read_everdriven_pdf(ever_path))
    all_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not all_df.empty:
        all_df.to_csv(out / "all_trips_analyzed.csv", index=False)
    by_state = summary_table(all_df, ["Source", "State"])
    by_city = summary_table(all_df, ["Source", "State", "City"])
    by_driver = summary_table(all_df, ["Source", "State", "Driver"])
    violations = all_df[all_df.get("Is Violation", False)].copy() if not all_df.empty else pd.DataFrame()
    excel_path = out / "beyond_weekly_reports.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        all_df.to_excel(writer, sheet_name="All Trips", index=False)
        by_state.to_excel(writer, sheet_name="By State", index=False)
        by_city.to_excel(writer, sheet_name="By City", index=False)
        by_driver.to_excel(writer, sheet_name="By Driver", index=False)
        violations.to_excel(writer, sheet_name="Violations", index=False)
        POLICY_DF.to_excel(writer, sheet_name="Policies", index=False)
    return {"excel": str(excel_path), "csv": str(out / "all_trips_analyzed.csv"), "rows": str(len(all_df))}


def app():
    import streamlit as st
    st.set_page_config(page_title="Beyond Transportation Analyzer", layout="wide")
    st.title("Beyond Transportation — Weekly Trip Analyzer")
    st.caption("First + EverDriven | Cross Border is classified as Beyond revenue in Alaska")
    first = st.file_uploader("Upload First Excel report", type=["xlsx"])
    ever = st.file_uploader("Upload EverDriven Cashiering Receipt", type=["pdf"])
    if not first and not ever:
        st.info("Upload one or both reports to begin.")
        return
    frames = []
    if first:
        frames.append(read_first_excel(io.BytesIO(first.getvalue())))
    if ever:
        frames.append(read_everdriven_pdf(io.BytesIO(ever.getvalue())))
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if df.empty:
        st.warning("No itemized trips were detected. Check the report format.")
        return
    st.success(f"Loaded {len(df):,} itemized trips.")
    states = ["All"] + sorted(df.State.dropna().unique().tolist())
    selected = st.selectbox("State", states)
    view = df if selected == "All" else df[df.State == selected]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Trips", f"{len(view):,}")
    c2.metric("Revenue", f"${view.Revenue.sum():,.2f}")
    c3.metric("Net Pay", f"${view['Net Pay'].sum():,.2f}")
    c4.metric("Violations", f"{int(view['Is Violation'].sum()):,}")
    st.subheader("By City")
    st.dataframe(summary_table(view, ["Source", "State", "City"]), use_container_width=True)
    st.subheader("By Driver")
    st.dataframe(summary_table(view, ["Source", "State", "Driver"]), use_container_width=True)
    st.subheader("Pricing Violations")
    st.dataframe(view[view["Is Violation"]], use_container_width=True)
    st.subheader("All Analyzed Trips")
    st.dataframe(view, use_container_width=True)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        view.to_excel(writer, sheet_name="All Trips", index=False)
        summary_table(view, ["Source", "State"]).to_excel(writer, sheet_name="By State", index=False)
        summary_table(view, ["Source", "State", "City"]).to_excel(writer, sheet_name="By City", index=False)
        summary_table(view, ["Source", "State", "Driver"]).to_excel(writer, sheet_name="By Driver", index=False)
        view[view["Is Violation"]].to_excel(writer, sheet_name="Violations", index=False)
        POLICY_DF.to_excel(writer, sheet_name="Policies", index=False)
    st.download_button("Download Excel report", buffer.getvalue(), "beyond_weekly_reports.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--first")
    parser.add_argument("--everdriven")
    parser.add_argument("--out", default="/home/ubuntu/beyond_reports")
    args = parser.parse_args()
    if args.first or args.everdriven:
        print(write_reports(args.first, args.everdriven, args.out))
    else:
        app()
