"""
parse_header.py — extract employee/company metadata from an uploaded company
.xls's title rows (0-3), so Settings can be pre-filled instead of retyped.
Read-only: never writes anything.

Usage:
    python parse_header.py <input_xls_path>

Prints a single JSON object to stdout:
    { "companyName", "employeeName", "employeeCode", "cardNumber",
      "payrollNumber", "startDate", "agreementText" }
Fields that can't be parsed are left as ''.
"""

import sys
import json
import re

import xlrd
import report_core  # noqa: F401 — applies the compdoc monkey-patch on import


def parse_header(sheet):
    row0 = str(sheet.cell_value(0, 0) or '')
    row2 = str(sheet.cell_value(2, 0) or '')
    row3 = str(sheet.cell_value(3, 0) or '')

    company = re.sub(r'\s*-\s*$', '', row0).strip()

    employee_name = employee_code = card_number = payroll_number = ''
    m2 = re.match(
        r'שם עובד\s*:\s*(.+?)\s+קוד עובד:(\S+)\s+מספר כרטיס:(\S+)\s+מס\. בתוכנת שכר:(\S+)',
        row2,
    )
    if m2:
        employee_name, employee_code, card_number, payroll_number = m2.groups()

    start_date = agreement_text = ''
    m3 = re.match(r'התחלה:(\S+)\s+הסכם עבודה:(.+)$', row3)
    if m3:
        start_date, agreement_text = m3.groups()

    return {
        'companyName': company,
        'employeeName': employee_name,
        'employeeCode': employee_code,
        'cardNumber': card_number,
        'payrollNumber': payroll_number,
        'startDate': start_date,
        'agreementText': agreement_text,
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({'error': 'Usage: python parse_header.py <input_xls_path>'}))
        sys.exit(1)

    try:
        rb = xlrd.open_workbook(sys.argv[1], formatting_info=True, ignore_workbook_corruption=True)
        sheet = rb.sheet_by_index(0)
        result = parse_header(sheet)
    except Exception as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)

    # ensure_ascii (default) keeps stdout pure-ASCII (\uXXXX escapes) so this
    # prints safely regardless of the invoking process's console encoding.
    print(json.dumps(result))


if __name__ == "__main__":
    main()
