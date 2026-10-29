# Hatem's B.T. Analyzer  -  Beyond Transportation weekly financial analyzer
# -------------------------------------------------------------------------
# DATA MODEL (as defined by Hatem):
#   First report  (SP ITEMIZED REPORT)  -> NET PAY = what First ACTUALLY paid
#                                           Beyond, per trip  (the cash truth).
#   State reports (one file per state)   -> per trip:
#        revenue  = the CONTRACTED price Beyond is supposed to earn
#        PAY/payment = what Beyond pays the driver for that trip (the policy).
#   So the pricing policy is taken straight from the state files - no manual
#   rates to type. The state files also tell us which driver belongs to which
#   state (grouping is baked into the files: S.CA = Riverside+Arizona,
#   N.CA = Benicia+Sacramento+San Leandro+Berkeley+Richmond+El Dorado ...).
#
#   Revenue Gap = Contract Revenue - First Paid   (what First still owes)
#   Profit      = Contract Revenue - Driver Pay
#   Margin      = Profit / Contract Revenue
# -------------------------------------------------------------------------
import io, re, unicodedata
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Hatem's B.T. Analyzer", page_icon="BT", layout="wide")

# ----------------------------- styling (dark app) -----------------------------
st.markdown("""
<style>
.stApp { background:#0f1420; color:#e8edf6; }
section[data-testid="stSidebar"] { background:#131a2a; }
h1,h2,h3,h4 { color:#f2f6ff; }
.kpi { background:linear-gradient(145deg,#1b2436,#141c2c); border:1px solid #27324a;
       border-radius:14px; padding:14px 16px; }
.kpi .lbl { font-size:12px; letter-spacing:.5px; color:#9fb0cc; text-transform:uppercase; }
.kpi .val { font-size:26px; font-weight:700; color:#ffffff; margin-top:4px; }
.kpi .sub { font-size:12px; color:#8aa0c2; margin-top:2px; }
.good { color:#35d49a; } .bad { color:#ff6b6b; } .warn { color:#ffcf5c; }
div[data-testid="stDataFrame"] { border-radius:12px; overflow:hidden; }
</style>
""", unsafe_allow_html=True)

# ----------------------------- helpers -----------------------------
MONITOR_RE = re.compile(r"\((?:M|MO|MON|MONITOR)\)", re.I)

SUMMARY_NAMES = {"total", "grand total", "subtotal", "sub total", "sum", "totals", "nan", ""}

STATE_ALIASES = {
    "SCA":"S.CA","SOUTHCA":"S.CA","SOUTHERNCA":"S.CA","SOUTHCALIFORNIA":"S.CA",
    "RSAZ":"S.CA","RIVERSIDE":"S.CA","ARIZONA":"S.CA","AZ":"S.CA",
    "NCA":"N.CA","NORTHCA":"N.CA","NORTHERNCA":"N.CA","NORTHCALIFORNIA":"N.CA",
    "NORTHCAREPORT":"N.CA","BENICIA":"N.CA","SACRAMENTO":"N.CA","SANLEANDRO":"N.CA",
    "BERKELEY":"N.CA","RICHMOND":"N.CA","ELDORADO":"N.CA",
    "IL":"IL","ILLINOIS":"IL","ILREPORT":"IL",
    "NM":"NM","NEWMEXICO":"NM","ABQ":"NM","ALBUQUERQUE":"NM",
    "OR":"OR","OREGON":"OR",
    "AK":"AK","ALASKA":"AK",
}

def norm_name(s):
    s = unicodedata.normalize("NFKD", str(s)).replace("\u200b", "")
    return re.sub(r"\s+", " ", s).strip().lower()

def state_from_filename(name):
    base = re.sub(r"\.[^.]+$", "", str(name))
    key = re.sub(r"[^A-Za-z]", "", base).upper()
    if key in STATE_ALIASES:
        return STATE_ALIASES[key]
    for alias, val in STATE_ALIASES.items():
        if alias in key:
            return val
    return (re.sub(r"[_\s]+", " ", base).strip().upper() or "STATE")

def find_col(cols, *keys):
    low = {re.sub(r"\s+", "", str(c)).lower(): c for c in cols}
    for k in keys:
        kk = re.sub(r"\s+", "", k).lower()
        if kk in low:
            return low[kk]
    for k in keys:
        kk = re.sub(r"\s+", "", k).lower()
        for lc, orig in low.items():
            if kk and kk in lc:
                return orig
    return None

def money(x):
    try:
        return f"${x:,.0f}"
    except Exception:
        return "-"

# ----------------------------- readers -----------------------------
def _clean_driver(df):
    df = df[df["driver"].ne("")]
    df = df[df["driver"].ne("nan")]
    return df

@st.cache_data(show_spinner=False)
def read_first(file_bytes, fname):
    """Read a First report (SP ITEMIZED). Returns per-trip df:
       driver, driver_disp, net (First paid), trip, miles, monitor."""
    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    best = None
    for sh in xl.sheet_names:
        df = xl.parse(sh)
        df.columns = [str(c).strip() for c in df.columns]
        dn = find_col(df.columns, "DRIVER NAME", "DRIVER")
        npc = find_col(df.columns, "NET PAY", "NETPAY")
        if not (dn and npc):
            continue
        tn = find_col(df.columns, "TRIP NAME", "TRIP")
        mi = find_col(df.columns, "TOTAL MILES", "MILES")
        out = pd.DataFrame({
            "driver": df[dn].map(norm_name),
            "driver_disp": df[dn].astype(str).str.strip(),
            "net": pd.to_numeric(df[npc], errors="coerce"),
            "trip": df[tn].astype(str) if tn else "",
            "miles": pd.to_numeric(df[mi], errors="coerce") if mi else 0,
        })
        out = out.dropna(subset=["net"])
        out = _clean_driver(out)
        if best is None or len(out) > len(best):
            best = out
    if best is None:
        return pd.DataFrame(columns=["driver", "driver_disp", "net", "trip", "miles", "monitor"])
    best = best.copy()
    best["monitor"] = best["trip"].astype(str).apply(lambda t: bool(MONITOR_RE.search(t)))
    best["source"] = fname
    return best

@st.cache_data(show_spinner=False)
def read_state(file_bytes, fname):
    """Read a state reference file. Returns (state_code, per-trip df:
       driver, driver_disp, contract, driverpay, state)."""
    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    best = None
    for sh in xl.sheet_names:
        df = xl.parse(sh)
        df.columns = [str(c).strip() for c in df.columns]
        dn = find_col(df.columns, "DRIVER NAME", "DRIVER")
        rc = find_col(df.columns, "revenue")
        pc = find_col(df.columns, "PAY", "payment")
        if not (dn and rc and pc):
            continue
        out = pd.DataFrame({
            "driver": df[dn].map(norm_name),
            "driver_disp": df[dn].astype(str).str.strip(),
            "contract": pd.to_numeric(df[rc], errors="coerce"),
            "driverpay": pd.to_numeric(df[pc], errors="coerce"),
        }).dropna(subset=["driver"])
        out = _clean_driver(out)
        out = out[~out["driver"].isin(SUMMARY_NAMES)]
        out = out.dropna(subset=["contract", "driverpay"], how="all")
        if best is None or len(out) > len(best):
            best = out
    code = state_from_filename(fname)
    if best is None:
        best = pd.DataFrame(columns=["driver", "driver_disp", "contract", "driverpay"])
    best = best.copy()
    best["contract"] = best["contract"].fillna(0.0)
    best["driverpay"] = best["driverpay"].fillna(0.0)
    best["state"] = code
    return code, best

# ----------------------------- analytics -----------------------------
def classify(first_df, state_df):
    dmap = {}
    for _, r in state_df.iterrows():
        dmap.setdefault(r["driver"], r["state"])
    first_df = first_df.copy()
    first_df["state"] = first_df["driver"].map(dmap).fillna("Unassigned")
    return first_df

def state_totals(first_df, state_df, code):
    f = first_df[first_df["state"] == code]
    s = state_df[state_df["state"] == code]
    runs = int((~f["monitor"]).sum()) if len(f) else 0
    first_paid = float(f["net"].sum())
    contract = float(s["contract"].sum())
    driverpay = float(s["driverpay"].sum())
    gap = contract - first_paid
    profit = contract - driverpay
    margin = (profit / contract * 100.0) if contract else 0.0
    return {
        "State": code, "First Trips": runs, "State Trips": int(len(s)),
        "First Paid": first_paid,
        "Contract Revenue": contract, "Revenue Gap": gap,
        "Driver Pay": driverpay, "Profit": profit, "Margin %": round(margin, 1),
    }

def trips_comparison(first_df, state_df):
    """Per-state trip-count comparison: how many trips each state price file
    lists vs how many trips the First report has for those same drivers."""
    rows = []
    for code in state_df["state"].dropna().unique():
        s = state_df[state_df["state"] == code]
        drivers = set(s["driver"].unique())
        f = first_df[first_df["driver"].isin(drivers)]
        matched = sum(1 for d in drivers if d in set(first_df["driver"]))
        rows.append({
            "State": code,
            "Price-File Trips": int(len(s)),
            "First Trips": int(len(f)),
            "Trip Difference": int(len(s) - len(f)),
            "Price Drivers": len(drivers),
            "Matched Drivers": matched,
            "Unmatched Drivers": len(drivers) - matched,
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        tot = {"State": "TOTAL",
               "Price-File Trips": int(df["Price-File Trips"].sum()),
               "First Trips": int(df["First Trips"].sum()),
               "Trip Difference": int(df["Trip Difference"].sum()),
               "Price Drivers": int(df["Price Drivers"].sum()),
               "Matched Drivers": int(df["Matched Drivers"].sum()),
               "Unmatched Drivers": int(df["Unmatched Drivers"].sum())}
        df = pd.concat([df, pd.DataFrame([tot])], ignore_index=True)
    return df


def driver_table(first_df, state_df, code):
    f = first_df[first_df["state"] == code]
    fg = f.groupby(["driver", "driver_disp"]).agg(
        Runs=("monitor", lambda m: int((~m).sum())),
        **{"First Paid": ("net", "sum")}
    ).reset_index()
    s = state_df[state_df["state"] == code]
    sg = s.groupby("driver").agg(
        **{"Contract Revenue": ("contract", "sum"), "Driver Pay": ("driverpay", "sum")}
    ).reset_index()
    t = fg.merge(sg, on="driver", how="outer")
    t["driver_disp"] = t["driver_disp"].fillna(t["driver"].str.title())
    for c in ["Runs", "First Paid", "Contract Revenue", "Driver Pay"]:
        t[c] = pd.to_numeric(t.get(c), errors="coerce").fillna(0.0)
    t["Revenue Gap"] = t["Contract Revenue"] - t["First Paid"]
    t["Profit"] = t["Contract Revenue"] - t["Driver Pay"]
    t["Margin %"] = t.apply(
        lambda r: round(r["Profit"] / r["Contract Revenue"] * 100, 1) if r["Contract Revenue"] else 0.0,
        axis=1,
    )
    # non-compliant = Beyond loses money on the driver (First paid below driver pay)
    t["Flag"] = ""
    nofirst = (t["First Paid"].le(0)) & (t["Contract Revenue"].gt(0))
    nocontract = (t["Contract Revenue"].le(0)) & (t["First Paid"].gt(0))
    loss = (t["First Paid"].lt(t["Driver Pay"])) & (t["First Paid"].gt(0))
    t.loc[loss, "Flag"] = "LOSS"
    t.loc[nocontract, "Flag"] = "NO CONTRACT"
    t.loc[nofirst, "Flag"] = "NO FIRST MATCH"
    t = t.rename(columns={"driver_disp": "Driver"})
    cols = ["Driver", "Runs", "First Paid", "Contract Revenue", "Revenue Gap",
            "Driver Pay", "Profit", "Margin %", "Flag"]
    return t[cols].sort_values("Contract Revenue", ascending=False).reset_index(drop=True)

def to_excel(frames):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in frames.items():
            df.to_excel(xw, sheet_name=name[:31], index=False)
    return buf.getvalue()

# ----------------------------- UI -----------------------------
def kpi(col, label, value, sub="", cls=""):
    col.markdown(
        f'<div class="kpi"><div class="lbl">{label}</div>'
        f'<div class="val {cls}">{value}</div>'
        f'<div class="sub">{sub}</div></div>',
        unsafe_allow_html=True,
    )

st.title("Hatem's B.T. Analyzer")
st.caption("Beyond Transportation - weekly state profit, revenue gap and compliance")

with st.sidebar:
    st.header("1) First report(s)")
    first_files = st.file_uploader(
        "First / SP ITEMIZED reports (NET PAY = what First paid)",
        type=["xlsx", "xls"], accept_multiple_files=True, key="first")
    st.header("2) State price references")
    state_files = st.file_uploader(
        "One file per state (revenue = contract, PAY = driver payment)",
        type=["xlsx", "xls"], accept_multiple_files=True, key="state")

if not first_files:
    st.info("Upload at least one First report to begin. Add the state price "
            "reference files to unlock contract revenue, the revenue gap and profit.")
    st.stop()

first_all = pd.concat([read_first(f.getvalue(), f.name) for f in first_files], ignore_index=True)

state_frames, state_codes = [], []
if state_files:
    for f in state_files:
        code, sdf = read_state(f.getvalue(), f.name)
        state_frames.append(sdf)
        if code not in state_codes:
            state_codes.append(code)
state_all = (pd.concat(state_frames, ignore_index=True)
             if state_frames else
             pd.DataFrame(columns=["driver", "driver_disp", "contract", "driverpay", "state"]))

first_all = classify(first_all, state_all)
present_codes = state_codes + [c for c in first_all["state"].unique()
                               if c not in state_codes and c != "Unassigned"]
if (first_all["state"] == "Unassigned").any():
    present_codes = present_codes + ["Unassigned"]

summary = pd.DataFrame([state_totals(first_all, state_all, c)
                        for c in present_codes if c != "Unassigned"])

view = st.sidebar.radio("View", ["Consolidated Report", "Trips Comparison"] + present_codes)

# ----------------------------- rendering -----------------------------
def fmt_money_cols(df, cols):
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = out[c].map(money)
    return out

MONEY_COLS = ["First Paid", "Contract Revenue", "Revenue Gap", "Driver Pay", "Profit"]

if view == "Consolidated Report":
    st.subheader("Consolidated Report - all states")
    tot_runs = int((~first_all["monitor"]).sum())
    tot_first = float(first_all["net"].sum())
    tot_contract = float(state_all["contract"].sum())
    tot_pay = float(state_all["driverpay"].sum())
    tot_gap = tot_contract - tot_first
    tot_profit = tot_contract - tot_pay
    tot_margin = (tot_profit / tot_contract * 100) if tot_contract else 0

    c = st.columns(4)
    kpi(c[0], "Total Trips", f"{tot_runs:,}")
    kpi(c[1], "First Paid", money(tot_first), "cash received from First")
    kpi(c[2], "Contract Revenue", money(tot_contract), "what Beyond should earn")
    kpi(c[3], "Revenue Gap", money(tot_gap),
        "owed by First" if tot_gap >= 0 else "overpaid", "bad" if tot_gap > 0 else "good")
    c = st.columns(4)
    kpi(c[0], "Driver Pay", money(tot_pay))
    kpi(c[1], "Profit", money(tot_profit), cls="good" if tot_profit >= 0 else "bad")
    kpi(c[2], "Margin", f"{tot_margin:.1f}%")
    kpi(c[3], "States", f"{len(summary)}")

    if not summary.empty:
        st.markdown("#### Per-state summary")
        st.dataframe(fmt_money_cols(summary, MONEY_COLS), use_container_width=True, hide_index=True)
        st.caption("Revenue Gap = Contract Revenue - First Paid. Compare 'First Trips' "
                   "vs 'State Trips': if they differ for a state, that gap is an estimate "
                   "(the two files don't cover the exact same trips yet).")
        chart = summary.set_index("State")[["First Paid", "Contract Revenue"]]
        st.markdown("#### First paid vs contract revenue by state")
        st.bar_chart(chart)
        st.markdown("#### Revenue gap by state (what First still owes)")
        st.bar_chart(summary.set_index("State")[["Revenue Gap"]])
        st.download_button(
            "Download Excel report",
            data=to_excel({"Consolidated": summary}),
            file_name="BT_consolidated.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    un = first_all[first_all["state"] == "Unassigned"]
    if len(un):
        st.warning(f"{len(un):,} trips ({money(un['net'].sum())} First paid) belong to drivers "
                   f"not found in any uploaded state file. Upload those state price references "
                   f"to classify them (e.g. NM, OR, Alaska).")

elif view == "Trips Comparison":
    st.subheader("Trips Comparison - price files vs First report")
    st.caption("For each state this counts the trips listed in the price file "
               "and the trips the First report holds for the SAME drivers. A "
               "non-zero 'Trip Difference' means the two files don't yet cover "
               "the exact same trips, so the revenue gap for that state is an "
               "estimate. 'Unmatched Drivers' are in the price file but have no "
               "matching name in First (often a spelling difference).")
    cmp = trips_comparison(first_all, state_all)
    if cmp.empty:
        st.info("Upload the state price reference files to build the comparison.")
    else:
        tot = cmp[cmp["State"] == "TOTAL"].iloc[0]
        c = st.columns(4)
        kpi(c[0], "Price-File Trips", f"{int(tot['Price-File Trips']):,}")
        kpi(c[1], "First Trips", f"{int(tot['First Trips']):,}")
        kpi(c[2], "Trip Difference", f"{int(tot['Trip Difference']):,}",
            "extra trips in price files", "warn" if tot['Trip Difference'] else "good")
        kpi(c[3], "Unmatched Drivers", f"{int(tot['Unmatched Drivers']):,}",
            "no First name match", "bad" if tot['Unmatched Drivers'] else "good")
        st.dataframe(cmp, use_container_width=True, hide_index=True)
        chart = cmp[cmp["State"] != "TOTAL"].set_index("State")[["Price-File Trips", "First Trips"]]
        st.markdown("#### Trip counts by state")
        st.bar_chart(chart)
        st.download_button(
            "Download trips comparison (Excel)",
            data=to_excel({"Trips Comparison": cmp}),
            file_name="BT_trips_comparison.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

else:
    code = view
    st.subheader(f"{code} - state report")
    row = state_totals(first_all, state_all, code)
    c = st.columns(4)
    kpi(c[0], "Trips", f"{row['First Trips']:,}")
    kpi(c[1], "First Paid", money(row["First Paid"]))
    kpi(c[2], "Contract Revenue", money(row["Contract Revenue"]))
    kpi(c[3], "Revenue Gap", money(row["Revenue Gap"]),
        "owed by First" if row["Revenue Gap"] >= 0 else "overpaid",
        "bad" if row["Revenue Gap"] > 0 else "good")
    c = st.columns(3)
    kpi(c[0], "Driver Pay", money(row["Driver Pay"]))
    kpi(c[1], "Profit", money(row["Profit"]), cls="good" if row["Profit"] >= 0 else "bad")
    kpi(c[2], "Margin", f"{row['Margin %']}%")

    st_rows = int(row["State Trips"])
    if code != "Unassigned" and st_rows:
        delta = st_rows - int(row["First Trips"])
        if delta != 0:
            st.warning(
                f"Reconciliation check: the {code} price file lists {st_rows} trips, "
                f"but the First report has {int(row['First Trips'])} trips for {code}. "
                f"That {abs(delta)}-trip difference means this gap is NOT trip-by-trip "
                f"verified - it mixes real price differences with trips that exist in "
                f"one file but not the other. Treat the gap as an estimate until the "
                f"two files cover the exact same trips.")

    if code == "Unassigned":
        st.info("These drivers are not in any state price reference yet. "
                "Upload the matching state file so their contract prices and policy load.")
    dt = driver_table(first_all, state_all, code)
    st.markdown("#### Driver breakdown")
    st.caption("Flags: LOSS = First paid below driver pay. NO FIRST MATCH = this driver "
               "is in the price file but not matched in the First report (contract counted, "
               "First paid 0 - inflates the gap, often a name spelling difference). "
               "NO CONTRACT = in First but missing from the price file.")
    st.dataframe(fmt_money_cols(dt, MONEY_COLS), use_container_width=True, hide_index=True)

    noncompliant = dt[dt["Flag"] == "LOSS"]
    if len(noncompliant):
        st.markdown(f"#### Non-compliant drivers - {len(noncompliant)} losing money "
                    f"(First paid below driver pay)")
        st.bar_chart(noncompliant.set_index("Driver")[["First Paid", "Driver Pay"]])
    else:
        st.success("All drivers compliant - First paid covers driver pay on every driver. "
                   "(Trip chart hidden because there are no non-compliant trips.)")

    st.download_button(
        "Download this state (Excel)",
        data=to_excel({code: dt}),
        file_name=f"BT_{code.replace('.', '')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
