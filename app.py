import io
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Hatem's B.T. Analyzer", page_icon="\U0001f690", layout="wide")

st.markdown("""
<style>
.block-container{padding-top:1.4rem;max-width:1250px}
.kpi{background:#0f172a;border:1px solid #1e293b;border-radius:14px;padding:16px 18px;margin-bottom:6px}
.kpi .lbl{color:#94a3b8;font-size:12px;letter-spacing:.04em;text-transform:uppercase}
.kpi .val{color:#f8fafc;font-size:26px;font-weight:700;margin-top:4px}
.kpi .sub{color:#64748b;font-size:12px;margin-top:2px}
.brand{background:linear-gradient(135deg,#1d4ed8,#0ea5e9);border-radius:14px;padding:14px 16px;color:#fff;margin-bottom:10px}
.brand-title{font-weight:800;font-size:18px}
.brand-sub{font-size:12px;opacity:.9}
.section-title{color:#e2e8f0;font-weight:700;margin:12px 0 4px}
.note{color:#94a3b8;font-size:12px;margin-bottom:6px}
</style>
""", unsafe_allow_html=True)


def norm_name(s):
    s = str(s).strip().lower()
    return re.sub(r"\s+", " ", s)


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
        return f"${x:,.2f}"
    except Exception:
        return "-"


# Oregon school keywords: when no Oregon state report is uploaded, First trips to
# these schools are still recognised as Oregon so they are not lost.
OR_SCHOOLS = [
    "amity hs", "arata creek", "buel es", "burlingame creek", "canyon creek",
    "dexter mccarty", "edwards day", "gladstone", "gordon russell", "hall es",
    "happy valley", "heron creek", "highland es", "hollydale", "jennings lodge",
    "john wetten", "kraxberger", "kathryn jones harrison", "knott creek",
    "lifeworks", "marylhurst", "mcminnville", "meridian creek", "molalla river",
    "mulino es", "north salem", "oregon school for the deaf", "padtc",
    "patton ms", "phillips acdy", "philomath", "powell valley", "salem heights",
    "sequoia falls", "serendipity sch", "north albany", "south albany",
    "stayton ms", "structured skills", "trillium north point", "tualatin es",
    "twality", "wheatley sch", "mark twain es",
]

STATE_NAMES = {
    "NM": "New Mexico (ABQ)", "IL": "Illinois", "N.CA": "North California",
    "S.CA": "South California", "AK": "Alaska", "OR": "Oregon",
    "Unassigned": "Unassigned",
}

# Map an uploaded state-report filename to its state code.
STATE_FILE_HINTS = [
    ("albuquerque", "NM"), ("newmexico", "NM"), ("abq", "NM"),
    ("northca", "N.CA"), ("northerncalifornia", "N.CA"), ("nca", "N.CA"),
    ("southca", "S.CA"), ("riverside", "S.CA"), ("arizona", "S.CA"), ("sca", "S.CA"),
    ("alaska", "AK"),
    ("oregon", "OR"),
    ("illinois", "IL"),
]

# Short two-letter codes are matched only as a standalone word (token), never
# as a substring, so "report" never reads as OR and "il_report" stays IL.
STATE_TOKEN_HINTS = {
    "nm": "NM", "abq": "NM",
    "nca": "N.CA", "ncal": "N.CA",
    "sca": "S.CA", "scal": "S.CA",
    "ak": "AK", "alaska": "AK",
    "or": "OR", "oregon": "OR",
    "il": "IL", "illinois": "IL",
}


def _tokens(name):
    base = re.sub(r"\.[^.]+$", "", str(name)).lower()
    return [t for t in re.split(r"[^a-z]+", base) if t]


def state_from_filename(name):
    base = re.sub(r"\.[^.]+$", "", str(name)).lower()
    compact = re.sub(r"[^a-z]", "", base)
    toks = _tokens(name)
    # 1) standalone tokens win (handles IL / AK / OR / NM / ABQ safely)
    for t in toks:
        if t in STATE_TOKEN_HINTS:
            return STATE_TOKEN_HINTS[t]
    # 2) full descriptive keywords as substrings
    for kw, code in STATE_FILE_HINTS:
        k = re.sub(r"[^a-z]", "", kw)
        if k and k in compact:
            return code
    return None


def first_file_state(name):
    toks = _tokens(name)
    if "alaska" in toks or "ak" in toks:
        return "AK"
    compact = re.sub(r"[^a-z]", "", re.sub(r"\.[^.]+$", "", str(name)).lower())
    if "alaska" in compact:
        return "AK"
    return None

# ----------------------------- readers -----------------------------
@st.cache_data(show_spinner=False)
def read_first(file_bytes, fname):
    """Read a First / SP ITEMIZED report: one row per trip with the driver,
    trip (school), miles and NET PAY (what First paid)."""
    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    best, best_score = None, -1
    for sh in xl.sheet_names:
        df = xl.parse(sh)
        df.columns = [str(c).strip() for c in df.columns]
        dn = find_col(df.columns, "DRIVER NAME", "DRIVER")
        net = find_col(df.columns, "NET PAY", "NETPAY")
        trip = find_col(df.columns, "TRIP NAME", "TRIP")
        if not (dn and net and trip):
            continue
        score = len(df) + (1000 if "itemized" in sh.lower() else 0)
        if score > best_score:
            best_score = score
            miles = find_col(df.columns, "TOTAL MILES", "MILES")
            date = find_col(df.columns, "DATE")
            out = pd.DataFrame({
                "driver_disp": df[dn].astype(str).str.strip(),
                "driver": df[dn].map(norm_name),
                "trip": df[trip].astype(str).str.strip(),
                "date": df[date] if date else "",
                "miles": pd.to_numeric(df[miles], errors="coerce") if miles else 0.0,
                "net": pd.to_numeric(df[net], errors="coerce"),
            })
            best = out
    if best is None:
        return pd.DataFrame(columns=["driver_disp", "driver", "trip", "date", "miles", "net"])
    best = best.dropna(subset=["driver"]).copy()
    best = best[best["driver"].ne("") & best["driver"].ne("nan")]
    best["miles"] = pd.to_numeric(best["miles"], errors="coerce").fillna(0.0)
    best["net"] = pd.to_numeric(best["net"], errors="coerce").fillna(0.0)
    best["source"] = fname
    best["file_state"] = first_file_state(fname)
    return best


@st.cache_data(show_spinner=False)
def read_state(file_bytes, fname, forced_code=None):
    """Read a state report to learn which drivers belong to this state and,
    for reference, their contract revenue (price) and driver payment."""
    code = forced_code or state_from_filename(fname)
    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    best, best_score = None, -1
    for sh in xl.sheet_names:
        df = xl.parse(sh)
        df.columns = [str(c).strip() for c in df.columns]
        dn = find_col(df.columns, "DRIVER NAME", "DRIVER")
        if not dn:
            continue
        rc = find_col(df.columns, "revenue", "contract")
        pc = find_col(df.columns, "payment", "pay")
        score = len(df) + (10 if rc else 0) + (10 if pc else 0)
        if score > best_score:
            best_score = score
            out = pd.DataFrame({
                "driver": df[dn].map(norm_name),
                "driver_disp": df[dn].astype(str).str.strip(),
                "contract": pd.to_numeric(df[rc], errors="coerce") if rc else pd.NA,
                "driverpay": pd.to_numeric(df[pc], errors="coerce") if pc else pd.NA,
            })
            best = out
    if best is None:
        best = pd.DataFrame(columns=["driver", "driver_disp", "contract", "driverpay"])
    best = best.dropna(subset=["driver"]).copy()
    best = best[best["driver"].ne("") & best["driver"].ne("nan")]
    best = best[~best["driver"].isin(["total", "grand total", "totals"])]
    best["state"] = code
    return code, best


def or_school_hit(trip):
    t = str(trip).lower()
    return any(k in t for k in OR_SCHOOLS)


def classify(first_df, driver_state):
    """Assign each First trip to a state: driver->state from the uploaded state
    reports first; then the Alaska First file; then Oregon-school fallback."""
    df = first_df.copy()
    df["state"] = df["driver"].map(driver_state)
    fs = df.get("file_state")
    if fs is not None:
        m = df["state"].isna() & fs.notna()
        df.loc[m, "state"] = fs[m]
    m = df["state"].isna()
    df.loc[m, "state"] = df.loc[m, "trip"].map(lambda t: "OR" if or_school_hit(t) else None)
    df["state"] = df["state"].fillna("Unassigned")
    return df

def to_excel(frames):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in frames.items():
            df.to_excel(xw, sheet_name=name[:31], index=False)
    return buf.getvalue()


def per_state_table(first_df):
    g = first_df.groupby("state").agg(
        Trips=("net", "size"),
        Revenue=("net", "sum"),
        Miles=("miles", "sum"),
        Drivers=("driver", "nunique"),
    ).reset_index()
    g["Revenue"] = g["Revenue"].round(2)
    g["Miles"] = g["Miles"].round(1)
    g["State"] = g["state"].map(lambda c: STATE_NAMES.get(c, c))
    g = g[["State", "Trips", "Revenue", "Miles", "Drivers"]]
    g = g.sort_values("Revenue", ascending=False).reset_index(drop=True)
    return g


def per_driver_table(first_df, code):
    f = first_df[first_df["state"] == code]
    g = f.groupby("driver_disp").agg(
        Trips=("net", "size"),
        Revenue=("net", "sum"),
        Miles=("miles", "sum"),
    ).reset_index().rename(columns={"driver_disp": "Driver"})
    g["Revenue"] = g["Revenue"].round(2)
    g["Miles"] = g["Miles"].round(1)
    return g.sort_values("Revenue", ascending=False).reset_index(drop=True)


def kpi(col, label, value, sub=""):
    col.markdown(
        f'<div class="kpi"><div class="lbl">{label}</div>'
        f'<div class="val">{value}</div><div class="sub">{sub}</div></div>',
        unsafe_allow_html=True)


# ----------------------------- UI -----------------------------
st.title("Hatem's B.T. Analyzer")
st.caption("\u062a\u0642\u0631\u064a\u0631 First \u00b7 \u0627\u0644\u0625\u062c\u0645\u0627\u0644\u064a \u0648\u0627\u0644\u062a\u0641\u0635\u064a\u0644 \u0644\u0643\u0644 \u0648\u0644\u0627\u064a\u0629")

with st.sidebar:
    st.markdown('<div class="brand"><div class="brand-title">\U0001f690 Hatem\'s B.T. Analyzer</div>'
                '<div class="brand-sub">Beyond Transportation</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">1 \u00b7 \u062a\u0642\u0627\u0631\u064a\u0631 First</div>', unsafe_allow_html=True)
    st.markdown('<div class="note">\u0627\u0631\u0641\u0639 \u062a\u0642\u0631\u064a\u0631 First (\u0643\u0644 \u0627\u0644\u0648\u0644\u0627\u064a\u0627\u062a) \u0648\u062a\u0642\u0631\u064a\u0631 First Alaska. NET PAY = \u0627\u0644\u0625\u064a\u0631\u0627\u062f.</div>', unsafe_allow_html=True)
    first_files = st.file_uploader("First / SP ITEMIZED reports", type=["xlsx", "xls"],
                                   accept_multiple_files=True, key="first")
    st.markdown('<div class="section-title">2 \u00b7 \u062a\u0642\u0627\u0631\u064a\u0631 \u0627\u0644\u0648\u0644\u0627\u064a\u0627\u062a (\u0627\u0644\u0645\u0631\u062c\u0639)</div>', unsafe_allow_html=True)
    st.markdown('<div class="note">\u062a\u062d\u062f\u062f \u0623\u064a \u0633\u0627\u0626\u0642 \u0641\u064a \u0623\u064a \u0648\u0644\u0627\u064a\u0629 (\u0627\u062e\u062a\u064a\u0627\u0631\u064a). \u0627\u0644\u0625\u064a\u0631\u0627\u062f \u062f\u0627\u0626\u0645\u064b\u0627 \u0645\u0646 First.</div>', unsafe_allow_html=True)
    state_files = st.file_uploader("\u062a\u0642\u0627\u0631\u064a\u0631 \u0627\u0644\u0648\u0644\u0627\u064a\u0627\u062a", type=["xlsx", "xls"],
                                   accept_multiple_files=True, key="states")

if not first_files:
    st.info("\u0627\u0631\u0641\u0639 \u062a\u0642\u0631\u064a\u0631 First \u0648\u0627\u062d\u062f \u0639\u0644\u0649 \u0627\u0644\u0623\u0642\u0644 \u0644\u0644\u0628\u062f\u0621. "
            "\u0643\u0644 \u0631\u062d\u0644\u0629 \u0648\u0625\u064a\u0631\u0627\u062f\u0647\u0627 \u064a\u064f\u0642\u0631\u0623 \u0645\u0646 \u062a\u0642\u0631\u064a\u0631 First \u0645\u0628\u0627\u0634\u0631\u0629.")
    st.stop()

first_all = pd.concat([read_first(f.getvalue(), f.name) for f in first_files], ignore_index=True)

driver_state = {}
state_ref = []
for f in state_files or []:
    code, sdf = read_state(f.getvalue(), f.name)
    if sdf.empty:
        continue
    for d in sdf["driver"].unique():
        driver_state.setdefault(d, code)
    state_ref.append(sdf)

first_all = classify(first_all, driver_state)

per_state = per_state_table(first_all)
total_trips = int(len(first_all))
total_rev = float(first_all["net"].sum())
total_miles = float(first_all["miles"].sum())
total_drivers = int(first_all["driver"].nunique())

unassigned = int((first_all["state"] == "Unassigned").sum())

# detail + per-driver frames for download
detail = first_all[["state", "driver_disp", "date", "trip", "miles", "net"]].copy()
detail["state"] = detail["state"].map(lambda c: STATE_NAMES.get(c, c))
detail.columns = ["State", "Driver", "Date", "Trip", "Miles", "First NET PAY"]

per_driver_all = []
for code in first_all["state"].unique():
    t = per_driver_table(first_all, code)
    t.insert(0, "State", STATE_NAMES.get(code, code))
    per_driver_all.append(t)
per_driver_all = pd.concat(per_driver_all, ignore_index=True) if per_driver_all else pd.DataFrame()

totals_df = pd.DataFrame([
    {"Metric": "Total Trips", "Value": total_trips},
    {"Metric": "Total Revenue (First NET PAY)", "Value": round(total_rev, 2)},
    {"Metric": "Total Miles", "Value": round(total_miles, 1)},
    {"Metric": "Total Drivers", "Value": total_drivers},
    {"Metric": "States", "Value": int((per_state["State"] != "Unassigned").sum())},
])

ak = first_all[(first_all["state"] == "AK") & (first_all["net"] == 42.5)]
ak_n = int(len(ak))
ak_df = pd.DataFrame([
    {"Metric": "Agreed rate (Alaska)", "Value": 45.0},
    {"Metric": "Trips paid $42.50", "Value": ak_n},
    {"Metric": "Shortfall per trip", "Value": 2.5},
    {"Metric": "Total owed by First", "Value": round(ak_n * 2.5, 2)},
])

excel_bytes = to_excel({
    "1. Overall Totals": totals_df,
    "2. Per-State": per_state,
    "3. Per-Driver": per_driver_all,
    "4. Per-Trip Detail": detail,
    "5. Alaska Shortfall": ak_df,
})

STATE_ORDER = [c for c in first_all["state"].unique()]
nav = ["\U0001f4ca \u0627\u0644\u0625\u062c\u0645\u0627\u0644\u064a", "\U0001f5fa\ufe0f \u062a\u0642\u0631\u064a\u0631 \u0643\u0644 \u0648\u0644\u0627\u064a\u0629"]
nav += [f"\U0001f4cd {STATE_NAMES.get(c, c)}" for c in STATE_ORDER]
choice = st.sidebar.radio("Navigation", nav)
st.sidebar.download_button("\u2b07\ufe0f \u062a\u062d\u0645\u064a\u0644 \u0627\u0644\u062a\u0642\u0631\u064a\u0631 (Excel)", data=excel_bytes,
                           file_name="BT_First_Report.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)

if unassigned:
    st.warning(f"\u064a\u0648\u062c\u062f {unassigned:,} \u0631\u062d\u0644\u0629 \u0644\u0645 \u064a\u062a\u0645 \u0631\u0628\u0637\u0647\u0627 \u0628\u0648\u0644\u0627\u064a\u0629 (\u0627\u0644\u0633\u0627\u0626\u0642 \u063a\u064a\u0631 \u0645\u0648\u062c\u0648\u062f \u0641\u064a \u0623\u064a \u062a\u0642\u0631\u064a\u0631 \u0648\u0644\u0627\u064a\u0629 \u0648\u0644\u0627 \u0645\u062f\u0631\u0633\u0629 \u0623\u0648\u0631\u064a\u062c\u0648\u0646 \u0645\u0639\u0631\u0648\u0641\u0629). \u0627\u0631\u0641\u0639 \u062a\u0642\u0631\u064a\u0631 \u0627\u0644\u0648\u0644\u0627\u064a\u0629 \u0627\u0644\u0646\u0627\u0642\u0635.")

if choice == nav[0]:
    st.subheader("\U0001f4ca \u0627\u0644\u0625\u062c\u0645\u0627\u0644\u064a \u0627\u0644\u0639\u0627\u0645")
    c = st.columns(4)
    kpi(c[0], "\u0625\u062c\u0645\u0627\u0644\u064a \u0627\u0644\u0631\u062d\u0644\u0627\u062a", f"{total_trips:,}")
    kpi(c[1], "\u0625\u062c\u0645\u0627\u0644\u064a \u0627\u0644\u0625\u064a\u0631\u0627\u062f", money(total_rev), "First NET PAY")
    kpi(c[2], "\u0625\u062c\u0645\u0627\u0644\u064a \u0627\u0644\u0623\u0645\u064a\u0627\u0644", f"{total_miles:,.0f}")
    kpi(c[3], "\u0639\u062f\u062f \u0627\u0644\u0633\u0627\u0626\u0642\u064a\u0646", f"{total_drivers:,}")
    st.markdown("#### \u0627\u0644\u0625\u064a\u0631\u0627\u062f \u062d\u0633\u0628 \u0627\u0644\u0648\u0644\u0627\u064a\u0629")
    st.bar_chart(per_state.set_index("State")[["Revenue"]], height=340)
    st.markdown("#### \u0627\u0644\u0631\u062d\u0644\u0627\u062a \u062d\u0633\u0628 \u0627\u0644\u0648\u0644\u0627\u064a\u0629")
    st.bar_chart(per_state.set_index("State")[["Trips"]], height=340)

elif choice == nav[1]:
    st.subheader("\U0001f5fa\ufe0f \u062a\u0642\u0631\u064a\u0631 \u0643\u0644 \u0648\u0644\u0627\u064a\u0629")
    show = per_state.copy()
    grand = {"State": "TOTAL", "Trips": total_trips, "Revenue": round(total_rev, 2),
             "Miles": round(total_miles, 1), "Drivers": total_drivers}
    show = pd.concat([show, pd.DataFrame([grand])], ignore_index=True)
    show_disp = show.copy()
    show_disp["Revenue"] = show_disp["Revenue"].map(money)
    show_disp["Miles"] = show_disp["Miles"].map(lambda x: f"{x:,.0f}")
    st.dataframe(show_disp, use_container_width=True, hide_index=True)

else:
    label = choice.split(" ", 1)[1]
    code = next((c for c in STATE_ORDER if STATE_NAMES.get(c, c) == label), label)
    f = first_all[first_all["state"] == code]
    st.subheader(f"\U0001f4cd {label}")
    c = st.columns(4)
    kpi(c[0], "\u0627\u0644\u0631\u062d\u0644\u0627\u062a", f"{len(f):,}")
    kpi(c[1], "\u0627\u0644\u0625\u064a\u0631\u0627\u062f", money(f["net"].sum()), "First NET PAY")
    kpi(c[2], "\u0627\u0644\u0623\u0645\u064a\u0627\u0644", f"{f['miles'].sum():,.0f}")
    kpi(c[3], "\u0627\u0644\u0633\u0627\u0626\u0642\u064a\u0646", f"{f['driver'].nunique():,}")
    if code == "AK":
        n_short = int((f["net"] == 42.5).shape[0] and (f["net"] == 42.5).sum())
        owed = n_short * 2.5
        st.markdown(
            '<div class="note">\u0623\u0644\u0627\u0633\u0643\u0627: \u0627\u0644\u0633\u0639\u0631 \u0627\u0644\u0645\u062a\u0641\u0642 \u0639\u0644\u064a\u0647 <b>$45</b> \u0644\u0644\u0631\u062d\u0644\u0629. \u0641\u064a\u0647 <b>'
            + f"{n_short:,}"
            + '</b> \u0631\u062d\u0644\u0629 \u0645\u062f\u0641\u0648\u0639\u0629 <b>$42.50</b> (\u0646\u0627\u0642\u0635 $2.50 \u0644\u0644\u0631\u062d\u0644\u0629) \u2190 First \u0645\u062f\u064a\u0646 \u0644\u0644\u0634\u0631\u0643\u0629 \u0628\u0640 <b>'
            + money(owed)
            + '</b>.</div>',
            unsafe_allow_html=True,
        )
    dt = per_driver_table(first_all, code)
    dt_disp = dt.copy()
    dt_disp["Revenue"] = dt_disp["Revenue"].map(money)
    dt_disp["Miles"] = dt_disp["Miles"].map(lambda x: f"{x:,.0f}")
    st.markdown("#### \u0627\u0644\u0633\u0627\u0626\u0642\u0648\u0646")
    st.dataframe(dt_disp, use_container_width=True, hide_index=True)
    st.markdown("#### \u062a\u0641\u0627\u0635\u064a\u0644 \u0627\u0644\u0631\u062d\u0644\u0627\u062a")
    d = f[["driver_disp", "date", "trip", "miles", "net"]].copy()
    d.columns = ["Driver", "Date", "Trip", "Miles", "First NET PAY"]
    st.dataframe(d, use_container_width=True, hide_index=True)
