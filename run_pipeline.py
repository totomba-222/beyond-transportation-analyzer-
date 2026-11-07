"""Load the files in a folder, classify, reconcile, cache results to output/."""
import os, sys, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import readers, classification as C, reconciliation as R

def _rb(p):
    with open(p, "rb") as fh:
        return fh.read()


def run(folder, main_files, state_files, out="output"):
    """Folder-based wrapper around app_logic.process_uploads (single code path)."""
    import app_logic
    res = app_logic.process_uploads([(f, _rb(os.path.join(folder, f))) for f in main_files],
                                    [(f, _rb(os.path.join(folder, f))) for f in state_files])
    os.makedirs(out, exist_ok=True)
    res.rec.to_csv(f"{out}/recon_all_states.csv", index=False); res.main.to_pickle(f"{out}/main.pkl")
    res.st.to_pickle(f"{out}/state.pkl"); res.rec.to_pickle(f"{out}/recon.pkl")
    return res.mains, res.sts, res.main, res.st, res.rec
