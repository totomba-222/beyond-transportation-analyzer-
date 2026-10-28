# Hatem's B.T. Analyzer - Beyond Transportation weekly financial analyzer
# =============================================================================
# THREE INPUT SOURCES (uploaded separately in the sidebar):
#   1) First reports      -> itemized trip report(s) from the First broker
#                            (per trip: DRIVER NAME ... NET PAY = what First paid)
#   2) EverDriven reports  -> itemized trip report(s) from the EverDriven broker
#                            (same idea: driver + amount paid per trip)
#   3) State workbooks     -> weekly workbook(s) whose "Breakup" sheet holds the
#                            per-region, per-driver breakdown (trips / revenue /
#                            driver pay). This is the ONLY source that splits
#                            Arizona out of Riverside and splits North CA into
#                            its areas, so region grouping is read from it.
#
# If no dedicated First file is uploaded, the app falls back to the
# "SP ITEMIZED REPORT" (First) sheet found inside the state workbook(s).
#
# DEFINITIONS:
#   Revenue (booked)  = Breakup revenue column (what Beyond booked for the trip)
#   Driver Pay        = Breakup payment column (what Beyond pays the driver)
#   Profit = Revenue - Driver Pay ; Margin = Profit / Revenue
#   Payer paid        = sum of NET PAY / amount from the broker itemized report
#   Reconciliation    = broker trips & dollars vs Breakup trips & dollars, per
#                       region (a 0 difference proves they cover the same trips)
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
section[data-testid="stSidebar"] hr { border-color:#27324a; }
</style>
""", unsafe_allow_html=True)

# ----------------------------- region grouping -----------------------------
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
REGION_PREF = ["Riverside CA", "Arizona", "Benicia CA", "Richmond", "San Leandro CA",
               "Berkeley", "El Dorado", "Sacramento", "New Mexico", "IL", "Oregon", "Alaska"]

MONITOR_RE = re.compile(r"\((?:M|MO|MON|MONITOR)\)", re.I)
SKIP_HEADERS = {"sr #", "grand total", "total", ""}

def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).replace("\u200b", "")
    return re.sub(r"\s+", " ", s).strip().lower()

# ----------------------------- sheet / column finders -----------------------------
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

def _find_sheet(xl, *needles):
    for sh in xl.sheet_names:
        low = sh.strip().lower()
        if any(n in low for n in needles):
            return sh
    return None

# ----------------------------- readers -----------------------------
@st.cache_data(show_spinner=False)
def read_breakup(file_bytes, fname):
    """Read the master Breakup sheet -> per-region, per-driver rows."""
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

DRIVER_KEYS = ("DRIVER NAME", "DRIVER", "NAME")
AMOUNT_KEYS = ("NET PAY", "NETPAY", "AMOUNT PAID", "TOTAL PAY", "AMOUNT", "PAID",
               "PAYMENT", "REVENUE", "FARE", "TOTAL")
TRIP_KEYS   = ("TRIP NAME", "TRIP ID", "TRIP #", "TRIP", "TRIPS", "RUN")

@st.cache_data(show_spinner=False)
def read_itemized(file_bytes, fname, payer):
    """Generic broker itemized reader (First / EverDriven). Scans the sheets,
    prefers one whose name contains 'itemized', and picks the first sheet that
    exposes a driver column + an amount column. Returns trip-level rows."""
    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    cols = ["driver","driver_key","amount","trip","payer","source"]
    order = ([s for s in xl.sheet_names if "itemized" in s.lower()] +
             [s for s in xl.sheet_names if "itemized" not in s.lower()])
    for sh in order:
        try:
            df = xl.parse(sh)
        except Exception:
            continue
        df.columns = [str(c).strip() for c in df.columns]
        dn = _find_col(df.columns, *DRIVER_KEYS)
        amt = _find_col(df.columns, *AMOUNT_KEYS)
        if not (dn and amt):
            continue
        tn = _find_col(df.columns, *TRIP_KEYS)
        out = pd.DataFrame({
            "driver": df[dn].astype(str).str.strip(),
            "amount": pd.to_numeric(df[amt], errors="coerce"),
            "trip": df[tn].astype(str) if tn else "",
        })
        out = out[out["driver"].notna() & out["driver"].ne("") & out["driver"].ne("nan")]
        out = out.dropna(subset=["amount"])
        out = out[out["driver"].map(norm).isin(("total", "grand total")) == False]
        if out.empty:
            continue
        out["driver_key"] = out["driver"].map(norm)
        out["payer"] = payer
        out["source"] = fname
        return out[cols]
    return pd.DataFrame(columns=cols)

# ----------------------------- analytics -----------------------------
def enrich(g):
    g = g.copy()
    g["Profit"] = g["revenue"] - g["driverpay"]
    g["Margin %"] = g.apply(lambda r: round(r["Profit"]/r["revenue"]*100, 1) if r["revenue"] else 0.0, axis=1)
    return g

def agg_by(df, key):
    g = df.groupby(key, as_index=False).agg(
        Drivers=("driver", "nunique"), Trips=("trips", "sum"),
        revenue=("revenue", "sum"), driverpay=("driverpay", "sum"))
    return enrich(g)

def driver_region_map(bk):
    dmap = {}
    for _, r in bk.iterrows():
        dmap.setdefault(norm(r["driver"]), r["region"])
    return dmap

def itemized_by_region(it_payer, bk):
    """Map one payer's itemized rows to Breakup regions; per-region trips+paid.
    Returns (per_region_df, unmatched_df)."""
    dmap = driver_region_map(bk)
    f = it_payer.copy()
    f["region"] = f["driver_key"].map(dmap)
    matched = f[f["region"].notna()]
    g = matched.groupby("region", as_index=False).agg(
        trips=("amount", "size"), paid=("amount", "sum"))
    return g, f[f["region"].isna()]

def money(x):
    try:
        return "${:,.0f}".format(x)
    except Exception:
        return "-"

RENAME = {"region": "Region", "group": "Operating Group", "driver": "Driver",
          "revenue": "Revenue (booked)", "driverpay": "Driver Pay",
          "trips": "Trips", "paid": "Paid"}
MONEY_COLS = ["Revenue (booked)", "Driver Pay", "Profit", "First Paid",
              "EverDriven Paid", "Paid", "Booked Revenue", "$ Diff"]

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
XLMIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

def kpi(col, label, value, sub="", cls=""):
    col.markdown(
        '<div class="kpi"><div class="lbl">{}</div>'
        '<div class="val {}">{}</div>'
        '<div class="sub">{}</div></div>'.format(label, cls, value, sub),
        unsafe_allow_html=True)

def region_order(df):
    df = df.copy()
    df["_o"] = df["region"].map(lambda x: REGION_PREF.index(x) if x in REGION_PREF else 99)
    return df.sort_values(["_o", "revenue"], ascending=[True, False]).drop(columns="_o") \
        if "revenue" in df.columns else df.sort_values("_o").drop(columns="_o")

def metric_cols(g):
    return g[[c for c in ["region", "group", "driver", "Drivers", "Trips",
             "revenue", "driverpay", "Profit", "Margin %"] if c in g.columns]]

# ----------------------------- UI: upload -----------------------------
st.title("Hatem's B.T. Analyzer  \u2014  v2 (3 upload boxes)")
st.caption("Beyond Transportation - upload First reports, EverDriven reports and "
           "the state workbooks, then open a consolidated report per payer, a "
           "state-by-state view, and the trip reconciliation.")
st.success("NEW LAYOUT v2 \u00b7 3 separate upload boxes (First / EverDriven / "
           "State workbooks) in the left sidebar \u00b7 per-state buttons \u00b7 "
           "3 consolidated reports. If you still see one upload box, you are "
           "running the OLD file.")

with st.sidebar:
    st.header("1) First reports")
    first_files = st.file_uploader("First itemized report file(s).",
        type=["xlsx", "xls"], accept_multiple_files=True, key="first")
    st.markdown("---")
    st.header("2) EverDriven reports")
    ed_files = st.file_uploader("EverDriven itemized report file(s).",
        type=["xlsx", "xls"], accept_multiple_files=True, key="ed")
    st.markdown("---")
    st.header("3) State workbooks")
    state_files = st.file_uploader("Weekly state workbook(s) with the 'Breakup' sheet.",
        type=["xlsx", "xls"], accept_multiple_files=True, key="states")
    st.markdown("---")

def _concat(frames, cols=None):
    frames = [f for f in frames if f is not None and not f.empty]
    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame(columns=cols) if cols else pd.DataFrame()

if not (first_files or ed_files or state_files):
    st.info("Upload at least one file. Put First reports in box 1, EverDriven "
            "reports in box 2, and the weekly state workbook(s) (with the "
            "'Breakup' sheet) in box 3. If you skip box 1, the app reads the "
            "First 'SP ITEMIZED REPORT' sheet from the state workbook instead.")
    st.stop()

bk = _concat([read_breakup(f.getvalue(), f.name) for f in (state_files or [])])
first_it = _concat([read_itemized(f.getvalue(), f.name, "First") for f in (first_files or [])])
if first_it.empty and state_files:  # fallback: First itemized sheet inside the state workbook
    first_it = _concat([read_itemized(f.getvalue(), f.name, "First") for f in state_files])
ed_it = _concat([read_itemized(f.getvalue(), f.name, "EverDriven") for f in (ed_files or [])])
it = _concat([first_it, ed_it])

# build navigation dynamically
views = []
if not first_it.empty: views.append("First - consolidated")
if not ed_it.empty: views.append("EverDriven - consolidated")
if not bk.empty:
    views.append("States - consolidated")
    present_groups = [g for g in GROUP_ORDER if g in set(bk["group"])]
    present_groups += [g for g in bk["group"].unique() if g not in present_groups]
    views += ["State: " + g for g in present_groups]
    if bk["region_norm"].isin(["arizona", "az"]).any():
        views.append("Arizona (standalone)")
    views.append("Trip reconciliation")
if not views:
    st.error("Could not read any usable data. First/EverDriven files need a "
             "driver + amount column; state workbooks need a 'Breakup' sheet.")
    st.stop()

view = st.sidebar.radio("Open report", views)

# ============================== PAYER CONSOLIDATED ==============================
def payer_report(it_payer, payer):
    st.subheader(payer + " - consolidated report")
    tot_trips = int(len(it_payer)); tot_paid = float(it_payer["amount"].sum())
    drivers = int(it_payer["driver_key"].nunique())
    c = st.columns(4)
    kpi(c[0], "Trips (lines)", "{:,}".format(tot_trips))
    kpi(c[1], payer + " Paid", money(tot_paid), "total amount from the report")
    kpi(c[2], "Drivers", "{:,}".format(drivers))
    kpi(c[3], "Avg / trip", money(tot_paid / tot_trips) if tot_trips else "-")
    frames = {}
    if not bk.empty:
        reg, unm = itemized_by_region(it_payer, bk)
        if not reg.empty:
            reg["group"] = reg["region"].map(lambda x: group_of(norm(x)))
            reg = region_order(reg)
            st.markdown("#### " + payer + " paid by region")
            disp = reg.rename(columns={"trips": "Trips", "paid": "Paid", "region": "Region", "group": "Operating Group"}).copy()
            disp["Paid"] = disp["Paid"].map(money)
            st.dataframe(disp, use_container_width=True, hide_index=True)
            st.bar_chart(reg.set_index("region")[["paid"]])
            frames[payer + " by region"] = disp
        if not unm.empty:
            st.warning("{:,} {} line(s) ({} ) are for drivers not found in any "
                "Breakup region - usually a name-spelling difference.".format(
                    len(unm), payer, money(unm["amount"].sum())))
    dd = it_payer.groupby("driver", as_index=False).agg(
        Trips=("amount", "size"), Paid=("amount", "sum")).sort_values("Paid", ascending=False)
    st.markdown("#### " + payer + " - by driver")
    dddisp = dd.rename(columns={"driver": "Driver"}).copy(); dddisp["Paid"] = dddisp["Paid"].map(money)
    st.dataframe(dddisp, use_container_width=True, hide_index=True)
    frames[payer + " by driver"] = dddisp
    st.download_button("Download " + payer + " (Excel)", data=to_excel(frames),
        file_name="BT_" + payer + ".xlsx", mime=XLMIME)

if view == "First - consolidated":
    payer_report(first_it, "First")

elif view == "EverDriven - consolidated":
    payer_report(ed_it, "EverDriven")

# ============================== STATES CONSOLIDATED ==============================
elif view == "States - consolidated":
    st.subheader("States - consolidated profit")
    tot_trips = int(bk["trips"].sum()); tot_rev = float(bk["revenue"].sum())
    tot_pay = float(bk["driverpay"].sum()); tot_profit = tot_rev - tot_pay
    tot_margin = (tot_profit / tot_rev * 100) if tot_rev else 0
    c = st.columns(4)
    kpi(c[0], "Total Trips", "{:,}".format(tot_trips))
    kpi(c[1], "Revenue (booked)", money(tot_rev))
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
    rg = region_order(agg_by(bk, "region"))
    st.markdown("#### Summary by region")
    st.dataframe(fmt(metric_cols(rg)), use_container_width=True, hide_index=True)
    st.download_button("Download States (Excel)",
        data=to_excel({"By group": fmt(metric_cols(gg)), "By region": fmt(metric_cols(rg))}),
        file_name="BT_States_consolidated.xlsx", mime=XLMIME)

# ============================== ARIZONA STANDALONE ==============================
elif view == "Arizona (standalone)":
    st.subheader("Arizona - standalone")
    az = bk[bk["region_norm"].isin(["arizona", "az"])]
    rev = float(az["revenue"].sum()); pay = float(az["driverpay"].sum())
    profit = rev - pay; margin = (profit/rev*100) if rev else 0
    c = st.columns(4)
    kpi(c[0], "Trips", "{:,}".format(int(az["trips"].sum())))
    kpi(c[1], "Revenue (booked)", money(rev))
    kpi(c[2], "Driver Pay", money(pay))
    kpi(c[3], "Profit", money(profit), "{:.1f}% margin".format(margin),
        "good" if profit >= 0 else "bad")
    dt = enrich(az.groupby("driver", as_index=False).agg(
        Trips=("trips", "sum"), revenue=("revenue", "sum"), driverpay=("driverpay", "sum"))) \
        .sort_values("revenue", ascending=False)
    st.markdown("#### Arizona - driver detail")
    st.dataframe(fmt(dt[["driver", "Trips", "revenue", "driverpay", "Profit", "Margin %"]]),
                 use_container_width=True, hide_index=True)
    st.caption("Split out of the combined Riverside + Arizona file using the "
               "Arizona region header in the Breakup sheet.")
    st.download_button("Download Arizona (Excel)",
        data=to_excel({"Arizona": fmt(dt[["driver","Trips","revenue","driverpay","Profit","Margin %"]])}),
        file_name="BT_Arizona.xlsx", mime=XLMIME)

# ============================== PER-STATE VIEW ==============================
elif view.startswith("State: "):
    grp = view[len("State: "):]
    sub = bk[bk["group"] == grp]
    st.subheader(grp)
    rev = float(sub["revenue"].sum()); pay = float(sub["driverpay"].sum())
    profit = rev - pay; margin = (profit/rev*100) if rev else 0
    c = st.columns(4)
    kpi(c[0], "Trips", "{:,}".format(int(sub["trips"].sum())))
    kpi(c[1], "Revenue (booked)", money(rev))
    kpi(c[2], "Driver Pay", money(pay))
    kpi(c[3], "Profit", money(profit), "{:.1f}% margin".format(margin),
        "good" if profit >= 0 else "bad")
    # region / area breakdown when the state has more than one region
    if sub["region"].nunique() > 1:
        area = agg_by(sub, "region")
        if grp == "N.CA (Northern California)":
            area["_o"] = area["region"].map(lambda x: NCA_AREA_ORDER.index(x) if x in NCA_AREA_ORDER else 99)
            area = area.sort_values("_o").drop(columns="_o")
        else:
            area = region_order(area)
        st.markdown("#### By region / area")
        st.dataframe(fmt(metric_cols(area)), use_container_width=True, hide_index=True)
        st.bar_chart(area.set_index("region")[["Profit"]])
        if grp == "N.CA (Northern California)":
            miss = [a for a in NCA_AREA_ORDER if a not in set(area["region"])]
            if miss:
                st.caption("Areas with no trips this week: " + ", ".join(miss) + ".")
    # driver detail (flag monitors)
    dd = enrich(sub.groupby(["region", "driver", "monitor"], as_index=False).agg(
        Trips=("trips", "sum"), revenue=("revenue", "sum"), driverpay=("driverpay", "sum")))
    dd["Monitor"] = dd["monitor"].map(lambda m: "MONITOR" if m else "")
    dd = dd.sort_values(["region", "revenue"], ascending=[True, False])
    st.markdown("#### Driver detail")
    st.dataframe(fmt(dd[["region", "driver", "Monitor", "Trips", "revenue", "driverpay", "Profit", "Margin %"]]),
                 use_container_width=True, hide_index=True)
    mon = dd[dd["monitor"]]
    if not mon.empty:
        st.caption("Monitors (MO) show 0 trips but are still paid ({} in driver "
                   "pay) - they lower this state's margin.".format(money(mon["driverpay"].sum())))
    # payer cross-check for this state's regions
    regions_here = set(sub["region"])
    rows = []
    for payer, src in (("First", first_it), ("EverDriven", ed_it)):
        if src.empty:
            continue
        reg, _ = itemized_by_region(src, bk)
        here = reg[reg["region"].isin(regions_here)]
        if not here.empty:
            rows.append((payer, int(here["trips"].sum()), float(here["paid"].sum())))
    if rows:
        st.markdown("#### Payer cross-check (this state)")
        pc = pd.DataFrame(rows, columns=["Payer", "Trips", "Paid"])
        pc["Paid"] = pc["Paid"].map(money)
        st.dataframe(pc, use_container_width=True, hide_index=True)
    st.download_button("Download " + grp + " (Excel)",
        data=to_excel({"Drivers": fmt(dd[["region","driver","Monitor","Trips","revenue","driverpay","Profit","Margin %"]])}),
        file_name="BT_" + re.sub(r"[^A-Za-z0-9]+", "_", grp) + ".xlsx", mime=XLMIME)

# ============================== TRIP RECONCILIATION ==============================
elif view == "Trip reconciliation":
    st.subheader("Trip reconciliation - payers vs Breakup")
    rg = agg_by(bk, "region")[["region", "Trips", "revenue"]].rename(
        columns={"Trips": "Breakup Trips", "revenue": "Booked Revenue"})
    if not first_it.empty:
        fr, _ = itemized_by_region(first_it, bk); fl = fr.set_index("region")
        rg["First Trips"] = rg["region"].map(fl["trips"]).fillna(0).astype(int)
        rg["First Paid"] = rg["region"].map(fl["paid"]).fillna(0.0)
    if not ed_it.empty:
        er, _ = itemized_by_region(ed_it, bk); el = er.set_index("region")
        rg["EverDriven Trips"] = rg["region"].map(el["trips"]).fillna(0).astype(int)
        rg["EverDriven Paid"] = rg["region"].map(el["paid"]).fillna(0.0)
    if "First Trips" in rg.columns:
        rg["Trip Diff"] = rg["First Trips"] - rg["Breakup Trips"]
        rg["$ Diff"] = rg["First Paid"] - rg["Booked Revenue"]
        rg["Match"] = rg.apply(lambda r: "MATCH" if (r["Trip Diff"] == 0 and abs(r["$ Diff"]) < 0.5) else "CHECK", axis=1)
    rg = region_order(rg.rename(columns={"Booked Revenue": "revenue"})).rename(columns={"revenue": "Booked Revenue"})
    order = ["region", "First Trips", "EverDriven Trips", "Breakup Trips", "Trip Diff",
             "First Paid", "EverDriven Paid", "Booked Revenue", "$ Diff", "Match"]
    disp = rg[[c for c in order if c in rg.columns]].copy()
    for c in ["First Paid", "EverDriven Paid", "Booked Revenue", "$ Diff"]:
        if c in disp.columns:
            disp[c] = disp[c].map(money)
    disp = disp.rename(columns={"region": "Region"})
    st.dataframe(disp, use_container_width=True, hide_index=True)
    st.caption("MATCH = the First report and the Breakup sheet cover the exact "
               "same trips and dollars for that region. CHECK = one source has a "
               "trip the other does not; treat that region as an estimate until "
               "the files line up trip-by-trip. EverDriven columns show only when "
               "an EverDriven report is uploaded.")
