"""UI-independent processing used by app.py (and tested without Streamlit)."""
from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd
import classification as C, reconciliation as R, readers
from config import BASE_DRIVER_STATE, DEFAULT_SETTINGS
from normalization import file_hash, norm_name


@dataclass
class Result:
    mains: list = field(default_factory=list)
    sts: list = field(default_factory=list)
    main: pd.DataFrame = None
    st: pd.DataFrame = None
    rec: pd.DataFrame = None
    excluded: pd.DataFrame = None
    control: pd.DataFrame = None
    warnings: list = field(default_factory=list)
    unresolved_state_files: list = field(default_factory=list)   # (filename, suggestion)
    needs_mapping: list = field(default_factory=list)            # (filename, [fields])
    duplicate_uploads: list = field(default_factory=list)


def detect_state_by_content(records: pd.DataFrame, extra_map=None):
    """Suggest a state from the drivers' base-map states (>=80% agreement). Suggestion only."""
    base = C.base_map_normalised(extra_map)
    votes = [base[d] for d in records["driver"].unique() if d in base]
    if not votes:
        return None
    top = max(set(votes), key=votes.count)
    return top if votes.count(top) / len(votes) >= 0.8 else None


def process_uploads(main_files, state_files, settings=None, state_overrides=None, editable_map=None,
                    column_overrides=None) -> Result:
    """main_files/state_files: list of (filename, bytes). state_overrides: {filename: state code}."""
    S = {**DEFAULT_SETTINGS, **(settings or {})}
    res, seen = Result(), {}
    def take(lst, role):
        out = []
        for name, data in lst:
            h = file_hash(data)
            if h in seen:
                res.duplicate_uploads.append((name, seen[h])); continue
            seen[h] = name
            hint = None
            if role == "state":
                hint = (state_overrides or {}).get(name) or C.state_from_filename(name)
            elif "alaska" in name.lower():
                hint = "AK"
            p = readers.read_report(data, name, role, overrides=(column_overrides or {}).get(name), state_hint=hint)
            res.warnings += [f"{name}: {w}" for w in p.warnings]
            if p.needs_mapping:
                res.needs_mapping.append((name, p.needs_mapping)); continue
            if role == "state" and hint is None:
                res.unresolved_state_files.append((name, detect_state_by_content(p.records, editable_map)))
                res.warnings.append(f"{name}: state could not be detected from the file name - choose it manually (suggestion: {res.unresolved_state_files[-1][1]}). File NOT included until resolved.")
                continue
            out.append(p)
        return out
    res.mains, res.sts = take(main_files, "main"), take(state_files, "state")
    empty = pd.DataFrame(columns=readers.CANON_COLS)
    res.main = pd.concat([p.records for p in res.mains], ignore_index=True) if res.mains else empty
    res.st = pd.concat([p.records for p in res.sts], ignore_index=True) if res.sts else empty
    if len(res.main):
        res.main = C.classify(res.main, res.st, editable_map)
        res.rec = R.reconcile_all(res.main, res.st, S)
        res.rec["region"] = [C.region_label(s, t) for s, t in zip(res.rec.state, res.rec.trip_name)]
    else:
        res.rec = pd.DataFrame()
    ps = res.mains + res.sts
    ex = [p.excluded for p in ps if len(p.excluded)]
    res.excluded = pd.concat(ex, ignore_index=True) if ex else pd.DataFrame()
    ct = [readers.validate_control_totals(p) for p in ps]
    res.control = pd.concat([c for c in ct if len(c)], ignore_index=True) if any(len(c) for c in ct) else pd.DataFrame()
    return res


def apply_filters(rec, date_range=None, states=None, regions=None, drivers=None, statuses=None, providers=None):
    r = rec
    if date_range and len(date_range) == 2 and date_range[0] and date_range[1]:
        d0, d1 = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1]) + pd.Timedelta(hours=23, minutes=59)
        r = r[r.date.isna() | ((r.date >= d0) & (r.date <= d1))]   # undated rows stay visible (never silently hidden)
    for col, vals in (("state", states), ("region", regions), ("driver", drivers), ("audit_status", statuses), ("provider", providers)):
        if vals:
            r = r[r[col].isin(vals)]
    return r


def editable_map_frame(extra=None):
    m = C.base_map_normalised(extra)
    return pd.DataFrame(sorted(m.items()), columns=["driver", "state"])


def peek_headers(data: bytes, filename: str):
    """Header cells of the first sheet that looks like it has a header (for the manual column-mapping panel)."""
    try:
        for _, raw in readers._sheets_from_bytes(data, filename):
            h = readers._find_header(raw.reset_index(drop=True))
            if h is not None:
                return [str(c) for c in raw.iloc[h].tolist() if str(c) != "nan"]
            return [str(c) for c in raw.iloc[0].tolist() if str(c) != "nan"]
    except Exception:
        pass
    return []
