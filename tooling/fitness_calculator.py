"""
Fitness & Nutrition Excel Calculator Generator
==============================================
Generates a comprehensive Excel workbook with:
  - BMR / TDEE calculator (male + female sheets)
  - Macro split for cutting / maintenance / bulking
  - Weight loss trend tracker with calorie deficit
  - Cardio & step-based calorie burn estimator

Run:  python tooling/fitness_calculator.py
Output:  data/fitness_calculator.xlsx
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import openpyxl
from openpyxl.chart import LineChart, Reference
from openpyxl.formatting.rule import ColorScaleRule, DataBarRule
from openpyxl.styles import (
    Alignment,
    Border,
    Font,
    PatternFill,
    Side,
)
from openpyxl.utils import get_column_letter

# ── Paths ──────────────────────────────────────────────────────────────
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / "fitness_calculator.xlsx"

# ── Constants ───────────────────────────────────────────────────────────
ACTIVITY_LEVELS = {
    "Sedentary (little / no exercise)": 1.2,
    "Lightly active (1–3 days / week)": 1.375,
    "Moderately active (3–5 days / week)": 1.55,
    "Very active (6–7 days / week)": 1.725,
    "Extremely active (athlete / twice daily)": 1.9,
}

CAL_PER_KG_FAT = 7700  # 1 kg body fat ≈ 7700 kcal deficit

# ── Styles ──────────────────────────────────────────────────────────────
HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
SUBHEADER_FILL = PatternFill(start_color="D6E4F0", end_color="D6E4F0", fill_type="solid")
SUBHEADER_FONT = Font(name="Calibri", size=11, bold=True, color="1F4E79")
INPUT_FILL = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
RESULT_FILL = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
WARN_FILL = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)

NUMBER_FORMAT = "#,##0.0"
KCAL_FORMAT = '#,##0 "kcal"'
KG_FORMAT = '#,##0.0 "kg"'
PCT_FORMAT = "0.0%"

# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _style_header_row(ws, row: int, col_start: int, col_end: int) -> None:
    for c in range(col_start, col_end + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        cell.border = THIN_BORDER


def _style_input_cell(ws, row: int, col: int) -> None:
    cell = ws.cell(row=row, column=col)
    cell.fill = INPUT_FILL
    cell.border = THIN_BORDER
    cell.alignment = CENTER


def _style_result_row(ws, row: int, col_start: int, col_end: int) -> None:
    for c in range(col_start, col_end + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = RESULT_FILL
        cell.border = THIN_BORDER
        cell.alignment = CENTER


def _write_table_header(ws, row: int, headers: list[str], start_col: int = 1) -> None:
    for i, h in enumerate(headers):
        ws.cell(row=row, column=start_col + i, value=h)
    _style_header_row(ws, row, start_col, start_col + len(headers) - 1)


def _auto_width(ws, min_width: int = 10, max_width: int = 40) -> None:
    for col_cells in ws.columns:
        col_letter = get_column_letter(col_cells[0].column)
        lengths = []
        for cell in col_cells:
            if cell.value is not None:
                lengths.append(len(str(cell.value)))
        best = max(lengths) + 2 if lengths else min_width
        ws.column_dimensions[col_letter].width = max(min_width, min(best, max_width))


# ═══════════════════════════════════════════════════════════════════════
# BMR / TDEE sheet builder (shared for male & female)
# ═══════════════════════════════════════════════════════════════════════


def _build_bmr_tdee_sheet(ws, gender: str) -> None:
    """Build one BMR/TDEE sheet for a given gender ('Male' or 'Female').

    Layout:
      Row  1 : Title
      Row  3–6 : Inputs (Weight kg, Height cm, Age, Body Fat % optional)
      Row  8–12: BMR result + TDEE table
      Row 14+  : Macro split table
    """
    gender_label = gender
    bmr_offset = 161 if gender == "Female" else 5  # Mifflin-St Jeor constant

    # ── Title ──
    ws.merge_cells("A1:F1")
    title_cell = ws["A1"]
    title_cell.value = f"🏋️ {gender_label} — BMR · TDEE · Macro Calculator"
    title_cell.font = Font(name="Calibri", size=16, bold=True, color="1F4E79")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 32

    # ── Inputs ──
    _write_table_header(ws, 3, ["INPUT", "VALUE", "UNIT", "NOTES"], 1)
    inputs = [
        ("Weight", 75.0, "kg", "Enter your current body weight"),
        ("Height", 175.0, "cm", "Enter your height"),
        ("Age", 30, "years", "Enter your age"),
        ("Body Fat %", 20.0, "%", "Optional — improves macro calc"),
    ]
    for i, (label, default, unit, note) in enumerate(inputs):
        r = 4 + i
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=default)
        ws.cell(row=r, column=3, value=unit)
        ws.cell(row=r, column=4, value=note)
        ws.cell(row=r, column=1).font = Font(bold=True)
        ws.cell(row=r, column=1).border = THIN_BORDER
        ws.cell(row=r, column=3).border = THIN_BORDER
        ws.cell(row=r, column=4).border = THIN_BORDER
        _style_input_cell(ws, r, 2)

    # input cell refs  (B4=weight_kg, B5=height_cm, B6=age, B7=bf_pct)
    W = "$B$4"  # weight kg
    H = "$B$5"  # height cm
    A = "$B$6"  # age
    BF = "$B$7"  # body fat %

    # ── BMR ──
    r = 9
    _write_table_header(ws, r, ["METRIC", "FORMULA", "VALUE", "UNIT"], 1)
    r = 10
    ws.cell(row=r, column=1, value="BMR (Mifflin-St Jeor)")
    ws.cell(row=r, column=1).font = Font(bold=True)
    ws.cell(row=r, column=2, value=f"10×W + 6.25×H − 5×A − {bmr_offset}")
    ws.cell(row=r, column=3, value=f"=10*{W} + 6.25*{H} - 5*{A} - {bmr_offset}")
    ws.cell(row=r, column=3).number_format = KCAL_FORMAT
    ws.cell(row=r, column=4, value="kcal/day")
    _style_result_row(ws, r, 1, 4)
    BMR_CELL = f"$C${r}"

    # ── TDEE table ──
    r = 12
    _write_table_header(
        ws,
        r,
        [
            "ACTIVITY LEVEL",
            "MULTIPLIER",
            "TDEE (kcal/day)",
            "TDEE − 500 (cut)",
            "TDEE + 300 (bulk)",
        ],
        1,
    )
    tdee_start = r + 1
    for i, (label, mult) in enumerate(ACTIVITY_LEVELS.items()):
        rr = tdee_start + i
        ws.cell(row=rr, column=1, value=label)
        ws.cell(row=rr, column=1).font = Font(bold=True)
        ws.cell(row=rr, column=2, value=mult)
        ws.cell(row=rr, column=2).number_format = "0.000"
        ws.cell(row=rr, column=3, value=f"={BMR_CELL}*B{rr}")
        ws.cell(row=rr, column=3).number_format = KCAL_FORMAT
        ws.cell(row=rr, column=4, value=f"=C{rr}-500")
        ws.cell(row=rr, column=4).number_format = KCAL_FORMAT
        ws.cell(row=rr, column=5, value=f"=C{rr}+300")
        ws.cell(row=rr, column=5).number_format = KCAL_FORMAT
        for c in range(1, 6):
            ws.cell(row=rr, column=c).border = THIN_BORDER
            ws.cell(row=rr, column=c).alignment = CENTER if c > 1 else LEFT

    # highlight recommended row (moderately active)
    rec_row = tdee_start + 2  # index 2 = moderately active
    for c in range(1, 6):
        ws.cell(row=rec_row, column=c).fill = PatternFill(
            start_color="DAEEF3", end_color="DAEEF3", fill_type="solid"
        )

    # ── Macro split (cutting) ──
    r = tdee_start + len(ACTIVITY_LEVELS) + 1
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    ws.cell(row=r, column=1, value="🔪 MACRO SPLIT — CUTTING DAYS (based on selected TDEE − 500)")
    ws.cell(row=r, column=1).font = Font(name="Calibri", size=12, bold=True, color="C00000")
    ws.cell(row=r, column=1).alignment = CENTER

    # Let user pick the activity row to use for macros (reference row)
    r += 1
    _write_table_header(ws, r, ["Select Activity Row →", "(enter row number)", "", "", ""], 1)
    _style_input_cell(ws, r, 2)
    # default to moderately active (row 15 = tdee_start + 2)
    ws.cell(row=r, column=2, value=tdee_start + 2)
    ACT_ROW_REF = f"$B${r}"  # user-chosen activity row

    # Cutting calories ref
    CUT_CAL_REF = f'INDIRECT("D"&{ACT_ROW_REF})'  # column D = TDEE-500

    r += 2
    _write_table_header(ws, r, ["MACRO", "g per kg BW", "g / day", "kcal", "% of calories"], 1)

    # Protein: 2.2 g/kg
    rr = r + 1
    ws.cell(row=rr, column=1, value="🥩 Protein")
    ws.cell(row=rr, column=1).font = Font(bold=True, color="C00000")
    ws.cell(row=rr, column=2, value=2.2)
    ws.cell(row=rr, column=3, value=f"=2.2*{W}")
    ws.cell(row=rr, column=3).number_format = '#,##0.0 "g"'
    ws.cell(row=rr, column=4, value=f"=C{rr}*4")
    ws.cell(row=rr, column=4).number_format = KCAL_FORMAT
    ws.cell(row=rr, column=5, value=f"=IF({CUT_CAL_REF}>0, D{rr}/{CUT_CAL_REF}, 0)")
    ws.cell(row=rr, column=5).number_format = "0.0%"
    for c in range(1, 6):
        ws.cell(row=rr, column=c).border = THIN_BORDER
        ws.cell(row=rr, column=c).alignment = CENTER if c > 1 else LEFT

    # Fat: 0.8 g/kg
    rr = r + 2
    ws.cell(row=rr, column=1, value="🥑 Fat")
    ws.cell(row=rr, column=1).font = Font(bold=True, color="BF8F00")
    ws.cell(row=rr, column=2, value=0.8)
    ws.cell(row=rr, column=3, value=f"=0.8*{W}")
    ws.cell(row=rr, column=3).number_format = '#,##0.0 "g"'
    ws.cell(row=rr, column=4, value=f"=C{rr}*9")
    ws.cell(row=rr, column=4).number_format = KCAL_FORMAT
    ws.cell(row=rr, column=5, value=f"=IF({CUT_CAL_REF}>0, D{rr}/{CUT_CAL_REF}, 0)")
    ws.cell(row=rr, column=5).number_format = "0.0%"
    for c in range(1, 6):
        ws.cell(row=rr, column=c).border = THIN_BORDER
        ws.cell(row=rr, column=c).alignment = CENTER if c > 1 else LEFT

    # Carbs: remainder
    rr = r + 3
    ws.cell(row=rr, column=1, value="🍚 Carbs (remainder)")
    ws.cell(row=rr, column=1).font = Font(bold=True, color="2F5496")
    ws.cell(row=rr, column=2, value="—")
    ws.cell(row=rr, column=3, value=f"=MAX(0, ({CUT_CAL_REF} - D{r+1} - D{r+2}) / 4)")
    ws.cell(row=rr, column=3).number_format = '#,##0.0 "g"'
    ws.cell(row=rr, column=4, value=f"=C{rr}*4")
    ws.cell(row=rr, column=4).number_format = KCAL_FORMAT
    ws.cell(row=rr, column=5, value=f"=IF({CUT_CAL_REF}>0, D{rr}/{CUT_CAL_REF}, 0)")
    ws.cell(row=rr, column=5).number_format = "0.0%"
    for c in range(1, 6):
        ws.cell(row=rr, column=c).border = THIN_BORDER
        ws.cell(row=rr, column=c).alignment = CENTER if c > 1 else LEFT

    # Total row
    rr = r + 4
    ws.cell(row=rr, column=1, value="✅ TOTAL")
    ws.cell(row=rr, column=1).font = Font(bold=True)
    ws.cell(row=rr, column=3, value=f"=SUM(C{r+1}:C{r+3})")
    ws.cell(row=rr, column=3).number_format = '#,##0.0 "g"'
    ws.cell(row=rr, column=4, value=f"=SUM(D{r+1}:D{r+3})")
    ws.cell(row=rr, column=4).number_format = KCAL_FORMAT
    ws.cell(row=rr, column=5, value=f"=SUM(E{r+1}:E{r+3})")
    ws.cell(row=rr, column=5).number_format = "0.0%"
    for c in range(1, 6):
        ws.cell(row=rr, column=c).border = THIN_BORDER
        ws.cell(row=rr, column=c).fill = PatternFill(
            start_color="E2EFDA", end_color="E2EFDA", fill_type="solid"
        )
        ws.cell(row=rr, column=c).alignment = CENTER if c > 1 else LEFT

    # protein calcs based on lean mass (if BF% given)
    r = rr + 2
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    ws.cell(
        row=r,
        column=1,
        value="💡 TIP: If you entered Body Fat %, protein is calculated on lean body mass below:",
    )
    ws.cell(row=r, column=1).font = Font(italic=True, color="404040")
    r += 1
    ws.cell(row=r, column=1, value="Lean Body Mass (LBM)")
    ws.cell(row=r, column=2, value=f"={W}*(1-{BF}/100)")
    ws.cell(row=r, column=2).number_format = '#,##0.0 "kg"'
    ws.cell(row=r, column=3, value="Protein @ 2.5 g/kg LBM")
    ws.cell(row=r, column=3).font = Font(bold=True)
    ws.cell(row=r, column=4, value=f"=B{r}*2.5")
    ws.cell(row=r, column=4).number_format = '#,##0.0 "g/day"'
    for c in range(1, 5):
        ws.cell(row=r, column=c).border = THIN_BORDER

    _auto_width(ws, min_width=14, max_width=42)
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 20
    ws.column_dimensions["E"].width = 18

    # freeze panes below input area
    ws.freeze_panes = "A8"


# ═══════════════════════════════════════════════════════════════════════
# Weight Loss Tracker sheet
# ═══════════════════════════════════════════════════════════════════════


def _build_weight_tracker(ws) -> None:
    """Daily weight log with trend line, rolling average, and deficit projection."""

    ws.merge_cells("A1:J1")
    ws["A1"].value = "📉 WEIGHT LOSS TRACKER — Daily Log & Trend"
    ws["A1"].font = Font(name="Calibri", size=16, bold=True, color="1F4E79")
    ws["A1"].alignment = CENTER
    ws.row_dimensions[1].height = 32

    headers = [
        "Date",
        "Weight (kg)",
        "Calories Eaten",
        "TDEE (kcal)",
        "Net Deficit (kcal)",
        "Cumulative Deficit (kcal)",
        "Projected Weight (kg)",
        "7-Day Avg Weight (kg)",
        "Trend ∆ (kg)",
        "Notes",
    ]
    _write_table_header(ws, 3, headers, 1)

    # Pre-fill 90 rows of dates
    today = _dt.date.today()
    for i in range(90):
        r = 4 + i
        d = today + _dt.timedelta(days=i)
        ws.cell(row=r, column=1, value=d)
        ws.cell(row=r, column=1).number_format = "DD-MMM-YYYY"
        ws.cell(row=r, column=1).alignment = CENTER
        ws.cell(row=r, column=1).border = THIN_BORDER

        # Weight input (yellow)
        _style_input_cell(ws, r, 2)
        ws.cell(row=r, column=2).number_format = '#,##0.00 "kg"'

        # Calories eaten input (yellow)
        _style_input_cell(ws, r, 3)
        ws.cell(row=r, column=3).number_format = KCAL_FORMAT

        # TDEE input (or reference from BMR sheet)
        _style_input_cell(ws, r, 4)
        ws.cell(row=r, column=4).number_format = KCAL_FORMAT

        # Net deficit formula: TDEE - eaten
        ws.cell(row=r, column=5, value=f'=IF(AND(D{r}>0, C{r}>0), D{r}-C{r}, "")')
        ws.cell(row=r, column=5).number_format = KCAL_FORMAT
        ws.cell(row=r, column=5).border = THIN_BORDER
        ws.cell(row=r, column=5).alignment = CENTER

        # Cumulative deficit
        if i == 0:
            ws.cell(row=r, column=6, value=f'=IF(E{r}="", "", E{r})')
        else:
            ws.cell(row=r, column=6, value=f'=IF(E{r}="", "", F{r-1}+E{r})')
        ws.cell(row=r, column=6).number_format = KCAL_FORMAT
        ws.cell(row=r, column=6).border = THIN_BORDER
        ws.cell(row=r, column=6).alignment = CENTER

        # Projected weight: starting weight - (cumulative deficit / 7700)
        ws.cell(row=r, column=7, value=f'=IF(F{r}="", "", $B$4 - F{r}/{CAL_PER_KG_FAT})')
        ws.cell(row=r, column=7).number_format = '#,##0.00 "kg"'
        ws.cell(row=r, column=7).border = THIN_BORDER
        ws.cell(row=r, column=7).alignment = CENTER

        # 7-day rolling average weight
        if i >= 6:
            ws.cell(row=r, column=8, value=f'=IF(COUNT(B{r-6}:B{r})>=7, AVERAGE(B{r-6}:B{r}), "")')
        else:
            ws.cell(row=r, column=8, value="")
        ws.cell(row=r, column=8).number_format = '#,##0.00 "kg"'
        ws.cell(row=r, column=8).border = THIN_BORDER
        ws.cell(row=r, column=8).alignment = CENTER

        # Trend delta (7-day avg today - 7-day avg 7 days ago)
        if i >= 13:
            ws.cell(row=r, column=9, value=f'=IF(AND(H{r}<>"", H{r-7}<>""), H{r}-H{r-7}, "")')
        else:
            ws.cell(row=r, column=9, value="")
        ws.cell(row=r, column=9).number_format = '+#,##0.00 "kg";-#,##0.00 "kg"'
        ws.cell(row=r, column=9).border = THIN_BORDER
        ws.cell(row=r, column=9).alignment = CENTER

        # Notes
        ws.cell(row=r, column=10).border = THIN_BORDER
        ws.cell(row=r, column=10).alignment = LEFT

    # Summary row at top (row 2)
    ws.merge_cells("A2:J2")
    ws["A2"].value = (
        "📌 INSTRUCTIONS: Enter your Weight (col B), Calories Eaten (col C), and TDEE (col D) daily. "
        "The sheet auto-calculates deficit, projected weight, and 7-day trend. "
        "First row (B4) = your starting weight — used for projection baseline."
    )
    ws["A2"].font = Font(italic=True, size=9, color="666666")
    ws["A2"].alignment = LEFT

    # Conditional formatting: green for deficit, red for surplus
    ws.conditional_formatting.add(
        "E4:E93",
        ColorScaleRule(
            start_type="min",
            start_color="F8696B",
            mid_type="percentile",
            mid_value=50,
            mid_color="FFEB84",
            end_type="max",
            end_color="63BE7B",
        ),
    )

    # Data bar for cumulative deficit
    ws.conditional_formatting.add(
        "F4:F93",
        DataBarRule(start_type="min", end_type="max", color="5B9BD5", showValue=True),
    )

    # ── Chart: Weight trend ──
    chart = LineChart()
    chart.title = "Weight Loss Trend (7-Day Rolling Avg)"
    chart.style = 10
    chart.y_axis.title = "Weight (kg)"
    chart.x_axis.title = "Date"
    chart.height = 14
    chart.width = 22

    # categories = date column
    cats = Reference(ws, min_col=1, min_row=4, max_row=93)
    # actual weight
    data1 = Reference(ws, min_col=2, min_row=3, max_row=93)
    chart.add_data(data1, titles_from_data=True)
    chart.set_categories(cats)

    # 7-day avg
    data2 = Reference(ws, min_col=8, min_row=3, max_row=93)
    chart.add_data(data2, titles_from_data=True)

    # projected weight
    data3 = Reference(ws, min_col=7, min_row=3, max_row=93)
    chart.add_data(data3, titles_from_data=True)

    # style series
    chart.series[0].graphicalProperties.line.width = 15000  # thin
    chart.series[0].graphicalProperties.line.solidFill = "B0B0B0"
    chart.series[1].graphicalProperties.line.width = 28000  # thick
    chart.series[1].graphicalProperties.line.solidFill = "2F5496"
    chart.series[2].graphicalProperties.line.width = 22000
    chart.series[2].graphicalProperties.line.solidFill = "C00000"
    chart.series[2].graphicalProperties.line.dashStyle = "dash"

    ws.add_chart(chart, "A96")

    _auto_width(ws, min_width=12, max_width=24)
    ws.column_dimensions["J"].width = 22
    ws.freeze_panes = "A4"


# ═══════════════════════════════════════════════════════════════════════
# Cardio & Activity sheet
# ═══════════════════════════════════════════════════════════════════════


def _build_cardio_sheet(ws) -> None:
    """Step-based calorie burn calculator + common cardio activities."""

    ws.merge_cells("A1:G1")
    ws["A1"].value = "🚶 CARDIO & ACTIVITY — Calorie Burn Calculator"
    ws["A1"].font = Font(name="Calibri", size=16, bold=True, color="1F4E79")
    ws["A1"].alignment = CENTER
    ws.row_dimensions[1].height = 32

    # ── Inputs ──
    _write_table_header(ws, 3, ["INPUT", "VALUE", "UNIT", "NOTES"], 1)
    inputs = [
        ("Weight", 75.0, "kg", "Your current body weight"),
        ("Steps Walked", 10000, "steps", "Pedometer / watch reading"),
        ("Step Stride Length", 0.78, "m", "Avg ≈ 0.78 m (height × 0.415)"),
    ]
    for i, (label, default, unit, note) in enumerate(inputs):
        r = 4 + i
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=1).font = Font(bold=True)
        ws.cell(row=r, column=2, value=default)
        ws.cell(row=r, column=3, value=unit)
        ws.cell(row=r, column=4, value=note)
        ws.cell(row=r, column=1).border = THIN_BORDER
        ws.cell(row=r, column=3).border = THIN_BORDER
        ws.cell(row=r, column=4).border = THIN_BORDER
        _style_input_cell(ws, r, 2)

    # ── Calculated outputs ──
    r = 8
    _write_table_header(ws, r, ["METRIC", "FORMULA", "VALUE", "UNIT"], 1)

    W = "$B$4"  # weight kg
    STEPS = "$B$5"  # steps
    STRIDE = "$B$6"  # stride m

    calcs = [
        ("Distance walked", f"={STEPS}*{STRIDE}/1000", '#,##0.00 "km"'),
        ("Walking time (est.)", f"=B{r+1}/5.0*60", '#,##0 "min"'),  # 5 km/h
        ("MET · min", f"=B{r+2}*3.8", '#,##0.0 "MET·min"'),  # 3.8 METs for brisk walk
        ("Calories burned (gross)", f"=3.8*{W}*({STEPS}*{STRIDE}/1000)/5.0", KCAL_FORMAT),
        ("Calories per 1000 steps", f"=B{r+3}/ROUND({STEPS}/1000, 0)", KCAL_FORMAT),
    ]
    for i, (label, formula, fmt) in enumerate(calcs):
        rr = r + 1 + i
        ws.cell(row=rr, column=1, value=label)
        ws.cell(row=rr, column=1).font = Font(bold=True)
        ws.cell(row=rr, column=2, value=formula)
        ws.cell(row=rr, column=3, value=formula)
        ws.cell(row=rr, column=3).number_format = fmt
        ws.cell(row=rr, column=4, value="")
        for c in range(1, 5):
            ws.cell(row=rr, column=c).border = THIN_BORDER
            ws.cell(row=rr, column=c).alignment = CENTER if c > 1 else LEFT
        if i >= 3:
            _style_result_row(ws, rr, 1, 4)

    # ── Common cardio activities reference ──
    r = 17
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    ws.cell(
        row=r, column=1, value="📋 COMMON CARDIO — Calories Burned per Hour (based on your weight)"
    )
    ws.cell(row=r, column=1).font = Font(name="Calibri", size=12, bold=True, color="1F4E79")
    ws.cell(row=r, column=1).alignment = CENTER

    r += 1
    _write_table_header(ws, r, ["ACTIVITY", "METs", "kcal/hour", "kcal/30 min", "Notes"], 1)
    activities = [
        ("Walking (5 km/h)", 3.8, "brisk walk"),
        ("Walking (6.5 km/h)", 5.0, "power walk"),
        ("Running (8 km/h)", 8.3, "light jog"),
        ("Running (10 km/h)", 10.0, "steady run"),
        ("Running (12 km/h)", 12.0, "fast run"),
        ("Cycling (moderate, 20 km/h)", 8.0, "bike"),
        ("Cycling (vigorous, 25 km/h)", 10.0, "spin class"),
        ("Swimming (moderate)", 7.0, "laps"),
        ("Swimming (vigorous)", 10.0, "fast laps"),
        ("Jump Rope (moderate)", 10.0, "skipping"),
        ("Jump Rope (fast)", 12.3, "boxer skip"),
        ("HIIT / CrossFit", 12.0, "high intensity"),
        ("Rowing (moderate)", 7.0, "erg"),
        ("Elliptical (moderate)", 5.0, "gym"),
        ("Stair Climber", 9.0, "stepper"),
        ("Yoga (Hatha)", 2.5, "gentle"),
        ("Yoga (Power / Vinyasa)", 4.0, "flow"),
        ("Weight Lifting (moderate)", 5.0, "gym session"),
        ("Weight Lifting (vigorous)", 6.0, "heavy session"),
    ]
    for i, (name, mets, note) in enumerate(activities):
        rr = r + 1 + i
        ws.cell(row=rr, column=1, value=name)
        ws.cell(row=rr, column=1).font = Font(bold=True) if "Run" in name else Font()
        ws.cell(row=rr, column=2, value=mets)
        ws.cell(row=rr, column=2).number_format = "0.0"
        ws.cell(row=rr, column=3, value=f"={mets}*{W}")
        ws.cell(row=rr, column=3).number_format = KCAL_FORMAT
        ws.cell(row=rr, column=4, value=f"={mets}*{W}/2")
        ws.cell(row=rr, column=4).number_format = KCAL_FORMAT
        ws.cell(row=rr, column=5, value=note)
        for c in range(1, 6):
            ws.cell(row=rr, column=c).border = THIN_BORDER
            ws.cell(row=rr, column=c).alignment = CENTER if c > 1 else LEFT

    # ── 10,000 step daily addition to TDEE ──
    r = rr + 3
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    ws.cell(
        row=r,
        column=1,
        value=(
            f'💡 TIP: If you average {int(STEPS.replace("$B$", ""))} steps/day, '
            f'add the "Calories burned" value above to your TDEE to get your '
            f"true maintenance calories including daily movement."
        ),
    )
    ws.cell(row=r, column=1).font = Font(italic=True, color="404040")
    ws.cell(row=r, column=1).alignment = LEFT

    _auto_width(ws, min_width=14, max_width=36)
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["E"].width = 18
    ws.freeze_panes = "A8"


# ═══════════════════════════════════════════════════════════════════════
# Macro Reference sheet
# ═══════════════════════════════════════════════════════════════════════


def _build_macro_reference(ws) -> None:
    """Reference guide for macro splits across different goals."""

    ws.merge_cells("A1:F1")
    ws["A1"].value = "📊 MACRO QUICK REFERENCE — Cutting · Maintenance · Bulking"
    ws["A1"].font = Font(name="Calibri", size=16, bold=True, color="1F4E79")
    ws["A1"].alignment = CENTER
    ws.row_dimensions[1].height = 32

    # ── Goal-based splits ──
    r = 3
    _write_table_header(ws, r, ["GOAL", "Protein", "Carbs", "Fat", "Calorie Adjust", "Notes"], 1)
    goals = [
        (
            "Aggressive Cut",
            "45%",
            "25%",
            "30%",
            "TDEE − 750 kcal",
            "~1 kg / 10 days. Keep protein high.",
        ),
        ("Moderate Cut ⭐", "40%", "30%", "30%", "TDEE − 500 kcal", "~0.5 kg / week. Sustainable."),
        (
            "Slow Cut",
            "35%",
            "35%",
            "30%",
            "TDEE − 300 kcal",
            "~0.3 kg / week. Minimal muscle loss.",
        ),
        (
            "Body Recomposition",
            "40%",
            "30%",
            "30%",
            "TDEE ± 0",
            "Eat at maintenance, high protein.",
        ),
        ("Maintenance", "30%", "40%", "30%", "TDEE ± 0", "Balanced. Keep protein ≥ 1.6 g/kg."),
        ("Lean Bulk", "30%", "40%", "30%", "TDEE + 300 kcal", "Slow muscle gain, minimal fat."),
        ("Aggressive Bulk", "25%", "45%", "30%", "TDEE + 500 kcal", "Fast gain. Expect some fat."),
    ]
    for i, (goal, prot, carb, fat, cal_adj, note) in enumerate(goals):
        rr = r + 1 + i
        ws.cell(row=rr, column=1, value=goal)
        ws.cell(row=rr, column=1).font = Font(bold=True)
        ws.cell(row=rr, column=2, value=prot)
        ws.cell(row=rr, column=3, value=carb)
        ws.cell(row=rr, column=4, value=fat)
        ws.cell(row=rr, column=5, value=cal_adj)
        ws.cell(row=rr, column=6, value=note)
        for c in range(1, 7):
            ws.cell(row=rr, column=c).border = THIN_BORDER
            ws.cell(row=rr, column=c).alignment = CENTER if c < 6 else LEFT
        # highlight recommended
        if "⭐" in goal:
            for c in range(1, 7):
                ws.cell(row=rr, column=c).fill = PatternFill(
                    start_color="DAEEF3", end_color="DAEEF3", fill_type="solid"
                )

    # ── Per-kg protein guidelines ──
    r = rr + 2
    _write_table_header(ws, r, ["PROTEIN GUIDELINE", "g / kg BW", "g / kg LBM", "Notes"], 1)
    protein_guides = [
        ("Sedentary (minimum)", 0.8, 1.0, "RDA baseline — not enough for training"),
        ("Recreational exercise", 1.2, 1.5, "Light activity 2–3×/week"),
        ("Moderate training", 1.6, 2.0, "Gym 3–5×/week"),
        ("Cutting (muscle preservation) ⭐", 2.2, 2.5, "Higher to prevent muscle loss in deficit"),
        ("Bulking", 1.8, 2.2, "Sufficient for muscle protein synthesis"),
        ("Endurance athlete", 1.4, 1.8, "Marathon, triathlon, etc."),
    ]
    for i, (guide, g_kg, g_lbm, note) in enumerate(protein_guides):
        rr = r + 1 + i
        ws.cell(row=rr, column=1, value=guide)
        ws.cell(row=rr, column=1).font = Font(bold=True) if "⭐" in guide else Font()
        ws.cell(row=rr, column=2, value=g_kg)
        ws.cell(row=rr, column=2).number_format = "0.0"
        ws.cell(row=rr, column=3, value=g_lbm)
        ws.cell(row=rr, column=3).number_format = "0.0"
        ws.cell(row=rr, column=4, value=note)
        for c in range(1, 5):
            ws.cell(row=rr, column=c).border = THIN_BORDER
            ws.cell(row=rr, column=c).alignment = CENTER if c < 4 else LEFT
        if "⭐" in guide:
            for c in range(1, 5):
                ws.cell(row=rr, column=c).fill = PatternFill(
                    start_color="DAEEF3", end_color="DAEEF3", fill_type="solid"
                )

    # ── Key formulas ──
    r = rr + 2
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    ws.cell(row=r, column=1, value="🧮 KEY FORMULAS USED IN THIS WORKBOOK")
    ws.cell(row=r, column=1).font = Font(name="Calibri", size=12, bold=True, color="1F4E79")
    formulas = [
        "BMR (Mifflin-St Jeor):  Male = 10×W + 6.25×H − 5×A + 5  |  Female = 10×W + 6.25×H − 5×A − 161",
        "TDEE = BMR × Activity Multiplier (1.2 – 1.9)",
        "1 kg body fat ≈ 7,700 kcal deficit",
        "Protein: 4 kcal/g  |  Carbs: 4 kcal/g  |  Fat: 9 kcal/g",
        "Steps → distance: steps × stride (m) / 1000 = km",
        "Calories from steps ≈ METs × weight (kg) × time (hours)",
        "7-day rolling average smooths daily water-weight fluctuations",
    ]
    for i, f in enumerate(formulas):
        rr = r + 1 + i
        ws.merge_cells(start_row=rr, start_column=1, end_row=rr, end_column=5)
        ws.cell(row=rr, column=1, value=f"• {f}")
        ws.cell(row=rr, column=1).font = Font(size=10, color="333333")

    _auto_width(ws, min_width=14, max_width=42)
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["F"].width = 34


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════


def main() -> None:
    wb = openpyxl.Workbook()

    # Remove default sheet
    wb.remove(wb.active)

    # Sheet 1: Male BMR/TDEE
    ws_male = wb.create_sheet("🧔 Male Calculator", 0)
    _build_bmr_tdee_sheet(ws_male, "Male")

    # Sheet 2: Female BMR/TDEE
    ws_female = wb.create_sheet("👩 Female Calculator", 1)
    _build_bmr_tdee_sheet(ws_female, "Female")

    # Sheet 3: Weight Loss Tracker
    ws_tracker = wb.create_sheet("📉 Weight Tracker", 2)
    _build_weight_tracker(ws_tracker)

    # Sheet 4: Cardio & Activity
    ws_cardio = wb.create_sheet("🚶 Cardio & Steps", 3)
    _build_cardio_sheet(ws_cardio)

    # Sheet 5: Macro Reference
    ws_macro = wb.create_sheet("📊 Macro Reference", 4)
    _build_macro_reference(ws_macro)

    # ── Save ──
    wb.save(OUTPUT_PATH)
    print(f"✅ Excel workbook saved → {OUTPUT_PATH}")
    print(f"   Sheets: {wb.sheetnames}")


if __name__ == "__main__":
    main()
