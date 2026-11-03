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
import io, re, unicodedata, json, tempfile
from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Hatem's B.T. Analyzer", page_icon="BT", layout="wide")

# ----------------------------- styling (dark app) -----------------------------
st.markdown("""
<style>
.stApp { background:radial-gradient(circle at 10% 0%,#172554 0%,#0b1020 42%,#0b101b 100%); color:#e8edf6; }
section[data-testid="stSidebar"] { background:linear-gradient(180deg,#111b36 0%,#12172a 55%,#1e1635 100%); border-right:1px solid #26365d; }
[data-testid="stSidebar"] .block-container { padding:1rem .85rem 2rem; }
h1,h2,h3,h4 { color:#f2f6ff; }
.kpi { background:linear-gradient(145deg,rgba(30,41,72,.95),rgba(15,23,42,.96)); border:1px solid #33456f;
       border-radius:16px; padding:16px 18px; min-height:94px; box-shadow:0 8px 22px rgba(0,0,0,.16); }
.kpi .lbl { font-size:11px; letter-spacing:.08em; color:#a9bbdb; text-transform:uppercase; }
.kpi .val { font-size:26px; font-weight:750; color:#ffffff; margin-top:7px; }
.kpi .sub { font-size:12px; color:#8fa5ce; margin-top:4px; }
.good { color:#35d49a !important; } .bad { color:#ff7777 !important; } .warn { color:#ffcf5c !important; }
div[data-testid="stDataFrame"] { border-radius:14px; overflow:hidden; border:1px solid #2a3a60; }
.brand {padding:17px 15px;border-radius:18px;background:linear-gradient(135deg,#2563eb 0%,#4f46e5 48%,#7c3aed 100%);color:white;margin-bottom:17px;box-shadow:0 10px 28px rgba(37,99,235,.25);}
.brand-title {font-size:18px;font-weight:850;letter-spacing:-.02em;} .brand-sub {font-size:11px;opacity:.82;margin-top:5px;}
.section-title {font-size:10px;text-transform:uppercase;letter-spacing:.16em;color:#9fc5ff;font-weight:850;margin:18px 3px 8px;}
.sidebar-note {font-size:11px;color:#9aaed0;padding:7px 4px 10px;line-height:1.45;}
section[data-testid="stSidebar"] .stFileUploader {border-radius:12px;background:rgba(255,255,255,.035);}
section[data-testid="stSidebar"] [data-testid="stExpander"] {border:1px solid #2a3b64;border-radius:12px;background:rgba(15,23,42,.32);}
[data-testid="stMetric"] {background:#111b32;border:1px solid #2d416d;border-radius:13px;padding:10px;}
</style>
""", unsafe_allow_html=True)

# ----------------------------- helpers -----------------------------
MONITOR_RE = re.compile(r"\((?:M|MO|MON|MONITOR)\)", re.I)

SUMMARY_NAMES = {"total", "grand total", "subtotal", "sub total", "sum", "totals", "nan", ""}

STATE_ALIASES = {
    "SCA":"S.CA","SOUTHCA":"S.CA","SOUTHERNCA":"S.CA","SOUTHCALIFORNIA":"S.CA",
    "RSAZ":"S.CA","RIVERSIDE":"S.CA","ARIZONA":"S.CA","AZ":"S.CA",
    "NCA":"N.CA","NORTHCA":"N.CA","NORTHERNCA":"N.CA","NORTHCALIFORNIA":"N.CA",
    "NORTHCAREPORT":"N.CA","BENICIA":"N.CA","SAC":"N.CA","SACRAMENTO":"N.CA",
    "MON":"N.CA","MONTEREY":"N.CA","SANLEANDRO":"N.CA",
    "BERKELEY":"N.CA","RICHMOND":"N.CA","ELDORADO":"N.CA",
    "IL":"IL","ILLINOIS":"IL","ILREPORT":"IL",
    "NM":"NM","NEWMEXICO":"NM","ABQ":"NM","ALBUQUERQUE":"NM",
    "OR":"OR","OREGON":"OR",
    "AK":"AK","ALASKA":"AK",
}

# Route/city hints. Exact city pricing should be supplied in the weekly
# breakdown; these hints only assign a trip to its state.
ROUTE_STATE_HINTS = {
    "BERKELEY":"N.CA", "BENICIA":"N.CA", "RICHMOND":"N.CA",
    "SAN LEANDRO":"N.CA", "EL DORADO":"N.CA", "ELDORADO":"N.CA",
    "OAKLAND":"N.CA", "HAYWARD":"N.CA", "FREMONT":"N.CA",
    "CONCORD":"N.CA", "WALNUT CREEK":"N.CA", "VALLEJO":"N.CA",
    "SAN PABLO":"N.CA", "ANTIOCH":"N.CA", "FAIRFIELD":"N.CA",
    "SACRAMENTO":"N.CA", "MONTEREY":"N.CA",
    "RIVERSIDE":"S.CA", "ARIZONA":"S.CA", "PHOENIX":"S.CA",
    "SAN DIEGO":"S.CA", "LOS ANGELES":"S.CA",
    "ANCHORAGE":"AK", "PORTLAND":"OR", "GRESHAM":"OR",
    "SALEM":"OR", "ALBUQUERQUE":"NM", "CHICAGO":"IL",
}

def state_from_route(text):
    t = str(text or '').upper()
    for city, code in sorted(ROUTE_STATE_HINTS.items(), key=lambda kv: len(kv[0]), reverse=True):
        if city in t:
            return code
    return None

# Driver-to-location map extracted from the supplied weekly locations report.
LOCATION_DRIVER_STATE = {'2 608': 'N.CA',
 'abdalrahman omer fadlalla': 'N.CA',
 'abdelaziz dafi': 'NM',
 'abdoun abdulmutalb hassan abdoun': 'OR',
 'abdulazlz hamwl': 'OR',
 'abdulfatah ali alowdi': 'N.CA',
 'abdulgaleel a albadani': 'N.CA',
 'abdullah ahmed eissa': 'N.CA',
 'abdulrahman alnagar alnagar': 'N.CA',
 'abeer ahmad dhaifallah': 'N.CA',
 'abla suleiman': 'S.CA',
 'adam ait azzat': 'NM',
 'adeeb saleh anagar': 'N.CA',
 'adham hammadeh': 'OR',
 'adonis gonzalez': 'NM',
 'ahmad jaarah': 'S.CA',
 'ahmat aboubakar': 'OR',
 'ahmed musaad almakkawi': 'N.CA',
 'aicha orabi': 'OR',
 'akram awad': 'S.CA',
 'alaa hassan alhalaqi': 'OR',
 'alberto ramirez': 'S.CA',
 'alexis santos': 'NM',
 'ali saleh hassan': 'N.CA',
 'alsadig m mohammed': 'N.CA',
 'amer ali alabshalah': 'N.CA',
 'ammar alammari': 'N.CA',
 'angely wladiuska carrero': 'NM',
 'arette celeste eredia': 'S.CA',
 'asalia azucena escobedo barrios de giron': 'OR',
 'ashu no last name': 'S.CA',
 'asma mohammed alhamdani': 'N.CA',
 'atta ul mohsin': 'S.CA',
 'avinash tiwari': 'S.CA',
 'awad ali arbab': 'IL',
 'ayman awad': 'NM',
 'aziza rayan': 'S.CA',
 'azmi maghathe': 'S.CA',
 'basem chami': 'OR',
 'bashka hussein abdirahman': 'OR',
 'bassel bahnassi': 'S.CA',
 'brahim bouhamadi': 'NM',
 'christine abrego leyva': 'NM',
 'dana r dbiesi': 'S.CA',
 'danier requejo': 'NM',
 'dayanys pie rodriguez': 'NM',
 'denakhalil mahmoud al shoukha': 'S.CA',
 'dianelis dr la caridad delgado san juan': 'NM',
 'dina farha': 'S.CA',
 'djamal ali alkhali': 'OR',
 'doangjok otan': 'OR',
 'douglas omar giron': 'OR',
 'emad h zaki': 'OR',
 'fares ameen alshalh': 'N.CA',
 'fitsum t tessema': 'NM',
 'fuad aleiadih': 'S.CA',
 'getachew dadi areda': 'OR',
 'ghofran aldudu': 'OR',
 'hadeel m al imam': 'OR',
 'hanan hassan almalahi': 'N.CA',
 'hanan mezher alhashimi': 'OR',
 'hasan ammar alkadi': 'OR',
 'hashmatullah alam': 'OR',
 'hassan mahmoud hassan': 'N.CA',
 'heba al nser': 'S.CA',
 'hesham alrawhani': 'N.CA',
 'hiadar elsayed': 'N.CA',
 'himanshu gupta': 'S.CA',
 'hiter requejo pena': 'NM',
 'hoda sharaby': 'S.CA',
 'husni mubarik': 'N.CA',
 'hussein ibrahim alsheikh': 'OR',
 'hussien al akraa': 'OR',
 'ibrahim m elsayed': 'N.CA',
 'ibrahim mahmoud hassan mohamed': 'N.CA',
 'isam qadari': 'N.CA',
 'issa a ghallan': 'OR',
 'iyad yousef hamdan': 'S.CA',
 'jaafar jaafar': 'OR',
 'jennifer soes alizon': 'NM',
 'jihane benchaouch': 'S.CA',
 'jinan jasim': 'OR',
 'juan fuenmayor': 'NM',
 'judith mutalegwa kizungu': 'IL',
 'julie ali hussein': 'OR',
 'jumana f naser': 'NM',
 'kassaye amaha medhin': 'OR',
 'katy martinez barboza': 'OR',
 'khaled almaliki': 'N.CA',
 'khalid abu sarriyeh': 'S.CA',
 'khalil asfan': 'NM',
 'leen albahnassi': 'S.CA',
 'leila hamad rayan': 'S.CA',
 'lithe farouk abdullah': 'S.CA',
 'lucia c rosendo': 'NM',
 'lulit girma bune': 'N.CA',
 'mahamat noh': 'OR',
 'mandeep singh': 'S.CA',
 'maram issa ghallan': 'OR',
 'maria rivera ramirez': 'S.CA',
 'martin bugere': 'IL',
 'mayelin rives santiesteban': 'NM',
 'miriam dawod rayan': 'S.CA',
 'mohamad ali alakraa': 'OR',
 'mohamad ali shukur': 'OR',
 'mohamed ahmed hugais': 'N.CA',
 'mohamed hussein altayeb abdalla': 'N.CA',
 'mohamed omar ali': 'N.CA',
 'mohamed omir': 'N.CA',
 'mohammad hamdan ahmad alsutari': 'S.CA',
 'mohammad m al bitari': 'NM',
 'mohammad qasem hemat': 'N.CA',
 'mohammed a i hejab': 'N.CA',
 'mohammed h adam': 'N.CA',
 'mohaned abdelazim ahmed elwali': 'N.CA',
 'mona bazzoun': 'S.CA',
 'mostafa safwan alhakim': 'S.CA',
 'mostafa sharaby': 'S.CA',
 'muhammad bilal naeem': 'S.CA',
 'muhammad laiq': 'N.CA',
 'muhammad obaidul hussain': 'S.CA',
 'mustafa ali albarea': 'N.CA',
 'mustafa f m zatar': 'S.CA',
 'mustafa hassan abdalkareem': 'N.CA',
 'mustafa mabrour': 'OR',
 'nabeel aldabbas': 'S.CA',
 'nada a suleiman': 'S.CA',
 'nada abusnoubar': 'S.CA',
 'nafeesa hakimi': 'NM',
 'nagi alnaeem': 'N.CA',
 'nagibah e alghazali': 'N.CA',
 'najib fettah': 'NM',
 'nasri abdirahman hussen': 'OR',
 'nesrin elshabasy': 'S.CA',
 'niazbina joyan': 'NM',
 'niveen mohd abdel aziz abbad': 'S.CA',
 'nonamegiven sukhvinder': 'S.CA',
 'omer mustafa': 'N.CA',
 'omer omer': 'N.CA',
 'radwan soueidan': 'NM',
 'raisa rosendo': 'NM',
 'rana muhammad abrar bashir': 'S.CA',
 'rana nazmi abu samrah salaymeh': 'S.CA',
 'rasem s alessa': 'NM',
 'rashid masood malik': 'N.CA',
 'rehan ahmad malik': 'S.CA',
 'robert luis cabrera ibargoyin': 'NM',
 'rodney perez': 'NM',
 'ruben bruno ramirez rivera': 'S.CA',
 'safwan alhakim': 'S.CA',
 'saif said awda': 'S.CA',
 'salah hassan': 'N.CA',
 'salah musa hussein': 'S.CA',
 'salwa saleh anagar': 'N.CA',
 'samir m abas': 'N.CA',
 'sandeep singh bajwa': 'S.CA',
 'sanoussi ali alkhali': 'OR',
 'saqib hussain': 'S.CA',
 'sarah hamade rayyan': 'S.CA',
 'siddieg basher khair': 'N.CA',
 'snose omar hamid ali': 'N.CA',
 'solomon bekkele': 'N.CA',
 'sucad hassan cali': 'N.CA',
 'suhaib yousef batayneh': 'N.CA',
 'sukhjit singh': 'S.CA',
 'sultan alhalemi': 'N.CA',
 'syed saleem ahmad': 'S.CA',
 'tahani hussain': 'S.CA',
 'taquia davis': 'S.CA',
 'taranjeet singh': 'S.CA',
 'tarek m beltagy': 'NM',
 'thaer abusnoubar': 'S.CA',
 'thet naing tun': 'OR',
 'wadah alomaisi alomaisi': 'N.CA',
 'waeel al auosh': 'OR',
 'wesal m alemam': 'OR',
 'wilder antonio montejo arencibia': 'NM',
 'yara fakhrieh jaber': 'S.CA',
 'yaremys rodriguez rosendo': 'NM',
 'yasmany carmona luna': 'NM',
 'yeshi challa': 'N.CA',
 'yoel graveran': 'NM',
 'yosmer armando carrero': 'NM',
 'yousef yahya alzawkari': 'N.CA',
 'yuder casanova robles': 'NM',
 'zainab gheni': 'OR',
 'zajary laza chapotin': 'NM',
 'zeinab ali': 'NM',
 'zohra joyan': 'NM'}

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


# Company / aggregate markers that mean the filename is NOT a single state
# (e.g. "Beyond Transportation IL INC." is the company, not Illinois; the
# "ALL_STATES" / "WEEKLY" master is multi-state and handled by its sheets).
FILE_NON_STATE = ("inc", "beyond", "transport", "all state", "allstate",
                  "all_state", "allstates", "weekly", "friist", "first")


def first_file_state(name):
    """If a First file clearly belongs to ONE state (e.g. Alaska_first.xlsx),
    return that state code; otherwise None (don't force a state)."""
    base = re.sub(r"\.[^.]+$", "", str(name)).lower()
    scan = base
    for w in FILE_NON_STATE:
        scan = scan.replace(w, " ")
    key = re.sub(r"[^a-z]", "", scan).upper()
    if key in STATE_ALIASES:
        return STATE_ALIASES[key]
    for alias, val in STATE_ALIASES.items():
        if len(alias) >= 3 and alias in key:
            return val
    return None

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
    """Read a First report. Pick the TRIP-LEVEL sheet (SP ITEMIZED REPORT),
    never an aggregated summary sheet, so trip counts and NET PAY are the real
    per-trip cash. Returns per-trip df:
       driver, driver_disp, net (First paid), trip, miles, monitor."""
    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    best, best_key = None, (-1, -1)
    for sh in xl.sheet_names:
        df = xl.parse(sh)
        df.columns = [str(c).strip() for c in df.columns]
        dn = find_col(df.columns, "DRIVER NAME", "DRIVER")
        npc = find_col(df.columns, "NET PAY", "NETPAY")
        if not (dn and npc):
            continue
        tn = find_col(df.columns, "TRIP NAME", "TRIP")
        mi = find_col(df.columns, "TOTAL MILES", "MILES")
        tc = find_col(df.columns, "TRIP CODE")
        dt = find_col(df.columns, "DATE")
        # prefer the itemized trip-level sheet over any aggregated sheet
        name = str(sh).lower()
        if "itemized" in name:
            score = 3
        elif tn and (tc or dt):
            score = 2
        else:
            score = 1
        out = pd.DataFrame({
            "driver": df[dn].map(norm_name),
            "driver_disp": df[dn].astype(str).str.strip(),
            "net": pd.to_numeric(df[npc], errors="coerce"),
            "trip": df[tn].astype(str) if tn else "",
            "miles": pd.to_numeric(df[mi], errors="coerce") if mi else 0,
        })
        # First reports vary by export: city may be in Trip Name, District,
        # pickup/drop-off, company, or location columns. Combine all available
        # route fields so classification is based on the trip itself first.
        route_parts = [out["trip"].astype(str)]
        for alias in ("DISTRICT", "CITY", "LOCATION", "PICKUP", "PICK UP",
                      "DROP OFF", "DROPOFF", "ORIGIN", "DESTINATION", "COMPANY"):
            col = find_col(df.columns, alias)
            if col and col != tn:
                route_parts.append(df[col].astype(str).reset_index(drop=True))
        out["route_text"] = pd.Series(route_parts[0], index=out.index).fillna("")
        for part in route_parts[1:]:
            out["route_text"] = out["route_text"] + " | " + part.to_numpy(dtype=str)
        out["route_state"] = out["route_text"].map(state_from_route)
        out = out.dropna(subset=["net"])
        out = _clean_driver(out)
        out = out[~out["driver"].isin(SUMMARY_NAMES)]
        key = (score, len(out))
        if key > best_key:
            best_key, best = key, out
    if best is None:
        return pd.DataFrame(columns=["driver", "driver_disp", "net", "trip", "miles", "monitor"])
    best = best.copy()
    best["monitor"] = best["trip"].astype(str).apply(lambda t: bool(MONITOR_RE.search(t)))
    best["source"] = fname
    return best

@st.cache_data(show_spinner=False)
def read_state(file_bytes, fname, forced_code=None):
    """Read a state reference file. Returns (state_code, per-trip df:
       driver, driver_disp, contract, driverpay, state)."""
    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    best = None
    best_report_contract_total = None
    best_report_pay_total = None
    for sh in xl.sheet_names:
        df = xl.parse(sh)
        df.columns = [str(c).strip() for c in df.columns]
        dn = find_col(df.columns, "DRIVER NAME", "DRIVER")
        rc = find_col(df.columns, "revenue")
        pc = find_col(df.columns, "PAY", "payment")
        if not (dn and rc and pc):
            continue
        raw_contract = pd.to_numeric(df[rc], errors="coerce")
        raw_pay = pd.to_numeric(df[pc], errors="coerce")
        raw_driver = df[dn].astype(str).str.strip()
        # State reports often end with an official total row. Depending on the
        # export, its driver cell is blank, "Total", "Grand Total", "Subtotal",
        # or another label from SUMMARY_NAMES. Read the last such numeric row
        # explicitly; never treat it as a trip.
        summary_driver = raw_driver.map(norm_name)
        total_mask = summary_driver.isin(SUMMARY_NAMES) & (raw_contract.notna() | raw_pay.notna())
        report_contract_total = float(raw_contract[total_mask].dropna().iloc[-1]) if raw_contract[total_mask].notna().any() else None
        report_pay_total = float(raw_pay[total_mask].dropna().iloc[-1]) if raw_pay[total_mask].notna().any() else None
        out = pd.DataFrame({
            "driver": df[dn].map(norm_name),
            "driver_disp": df[dn].astype(str).str.strip(),
            "contract": raw_contract,
            "driverpay": raw_pay,
        }).dropna(subset=["driver"])
        out = _clean_driver(out)
        out = out[~out["driver"].isin(SUMMARY_NAMES)]
        out = out.dropna(subset=["contract", "driverpay"], how="all")
        # Monitor rows are operational labels, not payable trips. Keep MO rows
        # because the state report's numbered run count includes them.
        out["monitor"] = out["driver_disp"].astype(str).str.contains(r"\(\s*MONITOR\s*\)", case=False, regex=True)
        out = out[~out["monitor"]].copy()
        if best is None or len(out) > len(best):
            best = out
            best_report_contract_total = report_contract_total
            best_report_pay_total = report_pay_total
    code = forced_code or state_from_filename(fname)
    # Sacramento and Monterey are reporting locations inside North California,
    # never standalone states. Normalize both uploaded and filename-derived codes.
    code = {"SAC": "N.CA", "MON": "N.CA", "SACRAMENTO": "N.CA",
            "MONTEREY": "N.CA"}.get(str(code).upper(), code)
    if best is None:
        best = pd.DataFrame(columns=["driver", "driver_disp", "contract", "driverpay"])
    best = best.copy()
    best["contract"] = best["contract"].fillna(0.0)
    best["driverpay"] = best["driverpay"].fillna(0.0)
    # Carry official report totals on every detail row so downstream summaries
    # use one authoritative total instead of accidentally summing a duplicated
    # or rounded detail line.
    best["report_contract_total"] = best_report_contract_total
    best["report_pay_total"] = best_report_pay_total
    best["state"] = code
    return code, best

# Sheet-name -> state rules. The master First workbook carries one summary
# sheet per state (e.g. "NM Summary by Tahir", "North CA Summary by Hadeel",
# "RS&AZ Summary by George", "IL Summary by Neama", "OR Summary by Mansour",
# "CrossBorder Summary by Nancy"). We read those to learn which driver belongs
# to which state - straight from the First report, no extra files needed.
SHEET_STATE_RULES = [
    ("crossborder", "AK"), ("alaska", "AK"),
    ("new mexico", "NM"), ("nm ", "NM"), ("nm_", "NM"), (" nm", "NM"),
    ("north ca", "N.CA"), ("northern ca", "N.CA"), ("n.ca", "N.CA"),
    ("sacramento", "N.CA"), ("monterey", "N.CA"),
    ("rs&az", "S.CA"), ("rs & az", "S.CA"), ("riverside", "S.CA"),
    ("arizona", "S.CA"), ("south ca", "S.CA"), ("s.ca", "S.CA"),
    ("oregon", "OR"), ("or ", "OR"), ("or_", "OR"),
    ("illinois", "IL"), ("il ", "IL"), ("il_", "IL"),
]


def sheet_state(name):
    n = " " + re.sub(r"\s+", " ", str(name)).strip().lower() + " "
    for kw, code in SHEET_STATE_RULES:
        if kw in n:
            return code
    return None


@st.cache_data(show_spinner=False)
def read_first_statemap(file_bytes, fname):
    """Build a driver -> state map from the per-state summary/detail sheets
    that live INSIDE the First workbook. Returns {driver_norm: state_code}."""
    dmap = {}
    try:
        xl = pd.ExcelFile(io.BytesIO(file_bytes))
    except Exception:
        return dmap
    for sh in xl.sheet_names:
        code = sheet_state(sh)
        if not code:
            continue
        try:
            df = xl.parse(sh)
        except Exception:
            continue
        df.columns = [str(c).strip() for c in df.columns]
        dn = find_col(df.columns, "DRIVER NAME", "DRIVER", "Name")
        if not dn:
            continue
        for v in df[dn].dropna().map(norm_name):
            if v and v not in SUMMARY_NAMES:
                dmap.setdefault(v, code)
    return dmap


# ----------------------------- analytics -----------------------------
def classify(first_df, state_df, embedded_map=None):
    # Priority: explicit city/route in First > First embedded state sheet >
    # supplied driver/location map > state-file driver map > Unassigned.
    dmap = dict(LOCATION_DRIVER_STATE)
    dmap.update(embedded_map or {})
    for _, r in state_df.iterrows():
        dmap.setdefault(r["driver"], r["state"])
    first_df = first_df.copy()
    first_df["state_from_driver"] = first_df["driver"].map(dmap)
    route = first_df.get("route_state", pd.Series(index=first_df.index, dtype=object))
    first_df["state"] = route.combine_first(first_df["state_from_driver"]).fillna("Unassigned")
    return first_df

def state_totals(first_df, state_df, code):
    f = first_df[first_df["state"] == code]
    s = state_df[state_df["state"] == code]
    runs = int((~f["monitor"]).sum()) if len(f) else 0
    first_paid = float(f["net"].sum())
    detail_contract = float(s["contract"].sum())
    detail_driverpay = float(s["driverpay"].sum())
    official_contract = pd.to_numeric(s.get("report_contract_total", pd.Series(dtype=float)), errors="coerce").dropna()
    official_pay = pd.to_numeric(s.get("report_pay_total", pd.Series(dtype=float)), errors="coerce").dropna()
    contract = float(official_contract.iloc[0]) if len(official_contract) else detail_contract
    driverpay = float(official_pay.iloc[0]) if len(official_pay) else detail_driverpay
    gap = contract - first_paid
    profit = contract - driverpay
    margin = (profit / contract * 100.0) if contract else 0.0
    return {
        "State": code, "First Trips": runs, "State Trips": int(len(s)),
        "First Paid": first_paid,
        "Contract Revenue": contract, "Revenue Gap": gap,
        "Driver Pay": driverpay, "Profit": profit, "Margin %": round(margin, 1),
        # Keep the independently summed trip details visible for audit. The
        # official report totals above remain authoritative for the KPIs.
        "Detail Revenue Sum": detail_contract,
        "Revenue Reconciliation Diff": round(detail_contract - contract, 2),
        "Detail Payment Sum": detail_driverpay,
        "Payment Reconciliation Diff": round(detail_driverpay - driverpay, 2),
    }

# Agreed-rate rules that come straight from the First report (no price file
# needed). Alaska cross-border: First pays $42.50 per trip but the agreed
# rate is $45.00, so every $42.50 trip is underpaid by $2.50 and First owes
# (number of $42.50 trips) x $2.50.
UNDERPAY_RULES = {
    "AK": {"paid": 42.50, "agreed": 45.00},
}


def underpay_analysis(first_df, code):
    """For states with an agreed-rate rule, count trips paid at the underpaid
    rate and compute what First still owes."""
    rule = UNDERPAY_RULES.get(code)
    if not rule:
        return None
    f = first_df[first_df["state"] == code]
    if not len(f):
        return None
    paid, agreed = rule["paid"], rule["agreed"]
    per = round(agreed - paid, 2)
    hit = f[f["net"].round(2) == round(paid, 2)]
    n = int(len(hit))
    mon = int(hit["monitor"].sum()) if "monitor" in hit.columns else 0
    runs = n - mon
    return {
        "paid": paid, "agreed": agreed, "per": per,
        "underpaid_trips": n,
        "underpaid_runs": runs, "underpaid_monitors": mon,
        "owed": round(n * per, 2), "owed_runs": round(runs * per, 2),
        "total_trips": int(len(f)),
    }


def owed_table(first_df, state_df, codes):
    """Unified 'what First still owes' per state, from BOTH mechanisms:
      - agreed flat-rate shortfall (e.g. Alaska $42.50 paid vs $45 agreed)
      - contract-vs-paid gap when a state price file is uploaded.
    Automatically covers any state that shows a per-trip price difference."""
    rows = []
    for c in codes:
        if c == "Unassigned":
            continue
        row = state_totals(first_df, state_df, c)
        has_contract = row["Contract Revenue"] > 0
        up = underpay_analysis(first_df, c)
        owed = 0.0
        basis = []
        if has_contract and row["Revenue Gap"] > 0:
            owed += row["Revenue Gap"]
            basis.append("contract vs First paid")
        if up and up["underpaid_trips"]:
            owed += up["owed"]
            basis.append(f"{up['underpaid_trips']} trips x {money(up['per'])} "
                         f"({money(up['paid'])} vs {money(up['agreed'])})")
        if owed > 0.004:
            rows.append({
                "State": c,
                "Trips": int(row["First Trips"]),
                "First Paid": round(row["First Paid"], 2),
                "Amount Owed by First": round(owed, 2),
                "Basis": "; ".join(basis),
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Amount Owed by First", ascending=False).reset_index(drop=True)
    return df


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


def history_path():
    for candidate in (Path.cwd() / ".bt_weekly_history.json",
                      Path(tempfile.gettempdir()) / "bt_weekly_history.json"):
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            if not candidate.exists():
                candidate.write_text("{}", encoding="utf-8")
            return candidate
        except OSError:
            continue
    return None


def save_weekly_snapshot(summary, first_df=None, state_df=None):
    """Save per-state First/contract/pay metrics and return prior snapshot."""
    path = history_path()
    if path is None or summary.empty:
        return None
    now = pd.Timestamp.today()
    key = f"{int(now.isocalendar().year)}-W{int(now.isocalendar().week):02d}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    previous_keys = sorted(k for k in data if k < key)
    previous = data.get(previous_keys[-1]) if previous_keys else None
    records = summary.to_dict("records")
    data[key] = {
        "saved_at": now.isoformat(),
        "states": records,
        "first_total_paid": round(float(first_df["net"].sum()), 2) if first_df is not None and "net" in first_df else None,
        "first_trip_rows": int(len(first_df)) if first_df is not None else None,
        "state_contract_total": round(float(state_df["contract"].sum()), 2) if state_df is not None and "contract" in state_df else None,
        "state_trip_rows": int(len(state_df)) if state_df is not None else None,
    }
    try:
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    except OSError:
        pass
    return previous


def show_weekly_change(summary, previous):
    """Render the current-vs-previous weekly performance dashboard."""
    st.markdown("## Weekly performance dashboard")
    if not previous:
        st.info('Upload the saved JSON from last week in the sidebar to activate the graphical comparison.')
        return
    old = pd.DataFrame(previous.get("states", []))
    if old.empty or "State" not in old:
        st.info('The uploaded history file does not contain a previous state snapshot yet.')
        return

    cur = summary.set_index("State").copy()
    old = old.set_index("State").copy()
    states = sorted(set(cur.index) | set(old.index))
    metrics = ["First Paid", "Contract Revenue", "Revenue Gap", "Driver Pay", "Profit", "Margin %"]
    rows = []
    for state in states:
        row = {"State": state}
        for col in metrics:
            a = pd.to_numeric(cur[col], errors="coerce").get(state, float("nan")) if col in cur else float("nan")
            b = pd.to_numeric(old[col], errors="coerce").get(state, float("nan")) if col in old else float("nan")
            row[f"Current {col}"] = a
            row[f"Previous {col}"] = b
            row[f"Change {col}"] = round(a - b, 2) if pd.notna(a) and pd.notna(b) else float("nan")
        rows.append(row)
    comparison = pd.DataFrame(rows)

    # Headline cards: current total versus the previous saved week.
    cards = [
        ("First Paid", "Current First Paid", "Previous First Paid", "money"),
        ("Contract Revenue", "Current Contract Revenue", "Previous Contract Revenue", "money"),
        ("Revenue Gap", "Current Revenue Gap", "Previous Revenue Gap", "money"),
        ("Profit", "Current Profit", "Previous Profit", "money"),
        ("Margin", "Current Margin %", "Previous Margin %", "pct"),
    ]
    cols = st.columns(5)
    for col, (label, current_key, previous_key, kind) in zip(cols, cards):
        current = pd.to_numeric(comparison[current_key], errors="coerce").sum()
        previous_total = pd.to_numeric(comparison[previous_key], errors="coerce").sum()
        delta = current - previous_total
        if kind == "pct":
            # Margin is a ratio, not additive across states: use weighted total when available.
            value = (pd.to_numeric(cur.get("Profit", pd.Series(dtype=float)), errors="coerce").sum() /
                     pd.to_numeric(cur.get("Contract Revenue", pd.Series(dtype=float)), errors="coerce").sum() * 100
                     if pd.to_numeric(cur.get("Contract Revenue", pd.Series(dtype=float)), errors="coerce").sum() else current)
            prev_value = (pd.to_numeric(old.get("Profit", pd.Series(dtype=float)), errors="coerce").sum() /
                          pd.to_numeric(old.get("Contract Revenue", pd.Series(dtype=float)), errors="coerce").sum() * 100
                          if pd.to_numeric(old.get("Contract Revenue", pd.Series(dtype=float)), errors="coerce").sum() else previous_total)
            kpi(col, label, f"{value:.1f}%", f"previous {prev_value:.1f}% · change {value-prev_value:+.1f} pts",
                "good" if value >= prev_value else "bad")
        else:
            kpi(col, label, money(current), f"previous {money(previous_total)} · change {money(delta)}",
                "good" if delta >= 0 else "bad")

    st.markdown("### State performance: current vs previous")
    chart_cols = ["Current First Paid", "Previous First Paid", "Current Contract Revenue", "Previous Contract Revenue"]
    chart = comparison.set_index("State")[chart_cols].fillna(0)
    st.bar_chart(chart, height=360)

    st.markdown("### Profit and revenue-gap movement by state")
    movement = comparison.set_index("State")[["Current Profit", "Previous Profit", "Current Revenue Gap", "Previous Revenue Gap"]].fillna(0)
    st.bar_chart(movement, height=340)

    st.markdown("### Biggest changes this week")
    ranking = comparison[["State", "Change First Paid", "Change Contract Revenue", "Change Revenue Gap", "Change Profit", "Change Margin %"]].copy()
    ranking["Total movement"] = ranking[["Change First Paid", "Change Contract Revenue", "Change Profit"]].abs().sum(axis=1)
    ranking = ranking.sort_values("Total movement", ascending=False)
    # Remove the final helper column from the displayed report as requested.
    ranking = ranking.drop(columns=["Total movement"])
    st.dataframe(ranking, use_container_width=True, hide_index=True)

    st.download_button(
        "Download weekly comparison (Excel)",
        data=to_excel({"Weekly Comparison": ranking}),
        file_name="BT_weekly_comparison.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# ----------------------------- UI -----------------------------
STATE_UPLOAD_ORDER = [
    ('AK', 'Alaska'),
    ('N.CA', 'North California (includes Sacramento & Monterey)'),
    ('S.CA', 'South California / Riverside & Arizona'),
    ('AZ', 'Arizona'), ('OR', 'Oregon'), ('IL', 'Illinois'),
    ('NM', 'New Mexico'), ('NE', 'Nebraska'),
]
def kpi(col, label, value, sub="", cls=""):
    col.markdown(
        f'<div class="kpi"><div class="lbl">{label}</div>'
        f'<div class="val {cls}">{value}</div>'
        f'<div class="sub">{sub}</div></div>',
        unsafe_allow_html=True,
    )

st.title("Hatem's B.T. Analyzer")
st.caption("Weekly financial control center · First vs contract revenue · state compliance")

with st.sidebar:
    st.markdown('''<div class="brand"><div class="brand-title">🚐 Hatem's B.T. Analyzer</div><div class="brand-sub">Beyond Transportation · weekly financial control</div></div>''', unsafe_allow_html=True)
    st.markdown('<div class="section-title">1 · First reports</div>', unsafe_allow_html=True)
    first_files = st.file_uploader(
        'First / SP ITEMIZED reports (NET PAY = what First paid)',
        type=['xlsx', 'xls'], accept_multiple_files=True, key='first')
    st.markdown('<div class="section-title">2 · Ever Driven / state reports</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-note">Revenue = contract price · PAY = driver payment · NET PAY = First payment</div>', unsafe_allow_html=True)
    all_state_files = st.file_uploader(
        'Upload all state reports together', type=['xlsx', 'xls'],
        accept_multiple_files=True, key='state_all')
    state_inputs = []
    with st.expander('Upload one report per state', expanded=True):
        for code, label in STATE_UPLOAD_ORDER:
            files = st.file_uploader(label, type=['xlsx', 'xls'],
                                     accept_multiple_files=True, key=f'state_{code}')
            for file_obj in files or []:
                state_inputs.append((file_obj, code))
    for file_obj in all_state_files or []:
        state_inputs.append((file_obj, None))

    st.markdown('<div class="section-title">3 · Weekly history</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-note">Upload last week’s history JSON before analysis. After analysis, download the updated file and keep it for next week.</div>', unsafe_allow_html=True)
    history_file = st.file_uploader('Upload saved weekly history', type=['json'], key='history_up')

if not first_files:
    st.info("Upload at least one First report to begin. Each state's trips and "
            "revenue (First Paid) are read straight from the First report. Add "
            "the state price reference files only if you also want contract "
            "revenue, the revenue gap and profit.")
    st.stop()

# Restore the previous saved weeks when the app is running on a stateless host.
if history_file is not None:
    try:
        hp = history_path()
        hp.write_bytes(history_file.getvalue())
        st.sidebar.success('Weekly history restored')
    except Exception as exc:
        st.sidebar.error(f'History file could not be loaded: {exc}')

first_all = pd.concat([read_first(f.getvalue(), f.name) for f in first_files], ignore_index=True)

# driver -> state map read from the per-state sheets inside the First workbook(s)
embedded_map = {}
for f in first_files:
    embedded_map.update(read_first_statemap(f.getvalue(), f.name))

state_frames, state_codes = [], []
seen_state_files = set()
for f, forced_code in state_inputs:
    if f.name in seen_state_files:
        continue
    seen_state_files.add(f.name)
    code, sdf = read_state(f.getvalue(), f.name, forced_code=forced_code)
    state_frames.append(sdf)
    if code not in state_codes:
        state_codes.append(code)
state_all = (pd.concat(state_frames, ignore_index=True)
             if state_frames else
             pd.DataFrame(columns=["driver", "driver_disp", "contract", "driverpay", "state"]))

first_all = classify(first_all, state_all, embedded_map)

# Filename fallback: a First file that clearly belongs to ONE state (e.g.
# Alaska_first.xlsx) classifies its still-unassigned trips to that state.
file_state = {f.name: first_file_state(f.name) for f in first_files}
if "source" in first_all.columns:
    mask = first_all["state"].eq("Unassigned")
    fb = first_all.loc[mask, "source"].map(lambda s: file_state.get(s) or "Unassigned")
    first_all.loc[mask, "state"] = fb

present_codes = state_codes + [c for c in first_all["state"].unique()
                               if c not in state_codes and c != "Unassigned"]
if (first_all["state"] == "Unassigned").any():
    present_codes = present_codes + ["Unassigned"]

summary = pd.DataFrame([state_totals(first_all, state_all, c)
                        for c in present_codes if c != "Unassigned"])
previous_snapshot = save_weekly_snapshot(summary, first_all, state_all)
history_for_download = history_path()
if history_for_download is not None:
    st.sidebar.download_button(
        'Download updated weekly history',
        data=history_for_download.read_bytes(),
        file_name='bt_weekly_history.json',
        mime='application/json',
        use_container_width=True,
    )

STATE_LABELS = {
    "AK": "Alaska", "N.CA": "North California", "S.CA": "South California",
    "AZ": "Arizona", "OR": "Oregon", "IL": "Illinois", "NM": "New Mexico",
    "NE": "Nebraska", "Unassigned": "Unassigned"
}
view_labels = {
    "📊  Consolidated Dashboard": "Consolidated Report",
    "🧾  First Report Only": "First Report Only",
    "💰  Amounts owed by First": "Amounts Owed by First",
    "🔎  Trips comparison": "Trips Comparison",
}
for code in present_codes:
    view_labels[f"📍  {STATE_LABELS.get(code, code)}"] = code
selected_view = st.sidebar.radio("Navigation", list(view_labels), key="view_nav")
view = view_labels[selected_view]

def first_only_report(first_df, state_df):
    """First-only reconciliation view. It never replaces state contract revenue."""
    work = first_df.copy()
    work["Trip Count"] = (~work["monitor"]).astype(int)
    summary = work.groupby("state", dropna=False).agg(
        **{"First Trips": ("Trip Count", "sum"),
           "First Paid": ("net", "sum"),
           "First Drivers": ("driver", "nunique")}
    ).reset_index().rename(columns={"state": "State"})
    summary["Average First Pay"] = summary["First Paid"] / summary["First Trips"].replace(0, pd.NA)
    summary["Average First Pay"] = summary["Average First Pay"].fillna(0).round(2)
    if not state_df.empty:
        state_summary = state_df.groupby("state").agg(
            **{"State Revenue": ("contract", "sum"), "State Report Trips": ("driver", "size")}
        ).reset_index().rename(columns={"state": "State"})
        if "report_contract_total" in state_df.columns:
            official = (state_df.dropna(subset=["report_contract_total"])
                        .groupby("state")["report_contract_total"].first()
                        .rename("State Revenue"))
            state_summary = state_summary.drop(columns=["State Revenue"]).join(official, on="State")
            state_summary["State Revenue"] = state_summary["State Revenue"].fillna(0)
        summary = summary.merge(state_summary, on="State", how="outer")
        summary["First Paid"] = summary["First Paid"].fillna(0)
        summary["First Trips"] = summary["First Trips"].fillna(0).astype(int)
        summary["State Revenue"] = summary["State Revenue"].fillna(0)
        summary["State Report Trips"] = summary["State Report Trips"].fillna(0).astype(int)
        summary["Revenue Coverage Difference"] = (summary["State Revenue"] - summary["First Paid"]).round(2)
        summary["Trip Coverage Difference"] = summary["State Report Trips"] - summary["First Trips"]
    # Keep the independent First fields first; no hidden replacement of First by state revenue.
    summary = summary.sort_values("First Paid", ascending=False).reset_index(drop=True)
    detail_cols = ["state", "driver_disp", "trip", "miles", "net", "monitor"]
    detail = work[[c for c in detail_cols if c in work.columns]].copy()
    detail = detail.rename(columns={"state": "State", "driver_disp": "Driver", "trip": "Trip", "miles": "Miles", "net": "First Net Pay", "monitor": "Monitor"})
    return summary, detail


def render_first_only(first_df, state_df):
    st.subheader("First Report Only")
    st.caption("This page is the independent First view. First Paid comes only from the First report's NET PAY column; state contract revenue is shown separately only for reconciliation.")
    first_summary, first_detail = first_only_report(first_df, state_df)
    total_trips = int(first_summary["First Trips"].sum()) if not first_summary.empty else 0
    total_paid = float(first_summary["First Paid"].sum()) if not first_summary.empty else 0.0
    a, b, c = st.columns(3)
    kpi(a, "First Trips", f"{total_trips:,}")
    kpi(b, "First Paid / NET PAY", money(total_paid), "read only from First")
    kpi(c, "States detected", f"{len(first_summary):,}")

    st.markdown("### First revenue by state")
    display_cols = ["State", "First Trips", "First Paid", "First Drivers", "Average First Pay"]
    if "State Revenue" in first_summary.columns:
        display_cols += ["State Revenue", "Revenue Coverage Difference", "Trip Coverage Difference"]
    display_cols = [c for c in display_cols if c in first_summary.columns]
    st.dataframe(fmt_money_cols(first_summary[display_cols], ["First Paid", "Average First Pay", "State Revenue", "Revenue Coverage Difference"]), use_container_width=True, hide_index=True)
    st.bar_chart(first_summary.set_index("State")[["First Paid"]], height=320)

    if "State Revenue" in first_summary.columns:
        st.info("Coverage difference = State Report Revenue − First Paid. A positive amount means the state report contains more contract revenue than the First rows currently classified for that state; it is a reconciliation difference, not an automatic claim until trips are matched.")
        st.markdown("### First vs state-report coverage")
        cov = first_summary.set_index("State")[["First Paid", "State Revenue"]].fillna(0)
        st.bar_chart(cov, height=320)

    st.markdown("### Download First report for reference")
    # Exclude the technical source column from the user-facing report.
    download_detail = first_detail.drop(columns=["Source"], errors="ignore")
    download_summary = first_summary.drop(columns=["Trip Coverage Difference"], errors="ignore")
    st.download_button("Download First-only Excel report", data=to_excel({"First Summary": download_summary, "First Detail": download_detail}), file_name="BT_First_only_report.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ----------------------------- rendering -----------------------------
def fmt_money_cols(df, cols):
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = out[c].map(money)
    return out

MONEY_COLS = ["First Paid", "Contract Revenue", "Revenue Gap", "Driver Pay", "Profit",
              "Detail Revenue Sum", "Revenue Reconciliation Diff",
              "Detail Payment Sum", "Payment Reconciliation Diff"]

if view == "First Report Only":
    render_first_only(first_all, state_all)

elif view == "Consolidated Report":
    st.subheader("Consolidated Report - all states")
    owed_all = owed_table(first_all, state_all, present_codes)
    if not owed_all.empty:
        total_owed = float(owed_all["Amount Owed by First"].sum())
        states_list = ", ".join(
            f"{s} ({money(a)})" for s, a in
            zip(owed_all["State"], owed_all["Amount Owed by First"]))
        st.error(f"First owes a total of {money(total_owed)} across "
                 f"{len(owed_all)} state(s) with a trip-price difference: {states_list}. "
                 f"See the 'Amounts Owed by First' view for the full breakdown.")
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
    if tot_contract > 0:
        kpi(c[2], "Contract Revenue", money(tot_contract), "what Beyond should earn")
        kpi(c[3], "Revenue Gap", money(tot_gap),
            "owed by First" if tot_gap >= 0 else "overpaid", "bad" if tot_gap > 0 else "good")
    else:
        kpi(c[2], "Contract Revenue", "-", "upload price files to see it")
        kpi(c[3], "Revenue Gap", "-", "needs price files")
    c = st.columns(4)
    kpi(c[0], "Driver Pay", money(tot_pay) if tot_pay else "-")
    kpi(c[1], "Profit", money(tot_profit) if tot_contract else "-",
        cls="good" if tot_profit >= 0 else "bad")
    kpi(c[2], "Margin", f"{tot_margin:.1f}%" if tot_contract else "-")
    kpi(c[3], "States", f"{len(summary)}")

    if not summary.empty:
        st.markdown("#### Per-state summary")
        show = summary.copy()
        if (summary["Contract Revenue"].sum() == 0):
            # First-only mode: contract/gap/profit need price files - hide them
            show = show[["State", "First Trips", "First Paid"]].rename(
                columns={"First Trips": "Trips", "First Paid": "Revenue (First Paid)"})
            st.dataframe(fmt_money_cols(show, ["Revenue (First Paid)"]),
                         use_container_width=True, hide_index=True)
            st.caption("Trips and revenue are read straight from the First report. "
                       "Upload the state price files to also get contract revenue, "
                       "the revenue gap and profit per state.")
            st.markdown("#### Revenue (First Paid) by state")
            st.bar_chart(summary.set_index("State")[["First Paid"]])
            st.markdown("#### Trips by state")
            st.bar_chart(summary.set_index("State")[["First Trips"]])
        else:
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
        show_weekly_change(summary, previous_snapshot)

    up_rows = []
    for c0 in present_codes:
        up = underpay_analysis(first_all, c0)
        if up and up["underpaid_trips"]:
            up_rows.append({
                "State": c0, "Agreed Rate": up["agreed"], "First Paid Rate": up["paid"],
                "Underpaid Trips": up["underpaid_trips"], "Per Trip": up["per"],
                "First Owes": up["owed"]})
    if up_rows:
        updf = pd.DataFrame(up_rows)
        st.markdown("#### Agreed-rate check - First underpaid")
        st.caption("Trips First paid below the agreed rate. 'First Owes' = "
                   "underpaid trips x the per-trip shortfall.")
        st.dataframe(fmt_money_cols(updf, ["Agreed Rate", "First Paid Rate", "Per Trip", "First Owes"]),
                     use_container_width=True, hide_index=True)
        st.metric("Total First owes (agreed-rate shortfall)", money(updf["First Owes"].sum()))

    un = first_all[first_all["state"] == "Unassigned"]
    if len(un):
        st.warning(f"{len(un):,} trips ({money(un['net'].sum())} First paid) belong to drivers "
                   f"not found in the First report's per-state sheets or any uploaded state "
                   f"file. Make sure the First workbook includes its per-state summary sheets "
                   f"(NM / North CA / RS&AZ / IL / OR / CrossBorder), or upload the matching "
                   f"state file to classify them.")

elif view == "Amounts Owed by First":
    st.subheader("Amounts Owed by First - consolidated financial summary")
    st.caption("Automatic scan of every state for a trip-price difference. A state "
               "is listed when First paid less than agreed - either the flat agreed "
               "rate (e.g. Alaska $45) or the contract revenue from an uploaded price "
               "file. 'Amount Owed by First' is the shortfall it still owes Beyond.")
    owed = owed_table(first_all, state_all, present_codes)
    if owed.empty:
        st.success("No trip-price difference detected. Every state's First payments "
                   "match the agreed / contract rate on the uploaded data. (Add state "
                   "price files to check contract-based differences too.)")
    else:
        total_owed = float(owed["Amount Owed by First"].sum())
        total_paid = float(owed["First Paid"].sum())
        c = st.columns(3)
        kpi(c[0], "Total Owed by First", money(total_owed), "across all states", "bad")
        kpi(c[1], "States Affected", f"{len(owed):,}")
        kpi(c[2], "Trips Affected", f"{int(owed['Trips'].sum()):,}")
        show = owed.copy()
        grand = {"State": "TOTAL", "Trips": int(owed["Trips"].sum()),
                 "First Paid": round(owed["First Paid"].sum(), 2),
                 "Amount Owed by First": round(total_owed, 2), "Basis": ""}
        show = pd.concat([show, pd.DataFrame([grand])], ignore_index=True)
        st.dataframe(fmt_money_cols(show, ["First Paid", "Amount Owed by First"]),
                     use_container_width=True, hide_index=True)
        st.markdown("#### Amount owed by First, by state")
        st.bar_chart(owed.set_index("State")[["Amount Owed by First"]])
        st.download_button(
            "Download amounts owed (Excel)",
            data=to_excel({"Amounts Owed": show}),
            file_name="BT_amounts_owed.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

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
    has_contract = row["Contract Revenue"] > 0
    c = st.columns(4)
    kpi(c[0], "Trips", f"{row['First Trips']:,}")
    kpi(c[1], "First Paid", money(row["First Paid"]), "revenue from First")
    if has_contract:
        kpi(c[2], "Contract Revenue", money(row["Contract Revenue"]))
        kpi(c[3], "Revenue Gap", money(row["Revenue Gap"]),
            "owed by First" if row["Revenue Gap"] >= 0 else "overpaid",
            "bad" if row["Revenue Gap"] > 0 else "good")
        c = st.columns(3)
        kpi(c[0], "Driver Pay", money(row["Driver Pay"]))
        kpi(c[1], "Profit", money(row["Profit"]), cls="good" if row["Profit"] >= 0 else "bad")
        kpi(c[2], "Margin", f"{row['Margin %']}%")
    else:
        kpi(c[2], "Contract Revenue", "-", "upload the price file")
        kpi(c[3], "Revenue Gap", "-", "needs the price file")

    up = underpay_analysis(first_all, code)
    if up and up["underpaid_trips"]:
        st.markdown("#### Agreed-rate check (First underpaid)")
        c = st.columns(4)
        kpi(c[0], "Agreed rate", money(up["agreed"]), "per trip")
        kpi(c[1], "First paid rate", money(up["paid"]), "per trip", "bad")
        kpi(c[2], "Underpaid trips", f"{up['underpaid_trips']:,}",
            f"{up['underpaid_runs']:,} runs + {up['underpaid_monitors']:,} monitor (M)")
        kpi(c[3], "First owes", money(up["owed"]),
            f"{up['underpaid_trips']:,} x {money(up['per'])}", "bad")
        st.caption(
            f"{up['underpaid_trips']:,} trips were paid {money(up['paid'])} each "
            f"({up['underpaid_runs']:,} driving runs + {up['underpaid_monitors']:,} monitor (M) lines), "
            f"but the agreed rate is {money(up['agreed'])}. First still owes "
            f"{up['underpaid_trips']:,} x {money(up['per'])} = {money(up['owed'])} on all lines, "
            f"or {money(up['owed_runs'])} if monitor lines are excluded "
            f"({up['underpaid_runs']:,} runs x {money(up['per'])}).")

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
    if has_contract:
        st.caption("Flags: LOSS = First paid below driver pay. NO FIRST MATCH = this driver "
                   "is in the price file but not matched in the First report (contract counted, "
                   "First paid 0 - inflates the gap, often a name spelling difference). "
                   "NO CONTRACT = in First but missing from the price file.")
        st.dataframe(fmt_money_cols(dt, MONEY_COLS), use_container_width=True, hide_index=True)
    else:
        simple = dt[["Driver", "Runs", "First Paid"]].rename(
            columns={"First Paid": "Revenue (First Paid)"})
        st.caption("Trips and revenue read straight from the First report. Upload the "
                   f"{code} price file to add contract revenue, the gap and profit.")
        st.dataframe(fmt_money_cols(simple, ["Revenue (First Paid)"]),
                     use_container_width=True, hide_index=True)

    noncompliant = dt[dt["Flag"] == "LOSS"]
    if has_contract and len(noncompliant):
        st.markdown(f"#### Non-compliant drivers - {len(noncompliant)} losing money "
                    f"(First paid below driver pay)")
        st.bar_chart(noncompliant.set_index("Driver")[["First Paid", "Driver Pay"]])
    elif has_contract:
        st.success("All drivers compliant - First paid covers driver pay on every driver. "
                   "(Trip chart hidden because there are no non-compliant trips.)")

    st.download_button(
        "Download this state (Excel)",
        data=to_excel({code: dt}),
        file_name=f"BT_{code.replace('.', '')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
