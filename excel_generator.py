"""Multi-sheet Excel workbook (values, formatted; traceability columns kept)."""
import io
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

MONEY = '$#,##0.00;[Red]($#,##0.00);-'


def _drop_total_rows(df):
    # Kept for compatibility: totals are part of the report and must remain in Excel.
    return df.reset_index(drop=True) if df is not None else df


def build_workbook(frames: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in frames.items():
            df = _drop_total_rows(df.copy())
            df.to_excel(xw, sheet_name=name[:31], index=False)
            ws = xw.sheets[name[:31]]
            for j, col in enumerate(df.columns, 1):
                c = ws.cell(1, j); c.font = Font(bold=True, color="FFFFFF", name="Arial"); c.fill = PatternFill("solid", fgColor="153B5B")
                c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                c.border = Border(bottom=Side(style="medium", color="0F766E"))
                width = min(max(len(str(col)), *(len(str(v)) for v in df[col].head(200))) + 2, 45) if len(df) else len(str(col)) + 2
                ws.column_dimensions[get_column_letter(j)].width = width
                low = str(col).lower()
                if any(k in low for k in ("revenue", "payment", "profit", "difference", "shortfall", "owed", "expected", "actual")) and pd.api.types.is_numeric_dtype(df[col]):
                    for r in range(2, len(df) + 2): ws.cell(r, j).number_format = MONEY
                if "margin" in low:
                    for r in range(2, len(df) + 2): ws.cell(r, j).number_format = '0.0"%"'
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            ws.row_dimensions[1].height = 30
            for r in range(2, len(df) + 2):
                ws.cell(r, 1).alignment = Alignment(vertical="top")
                if str(ws.cell(r, 1).value).strip().upper() in ("TOTAL", "GRAND TOTAL"):
                    for j in range(1, len(df.columns) + 1):
                        ws.cell(r, j).font = Font(bold=True, color="153B5B", name="Arial")
                        ws.cell(r, j).fill = PatternFill("solid", fgColor="E5EEF5")
                        ws.cell(r, j).border = Border(top=Side(style="medium", color="0F766E"))
    return buf.getvalue()
