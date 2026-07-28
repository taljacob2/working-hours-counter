"""
generate_hours.py — produce a from-scratch JBClock-style monthly hours .xls,
with no uploaded company file required. Shares all business logic with
merge_hours.py via report_core.py, so the two paths can't drift apart.

Usage:
    python generate_hours.py <config_json_path> <logs_json_path> <output_xls_path>

config_json fields:
    year, month (int)
    companyName, employeeName, employeeCode, cardNumber, payrollNumber,
    startDate, agreementText (str)
    targetDailyHours (float, default 9.0)
    colorHomeHours (bool, default False)
    fillMissingOffice (bool, default True)
    dayOverrides ({ 'YYYY-MM-DD': 'work' | 'off' }, default {})
    printDate (str, 'DD/MM/YY', default: computed at run time)
"""

import sys
import json
import datetime
import xlwt

import report_core as core


def main():
    if len(sys.argv) < 4:
        print("Usage: python generate_hours.py <config_json> <logs_json> <output_xls>")
        sys.exit(1)

    config_path = sys.argv[1]
    logs_json_path = sys.argv[2]
    output_xls_path = sys.argv[3]

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"Error loading config JSON: {e}")
        sys.exit(1)

    try:
        logs_by_date = core.load_logs_by_date(logs_json_path)
    except Exception as e:
        print(f"Error loading logs JSON: {e}")
        sys.exit(1)

    try:
        year = int(cfg['year'])
        month = int(cfg['month'])
    except (KeyError, TypeError, ValueError) as e:
        print(f"Missing or invalid year/month in config: {e}")
        sys.exit(1)

    meta = core.EmployeeMeta(
        company_name=cfg.get('companyName', ''),
        employee_name=cfg.get('employeeName', ''),
        employee_code=cfg.get('employeeCode', ''),
        card_number=cfg.get('cardNumber', ''),
        payroll_number=cfg.get('payrollNumber', ''),
        start_date=cfg.get('startDate', ''),
        agreement_text=cfg.get('agreementText', ''),
    )
    target_hours = float(cfg.get('targetDailyHours') or 9.0)
    color_home_hours = bool(cfg.get('colorHomeHours', False))
    fill_missing_office = bool(cfg.get('fillMissingOffice', True))
    day_overrides = cfg.get('dayOverrides') or {}
    print_date_str = cfg.get('printDate') or datetime.date.today().strftime('%d/%m/%y')

    layout = core.compute_row_layout(year, month)
    styles = core.build_style_set()

    wb = xlwt.Workbook(encoding='utf-8')
    sheet = wb.add_sheet(meta.employee_name or 'Sheet1', cell_overwrite_ok=True)

    core.build_skeleton(sheet, layout, meta, styles, print_date_str)

    backend = core.GeneratedBackend(sheet, styles, layout.total_row)
    agg = core.Aggregates()

    for day_date in sorted(layout.day_rows):
        r = layout.day_rows[day_date]
        day_name = core.HEBREW_WEEKDAY_LETTERS[core.sun_first_weekday(day_date)]
        date_str = day_date.strftime('%Y-%m-%d')
        result = core.process_day(
            backend, r, date_str, day_name, day_overrides, True,
            logs_by_date, color_home_hours, fill_missing_office,
            core.COLOUR_POSITIVE, core.COLOUR_NEGATIVE, core.COLOUR_VACATION,
            target_hours=target_hours,
        )
        agg.accumulate(result)

    core.write_summary_rows(
        backend, layout.total_row, layout.rows, agg,
        colour_pos=core.COLOUR_POSITIVE, colour_neg=core.COLOUR_NEGATIVE,
    )

    wb.save(output_xls_path)
    print("Successfully generated workbook.")


if __name__ == "__main__":
    main()
