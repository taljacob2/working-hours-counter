"""
web_bridge.py — in-browser entry points for the Excel merge/generate/parse
features, called from src/lib/pyodideBridge.js via Pyodide. Mirrors what
merge_hours.py / generate_hours.py / parse_header.py's main() functions do,
minus argv/file-path/sys.exit — everything here operates on in-memory
bytes/JSON strings and raises on error so JS can catch it. All business
logic still lives in report_core.py; nothing here is new logic.
"""

import io
import json
import re
import datetime

import xlrd
import xlutils.copy
import xlwt

import report_core as core


def _logs_by_date(logs):
    """Same grouping as report_core.load_logs_by_date(), but from an
    already-parsed list of log dicts instead of a file path."""
    logs_by_date = {}
    for log in logs:
        log_date = log.get("date")
        if log_date:
            logs_by_date.setdefault(log_date, []).append(log)
    return logs_by_date


def run_merge(xls_bytes, logs_json_str, color_home_hours, day_overrides_json_str, fill_missing_office):
    """Mirrors merge_hours.py's main(). Returns the merged workbook's bytes."""
    day_overrides_provided = day_overrides_json_str is not None
    day_overrides = json.loads(day_overrides_json_str) if day_overrides_provided else {}
    logs_by_date = _logs_by_date(json.loads(logs_json_str))

    rb = xlrd.open_workbook(file_contents=bytes(xls_bytes), formatting_info=True, ignore_workbook_corruption=True)
    sheet_read = rb.sheet_by_index(0)
    wb = xlutils.copy.copy(rb)
    sheet_write = wb.get_sheet(0)

    colour_pos, colour_neg, colour_vac = core.detect_colours(rb, sheet_read)
    hour_fmt = core.detect_hour_format(rb, sheet_read)
    monthly_hour_fmt = core.to_elapsed_hour_format(hour_fmt)

    backend = core.UploadBackend(rb, sheet_read, sheet_write, hour_fmt, monthly_hour_fmt)

    month = 7
    year = 2026
    m_text = sheet_read.cell_value(1, 0)
    match = re.search(r'(\d{2})/(\d{2})', m_text)
    if match:
        month = int(match.group(1))
        year = 2000 + int(match.group(2))

    agg = core.Aggregates()

    for r in range(6, sheet_read.nrows):
        cell_val = sheet_read.cell_value(r, 1)
        if not cell_val:
            break

        parsed_day = re.match(r'^(\d{2})/(\d{2})\s+([א-ת])$', str(cell_val).strip())
        if not parsed_day:
            continue

        day = int(parsed_day.group(1))
        day_name = parsed_day.group(3)
        date_str = f"{year}-{month:02d}-{day:02d}"

        result = core.process_day(
            backend, r, date_str, day_name, day_overrides, day_overrides_provided,
            logs_by_date, color_home_hours, fill_missing_office,
            colour_pos, colour_neg, colour_vac, target_hours=9.0,
        )
        agg.accumulate(result)

    core.write_summary_rows(
        backend, total_row=41,
        rows={
            'row_100_paid': 45, 'row_125': 46, 'row_150': 47, 'row_200': 48,
            'row_sum_ot': 52, 'row_deficit': 53, 'row_surplus': 54,
        },
        agg=agg, colour_pos=colour_pos, colour_neg=colour_neg,
    )

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def run_generate(config_json_str, logs_json_str):
    """Mirrors generate_hours.py's main(). Returns the generated workbook's bytes."""
    cfg = json.loads(config_json_str)
    logs_by_date = _logs_by_date(json.loads(logs_json_str))

    year = int(cfg['year'])
    month = int(cfg['month'])

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

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def run_parse_header(xls_bytes):
    """Mirrors parse_header.py's main(). Returns a JSON string (dicts don't
    cross the Pyodide boundary as cleanly as plain strings/bytes)."""
    rb = xlrd.open_workbook(file_contents=bytes(xls_bytes), formatting_info=True, ignore_workbook_corruption=True)
    sheet = rb.sheet_by_index(0)
    return json.dumps(core.parse_header(sheet))
