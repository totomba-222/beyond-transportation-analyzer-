"""Official Northern California pay policy (mile bands per city) and price list, used to review state reports.
Bands come from the header text of the city price PDFs. Richmond has no band text: its bands are inferred from its trips (same as Berkeley) - confirm.
Beyond the last band (and in Sacramento) pay is set by management per trip: such trips are checked against the approved pay seen in the price list.
The per-mile rate after the last band is unreadable in the PDF ('1?2 in each mile'), so it is NOT assumed: set LONG_RATE once confirmed."""
import re
import numpy as np
import pandas as pd
from ratebook import route_key
from config import STATE_NAMES

try:
    from nc_policy import ROUTES as NC
    NC_LOAD_ERROR = None
except Exception as _e:                      # never silent: the reports warn when the North California price list is missing
    NC = {}; NC_LOAD_ERROR = repr(_e)

# (from mile, to mile, driver pay)
BANDS = {"Benicia": [(1, 7, 38.0)],
         "Berkeley": [(1, 6, 38.0), (7, 11, 42.0)],
         "Richmond": [(1, 6, 38.0), (7, 11, 42.0)],
         "San Leandro": [(1, 7, 38.0), (8, 16, 43.0)]}
LONG_RATE = None            # dollars per mile after the last band (None = not confirmed -> long trips need approval)
SACRAMENTO = {              # no mile formula: pay approved per trip by management; values seen in the price list
    "golden west ms 01": {"gross": [85.0], "pay": [37.0, 40.0]}, "dan o root ii es 01": {"gross": [45.0], "pay": [37.0]},
    "point quest cmp 04": {"gross": [85.0], "pay": [55.0, 60.0]}, "point quest cmp 03": {"gross": [83.25], "pay": [60.0]},
    "arthur b ingham prg 01": {"gross": [60.0, 70.5], "pay": [55.0, 65.0]}}
STATE = "N.CA"; TOL = 0.005
# South California (Riverside / Arizona): bands read from the Nov 9-13 state report (563 trips, all matched with First). Beyond 16 miles the pay is set by
# management (about 70-76% of the trip revenue), so it is shown with its share of revenue and not judged against a formula.
STATE_BANDS = {"S.CA": [(1, 4, 38.0), (5, 8, 40.0), (9, 16, 43.0)]}
SCA_LABEL = "South California"
# New Mexico (rule sent by management): First pays 48$ up to 14 miles, then 48$ + 2.25$ per mile over 14; Beyond pays the driver 33$ (0-6 mi), 37$ (7-14 mi), then 37$ + 1.5$ per mile over 14.
# Oregon (rule sent by the Oregon manager, same table for all areas except Gresham, which starts at 30$ instead of 33$): 1-6 mi 33$, 7-10 mi 36$, 11-14 mi 38$, then 1.25$ per extra mile over 14.
# Very hard trips are negotiated with the drivers, so a pay that differs from the rule but equals that route's usual pay is shown as "route policy", not as a deviation.
FORMULA_STATES = {
    "NM": {"label": "New Mexico", "pay": [(0, 6, 33.0), (7, 14, 37.0)], "pay_tail": (14, 37.0, 1.5), "rev": [(0, 14, 48.0)], "rev_tail": (14, 48.0, 2.25)},
    "OR": {"label": "Oregon", "pay": [(0, 6, 33.0), (7, 10, 36.0), (11, 14, 38.0)], "pay_tail": (14, 38.0, 1.25), "rev": None, "rev_tail": None},
    # Kansas (rule from Neama, state manager): driver pay 0-7 mi 28$, 8-13 mi 30$, then 0.8$ per mile over 13 (the tail uses the exact miles).
    "KS": {"label": "Kansas", "pay": [(0, 7, 28.0), (8, 13, 30.0)], "pay_tail": (13, 30.0, 0.8), "rev": None, "rev_tail": None, "exact_tail": True, "tail_tol": 0.25},
    # Nebraska (Neama): fixed price. First pays 39.50 net, Beyond pays the driver 30$; exceptional trips 35$, and 33$ when a driver is urgently needed.
    # A half-price trip from EverDriven (18.75 net) is paid 15$ to the driver.
    "NE": {"label": "Nebraska", "pay": [(0, 9999, 30.0)], "pay_tail": None, "rev": [(0, 9999, 39.5)], "rev_tail": None, "flat": True, "alt_pay": [33.0, 35.0], "half_pay": 15.0, "half_rev": 18.75},
    # Alaska / Anchorage (price sheet from the state manager): Sedan 1-8 mi 35$, 9-16 mi 37$; Minivan 1-8 mi 40$, 9-16 mi 42$. The vehicle is not in the reports, so both
    # prices are accepted in each band. Some drivers have their own price and trips over 16 miles are outside the sheet: those are listed for review.
    "AK": {"label": "Alaska", "pay": [(0, 8, 35.0), (9, 16, 37.0)], "pay_tail": None, "rev": None, "rev_tail": None, "alt_by_band": {35.0: [40.0], 37.0: [42.0]}},
    # Illinois: priced per route (no mile bands). route name -> (revenue, driver pay)
    "IL": {"label": "Illinois", "pay": [], "pay_tail": None, "rev": None, "rev_tail": None,
           "routes": {"Connect Academy (Carol Stream) SS IB 02": (103.5, 85.0), "The Winston Knolls School SS IB 02": (107.0, 85.0)}}}
OR_GRESHAM_START = 30.0   # Gresham starts at 30$ instead of 33$ (0-6 miles); Gresham routes are not tagged in the data, so 30$ on a 0-6 mile Oregon trip is accepted as Gresham
TAIL_TOL = 1.5      # pay on a per-mile tail may differ by up to this (miles are rounded and the pay is rounded to the dollar)
REV_TOL = 2.25      # revenue on a per-mile tail: within one mile


def _formula(spec, key, tail_key, miles):
    if spec.get("flat") and spec.get(key): return spec[key][0][2], False          # fixed price: miles do not matter
    if pd.isna(miles) or not (spec.get(key) or spec.get(tail_key)): return np.nan, False
    m = round(float(miles))
    for lo, hi, v in spec.get(key) or []:
        if lo <= m <= hi: return v, False
    t = spec.get(tail_key)
    if t and m > t[0]: return t[1] + t[2] * ((float(miles) if spec.get("exact_tail") else m) - t[0]), True
    return np.nan, False


def ks_net_price(miles):
    """EverDriven Kansas price read from the Nov 2-8 receipt (51 trips, exact): gross 39$ up to 12 miles, then 2.20$ per mile over 12;
    net = gross - 3.5% (RAD) - 2$ (WUD). The 12-mile break is inferred (no trips between 8 and 15 miles in that receipt) - confirm."""
    g = 39.0 if miles <= 12 else 39.0 + 2.2 * (miles - 12)
    return round(g * 0.965 - 2.0, 2)


def _band_pay(city, miles):
    b = BANDS.get(city)
    if not b or pd.isna(miles): return np.nan, ""
    m = round(float(miles))
    for lo, hi, p in b:
        if lo <= m <= hi: return p, "band"
    return np.nan, "above last band"


def _variants(k):
    """Same route written differently: stray '_a' left by '(W)_A', and the mirror trip (IB <-> OB) of the same school and number."""
    k2 = re.sub(r"(?<=\d)\s+[a-z]$", "", re.sub(r"\s+_[a-z]\b", "", k))     # 'ob 01 a' (from '(W)_A') -> 'ob 01'
    out = [k, k2]
    for x in (k, k2):
        if " ib " in x: out.append(x.replace(" ib ", " ob ", 1))
        elif " ob " in x: out.append(x.replace(" ob ", " ib ", 1))
    return out


def _stem_cities():
    from classification import _school_stem
    m = {}
    for rk, v in NC.items(): m.setdefault(_school_stem(rk), set()).add(v["city"])
    return m, _school_stem


def route_info(trip_name):
    """(city, info). 1 exact route in the city price lists; 2 same route written differently (suffix / IB-OB mirror);
    3 same SCHOOL listed in only ONE city (city by school; no approved pay list, so only the city bands apply); Sacramento by route."""
    k = route_key(trip_name)
    for v in _variants(k):
        if v in NC: return NC[v]["city"], NC[v]
    nib = re.sub(r"\b(?:ib|ob)\b ?", "", k).replace("  ", " ").strip()
    for sk, v in SACRAMENTO.items():
        if k.startswith(sk) or nib.startswith(sk) or re.sub(r"\b(?:ib|ob)\b ?", "", sk).strip() == nib.rstrip(" 0123456789").strip() + " " + nib.split()[-1]: return "Sacramento", v
    if NC:
        m, stem = _stem_cities(); cs = m.get(stem(k), set())
        if len(cs) == 1: c = next(iter(cs)); return c, {"city": c, "gross": [], "pay": [], "by_school": True}
    return None, None


def _sca_row(t, mi, pay):
    bands = STATE_BANDS["S.CA"]
    if pay is None or pd.isna(pay): return "No driver pay", np.nan
    if abs(pay) < TOL: return "ZERO pay (check the driver)", bands_pay(mi)
    exp = bands_pay(mi)
    if pd.isna(exp):
        return "Long trip (>16 mi): management-set", np.nan
    if abs(pay - exp) < TOL: return "Matches band", exp
    return ("ABOVE band" if pay > exp else "BELOW band"), exp


def bands_pay(mi):
    if pd.isna(mi): return np.nan
    m = round(float(mi))
    for lo, hi, p in STATE_BANDS["S.CA"]:
        if lo <= m <= hi: return p
    return np.nan


def _cancel_fee(code, amount):
    from simple_reports import is_cancel_fee
    return is_cancel_fee(code, amount)


def band_check(rec, book=None):
    """Driver pay in the state report vs the mile-band policy. N.CA: bands of the route's city (price PDFs). S.CA: the state bands.
    Returns (summary, detail)."""
    # a trip name (route) is needed for the per-route price lists (N.CA, IL); the mile-based states only need the miles of the state report
    base = rec[(rec.state_source != "") & rec.driver_payment.notna() & (rec.audit_status != "MONITOR PAYMENT") & (rec.trip_name.fillna("").ne("") | rec.state.isin(["S.CA", "AK", "KS", "NE", "NM", "OR"]))]
    r = base[base.state == STATE]
    rows = []
    for t in r.itertuples():
        city, info = route_info(t.trip_name); mi = t.main_miles if pd.notna(t.main_miles) else t.state_miles; pay = t.driver_payment
        if city is None: st, exp = "City not identified (route not in the price lists)", np.nan
        else:
            approved = [float(x) for x in info.get("pay", [])]
            if city == "Sacramento":
                st, exp = ("Sacramento: management-approved pay", pay) if any(abs(pay - a) < TOL for a in approved) else ("Sacramento: pay NOT in approved list", np.nan)
            else:
                exp, kind = _band_pay(city, mi)
                if kind == "band":
                    if abs(pay - exp) < TOL: st = "Matches band"
                    elif any(abs(pay - a) < TOL for a in approved): st = "Approved exception (price list)"
                    elif city == "San Leandro" and pay > exp: st = "Approved exception (San Leandro: per N.CA manager, confirmed Nov 24; approved by Mr. Abdoun)"
                    else: st = "ABOVE band" if pay > exp else "BELOW band"
                else:
                    if LONG_RATE is not None and pd.notna(mi):
                        last = BANDS[city][-1]; exp = last[2] + (round(float(mi)) - last[1]) * LONG_RATE
                    st = "Approved long trip (price list)" if any(abs(pay - a) < TOL for a in approved) else "Long trip: needs management approval"
        rows.append({"State": STATE_NAMES.get(t.state, t.state), "City": city or "", "Date": t.date, "Driver": t.driver, "Trip Name": t.trip_name, "Miles": mi,
                     "Driver pay": pay, "Trip revenue": t.state_revenue, "Policy pay": exp, "Difference": pay - exp if pd.notna(exp) else np.nan, "Pay % of revenue": np.nan, "Status": st})
    for t in base[base.state == "S.CA"].itertuples():
        mi = t.main_miles if pd.notna(t.main_miles) else t.state_miles; st, exp = _sca_row(t, mi, t.driver_payment)
        share = t.driver_payment / t.state_revenue * 100 if pd.notna(t.state_revenue) and t.state_revenue else np.nan
        rows.append({"State": STATE_NAMES.get("S.CA", "S.CA"), "City": SCA_LABEL, "Date": t.date, "Driver": t.driver, "Trip Name": t.trip_name, "Miles": mi,
                     "Driver pay": t.driver_payment, "Trip revenue": t.state_revenue, "Policy pay": exp, "Difference": t.driver_payment - exp if pd.notna(exp) else np.nan, "Pay % of revenue": share, "Status": st})
    import ratebook as RB
    for code, spec in FORMULA_STATES.items():
        for t in base[base.state == code].itertuples():
            mi = t.main_miles if pd.notna(t.main_miles) else t.state_miles; pay = t.driver_payment
            exp, tail = _formula(spec, "pay", "pay_tail", mi)
            share = pay / t.state_revenue * 100 if pd.notna(t.state_revenue) and t.state_revenue else np.nan
            if spec.get("routes") is not None:        # Illinois: price per route
                rk = route_key(t.trip_name); hit = next((v for k, v in spec["routes"].items() if rk.startswith(route_key(k)) or route_key(k).startswith(rk)), None) if rk else None
                if hit is not None: exp = hit[1]
                else:
                    rp = RB.expected(book, code, t.trip_name, mi, None)["pay"] if book is not None else np.nan; exp = rp
                    if pd.isna(exp): rows.append({"State": spec["label"], "City": spec["label"], "Date": t.date, "Driver": t.driver, "Trip Name": t.trip_name, "Miles": mi, "Driver pay": pay,
                                                  "Trip revenue": t.state_revenue, "Policy pay": np.nan, "Difference": np.nan, "Pay % of revenue": share, "Status": "No policy for this route"}); continue
                st = "Matches route policy" if abs(pay - exp) < TOL else ("ABOVE route policy" if pay > exp else "BELOW route policy")
                rows.append({"State": spec["label"], "City": spec["label"], "Date": t.date, "Driver": t.driver, "Trip Name": t.trip_name, "Miles": mi, "Driver pay": pay,
                             "Trip revenue": t.state_revenue, "Policy pay": exp, "Difference": pay - exp, "Pay % of revenue": share, "Status": st}); continue
            alts = list(spec.get("alt_pay", [])) + list((spec.get("alt_by_band") or {}).get(exp, []))
            half = spec.get("half_pay") is not None and abs(pay - spec["half_pay"]) < TOL and (
                (pd.notna(getattr(t, "main_revenue", np.nan)) and abs(t.main_revenue - spec["half_rev"]) < 0.05)
                or _cancel_fee(code, getattr(t, "main_revenue", np.nan)) or _cancel_fee(code, getattr(t, "state_revenue", np.nan)))
            if pd.isna(exp): st = "No policy for these miles"
            elif abs(pay - exp) < TOL: st = "Matches band"
            elif half: st, exp = "Matches policy (half-price trip)", spec["half_pay"]
            elif any(abs(pay - a) < TOL for a in alts): st = "Allowed exception (listed in the policy)"
            elif code == "OR" and exp == 33.0 and abs(pay - OR_GRESHAM_START) < TOL: st, exp = "Matches band (Gresham start 30$)", OR_GRESHAM_START
            elif tail and abs(pay - exp) <= spec.get("tail_tol", TAIL_TOL): st = "Matches band (within rounding)"
            else:
                rp = RB.expected(book, code, t.trip_name, mi, None)["pay"] if book is not None else np.nan
                if pd.notna(rp) and abs(pay - rp) < TOL: st = "Matches route policy (differs from the band)"
                else: st = "ABOVE band" if pay > exp else "BELOW band"
            rows.append({"State": spec["label"], "City": spec["label"], "Date": t.date, "Driver": t.driver, "Trip Name": t.trip_name, "Miles": mi, "Driver pay": pay,
                         "Trip revenue": t.state_revenue, "Policy pay": exp, "Difference": pay - exp if pd.notna(exp) else np.nan, "Pay % of revenue": share, "Status": st})
    d = pd.DataFrame(rows)
    if d.empty: return pd.DataFrame(columns=["City", "Status", "Trips", "Driver pay", "Difference"]), d
    s = d.groupby(["City", "Status"]).agg(Trips=("Driver pay", "size"), **{"Driver pay": ("Driver pay", "sum"), "Difference": ("Difference", "sum")}).reset_index()
    return s, d.sort_values(["City", "Status", "Trip Name"]).reset_index(drop=True)


def price_list_check(main):
    """Price First paid per trip (N.CA) vs the price list (gross) of the same route. Returns (summary, detail of trips not at list price)."""
    m = main[(main.state == STATE) & main.main_amount.notna() & (main.main_amount.abs() > TOL) & main.trip_name.fillna("").ne("")]
    rows = []
    for t in m.itertuples():
        city, info = route_info(t.trip_name)
        if city is None: continue
        g = [float(x) for x in info.get("gross", [])]
        if not g: continue
        st = "At list price" if any(abs(t.main_amount - x) < TOL for x in g) else ("BELOW list price" if t.main_amount < min(g) else "ABOVE list price")
        rows.append({"City": city, "Date": t.date, "Driver": t.driver_disp, "Trip Name": t.trip_name, "Paid by provider": t.main_amount, "List price": "/".join(f"{x:g}" for x in g), "Status": st,
                     "Shortfall": (min(g) - t.main_amount) if st.startswith("BELOW") else 0.0})
    spec = FORMULA_STATES["NM"]
    for t in main[(main.state == "NM") & main.main_amount.notna() & (main.main_amount.abs() > TOL)].itertuples():
        exp, tail = _formula(spec, "rev", "rev_tail", t.miles)
        if pd.isna(exp): continue
        diff = t.main_amount - exp; ok = abs(diff) < TOL or (tail and abs(diff) <= REV_TOL)
        st = "At list price" if ok else ("BELOW list price" if diff < 0 else "ABOVE list price")
        rows.append({"City": spec["label"], "Date": t.date, "Driver": t.driver_disp, "Trip Name": t.trip_name, "Paid by provider": t.main_amount, "List price": f"{exp:g}", "Status": st,
                     "Shortfall": -diff if st.startswith("BELOW") else 0.0})
    ne = FORMULA_STATES["NE"]
    for t in main[(main.state == "NE") & main.main_amount.notna() & (main.main_amount.abs() > TOL)].itertuples():
        if _cancel_fee("NE", t.main_amount): continue          # cancelled trip: the provider pays its fee, not the list price
        diff = t.main_amount - ne["rev"][0][2]; st = "At list price" if abs(diff) < TOL else ("BELOW list price" if diff < 0 else "ABOVE list price")
        rows.append({"City": ne["label"], "Date": t.date, "Driver": t.driver_disp, "Trip Name": t.trip_name, "Paid by provider": t.main_amount, "List price": f"{ne['rev'][0][2]:g}", "Status": st,
                     "Shortfall": -diff if st.startswith("BELOW") else 0.0})
    for t in main[(main.state == "KS") & main.main_amount.notna() & (main.main_amount.abs() > TOL) & main.miles.notna()].itertuples():
        exp = ks_net_price(t.miles); diff = t.main_amount - exp
        st = "At list price" if abs(diff) <= 0.03 else ("BELOW list price" if diff < 0 else "ABOVE list price")
        rows.append({"City": "Kansas", "Date": t.date, "Driver": t.driver_disp, "Trip Name": t.trip_name, "Paid by provider": t.main_amount, "List price": f"{exp:.2f}", "Status": st,
                     "Shortfall": -diff if st.startswith("BELOW") else 0.0})
    d = pd.DataFrame(rows)
    if d.empty: return pd.DataFrame(columns=["City", "Trips", "At list price", "Below list", "Above list", "Shortfall"]), d
    s = d.groupby("City").agg(Trips=("Status", "size"), **{"At list price": ("Status", lambda x: (x == "At list price").sum()), "Below list": ("Status", lambda x: x.str.startswith("BELOW").sum()),
                                                            "Above list": ("Status", lambda x: x.str.startswith("ABOVE").sum()), "Shortfall": ("Shortfall", "sum")}).reset_index()
    return s, d[d.Status != "At list price"].reset_index(drop=True)


def bands_table():
    rows = [{"City": c, "From mile": lo, "To mile": hi, "Driver pay": p} for c, bs in BANDS.items() for lo, hi, p in bs]
    for spec in FORMULA_STATES.values():
        rows += [{"City": spec["label"], "From mile": lo, "To mile": hi, "Driver pay": v} for lo, hi, v in spec["pay"]]
        if spec.get("pay_tail"): rows.append({"City": spec["label"], "From mile": spec["pay_tail"][0] + 1, "To mile": 999, "Driver pay": f"{spec['pay_tail'][1]:g} + {spec['pay_tail'][2]:g} per mile over {spec['pay_tail'][0]}"})
        for base_pay, alt in (spec.get("alt_by_band") or {}).items(): rows.append({"City": spec["label"] + " (minivan)", "From mile": "", "To mile": "", "Driver pay": f"{base_pay:g} -> {alt[0]:g}"})
        for k, (rv, pv) in (spec.get("routes") or {}).items(): rows.append({"City": spec["label"], "From mile": k, "To mile": "route", "Driver pay": pv})
    rows += [{"City": SCA_LABEL, "From mile": lo, "To mile": hi, "Driver pay": p} for lo, hi, p in STATE_BANDS["S.CA"]]
    return pd.DataFrame(rows)
