"""Multi-sheet Excel workbook (values, formatted; traceability columns kept)."""
import io
import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

MONEY = '$#,##0.00;[Red]($#,##0.00);-'


def build_workbook(frames: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in frames.items():
            df = df.copy()
            df.to_excel(xw, sheet_name=name[:31], index=False)
            ws = xw.sheets[name[:31]]
            for j, col in enumerate(df.columns, 1):
                c = ws.cell(1, j); c.font = Font(bold=True, color="FFFFFF", name="Arial"); c.fill = PatternFill("solid", fgColor="1F3A5F")
                width = min(max(len(str(col)), *(len(str(v)) for v in df[col].head(200))) + 2, 45) if len(df) else len(str(col)) + 2
                ws.column_dimensions[get_column_letter(j)].width = width
                low = str(col).lower()
                if any(k in low for k in ("revenue", "payment", "profit", "difference", "shortfall", "owed", "expected", "actual")) and pd.api.types.is_numeric_dtype(df[col]):
                    for r in range(2, len(df) + 2): ws.cell(r, j).number_format = MONEY
                if "margin" in low:
                    for r in range(2, len(df) + 2): ws.cell(r, j).number_format = '0.0"%"'
            ws.freeze_panes = "A2"
    return buf.getvalue()
