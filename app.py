import re
import io
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Beyond Transportation — Reconciliation",
                   page_icon="🚐", layout="wide")


# ---------------- helpers ----------------
def norm(s):
    return re.sub(r"\s+", " ", str(s)).strip()


def mkey(name):
    k = re.sub(r"\s+", " ", str(name)).strip().lower()
    k = re.sub(r"[.,]+$", "", k).strip()
    return k


def find_col(cols, cands, avoid=()):
    cu = {c: c.upper() for c in cols}
    for cand in cands:                       # exact match first
        for c in cols:
            if cu[c] == cand and not any(a in cu[c] for a in avoid):
                return c
    for cand in cands:                       # partial match
        for c in cols:
            if cand in cu[c] and not any(a in cu[c] for a in avoid):
                return c
    return None


STATE_RULES = [
    ("ABQ", "New Mexico (ABQ)"), ("NEW MEXICO", "New Mexico (ABQ)"),
    ("NORTH CA", "North California"), ("NORTHCA", "North California"),
    ("OREGON", "Oregon"), ("RS", "Riverside & Arizona"),
    ("ARIZONA", "Riverside & Arizona"), ("ALASKA", "Alaska"),
    ("AK", "Alaska"), ("IL", "Illinois"), ("NM", "New Mexico (ABQ)"),
    ("AZ", "Riverside & Arizona"),
]


def guess_state(fname):
    up = fname.upper().replace("_", " ")
    for kw, label in STATE_RULES:
        if kw in up:
            return label
    return fname.rsplit(".", 1)[0]


def is_first(df):
    cu = " ".join(c.upper() for c in df.columns)
    return ("SP COMPANY" in cu) or ("BATCH" in cu)


def load_weekly(df):
    cols = list(df.columns)
    dcol = find_col(cols, ["DRIVER NAME", "DRIVER"])
    rcol = find_col(cols, ["REVENUE"])
    pcol = find_col(cols, ["PAY", "PAYMENT"], avoid=("GROSS", "DEDUCT", "NET"))
    out = pd.DataFrame()
    out["driver"] = df[dcol].map(norm)
    out["revenue"] = pd.to_numeric(df[rcol], errors="coerce").fillna(0.0)
    out["pay"] = (pd.to_numeric(df[pcol], errors="coerce").fillna(0.0)
                  if pcol else 0.0)
    out = out[out["driver"].str.len() > 0]
    out = out[out["driver"].str.lower() != "nan"]
    out["key"] = out["driver"].map(mkey)
    return out


def load_first(df):
    cols = list(df.columns)
    dcol = find_col(cols, ["DRIVER NAME", "DRIVER"])
    rcol = find_col(cols, ["REVENUE", "NET PAY", "NET"], avoid=("GROSS",))
    out = pd.DataFrame()
    out["driver"] = df[dcol].map(norm)
    out["revenue"] = pd.to_numeric(df[rcol], errors="coerce").fillna(0.0)
    out = out[out["driver"].str.len() > 0]
    out = out[out["driver"].str.lower() != "nan"]
    out["key"] = out["driver"].map(mkey)
    return out


def reconcile(weekly, firstpool):
    wk = weekly.groupby("key").agg(
        driver=("driver", "first"),
        w_trips=("revenue", "size"),
        w_rev=("revenue", "sum"),
        w_pay=("pay", "sum"),
    )
    if len(firstpool):
        fp = firstpool.groupby("key").agg(
            f_trips=("revenue", "size"),
            f_rev=("revenue", "sum"),
        )
    else:
        fp = pd.DataFrame(columns=["f_trips", "f_rev"])
    m = wk.join(fp, how="left")
    m["f_trips"] = m["f_trips"].fillna(0).astype(int)
    m["f_rev"] = m["f_rev"].fillna(0.0)
    m["margin"] = m["w_rev"] - m["w_pay"]
    m["trip_gap"] = m["w_trips"] - m["f_trips"]
    m["claim"] = (m["w_rev"] - m["f_rev"]).round(2)

    def status(r):
        if r["f_trips"] == 0:
            return "⛔ مش موجود في فرست"
        if r["trip_gap"] != 0 or abs(r["claim"]) >= 0.01:
            return "⚠️ فرق"
        return "✅ مطابق"
    m["status"] = m.apply(status, axis=1)
    m = m.reset_index(drop=True)
    return m.sort_values(["status", "driver"]).reset_index(drop=True)


def money(x):
    return f"${x:,.2f}"


st.title("🚐 Beyond Transportation — مطابقة التقارير")
st.markdown(
    "ارفع **تقارير فرست المفصّلة** (First detailed) وكمان "
    "**تقارير الولايات الأسبوعية** (اللي فيها Revenue و Pay). "
    "التطبيق هيطابق كل سواق في تقرير الولاية مع تقرير فرست، "
    "ويوضّح الرحلات الناقصة والفروق في الفلوس والـ margin."
)

c1, c2 = st.columns(2)
with c1:
    first_files = st.file_uploader(
        "① تقارير فرست المفصّلة (First)", type=["xlsx", "xls"],
        accept_multiple_files=True, key="firstup")
with c2:
    weekly_files = st.file_uploader(
        "② تقارير الولايات الأسبوعية", type=["xlsx", "xls"],
        accept_multiple_files=True, key="weekup")

if not weekly_files:
    st.info("👆 ارفع تقارير الولايات (وتقارير فرست) عشان نبدأ المطابقة.")
    st.stop()

# build First pool
pool = []
first_info = []
for f in (first_files or []):
    try:
        df = pd.read_excel(f)
        df.columns = [norm(c) for c in df.columns]
        fp = load_first(df)
        pool.append(fp)
        first_info.append((f.name, len(fp), round(fp["revenue"].sum(), 2)))
    except Exception as e:
        st.error(f"مش قادر أقرا {f.name}: {e}")
firstpool = (pd.concat(pool, ignore_index=True) if pool
             else pd.DataFrame(columns=["driver", "revenue", "key"]))

if first_info:
    with st.expander("📁 ملفات فرست اللي اترفعت"):
        st.table(pd.DataFrame(
            first_info, columns=["الملف", "عدد الرحلات", "إجمالي Revenue"]))
else:
    st.warning("⚠️ مافيش تقارير فرست اترفعت — هيظهر كل السواقين كـ «ناقص».")

all_summaries = []
all_tables = {}

for f in weekly_files:
    try:
        df = pd.read_excel(f)
        df.columns = [norm(c) for c in df.columns]
        if is_first(df):
            st.warning(f"⚠️ «{f.name}» شكله تقرير فرست مش تقرير ولاية — تخطيته.")
            continue
        wk = load_weekly(df)
    except Exception as e:
        st.error(f"مش قادر أقرا {f.name}: {e}")
        continue

    state = guess_state(f.name)
    m = reconcile(wk, firstpool)

    st.header(f"📍 {state}")
    st.caption(f"الملف: {f.name}")
    tot_wtrips = int(m["w_trips"].sum())
    tot_ftrips = int(m["f_trips"].sum())
    tot_rev = m["w_rev"].sum()
    tot_pay = m["w_pay"].sum()
    tot_margin = m["margin"].sum()
    tot_claim = m["claim"].sum()
    cs = st.columns(6)
    cs[0].metric("السواقين", len(m))
    cs[1].metric("رحلات (ولاية/فرست)", f"{tot_wtrips}/{tot_ftrips}")
    cs[2].metric("Revenue", money(tot_rev))
    cs[3].metric("Driver Pay", money(tot_pay))
    cs[4].metric("Margin", money(tot_margin))
    cs[5].metric("Claim من فرست", money(tot_claim))

    miss = m[m["status"].str.contains("مش موجود")]
    diff = m[m["status"].str.contains("فرق")]
    if len(miss):
        st.error(
            f"⛔ {len(miss)} سواق في تقرير الولاية مش موجودين في فرست "
            f"(رحلات ناقصة: {int(miss['w_trips'].sum())}، "
            f"فلوس: {money(miss['w_rev'].sum())}).")
    if len(diff):
        st.warning(f"⚠️ {len(diff)} سواق فيهم فرق في عدد الرحلات أو الفلوس.")
    if not len(miss) and not len(diff):
        st.success("✅ كل السواقين مطابقين تمام مع تقرير فرست.")

    show = m.rename(columns={
        "driver": "السواق", "w_trips": "رحلات (ولاية)",
        "f_trips": "رحلات (فرست)", "trip_gap": "فرق رحلات",
        "w_rev": "Revenue", "f_rev": "Revenue فرست",
        "claim": "Claim", "w_pay": "Driver Pay",
        "margin": "Margin", "status": "الحالة"})
    cols_order = ["الحالة", "السواق", "رحلات (ولاية)", "رحلات (فرست)",
                  "فرق رحلات", "Revenue", "Revenue فرست", "Claim",
                  "Driver Pay", "Margin"]
    show = show[cols_order]
    st.dataframe(show, use_container_width=True, hide_index=True)
    all_tables[state] = show
    all_summaries.append(dict(
        الولاية=state, سواقين=len(m),
        رحلات_ولاية=tot_wtrips, رحلات_فرست=tot_ftrips,
        Revenue=round(tot_rev, 2), Driver_Pay=round(tot_pay, 2),
        Margin=round(tot_margin, 2), Claim=round(tot_claim, 2)))
    st.divider()

if all_summaries:
    st.header("📊 ملخّص كل الولايات")
    summ = pd.DataFrame(all_summaries)
    st.dataframe(summ, use_container_width=True, hide_index=True)
    g = st.columns(4)
    g[0].metric("إجمالي Revenue", money(summ["Revenue"].sum()))
    g[1].metric("إجمالي Driver Pay", money(summ["Driver_Pay"].sum()))
    g[2].metric("إجمالي Margin", money(summ["Margin"].sum()))
    g[3].metric("إجمالي Claim", money(summ["Claim"].sum()))

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        summ.to_excel(xw, sheet_name="Summary", index=False)
        for state, tb in all_tables.items():
            safe = re.sub(r"[\[\]:*?/\\]", "-", state)[:31]
            tb.to_excel(xw, sheet_name=safe, index=False)
    st.download_button(
        "⬇️ نزّل النتيجة Excel", buf.getvalue(),
        file_name="reconciliation.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
