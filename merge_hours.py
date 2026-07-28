import xlrd
import xlutils.copy
import json
import sys
import os
import re

import report_core as core


def main():
    if len(sys.argv) < 4:
        print("Usage: python merge_hours.py <input_xls> <logs_json> <output_xls> "
              "[color_home_hours] [day_overrides_json] [fill_missing_office]")
        sys.exit(1)

    input_xls_path = sys.argv[1]
    logs_json_path = sys.argv[2]
    output_xls_path = sys.argv[3]
    color_home_hours = len(sys.argv) > 4 and sys.argv[4].strip().lower() == 'true'

    # day_overrides: { 'YYYY-MM-DD': 'work' | 'off' }, as set by the user in-app.
    # When provided (even empty), it is the authoritative source for which days are
    # 'חופש' — a day is synced to match the app's per-date override rather than
    # trusting whatever the company's XLS already had marked.
    day_overrides_provided = len(sys.argv) > 5
    day_overrides = {}
    if day_overrides_provided:
        try:
            with open(sys.argv[5], 'r', encoding='utf-8') as f:
                day_overrides = json.load(f)
        except Exception as e:
            print(f"Error loading day overrides JSON: {e}")
            day_overrides = {}

    # Whether to backfill an office session the app recorded but the company's own
    # file never got around to detailing. Defaults to on (matches the in-app
    # toggle's default) so a bare CLI invocation without this arg still does it.
    fill_missing_office = True
    if len(sys.argv) > 6:
        fill_missing_office = sys.argv[6].strip().lower() == 'true'

    if not os.path.exists(input_xls_path):
        print(f"Input file not found: {input_xls_path}")
        sys.exit(1)

    # 1. Load logs
    try:
        logs_by_date = core.load_logs_by_date(logs_json_path)
    except Exception as e:
        print(f"Error loading logs JSON: {e}")
        sys.exit(1)

    # 2. Open XLS
    try:
        rb = xlrd.open_workbook(input_xls_path, formatting_info=True, ignore_workbook_corruption=True)
    except Exception as e:
        print(f"Error opening XLS file: {e}")
        sys.exit(1)

    sheet_read = rb.sheet_by_index(0)
    wb = xlutils.copy.copy(rb)
    sheet_write = wb.get_sheet(0)

    colour_pos, colour_neg, colour_vac = core.detect_colours(rb, sheet_read)
    hour_fmt = core.detect_hour_format(rb, sheet_read)
    monthly_hour_fmt = core.to_elapsed_hour_format(hour_fmt)

    backend = core.UploadBackend(rb, sheet_read, sheet_write, hour_fmt, monthly_hour_fmt)

    # 3. Parse month/year from Row 1
    month = 7
    year = 2026
    m_text = sheet_read.cell_value(1, 0)
    match = re.search(r'(\d{2})/(\d{2})', m_text)
    if match:
        month = int(match.group(1))
        year = 2000 + int(match.group(2))

    # 4. Process each row
    agg = core.Aggregates()

    for r in range(6, sheet_read.nrows):
        cell_val = sheet_read.cell_value(r, 1)
        if not cell_val:
            # We reached the end of the days rows if we see Row 41 (which has empty Col 1)
            # Row 41 is the summary totals row
            break

        parsed_day = re.match(r'^(\d{2})/(\d{2})\s+([א-ת])$', str(cell_val).strip())
        if not parsed_day:
            # Separator row like '------------'
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

    # 5-6. Write the total row and bottom summary table (literal row numbers,
    # matching this template's fixed 5-week-group shape).
    core.write_summary_rows(
        backend, total_row=41,
        rows={
            'row_100_paid': 45, 'row_125': 46, 'row_150': 47, 'row_200': 48,
            'row_sum_ot': 52, 'row_deficit': 53, 'row_surplus': 54,
        },
        agg=agg, colour_pos=colour_pos, colour_neg=colour_neg,
    )

    # 7. Save workbook
    wb.save(output_xls_path)
    print("Successfully processed and saved workbook.")

if __name__ == "__main__":
    main()
