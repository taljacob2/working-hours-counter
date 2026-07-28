"""
parse_header.py — CLI wrapper around report_core.parse_header(). Extracts
employee/company metadata from an uploaded company .xls's title rows,
so Settings can be pre-filled instead of retyped. Read-only: never writes
anything.

Usage:
    python parse_header.py <input_xls_path>

Prints a single JSON object to stdout:
    { "companyName", "employeeName", "employeeCode", "cardNumber",
      "payrollNumber", "startDate", "agreementText" }
Fields that can't be parsed are left as ''.
"""

import sys
import json

import xlrd
import report_core as core


def main():
    if len(sys.argv) < 2:
        print(json.dumps({'error': 'Usage: python parse_header.py <input_xls_path>'}))
        sys.exit(1)

    try:
        rb = xlrd.open_workbook(sys.argv[1], formatting_info=True, ignore_workbook_corruption=True)
        sheet = rb.sheet_by_index(0)
        result = core.parse_header(sheet)
    except Exception as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)

    # ensure_ascii (default) keeps stdout pure-ASCII (\uXXXX escapes) so this
    # prints safely regardless of the invoking process's console encoding.
    print(json.dumps(result))


if __name__ == "__main__":
    main()
