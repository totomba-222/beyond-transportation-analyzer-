# Hatem's B.T. Analyzer - Beyond Transportation weekly financial analyzer
# =============================================================================
# DATA SOURCE (as it really is in Hatem's weekly workbooks):
#   Each weekly workbook contains:
#     * a "Breakup" sheet  -> the master per-region, per-driver breakdown
#         (region headers in col A, then driver rows: Sr# | name | trips |
#          revenue | payment, then a region subtotal). THIS is the only place
#          that splits Arizona out of Riverside and splits North CA into its
#          areas (Benicia / Richmond / San Leandro / Berkeley / El Dorado /
#          Sacramento), so the app reads region grouping straight from it.
#     * an "SP ITEMIZED REPORT" sheet -> the First report, trip level
#         (DRIVER NAME ... NET PAY = what First actually paid, per trip).
#   The app reads BOTH: the state Breakup sheet AND the First itemized sheet,
#   on every uploaded workbook (including the Alaska workbook).
#
# DEFINITIONS:
#   Revenue (First Paid) = NET PAY  (what First pays Beyond for the trip)
#   Driver Pay           = payment  (what Beyond pays the driver)
#   Profit  = Revenue - Driver Pay
#   Margin  = Profit / Revenue
#   Trip reconciliation  = First-report trips vs Breakup trips, per region
#                          (a 0 difference proves the two cover the same trips)
# =============================================================================
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

# ----------------------------- region grouping -----------------------------
# Normalised region name -> (canonical region label, operating group)
SCA_REGIONS = {"riverside", "riverside ca", "arizona", "az"}
NCA_REGIONS = {"benicia", "benicia ca", "richmond", "san leandro", "san leandro ca",
               "berkeley", "el dorado", "sacramento", "sacramento ca"}

def group_of(region_norm):
    r = region_norm
    if r in SCA_REGIONS:
        return "S.CA (Riverside + Arizona)"
    if r in NCA_REGIONS:
        return "N.CA (Northern California)"
    if r in ("new mexico", "nm"):
        return "New Mexico"
    if r in ("il", "illinois"):
        return "Illinois"
    if r in ("oregon", "or"):
        return "Oregon"
    if r in ("alaska", "ak"):
        return "Alaska"
    return region_norm.title()

GROUP_ORDER = ["S.CA (Riverside + Arizona)", "N.CA (Northern California)",
               "New Mexico", "Illinois", "Oregon", "Alaska"]
NCA_AREA_ORDER = ["Benicia CA", "Richmond", "San Leandro CA", "Berkeley", "El Dorado", "Sacramento"]

MONITOR_RE = re.compile(r"\((?:M|MO|MON|MONITOR)\)", re.I)
SKIP_HEADERS = {"sr #", "grand total", "total", ""}

def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).replace("\u200b", "")
    return re.sub(r"\s+", " ", s).strip().lower()

# ----------------------------- sheet finders -----------------------------
def _find_sheet(xl, *needles):
    for sh in xl.sheet_names:
        low = sh.strip().lower()
        if any(n in low for n in needles):
            return sh
    return None

def _find_col(cols, *keys):
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

# ----------------------------- readers -----------------------------
@st.cache_data(show_spinner=False)
def read_breakup(file_bytes, fname):
    """Read the master Breakup sheet -> per-region, per-driver rows.
    Region grouping (Arizona split, North-CA areas) comes straight from the
    region header rows inside this sheet."""
    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    sh = _find_sheet(xl, "breakup")
    cols = ["region","region_norm","group","driver","monitor","trips","revenue","driverpay","source"]
    if sh is None:
        return pd.DataFrame(columns=cols)
    df = xl.parse(sh, header=None)
    rows, region = [], None
    for _, r in df.iterrows():
        c0, c1, c2, c3, c4 = r.get(0), r.get(1), r.get(2), r.get(3), r.get(4)
        if isinstance(c0, str) and c0.strip() and pd.isna(c1) and norm(c0) not in SKIP_HEADERS:
            region = c0.strip()
            continue
        if pd.notna(c0) and pd.notna(c1) and str(c0).strip().replace(".", "").isdigit():
            name = str(c1).strip()
            if norm(name) in SKIP_HEADERS:
                continue
            rows.append(dict(region=region or "Unknown", driver=name,
                monitor=bool(MONITOR_RE.search(name)),
                trips=pd.to_numeric(c2, errors="coerce"),
                revenue=pd.to_numeric(c3, errors="coerce"),
                driverpay=pd.to_numeric(c4, errors="coerce")))
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=cols)
    for c in ["trips", "revenue", "driverpay"]:
        out[c] = out[c].fillna(0.0)
    out["region_norm"] = out["region"].map(norm)
    out["group"] = out["region_norm"].map(group_of)
    out["source"] = fname
    return out[cols]

@st.cache_data(show_spinner=False)
def read_first(file_bytes, fname):
    """Read the First report (SP ITEMIZED) -> trip-level rows.
    driver, driver_key, net (First paid), trip, source."""
    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    sh = _find_sheet(xl, "itemized")
    cols = ["driver","driver_key","net","trip","source"]
    if sh is None:
        return pd.DataFrame(columns=cols)
    df = xl.parse(sh)
    df.columns = [str(c).strip() for c in df.columns]
    dn = _find_col(df.columns, "DRIVER NAME", "DRIVER")
    npc = _find_col(df.columns, "NET PAY", "NETPAY")
    tn = _find_col(df.columns, "TRIP NAME", "TRIP")
    if not (dn and npc):
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame({
        "driver": df[dn].astype(str).str.strip(),
        "net": pd.to_numeric(df[npc], errors="coerce"),
        "trip": df[tn].astype(str) if tn else "",
    })
    out = out[out["driver"].notna() & out["driver"].ne("") & out["driver"].ne("nan")]
    out = out.dropna(subset=["net"])
    out = out[out["driver"].map(norm) != "total"]
    out["driver_key"] = out["driver"].map(norm)
    out["source"] = fname
    return out[cols]

# ----------------------------- analytics -----------------------------
def enrich(g):
    g = g.copy()
    g["Profit"] = g["revenue"] - g["driverpay"]
    g["Margin %"] = g.apply(lambda r: round(r["Profit"]/r["revenue"]*100, 1) if r["revenue"] else 0.0, axis=1)
    return g

def agg_by(df, key):
    g = df.groupby(key, as_index=False).agg(
        Drivers=("driver", "nunique"),
        Trips=("trips", "sum"),
        revenue=("revenue", "sum"),
        driverpay=("driverpay", "sum"),
    )
    return enrich(g)

def first_by_region(first_df, bk):
    """Map First report drivers to their Breakup region, then count trips and
    sum First-paid per region."""
    dmap = {}
    for _, r in bk.iterrows():
        dmap.setdefault(norm(r["driver"]), r["region"])
    f = first_df.copy()
    f["region"] = f["driver_key"].map(dmap)
    matched = f[f["region"].notna()]
    g = matched.groupby("region", as_index=False).agg(
        first_trips=("net", "size"), first_paid=("net", "sum"))
    unmatched = f[f["region"].isna()]
    return g, unmatched

def money(x):
    try:
        return "${:,.0f}".format(x)
    except Exception:
        return "-"

RENAME = {"region": "Region", "group": "Operating Group", "driver": "Driver",
          "revenue": "Revenue (First Paid)", "driverpay": "Driver Pay"}
MONEY_COLS = ["Revenue (First Paid)", "Driver Pay", "Profit", "First Paid",
              "Contract Revenue", "$ Diff"]

def fmt(df):
    out = df.rename(columns=RENAME).copy()
    for c in MONEY_COLS:
        if c in out.columns:
            out[c] = out[c].map(money)
    if "Margin %" in out.columns:
        out["Margin %"] = out["Margin %"].map(lambda v: "{:.1f}%".format(v))
    return out

def to_excel(frames):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in frames.items():
            df.to_excel(xw, sheet_name=str(name)[:31], index=False)
    return buf.getvalue()

def kpi(col, label, value, sub="", cls=""):
    col.markdown(
        '<div class="kpi"><div class="lbl">{}</div>'
        '<div class="val {}">{}</div>'
        '<div class="sub">{}</div></div>'.format(label, cls, value, sub),
        unsafe_allow_html=True)

# ----------------------------- UI: upload & parse -----------------------------
st.title("Hatem's B.T. Analyzer")
st.caption("Beyond Transportation - weekly profit by state, Arizona split, "
           "North CA area analysis, and trip reconciliation vs the First report")

with st.sidebar:
    st.header("Weekly workbook(s)")
    files = st.file_uploader(
        "Upload the weekly workbook(s). Each is read in full: the state "
        "'Breakup' sheet AND the 'SP ITEMIZED REPORT' (First) sheet.",
        type=["xlsx", "xls"], accept_multiple_files=True)

if not files:
    st.info("Upload at least one weekly workbook (e.g. '41. WEEKLY ALL STATES 9 "
            "Oct.xlsx' and 'ALASKA WEEKLY 41.xlsx'). The app reads the Breakup "
            "sheet for the per-region driver breakdown and the SP ITEMIZED "
            "REPORT for the First-paid trip reconciliation.")
    st.stop()

bk = pd.concat([read_breakup(f.getvalue(), f.name) for f in files], ignore_index=True)
fr = pd.concat([read_first(f.getvalue(), f.name) for f in files], ignore_index=True)

if bk.empty:
    st.error("No 'Breakup' sheet found in the uploaded workbook(s). This app "
             "reads the per-region breakdown from that sheet.")
    st.stop()

fr_region, fr_unmatched = first_by_region(fr, bk)
first_lookup = fr_region.set_index("region") if not fr_region.empty else pd.DataFrame()

present_groups = [g for g in GROUP_ORDER if g in set(bk["group"])]
present_groups += [g for g in bk["group"].unique() if g not in present_groups]

view = st.sidebar.radio("View", [
    "Consolidated", "By operating group", "By region",
    "Trip reconciliation", "Arizona", "North CA (analytical)", "Alaska"])

def region_order(df):
    pref = ["Riverside CA", "Arizona", "Benicia CA", "Richmond", "San Leandro CA",
            "Berkeley", "El Dorado", "Sacramento", "New Mexico", "IL", "Oregon", "Alaska"]
    df = df.copy()
    df["_o"] = df["region"].map(lambda x: pref.index(x) if x in pref else 99)
    return df.sort_values(["_o", "revenue"], ascending=[True, False]).drop(columns="_o")

def metric_cols(g):
    return g[[c for c in ["region", "group", "driver", "Drivers", "Trips",
             "revenue", "driverpay", "Profit", "Margin %"] if c in g.columns]]

# ============================== CONSOLIDATED ==============================
if view == "Consolidated":
    st.subheader("Consolidated - all states")
    tot_trips = int(bk["trips"].sum()); tot_rev = float(bk["revenue"].sum())
    tot_pay = float(bk["driverpay"].sum()); tot_profit = tot_rev - tot_pay
    tot_margin = (tot_profit / tot_rev * 100) if tot_rev else 0
    c = st.columns(4)
    kpi(c[0], "Total Trips", "{:,}".format(tot_trips))
    kpi(c[1], "Revenue (First Paid)", money(tot_rev), "what First paid Beyond")
    kpi(c[2], "Driver Pay", money(tot_pay))
    kpi(c[3], "Profit", money(tot_profit), "{:.1f}% margin".format(tot_margin),
        "good" if tot_profit >= 0 else "bad")
    gg = agg_by(bk, "group")
    gg["_o"] = gg["group"].map(lambda x: GROUP_ORDER.index(x) if x in GROUP_ORDER else 99)
    gg = gg.sort_values("_o").drop(columns="_o")
    st.markdown("#### Summary by operating group")
    st.dataframe(fmt(metric_cols(gg)), use_container_width=True, hide_index=True)
    st.markdown("#### Revenue vs driver pay by group")
    st.bar_chart(gg.set_index("group")[["revenue", "driverpay"]])
    st.markdown("#### Profit by group")
    st.bar_chart(gg.set_index("group")[["Profit"]])
    st.download_button("Download Excel (by group + by region)",
        data=to_excel({"By group": fmt(metric_cols(gg)),
                       "By region": fmt(metric_cols(region_order(agg_by(bk, "region"))))}),
        file_name="BT_consolidated.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if not fr_unmatched.empty:
        st.warning("{:,} First-report trips ({} paid) belong to drivers not found "
            "in any Breakup region - usually a name-spelling difference. They are "
            "excluded from the per-region reconciliation.".format(
                len(fr_unmatched), money(fr_unmatched['net'].sum())))

# ============================== BY GROUP ==============================
elif view == "By operating group":
    st.subheader("By operating group")
    gg = agg_by(bk, "group")
    gg["_o"] = gg["group"].map(lambda x: GROUP_ORDER.index(x) if x in GROUP_ORDER else 99)
    gg = gg.sort_values("_o").drop(columns="_o")
    st.dataframe(fmt(metric_cols(gg)), use_container_width=True, hide_index=True)
    st.markdown("#### Margin % by group")
    st.bar_chart(gg.set_index("group")[["Margin %"]])

# ============================== BY REGION ==============================
elif view == "By region":
    st.subheader("By region")
    rg = region_order(agg_by(bk, "region"))
    st.dataframe(fmt(metric_cols(rg)), use_container_width=True, hide_index=True)
    st.markdown("#### Revenue vs driver pay by region")
    st.bar_chart(rg.set_index("region")[["revenue", "driverpay"]])
    st.caption("Arizona is shown as its own region (split out of the combined "
               "Riverside + Arizona file) because the Breakup sheet lists it separately.")

# ============================== TRIP RECONCILIATION ==============================
elif view == "Trip reconciliation":
    st.subheader("Trip count reconciliation - First report vs Breakup")
    rg = agg_by(bk, "region")[["region", "Trips", "revenue"]].rename(
        columns={"Trips": "Breakup Trips", "revenue": "Breakup Revenue"})
    if not first_lookup.empty:
        rg["First Trips"] = rg["region"].map(first_lookup["first_trips"]).fillna(0).astype(int)
        rg["First Paid"] = rg["region"].map(first_lookup["first_paid"]).fillna(0.0)
    else:
        rg["First Trips"] = 0; rg["First Paid"] = 0.0
    rg["Trip Diff"] = rg["First Trips"] - rg["Breakup Trips"]
    rg["$ Diff"] = rg["First Paid"] - rg["Breakup Revenue"]
    rg["Match"] = rg.apply(lambda r: "MATCH" if (r["Trip Diff"] == 0 and abs(r["$ Diff"]) < 0.5) else "CHECK", axis=1)
    rg = region_order(rg.rename(columns={"Breakup Revenue": "revenue"})).rename(columns={"revenue": "Breakup Revenue"})
    disp = rg[["region", "First Trips", "Breakup Trips", "Trip Diff",
               "First Paid", "Breakup Revenue", "$ Diff", "Match"]].copy()
    disp["First Paid"] = disp["First Paid"].map(money)
    disp["Breakup Revenue"] = disp["Breakup Revenue"].map(money)
    disp["$ Diff"] = disp["$ Diff"].map(money)
    disp = disp.rename(columns={"region": "Region"})
    st.dataframe(disp, use_container_width=True, hide_index=True)
    st.caption("A region shows MATCH when the First report and the Breakup sheet "
               "cover the exact same trips and dollars. CHECK means one source has "
               "a trip the other does not - treat that region's figure as an "
               "estimate until the two files line up trip-by-trip.")

# ============================== ARIZONA ==============================
elif view == "Arizona":
    st.subheader("Arizona - standalone")
    az = bk[bk["region_norm"].isin(["arizona", "az"])]
    if az.empty:
        st.info("No Arizona rows in the uploaded workbook(s) this week.")
    else:
        rev = float(az["revenue"].sum()); pay = float(az["driverpay"].sum())
        profit = rev - pay; margin = (profit/rev*100) if rev else 0
        c = st.columns(4)
        kpi(c[0], "Trips", "{:,}".format(int(az["trips"].sum())))
        kpi(c[1], "Revenue (First Paid)", money(rev))
        kpi(c[2], "Driver Pay", money(pay))
        kpi(c[3], "Profit", money(profit), "{:.1f}% margin".format(margin),
            "good" if profit >= 0 else "bad")
        dt = enrich(az.groupby("driver", as_index=False).agg(
            Trips=("trips", "sum"), revenue=("revenue", "sum"), driverpay=("driverpay", "sum")))
        dt = dt.sort_values("revenue", ascending=False)
        st.markdown("#### Arizona - driver detail")
        st.dataframe(fmt(dt[["driver", "Trips", "revenue", "driverpay", "Profit", "Margin %"]]),
                     use_container_width=True, hide_index=True)
        st.caption("Split out of the combined Riverside + Arizona (RS&AZ) file using "
                   "the Arizona region header in the Breakup sheet.")
        st.download_button("Download Arizona (Excel)",
            data=to_excel({"Arizona": fmt(dt[["driver","Trips","revenue","driverpay","Profit","Margin %"]])}),
            file_name="BT_Arizona.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ============================== NORTH CA ==============================
elif view == "North CA (analytical)":
    st.subheader("Northern California - analytical")
    nca = bk[bk["group"] == "N.CA (Northern California)"]
    if nca.empty:
        st.info("No Northern California rows in the uploaded workbook(s) this week.")
    else:
        rev = float(nca["revenue"].sum()); pay = float(nca["driverpay"].sum())
        profit = rev - pay; margin = (profit/rev*100) if rev else 0
        c = st.columns(4)
        kpi(c[0], "Trips", "{:,}".format(int(nca["trips"].sum())))
        kpi(c[1], "Revenue (First Paid)", money(rev))
        kpi(c[2], "Driver Pay", money(pay))
        kpi(c[3], "Profit", money(profit), "{:.1f}% margin".format(margin),
            "good" if profit >= 0 else "bad")
        area = agg_by(nca, "region")
        area["_o"] = area["region"].map(lambda x: NCA_AREA_ORDER.index(x) if x in NCA_AREA_ORDER else 99)
        area = area.sort_values("_o").drop(columns="_o")
        st.markdown("#### Summary by area")
        st.dataframe(fmt(metric_cols(area)), use_container_width=True, hide_index=True)
        st.markdown("#### Profit by area")
        st.bar_chart(area.set_index("region")[["Profit"]])
        missing = [a for a in NCA_AREA_ORDER if a not in set(area["region"])]
        if missing:
            st.caption("Areas with no trips this week: " + ", ".join(missing) + ".")
        dd = enrich(nca.groupby(["region", "driver"], as_index=False).agg(
            Trips=("trips", "sum"), revenue=("revenue", "sum"), driverpay=("driverpay", "sum")))
        dd["_o"] = dd["region"].map(lambda x: NCA_AREA_ORDER.index(x) if x in NCA_AREA_ORDER else 99)
        dd = dd.sort_values(["_o", "revenue"], ascending=[True, False]).drop(columns="_o")
        st.markdown("#### Driver detail (by area)")
        st.dataframe(fmt(dd[["region", "driver", "Trips", "revenue", "driverpay", "Profit", "Margin %"]]),
                     use_container_width=True, hide_index=True)
        st.download_button("Download North CA (Excel)",
            data=to_excel({"NCA by area": fmt(metric_cols(area)),
                           "NCA drivers": fmt(dd[["region","driver","Trips","revenue","driverpay","Profit","Margin %"]])}),
            file_name="BT_NorthCA.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ============================== ALASKA ==============================
elif view == "Alaska":
    st.subheader("Alaska")
    ak = bk[bk["group"] == "Alaska"]
    if ak.empty:
        st.info("No Alaska workbook uploaded this week.")
    else:
        rev = float(ak["revenue"].sum()); pay = float(ak["driverpay"].sum())
        profit = rev - pay; margin = (profit/rev*100) if rev else 0
        c = st.columns(4)
        kpi(c[0], "Trips", "{:,}".format(int(ak["trips"].sum())))
        kpi(c[1], "Revenue (First Paid)", money(rev))
        kpi(c[2], "Driver Pay", money(pay))
        kpi(c[3], "Profit", money(profit), "{:.1f}% margin".format(margin),
            "good" if profit >= 0 else "bad")
        dt = enrich(ak.groupby(["driver", "monitor"], as_index=False).agg(
            Trips=("trips", "sum"), revenue=("revenue", "sum"), driverpay=("driverpay", "sum")))
        dt["Monitor"] = dt["monitor"].map(lambda m: "MONITOR" if m else "")
        dt = dt.sort_values("revenue", ascending=False)
        st.markdown("#### Alaska - driver detail")
        st.dataframe(fmt(dt[["driver", "Monitor", "Trips", "revenue", "driverpay", "Profit", "Margin %"]]),
                     use_container_width=True, hide_index=True)
        mon = dt[dt["monitor"]]
        if not mon.empty:
            st.caption("Monitors (MO) show 0 trips but are still paid "
                       "({} in driver pay) - they lower the Alaska margin.".format(
                           money(mon['driverpay'].sum())))
        st.download_button("Download Alaska (Excel)",
            data=to_excel({"Alaska": fmt(dt[["driver","Monitor","Trips","revenue","driverpay","Profit","Margin %"]])}),
            file_name="BT_Alaska.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
