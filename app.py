import io
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Hatem's B.T. Analyzer", page_icon="🚐", layout="wide")

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

# Driver -> state map (driver-first base map, 189 drivers / zero cross-state
# collisions) learned from the state reports. It is baked in so a First-only
# upload still classifies every trip to the right state; uploading a state
# report still refines / overrides it.
BASE_DRIVER_STATE = {
    'abdalrahman omer fadlalla': 'N.CA', 'abdelaziz dafi': 'NM',
    'abdelhakem benazouz': 'AK', 'abdul azizi': 'S.CA', 'abdulfatah ali alowdi': 'N.CA',
    'abdulgaleel a albadani': 'N.CA', 'abdullah ahmed eissa': 'N.CA',
    'abdulrahman alnagar alnagar': 'N.CA', 'abeer ahmad dhaifallah': 'N.CA',
    'abla suleiman': 'S.CA', 'adam ait azzat': 'NM', 'adeeb saleh anagar': 'N.CA',
    'adonis gonzalez': 'NM', 'ahmad jaarah': 'S.CA', 'ahmed (mo)': 'AK',
    'ahmed musaad almakkawi': 'N.CA', 'akram awad': 'S.CA', 'alal mohammed bosh': 'N.CA',
    'alamin mohammed y bakor': 'AK', 'alberto ramirez': 'S.CA', 'alexis santos': 'NM',
    'ali adam babeker': 'AK', 'ali saleh hassan': 'N.CA', 'alsadig m mohammed': 'N.CA',
    'ammar alammari': 'N.CA', 'angely wladiuska carrero': 'NM',
    'arette celeste eredia': 'S.CA', 'ashu no last name': 'S.CA',
    'asma mohammed alhamdani': 'N.CA', 'atta ul mohsin': 'S.CA', 'avinash tiwari': 'S.CA',
    'awad ali arbab': 'IL', 'ayman awad': 'NM', 'aziza rayan': 'S.CA',
    'azmi maghathe': 'S.CA', 'bahati basoma': 'AK', 'bassel bahnassi': 'S.CA',
    'brahim bouhamadi': 'NM', 'brahima conde': 'AK', 'christine abrego leyva': 'NM',
    'christopher nicholas rutty': 'AK', 'dana r dbiesi': 'S.CA', 'danier requejo': 'NM',
    'dayanys pie rodriguez': 'NM', 'dehanyi ruiz piti (mo)': 'AK',
    'denakhalil mahmoud al shoukha': 'S.CA', 'denis zamora': 'S.CA',
    'dianelis dr la caridad delgado san juan': 'NM', 'dieumerci chongo (mo)': 'AK',
    'dina farha': 'S.CA', 'ezzat (mo)': 'AK', 'faisal seifou mahamat eltahir': 'AK',
    'fares ameen alshalh': 'N.CA', 'fathi aloui': 'NM', 'fausta piti montero': 'AK',
    'fitsum t tessema': 'NM', 'francisco berrocal camposano': 'AK',
    'franco berrocal camposano': 'AK', 'fuad aleiadih': 'S.CA',
    'gabriel feliz suarez': 'AK', 'habes al tayyeb': 'N.CA',
    'hanan hassan almalahi': 'N.CA', 'hassan mahmoud hassan': 'N.CA',
    'hayat khudhair khalaf': 'AK', 'heba al nser': 'S.CA', 'hesham alrawhani': 'N.CA',
    'hiadar elsayed': 'N.CA', 'himanshu gupta': 'S.CA', 'hiter requejo pena': 'NM',
    'hoda sharaby': 'S.CA', 'husni mubarik': 'N.CA', 'ibrahim m elsayed': 'N.CA',
    'ibrahim mahmoud hassan mohamed': 'N.CA', 'ildephonse tshimpumpu': 'AK',
    'isam qadari': 'N.CA', 'iyad yousef hamdan': 'S.CA', 'james ken puol': 'AK',
    'jennifer soes alizon': 'NM', 'jeremie kitenge katumba': 'AK',
    'jihane benchaouch': 'S.CA', 'jose antonio abreu': 'AK', 'juan fuenmayor': 'NM',
    'judith mutalegwa kizungu': 'IL', 'julio e victoriano': 'AK', 'jumana f naser': 'NM',
    'kevin j machuca': 'AK', 'khalid abu sarriyeh': 'S.CA', 'khalil asfan': 'NM',
    'laith alfayadh': 'S.CA', 'lazaro armentero': 'NM', 'leen albahnassi': 'S.CA',
    'leila hamad rayan': 'S.CA', 'lithe farouk abdullah': 'S.CA', 'lucia c rosendo': 'NM',
    'lulit girma bune': 'N.CA', 'magali de los angeles garcia': 'AK',
    'mandeep singh': 'S.CA', 'mansoor saleh mohammed al ansy': 'AK',
    'maria rivera-ramirez': 'S.CA', 'martin bugere': 'IL',
    'mayelin rives santiesteban': 'NM', 'miriam dawod rayan': 'S.CA',
    'mohamed ahmed hugais': 'N.CA', 'mohamed b ayuob': 'AK',
    'mohamed hussein altayeb abdalla': 'N.CA', 'mohamed omar ali': 'N.CA',
    'mohamed omir': 'N.CA', 'mohammad hamdan ahmad alsutari': 'S.CA',
    'mohammad m al bitari': 'NM', 'mohammed a.i hejab': 'N.CA',
    'mohammed emad bedaer': 'S.CA', 'mohammed h adam': 'N.CA',
    'mohaned abdelazim ahmed elwali': 'N.CA', 'mona bazzoun': 'S.CA',
    'mostafa safwan alhakim': 'S.CA', 'mostafa sharaby': 'S.CA',
    'mubashar b ahmad': 'S.CA', 'muhammad bilal naeem': 'S.CA', 'muhammad laiq': 'N.CA',
    'muhammad obaidul hussain': 'S.CA', 'mustafa ali albarea': 'N.CA',
    'mustafa f m zatar': 'S.CA', 'mustafa hassan abdalkareem': 'N.CA',
    'nabeel aldabbas': 'S.CA', 'nada a suleiman': 'S.CA', 'nafeesa hakimi': 'NM',
    'nagibah e alghazali': 'N.CA', 'najib fettah': 'NM', 'neelam sadiq': 'S.CA',
    'nesrin elshabasy': 'S.CA', 'niazbina joyan': 'NM', 'nihma farha': 'S.CA',
    'niveen mohd abdel aziz abbad': 'S.CA', 'no given name rohit kumar': 'S.CA',
    'nonamegiven sukhvinder': 'S.CA', 'noreldin saddig osaman': 'AK',
    'nour rayyan': 'S.CA', 'omer mustafa': 'N.CA', 'omer omer': 'N.CA',
    'pandasi mugisha': 'AK', 'pedro julio victoriano , (mo)': 'AK',
    'radwan soueidan': 'NM', 'raisa rosendo': 'NM', 'rana muhammad abrar bashir': 'S.CA',
    'rana nazmi abu samrah salaymeh': 'S.CA', 'rasem s alessa': 'NM',
    'rashid masood malik': 'N.CA', 'rehan ahmad malik': 'S.CA',
    'robert luis cabrera ibargoyin': 'NM', 'rodney perez': 'NM',
    'ruben bruno ramirez rivera': 'S.CA', 'safwan alhakim': 'S.CA',
    'saif said awda': 'S.CA', 'salah hassan': 'N.CA', 'salah musa hussein': 'S.CA',
    'salwa saleh anagar': 'N.CA', 'samir m abas': 'N.CA', 'sandeep singh bajwa': 'S.CA',
    'saqib hussain': 'S.CA', 'sarah hamade rayyan': 'S.CA',
    'sheikh shahzaib anwar': 'N.CA', 'siddieg basher khair': 'N.CA',
    'snose omar hamid ali': 'N.CA', 'solomon bekkele': 'N.CA', 'sucad hassan cali': 'N.CA',
    'sukhjit singh': 'S.CA', 'sultan alhalemi': 'N.CA', 'syed saleem ahmad': 'S.CA',
    'tahani hussain': 'S.CA', 'taquia davis': 'S.CA', 'taranjeet singh': 'S.CA',
    'tarek m beltagy': 'NM', 'thaer abusnoubar': 'S.CA', 'wadah alomaisi alomaisi': 'N.CA',
    'wilder antonio montejo arencibia': 'NM', 'xiomara estrellita (mo)': 'AK',
    'yajaira mercedes rodriguez (mo)': 'AK', 'yanina leydinan burgos linares': 'AK',
    'yara fakhrieh jaber': 'S.CA', 'yaremys rodriguez rosendo': 'NM',
    'yasmany carmona luna': 'NM', 'yeshi challa': 'N.CA', 'yoel graveran': 'NM',
    'yosmer armando carrero': 'NM', 'yousef yahya alzawkari': 'N.CA',
    'yuder casanova robles': 'NM', 'zajary laza chapotin': 'NM', 'zeinab ali': 'NM',
    'zohra joyan': 'NM',
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
    # keep the column as object dtype so string assignment never hits
    # pandas 3.0 LossySetitemError (float->str) when there are no matches.
    state = df["driver"].map(driver_state).astype("object")
    fs = df.get("file_state")
    if fs is not None:
        fs = fs.astype("object")
        need = state.isna() & fs.notna()
        state = state.where(~need, fs)
    need = state.isna()
    or_state = df["trip"].map(lambda t: "OR" if or_school_hit(t) else None).astype("object")
    state = state.where(~need, or_state)
    df["state"] = state.fillna("Unassigned").astype("object")
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
    tot = g["Revenue"].sum()
    g["Share %"] = (g["Revenue"] / tot * 100).round(1) if tot else 0.0
    g["Rev/Trip"] = (g["Revenue"] / g["Trips"].replace(0, pd.NA)).round(2)
    g = g[["State", "Trips", "Revenue", "Miles", "Drivers", "Share %", "Rev/Trip"]]
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
st.caption("First Report · Totals & Per-State Breakdown")

with st.sidebar:
    st.markdown('<div class="brand"><div class="brand-title">🚐 Hatem\'s B.T. Analyzer</div>'
                '<div class="brand-sub">Beyond Transportation</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">1 · First Reports</div>', unsafe_allow_html=True)
    st.markdown('<div class="note">Upload the First report (all states) and the First Alaska report. NET PAY = Revenue.</div>', unsafe_allow_html=True)
    first_files = st.file_uploader("First / SP ITEMIZED reports", type=["xlsx", "xls"],
                                   accept_multiple_files=True, key="first")
    st.markdown('<div class="section-title">2 · State Reports (reference)</div>', unsafe_allow_html=True)
    st.markdown('<div class="note">Maps each driver to a state (optional). Revenue always comes from First.</div>', unsafe_allow_html=True)
    state_files = st.file_uploader("State reports", type=["xlsx", "xls"],
                                   accept_multiple_files=True, key="states")

if not first_files:
    st.info("Upload at least one First report to begin. "
            "Every trip and its revenue is read directly from the First report.")
    st.stop()

first_all = pd.concat([read_first(f.getvalue(), f.name) for f in first_files], ignore_index=True)

driver_state = dict(BASE_DRIVER_STATE)
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
nav = ["📊 Overview", "🗺️ Per-State Report"]
nav += [f"📍 {STATE_NAMES.get(c, c)}" for c in STATE_ORDER]
choice = st.sidebar.radio("Navigation", nav)
st.sidebar.download_button("⬇️ Download Report (Excel)", data=excel_bytes,
                           file_name="BT_First_Report.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)

if unassigned:
    st.warning(f"{unassigned:,} trips could not be matched to a state (driver not found in any state report or known Oregon school). Upload the missing state report.")

if choice == nav[0]:
    st.subheader("📊 Overall Totals")
    c = st.columns(4)
    kpi(c[0], "Total Trips", f"{total_trips:,}")
    kpi(c[1], "Total Revenue", money(total_rev), "First NET PAY")
    kpi(c[2], "Total Miles", f"{total_miles:,.0f}")
    kpi(c[3], "Drivers", f"{total_drivers:,}")
    st.markdown("#### Revenue by State")
    st.bar_chart(per_state.set_index("State")[["Revenue"]], height=340)
    st.markdown("#### Trips by State")
    st.bar_chart(per_state.set_index("State")[["Trips"]], height=340)

elif choice == nav[1]:
    st.subheader("🗺️ Per-State Report")
    show = per_state.copy()
    grand = {"State": "TOTAL", "Trips": total_trips, "Revenue": round(total_rev, 2),
             "Miles": round(total_miles, 1), "Drivers": total_drivers,
             "Share %": 100.0,
             "Rev/Trip": round(total_rev / total_trips, 2) if total_trips else 0.0}
    show = pd.concat([show, pd.DataFrame([grand])], ignore_index=True)
    show_disp = show.copy()
    show_disp["Revenue"] = show_disp["Revenue"].map(money)
    show_disp["Miles"] = show_disp["Miles"].map(lambda x: f"{x:,.0f}")
    show_disp["Share %"] = show_disp["Share %"].map(lambda x: f"{x:.1f}%")
    show_disp["Rev/Trip"] = show_disp["Rev/Trip"].map(money)
    st.dataframe(show_disp, use_container_width=True, hide_index=True)

else:
    label = choice.split(" ", 1)[1]
    code = next((c for c in STATE_ORDER if STATE_NAMES.get(c, c) == label), label)
    f = first_all[first_all["state"] == code]
    st.subheader(f"📍 {label}")
    c = st.columns(4)
    kpi(c[0], "Trips", f"{len(f):,}")
    kpi(c[1], "Revenue", money(f["net"].sum()), "First NET PAY")
    kpi(c[2], "Miles", f"{f['miles'].sum():,.0f}")
    kpi(c[3], "Drivers", f"{f['driver'].nunique():,}")
    if code == "AK":
        n_short = int((f["net"] == 42.5).shape[0] and (f["net"] == 42.5).sum())
        owed = n_short * 2.5
        st.markdown(
            '<div class="note">Alaska: agreed rate <b>$45</b> per trip. There are <b>'
            + f"{n_short:,}"
            + '</b> trips paid <b>$42.50</b> (short by $2.50 each) → First owes the company <b>'
            + money(owed)
            + '</b>.</div>',
            unsafe_allow_html=True,
        )
    dt = per_driver_table(first_all, code)
    dt_disp = dt.copy()
    dt_disp["Revenue"] = dt_disp["Revenue"].map(money)
    dt_disp["Miles"] = dt_disp["Miles"].map(lambda x: f"{x:,.0f}")
    st.markdown("#### Drivers")
    st.dataframe(dt_disp, use_container_width=True, hide_index=True)
    st.markdown("#### Trip Details")
    d = f[["driver_disp", "date", "trip", "miles", "net"]].copy()
    d.columns = ["Driver", "Date", "Trip", "Miles", "First NET PAY"]
    st.dataframe(d, use_container_width=True, hide_index=True)
