"""
report_core.py — shared business logic for producing a JBClock-style monthly
hours .xls, used by both merge_hours.py (merges app logs into an uploaded
company file) and generate_hours.py (builds the same kind of file from
scratch, with no upload required). Keeping this logic in one place means the
two paths can't silently drift apart — the vacation/slot-filling/overtime-
split rules here have already needed several bugfixes, and duplicating them
would risk fixing one copy and not the other.
"""

import xlrd
import xlrd.compdoc
import xlwt
import json
import os
import re
import calendar
from dataclasses import dataclass, field
from datetime import date


# ── Cell colour constants (xlwt colour_index from the standard palette) ──────
# Defaults for JBClock-style sheets; overridden per workbook by detect_colours()
# on the upload path. The generate path (no source file to detect from) always
# uses these directly.
COLOUR_DEFAULT  = 8   # Black       — regular office / data cells
COLOUR_POSITIVE = 17  # Dark Green  — surplus / overtime
COLOUR_NEGATIVE = 10  # Red         — deficit
COLOUR_VACATION = 12  # Blue        — vacation (חופש)
COLOUR_HOME     = 49  # Teal/Cyan   — optional colour for inserted home intervals
COLOUR_OFFICE_GAP = 46  # Purple (renders per the uploaded workbook's own custom
                        # palette) — office hours backfilled from the app, not yet
                        # confirmed by the company's own attendance system

HEADER_ROW = 5
FIRST_DAY_ROW = 6
HEADER_FILL_FG = 31
SEPARATOR_FILL_FG = 24
BORDER_COLOUR = 22
FONT_NAME = 'Tahoma'
FONT_HEIGHT = 165  # 8.25pt, in 1/20-pt units

HEBREW_WEEKDAY_LETTERS = ['א', 'ב', 'ג', 'ד', 'ה', 'ו', 'ש']  # index 0=Sunday..6=Saturday

# Bottom summary block row offsets, relative to the total row — verified
# against a real exported file (where total_row=41): row 45 is offset+4, etc.
SUMMARY_OFFSETS = {
    'subheader': 3,
    'row_100_paid': 4,
    'row_125': 5,
    'row_150': 6,
    'row_200': 7,
    'row_sum_ot': 11,
    'row_deficit': 12,
    'row_surplus': 13,
    'row_additions': 14,
    'row_signature': 15,
    'row_footer': 17,
}

# Merged-cell column zones for the bottom summary grid (xlwt inclusive coords),
# verified against the real file's merged_cells ranges.
SUBHEADER_MERGE_ZONES  = [(1, 3), (4, 6), (7, 8), (9, 10), (11, 12), (13, 15)]
DATA_ROW_MERGE_ZONES   = [(1, 2), (4, 5), (7, 8), (9, 10), (11, 12), (13, 14)]
LABEL_ONLY_MERGE_ZONES = [(4, 5), (7, 8), (9, 10), (11, 12), (13, 14)]


def font_colour_at(rb, sheet, row, col):
    """Return the font colour_index for a cell, or COLOUR_DEFAULT on failure."""
    try:
        xf_idx = sheet.cell_xf_index(row, col)
        xf = rb.xf_list[xf_idx]
        return rb.font_list[xf.font_index].colour_index
    except Exception:
        return COLOUR_DEFAULT


def detect_colours(rb, sheet):
    """Learn red/green/blue indices from already-formatted cells in the template."""
    positive = COLOUR_POSITIVE
    negative = COLOUR_NEGATIVE
    vacation = COLOUR_VACATION

    for r in range(6, sheet.nrows):
        if sheet.cell_value(r, 2) == 'חופש':
            ci = font_colour_at(rb, sheet, r, 2)
            if ci not in (COLOUR_DEFAULT, 0):
                vacation = ci

        val = sheet.cell_value(r, 14)
        if isinstance(val, str):
            s = val.strip()
            ci = font_colour_at(rb, sheet, r, 14)
            if ci not in (COLOUR_DEFAULT, 0):
                if s.startswith('+'):
                    positive = ci
                elif s.startswith('-'):
                    negative = ci

    for r in range(41, min(sheet.nrows, 56)):
        for c in (6, 14):
            val = sheet.cell_value(r, c)
            if val in ('', None):
                continue
            s = str(val).strip()
            ci = font_colour_at(rb, sheet, r, c)
            if ci in (COLOUR_DEFAULT, 0):
                continue
            if s.startswith('+'):
                positive = ci
            elif s.startswith('-'):
                negative = ci

    return positive, negative, vacation


def detect_hour_format(rb, sheet):
    """Find the elapsed-hours number format (e.g. 'h:mm') this template uses for
    worked-hour cells (entry/exit times, daily 100%/125%/150% columns). The format
    is only ever applied by the source software to cells that actually hold a
    value — a day that has never had e.g. 125% overtime keeps its cell blank with
    a bare 'General' format — so we scan for any populated cell in the known
    hour columns rather than trusting a single row/col.
    """
    for r in range(6, min(sheet.nrows, 41)):
        for c in (9, 2, 3, 13, 10, 11):
            try:
                xf_idx = sheet.cell_xf_index(r, c)
                xf = rb.xf_list[xf_idx]
                fmt = rb.format_map.get(xf.format_key)
                if fmt and fmt.format_str and fmt.format_str != 'General':
                    return fmt.format_str
            except Exception:
                continue
    return 'h:mm'


def to_elapsed_hour_format(fmt_str):
    """Convert a plain hour format like 'h:mm' to its non-wrapping elapsed form
    '[h]:mm'. A plain (unbracketed) hour token wraps at 24h in Excel — a monthly
    total of e.g. 42:27 would silently render as '18:27', dropping a full day.
    Monthly aggregate cells (total 125%/150%/200% overtime, etc.) can genuinely
    exceed 24 hours, so they need the bracketed elapsed form; per-day cells never
    do, so they keep the template's original format as-is.
    """
    if not fmt_str or fmt_str.strip().startswith('['):
        return fmt_str or '[h]:mm'
    m = re.match(r'^(h+)', fmt_str, re.IGNORECASE)
    if not m:
        return '[h]:mm'
    return f'[{m.group(1)}]{fmt_str[m.end():]}'


def style_with_number_format(base_style, num_format_str):
    """Return a shallow copy of base_style with only the number format changed."""
    new_style = xlwt.XFStyle()
    new_style.font          = base_style.font
    new_style.pattern       = base_style.pattern
    new_style.borders       = base_style.borders
    new_style.alignment     = base_style.alignment
    new_style.num_format_str = num_format_str
    return new_style


def style_with_colour(base_style, colour_index):
    """Return a shallow copy of base_style with only the font colour changed."""
    new_style = xlwt.XFStyle()
    f = xlwt.Font()
    f.name          = base_style.font.name
    f.height        = base_style.font.height
    f.bold          = base_style.font.bold
    f.italic        = base_style.font.italic
    f.underline     = base_style.font.underline
    f.colour_index  = colour_index
    new_style.font          = f
    new_style.pattern       = base_style.pattern
    new_style.borders       = base_style.borders
    new_style.alignment     = base_style.alignment
    new_style.num_format_str = base_style.num_format_str
    return new_style


def make_style_from_xf(rb, xf_index):
    """Reconstruct an xlwt XFStyle from an xlrd XF-format index.
    This preserves the original font, colour, background, borders and number format.
    """
    xf    = rb.xf_list[xf_index]
    font  = rb.font_list[xf.font_index]
    bg    = xf.background
    bdr   = xf.border
    align = xf.alignment

    style = xlwt.XFStyle()

    num_fmt = rb.format_map.get(xf.format_key)
    style.num_format_str = num_fmt.format_str if num_fmt else 'General'

    f = xlwt.Font()
    f.name          = font.name
    f.height        = font.height       # in 1/20 pt units
    f.bold          = font.bold
    f.colour_index  = font.colour_index
    f.italic        = font.italic
    f.underline     = font.underline_type != 0
    style.font = f

    p = xlwt.Pattern()
    p.pattern             = bg.fill_pattern
    p.pattern_fore_colour = bg.pattern_colour_index
    p.pattern_back_colour = bg.background_colour_index
    style.pattern = p

    b = xlwt.Borders()
    b.left          = bdr.left_line_style
    b.right         = bdr.right_line_style
    b.top           = bdr.top_line_style
    b.bottom        = bdr.bottom_line_style
    b.left_colour   = bdr.left_colour_index
    b.right_colour  = bdr.right_colour_index
    b.top_colour    = bdr.top_colour_index
    b.bottom_colour = bdr.bottom_colour_index
    style.borders = b

    a = xlwt.Alignment()
    a.horz = align.hor_align
    a.vert = align.vert_align
    style.alignment = a

    return style


# Monkey-patch xlrd to ignore size limit checking issues in OLE streams
def _patched_locate_stream(self, mem, base, sat, sec_size, start_sid, expected_stream_size, qname, seen_id):
    s = start_sid
    if s < 0:
        raise xlrd.compdoc.CompDocError("_locate_stream: start_sid (%d) is -ve" % start_sid)
    p = -99
    start_pos = -9999
    end_pos = -8888
    slices = []
    tot_found = 0
    found_limit = (expected_stream_size + sec_size - 1) // sec_size
    while s >= 0:
        if self.seen[s]:
            if not self.ignore_workbook_corruption:
                raise xlrd.compdoc.CompDocError("%s corruption: seen[%d] == %d" % (qname, s, self.seen[s]))
        self.seen[s] = seen_id
        tot_found += 1
        if tot_found > found_limit:
            if not self.ignore_workbook_corruption:
                raise xlrd.compdoc.CompDocError(
                    "%s: size exceeds expected %d bytes; corrupt?" % (qname, found_limit * sec_size)
                )
        if s == p+1:
            end_pos += sec_size
        else:
            if p >= 0:
                slices.append((start_pos, end_pos))
            start_pos = base + s * sec_size
            end_pos = start_pos + sec_size
        p = s
        s = sat[s]
    if tot_found != found_limit and self.ignore_workbook_corruption:
        found_limit = tot_found
    if not self.ignore_workbook_corruption:
        assert s == xlrd.compdoc.EOCSID
        assert tot_found == found_limit
    if not slices:
        return (mem, start_pos, expected_stream_size)
    slices.append((start_pos, end_pos))
    return (b''.join(mem[start_pos:end_pos] for start_pos, end_pos in slices), 0, expected_stream_size)

xlrd.compdoc.CompDoc._locate_stream = _patched_locate_stream


def time_str_to_float(time_str):
    if not time_str or not isinstance(time_str, str):
        return 0.0
    time_str = time_str.strip()
    if time_str.startswith('*'):
        time_str = time_str[1:]
    try:
        parts = time_str.split(':')
        h = int(parts[0])
        m = int(parts[1])
        return (h + m / 60.0) / 24.0
    except:
        return 0.0


def parse_xls_time(val):
    if isinstance(val, float):
        return val
    if isinstance(val, str):
        val = val.strip()
        if not val or val in ['-', 'חופש', 'חג']:
            return None
        return time_str_to_float(val)
    return None


def float_to_time_str(frac):
    """Inverse of time_str_to_float: a fraction-of-day back to an 'HH:MM' string."""
    total_minutes = int(round(frac * 24 * 60)) % (24 * 60)
    h, m = divmod(total_minutes, 60)
    return f"{h:02d}:{m:02d}"


def is_placeholder_time(val):
    """True for a template default like '*08:00' — the standard nominal shift the
    company's sheet writes into a חופש day's slot, not a real confirmed time. It
    parses fine as a float (time_str_to_float strips the '*'), so it must be
    checked for separately wherever we decide if a slot holds real occupied data.
    """
    return isinstance(val, str) and val.strip().startswith('*')


def parse_diff_str(s):
    if not s or not isinstance(s, str):
        return 0
    s = s.strip()
    if not (s.startswith('-') or s.startswith('+')):
        return 0
    sign = -1 if s.startswith('-') else 1
    try:
        parts = s[1:].split(':')
        h = int(parts[0])
        m = int(parts[1])
        return sign * (h * 60 + m)
    except:
        return 0


def fmt_minutes(mins):
    h = abs(mins) // 60
    m = abs(mins) % 60
    return f"{h:02d}:{m:02d}"


def is_off_day(day_name):
    return day_name in ['ו', 'ש']


def parse_header(sheet):
    """Extract employee/company metadata from a company .xls's title rows
    (0-3), so Settings can be pre-filled instead of retyped. Read-only —
    never writes anything. Fields that can't be parsed are left as ''."""
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


def load_logs_by_date(path):
    logs_by_date = {}
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            logs = json.load(f)
        for log in logs:
            log_date = log.get("date")
            if log_date:
                logs_by_date.setdefault(log_date, []).append(log)
    return logs_by_date


# ── Calendar-driven row layout (generate path; also documents the shape the
#    upload path's day-row scan discovers dynamically at runtime) ────────────

def sun_first_weekday(d):
    """0=Sunday..6=Saturday, matching the template's week-start convention."""
    return (d.weekday() + 1) % 7


@dataclass
class RowLayout:
    year: int
    month: int
    day_rows: dict         # datetime.date -> row index
    separator_rows: list   # list[int]
    total_row: int
    rows: dict             # SUMMARY_OFFSETS name -> absolute row index
    last_row: int


def compute_row_layout(year, month):
    """Sunday-first calendar weeks, a '------------' separator row between
    (never before the first or after the last) week-group, day rows starting
    at FIRST_DAY_ROW. Verified to reproduce total_row=41 for July 2026 against
    the real sample file (week sizes [4,7,7,7,6])."""
    days_in_month = calendar.monthrange(year, month)[1]
    all_days = [date(year, month, d) for d in range(1, days_in_month + 1)]

    weeks = []
    current = []
    for d in all_days:
        if current and sun_first_weekday(d) == 0:
            weeks.append(current)
            current = []
        current.append(d)
    if current:
        weeks.append(current)

    r = FIRST_DAY_ROW
    day_rows = {}
    separator_rows = []
    for i, week in enumerate(weeks):
        if i > 0:
            separator_rows.append(r)
            r += 1
        for d in week:
            day_rows[d] = r
            r += 1

    total_row = r
    rows = {name: total_row + off for name, off in SUMMARY_OFFSETS.items()}
    last_row = total_row + 17
    return RowLayout(year, month, day_rows, separator_rows, total_row, rows, last_row)


# ── Style palette (generate path only — the upload path derives styles from
#    the uploaded file's own cells via make_style_from_xf) ────────────────────

@dataclass
class StyleSet:
    default: object
    header_fill: object
    header_fill_pct: object
    hour: object
    monthly_hour: object
    positive: object
    negative: object
    separator: object
    vacation: object
    monthly_total_fill_hour: object
    monthly_total_fill_right: object
    blank_spacer: object


def _borders():
    b = xlwt.Borders()
    b.left = b.right = b.top = b.bottom = 1  # thin
    b.left_colour = b.right_colour = b.top_colour = b.bottom_colour = BORDER_COLOUR
    return b


def _font(colour_index=COLOUR_DEFAULT):
    f = xlwt.Font()
    f.name = FONT_NAME
    f.height = FONT_HEIGHT
    f.colour_index = colour_index
    return f


def _pattern(fg=None):
    p = xlwt.Pattern()
    if fg is not None:
        p.pattern = 1
        p.pattern_fore_colour = fg
        p.pattern_back_colour = 65
    else:
        p.pattern = 0
        p.pattern_fore_colour = 64
        p.pattern_back_colour = 65
    return p


def _base_style(colour_index=COLOUR_DEFAULT, fg=None, num_format_str='General', horz=2):
    st = xlwt.XFStyle()
    st.font = _font(colour_index)
    st.pattern = _pattern(fg)
    st.borders = _borders()
    a = xlwt.Alignment()
    a.horz = horz
    a.vert = 0
    st.alignment = a
    st.num_format_str = num_format_str
    return st


def build_style_set(hour_fmt='h:mm', monthly_hour_fmt='[h]:mm'):
    return StyleSet(
        default=_base_style(),
        header_fill=_base_style(fg=HEADER_FILL_FG),
        header_fill_pct=_base_style(fg=HEADER_FILL_FG, num_format_str='0%'),
        hour=_base_style(num_format_str=hour_fmt),
        monthly_hour=_base_style(num_format_str=monthly_hour_fmt),
        positive=_base_style(colour_index=COLOUR_POSITIVE),
        negative=_base_style(colour_index=COLOUR_NEGATIVE),
        separator=_base_style(fg=SEPARATOR_FILL_FG),
        vacation=_base_style(colour_index=COLOUR_VACATION),
        monthly_total_fill_hour=_base_style(fg=HEADER_FILL_FG, num_format_str=monthly_hour_fmt),
        monthly_total_fill_right=_base_style(fg=HEADER_FILL_FG, horz=3),
        blank_spacer=_base_style(horz=1),
    )


# ── Backend abstraction: lets process_day()/write_summary_rows() run
#    identically whether writing into a copy of an uploaded file or a
#    freshly-built workbook ────────────────────────────────────────────────

class SheetBackend:
    def existing_cell(self, r, col):
        raise NotImplementedError

    def style(self, r, col=1):
        raise NotImplementedError

    def hour_style(self, r, col):
        raise NotImplementedError

    def monthly_hour_style(self, r, col):
        raise NotImplementedError

    def has_row(self, r):
        raise NotImplementedError

    def write(self, r, col, value, style):
        raise NotImplementedError


class UploadBackend(SheetBackend):
    """Wraps reading from the uploaded file's own cells/styles, exactly as
    merge_hours.py did before this refactor."""

    def __init__(self, rb, sheet_read, sheet_write, hour_fmt, monthly_hour_fmt):
        self.rb = rb
        self.sheet_read = sheet_read
        self.sheet_write = sheet_write
        self.hour_fmt = hour_fmt
        self.monthly_hour_fmt = monthly_hour_fmt
        self._style_cache = {}

    def existing_cell(self, r, col):
        return self.sheet_read.cell_value(r, col)

    def style(self, r, col=1):
        key = (r, col)
        if key not in self._style_cache:
            try:
                xf_idx = self.sheet_read.cell_xf_index(r, col)
            except Exception:
                xf_idx = self.sheet_read.cell_xf_index(r, 0)
            self._style_cache[key] = make_style_from_xf(self.rb, xf_idx)
        return self._style_cache[key]

    def hour_style(self, r, col):
        return style_with_number_format(self.style(r, col), self.hour_fmt)

    def monthly_hour_style(self, r, col):
        return style_with_number_format(self.style(r, col), self.monthly_hour_fmt)

    def has_row(self, r):
        return r < self.sheet_read.nrows

    def write(self, r, col, value, style):
        self.sheet_write.write(r, col, value, style)


class GeneratedBackend(SheetBackend):
    """No existing data — style choice only depends on whether a cell sits in
    the (header-filled) total row or an ordinary row."""

    def __init__(self, sheet_write, styles, total_row):
        self.sheet_write = sheet_write
        self.styles = styles
        self.total_row = total_row

    def existing_cell(self, r, col):
        return ''

    def style(self, r, col=1):
        if r == self.total_row:
            if col in (14, 15):
                return self.styles.monthly_total_fill_right
            return self.styles.header_fill
        return self.styles.default

    def hour_style(self, r, col):
        return self.styles.hour

    def monthly_hour_style(self, r, col):
        if r == self.total_row and col in (10, 11):
            return self.styles.monthly_total_fill_hour
        return self.styles.monthly_hour

    def has_row(self, r):
        return True

    def write(self, r, col, value, style):
        self.sheet_write.write(r, col, value, style)


@dataclass
class EmployeeMeta:
    company_name: str = ''
    employee_name: str = ''
    employee_code: str = ''
    card_number: str = ''
    payroll_number: str = ''
    start_date: str = ''
    agreement_text: str = ''


# ── Per-day business logic (verbatim port of merge_hours.py's former loop
#    body) ──────────────────────────────────────────────────────────────────

@dataclass
class DayResult:
    is_vacation: bool
    is_worked: bool
    is_standard_weekday: bool
    regular_f: object
    ot125_f: object
    ot150_f: object
    ot200_f: object
    total_f: object
    deficit_minutes_delta: int = 0
    surplus_minutes_delta: int = 0


def process_day(backend, r, date_str, day_name, day_overrides, day_overrides_provided,
                 logs_by_date, color_home_hours, fill_missing_office,
                 colour_pos, colour_neg, colour_vac, target_hours=9.0):
    xls_is_vac = (backend.existing_cell(r, 2) == 'חופש')
    if day_overrides_provided:
        is_vac = day_overrides.get(date_str) == 'off'
    else:
        is_vac = xls_is_vac

    if is_vac:
        # The app's override is authoritative for a חופש day — overwrite the
        # entire row to match the company template's own vacation-day pattern,
        # rather than leaving behind whatever this row previously held.
        vac_day_f = 9.0 / 24.0
        vac_st = style_with_colour(backend.style(r, 2), colour_vac)
        backend.write(r, 2, 'חופש',  vac_st)
        backend.write(r, 3, '-',      backend.style(r, 3))
        backend.write(r, 4, '*08:00', backend.style(r, 4))
        backend.write(r, 5, '*17:00', backend.style(r, 5))
        backend.write(r, 6, '-',      backend.style(r, 6))
        backend.write(r, 7, '-',      backend.style(r, 7))
        backend.write(r, 8, '-',      backend.style(r, 8))
        backend.write(r,  9, vac_day_f, backend.hour_style(r, 9))
        backend.write(r, 10, '',        backend.style(r, 10))
        backend.write(r, 11, '',        backend.style(r, 11))
        backend.write(r, 12, '',        backend.style(r, 12))
        backend.write(r, 13, vac_day_f, backend.hour_style(r, 13))
        backend.write(r, 14, '',        backend.style(r, 14))

        return DayResult(
            is_vacation=True, is_worked=True,
            is_standard_weekday=not is_off_day(day_name),
            regular_f=vac_day_f, ot125_f='', ot150_f='', ot200_f='', total_f=vac_day_f,
        )

    # Not a vacation day per the app — erase a stale 'חופש' marking the company
    # sheet had, so column 2 is free to receive normal entry-time processing below.
    if xls_is_vac:
        backend.write(r, 2, '', backend.style(r, 2))

    # Detect which of the 3 entry/exit slots are genuinely occupied by keying
    # on slot index rather than assuming they're filled compactly from slot 0.
    occupied = {}  # slot index (0, 1, 2) -> (ent, ex) float tuple
    for p in range(3):
        ent_val = backend.existing_cell(r, 2 + 2 * p)
        ex_val = backend.existing_cell(r, 3 + 2 * p)
        if is_placeholder_time(ent_val) or is_placeholder_time(ex_val):
            # A חופש day's nominal default shift, now stale — clear it.
            backend.write(r, 2 + 2 * p, '', backend.style(r, 2 + 2 * p))
            backend.write(r, 3 + 2 * p, '', backend.style(r, 3 + 2 * p))
            continue
        ent = parse_xls_time(ent_val)
        ex = parse_xls_time(ex_val)
        if ent is not None and ex is not None:
            occupied[p] = (ent, ex)

    free_slots = [p for p in range(3) if p not in occupied]
    company_had_any_data = len(occupied) > 0

    day_logs_all = logs_by_date.get(date_str, [])
    day_home_logs = sorted(
        (log for log in day_logs_all if log.get("platform") == "home" and log.get("start") and log.get("end")),
        key=lambda x: x["start"]
    )
    day_office_logs = sorted(
        (log for log in day_logs_all if log.get("platform") == "office" and log.get("start") and log.get("end")),
        key=lambda x: x["start"]
    )

    candidates = [dict(log, _source="home") for log in day_home_logs]
    if fill_missing_office and not company_had_any_data:
        candidates += [dict(log, _source="office_backfill") for log in day_office_logs]
    candidates.sort(key=lambda x: x["start"])

    self_filled_source = {}  # slot index -> "home" | "office_backfill"
    placed_count = min(len(free_slots), len(candidates))

    def write_slot(p, start_str, end_str, source):
        col_ent = 2 + 2 * p
        col_ex = 3 + 2 * p
        ent_style = backend.style(r, col_ent)
        ex_style = backend.style(r, col_ex)
        if source == "office_backfill":
            ent_style = style_with_colour(ent_style, COLOUR_OFFICE_GAP)
            ex_style = style_with_colour(ex_style, COLOUR_OFFICE_GAP)
        elif color_home_hours:
            ent_style = style_with_colour(ent_style, COLOUR_HOME)
            ex_style = style_with_colour(ex_style, COLOUR_HOME)
        backend.write(r, col_ent, start_str, ent_style)
        backend.write(r, col_ex,  end_str,   ex_style)
        occupied[p] = (time_str_to_float(start_str), time_str_to_float(end_str))
        self_filled_source[p] = source

    for i in range(placed_count):
        p = free_slots[i]
        log = candidates[i]
        write_slot(p, log["start"], log["end"], log["_source"])

    # Overflow: fold any extra sessions into the boundary of the nearest slot
    # we ourselves just wrote, never a slot holding the company's own data.
    for log in candidates[placed_count:]:
        ov_start = time_str_to_float(log["start"])
        ov_end   = time_str_to_float(log["end"])
        ov_dur   = ov_end - ov_start
        if ov_dur <= 0 or not self_filled_source:
            continue

        attach_candidates = []  # (gap, slot, extend_forward)
        for p in self_filled_source:
            s_ent, s_ex = occupied[p]
            if ov_start >= s_ex:
                attach_candidates.append((ov_start - s_ex, p, True))
            if ov_end <= s_ent:
                attach_candidates.append((s_ent - ov_end, p, False))
        if not attach_candidates:
            continue

        attach_candidates.sort(key=lambda c: c[0])
        _, best_p, extend_forward = attach_candidates[0]
        s_ent, s_ex = occupied[best_p]
        new_ent, new_ex = (s_ent, s_ex + ov_dur) if extend_forward else (s_ent - ov_dur, s_ex)
        write_slot(best_p, float_to_time_str(new_ent), float_to_time_str(new_ex), self_filled_source[best_p])

    xls_intervals = list(occupied.values())
    net_total = sum(ex - ent for ent, ex in xls_intervals)
    is_standard_weekday = not is_off_day(day_name)

    if net_total <= 0:
        # Deficit day or weekend with no work
        backend.write(r,  9, '', backend.style(r, 9))
        backend.write(r, 10, '', backend.style(r, 10))
        backend.write(r, 11, '', backend.style(r, 11))
        backend.write(r, 12, '', backend.style(r, 12))
        backend.write(r, 13, '', backend.style(r, 13))

        deficit_delta = 0
        if not is_off_day(day_name):
            neg_st = style_with_colour(backend.style(r, 14), colour_neg)
            backend.write(r, 14, '-09:00', neg_st)
            deficit_delta = 9 * 60
        else:
            backend.write(r, 14, '', backend.style(r, 14))

        return DayResult(
            is_vacation=False, is_worked=False, is_standard_weekday=is_standard_weekday,
            regular_f='', ot125_f='', ot150_f='', ot200_f='', total_f='',
            deficit_minutes_delta=deficit_delta,
        )

    # Worked day!
    total_hours = net_total * 24.0

    if is_off_day(day_name):
        # Weekend work: all hours are overtime!
        backend.write(r,  9, '',        backend.style(r, 9))
        backend.write(r, 10, '',        backend.style(r, 10))
        backend.write(r, 11, net_total, backend.hour_style(r, 11))
        backend.write(r, 12, '',        backend.style(r, 12))
        backend.write(r, 13, net_total, backend.hour_style(r, 13))

        mins = int(round(total_hours * 60))
        pos_st = style_with_colour(backend.style(r, 14), colour_pos)
        backend.write(r, 14, f"+{fmt_minutes(mins)}", pos_st)

        return DayResult(
            is_vacation=False, is_worked=True, is_standard_weekday=is_standard_weekday,
            regular_f='', ot125_f='', ot150_f=net_total, ot200_f='', total_f=net_total,
            surplus_minutes_delta=mins,
        )

    # Regular weekday work
    regular_hours = min(total_hours, target_hours)
    ot_hours = max(0.0, total_hours - target_hours)

    ot_125 = min(ot_hours, 2.0)
    ot_150 = max(0.0, ot_hours - 2.0)

    reg_f    = regular_hours / 24.0
    ot_125_f = ot_125 / 24.0 if ot_125 > 0 else ''
    ot_150_f = ot_150 / 24.0 if ot_150 > 0 else ''

    backend.write(r,  9, reg_f,    backend.hour_style(r, 9))
    backend.write(r, 10, ot_125_f, backend.hour_style(r, 10))
    backend.write(r, 11, ot_150_f, backend.hour_style(r, 11))
    backend.write(r, 12, '',        backend.style(r, 12))
    backend.write(r, 13, net_total, backend.hour_style(r, 13))

    diff_hours = total_hours - target_hours
    diff_mins  = int(round(diff_hours * 60))
    deficit_delta = 0
    surplus_delta = 0
    if diff_mins > 0:
        pos_st = style_with_colour(backend.style(r, 14), colour_pos)
        backend.write(r, 14, f"+{fmt_minutes(diff_mins)}", pos_st)
        surplus_delta = diff_mins
    elif diff_mins < 0:
        neg_st = style_with_colour(backend.style(r, 14), colour_neg)
        backend.write(r, 14, f"-{fmt_minutes(abs(diff_mins))}", neg_st)
        deficit_delta = abs(diff_mins)
    else:
        backend.write(r, 14, '+00:00', backend.style(r, 14))

    return DayResult(
        is_vacation=False, is_worked=True, is_standard_weekday=is_standard_weekday,
        regular_f=reg_f, ot125_f=ot_125_f, ot150_f=ot_150_f, ot200_f='', total_f=net_total,
        deficit_minutes_delta=deficit_delta, surplus_minutes_delta=surplus_delta,
    )


@dataclass
class Aggregates:
    daily_regular_vals: list = field(default_factory=list)
    daily_125_vals: list = field(default_factory=list)
    daily_150_vals: list = field(default_factory=list)
    daily_200_vals: list = field(default_factory=list)
    daily_total_vals: list = field(default_factory=list)
    total_deficit_minutes: int = 0
    total_surplus_minutes: int = 0
    vacation_days_count: int = 0
    days_worked_count: int = 0
    standard_weekdays_count: int = 0

    def accumulate(self, result):
        self.daily_regular_vals.append(result.regular_f)
        self.daily_125_vals.append(result.ot125_f)
        self.daily_150_vals.append(result.ot150_f)
        self.daily_200_vals.append(result.ot200_f)
        self.daily_total_vals.append(result.total_f)
        self.total_deficit_minutes += result.deficit_minutes_delta
        self.total_surplus_minutes += result.surplus_minutes_delta
        if result.is_vacation:
            self.vacation_days_count += 1
        if result.is_worked:
            self.days_worked_count += 1
        if result.is_standard_weekday:
            self.standard_weekdays_count += 1


def write_summary_rows(backend, total_row, rows, agg, colour_pos, colour_neg):
    """Verbatim port of merge_hours.py's former totals-writing block,
    parameterized by row position instead of literal constants. Writes only
    computed values — both paths' skeletons already contain the labels."""
    sum_regular_f = sum(v for v in agg.daily_regular_vals if isinstance(v, float))
    sum_125_f = sum(v for v in agg.daily_125_vals if isinstance(v, float))
    sum_150_f = sum(v for v in agg.daily_150_vals if isinstance(v, float))
    sum_200_f = sum(v for v in agg.daily_200_vals if isinstance(v, float))
    sum_total_f = sum(v for v in agg.daily_total_vals if isinstance(v, float))

    sum_regular_mins = int(round(sum_regular_f * 24 * 60))
    sum_total_mins = int(round(sum_total_f * 24 * 60))

    reg_sum_str = f"{sum_regular_mins // 60}:{sum_regular_mins % 60:02d}"
    tot_sum_str = f"{sum_total_mins // 60}:{sum_total_mins % 60:02d}"

    cum_diff_str = f"-{fmt_minutes(agg.total_deficit_minutes)}/+{fmt_minutes(agg.total_surplus_minutes)}"

    backend.write(total_row,  9, reg_sum_str,                        backend.style(total_row, 9))
    backend.write(total_row, 10, sum_125_f if sum_125_f > 0 else '', backend.monthly_hour_style(total_row, 10))
    backend.write(total_row, 11, sum_150_f if sum_150_f > 0 else '', backend.monthly_hour_style(total_row, 11))
    backend.write(total_row, 12, sum_200_f if sum_200_f > 0 else '', backend.monthly_hour_style(total_row, 12))
    backend.write(total_row, 13, tot_sum_str,                        backend.style(total_row, 13))
    backend.write(total_row, 14, cum_diff_str,                       backend.style(total_row, 14))

    r45 = rows['row_100_paid']
    backend.write(r45,  6, reg_sum_str,                 backend.style(r45,  6))
    backend.write(r45,  9, tot_sum_str,                 backend.style(r45,  9))
    backend.write(r45, 11, agg.days_worked_count,       backend.style(r45, 11))
    backend.write(r45, 15, agg.vacation_days_count,     backend.style(r45, 15))

    r46 = rows['row_125']
    backend.write(r46, 6, sum_125_f if sum_125_f > 0 else 0.0, backend.monthly_hour_style(r46, 6))

    r47 = rows['row_150']
    target_hours_mins = agg.standard_weekdays_count * 9 * 60
    target_hours_str  = f"{target_hours_mins // 60}:{target_hours_mins % 60:02d}"
    backend.write(r47,  6, sum_150_f if sum_150_f > 0 else 0.0, backend.monthly_hour_style(r47,  6))
    backend.write(r47,  9, target_hours_str,                     backend.style(r47,  9))
    backend.write(r47, 11, agg.standard_weekdays_count,          backend.style(r47, 11))

    r48 = rows['row_200']
    backend.write(r48, 6, sum_200_f if sum_200_f > 0 else 0.0, backend.monthly_hour_style(r48, 6))

    r52 = rows['row_sum_ot']
    sum_ot_f = sum_125_f + sum_150_f + sum_200_f
    backend.write(r52, 6, sum_ot_f if sum_ot_f > 0 else 0.0, backend.monthly_hour_style(r52, 6))

    r53 = rows['row_deficit']
    backend.write(r53, 6, f"-{fmt_minutes(agg.total_deficit_minutes)}",
                  style_with_colour(backend.style(r53, 6), colour_neg))

    r54 = rows['row_surplus']
    if backend.has_row(r54):
        backend.write(r54, 6, f"+{fmt_minutes(agg.total_surplus_minutes)}",
                      style_with_colour(backend.style(r54, 6), colour_pos))


# ── Skeleton builder (generate path only) ────────────────────────────────────

def write_separator_row(sheet, r, styles):
    for c in range(16):
        sheet.write(r, c, '' if c == 13 else '------------', styles.separator)


def _write_zone_row(sheet, r, zones, style, texts):
    for c0, c1 in zones:
        sheet.write_merge(r, r, c0, c1, texts.get(c0, ''), style)


def build_skeleton(sheet, layout, meta, styles, print_date_str):
    """Writes everything the upload path gets for free from the uploaded
    file: title rows, header row, day-row date labels, separator rows,
    column widths/row heights, and the bottom summary block's labels and
    merged-cell grid. process_day()/write_summary_rows() fill in the values
    afterward (the sheet is created with cell_overwrite_ok=True)."""
    # The real template's sheet is right-to-left (Hebrew) — column 0 renders
    # on the right, not the left. This is a sheet-level flag, not a per-cell
    # alignment; the template's own cells all use plain 'General'/center
    # alignment and rely on this flag for the Hebrew reading direction.
    sheet.cols_right_to_left = True

    widths = {13: 1719, 15: 2670}
    for c in range(16):
        sheet.col(c).width = widths.get(c, 2231)

    for r in range(0, layout.last_row + 1):
        row = sheet.row(r)
        row.height = 300
        row.height_mismatch = True

    yy = layout.year % 100
    sheet.write_merge(0, 0, 0, 15, f"{meta.company_name} - ", styles.default)
    sheet.write_merge(1, 1, 0, 15,
        f"{meta.company_name} -  - דוח שעות חודשי {layout.month:02d}/{yy:02d}", styles.default)
    sheet.write_merge(2, 2, 0, 15,
        f"שם עובד : {meta.employee_name} קוד עובד:{meta.employee_code} "
        f"מספר כרטיס:{meta.card_number} מס. בתוכנת שכר:{meta.payroll_number}", styles.default)
    sheet.write_merge(3, 3, 0, 15,
        f"התחלה:{meta.start_date} הסכם עבודה:{meta.agreement_text}", styles.default)
    sheet.write_merge(4, 4, 0, 15, '', styles.default)

    headers = ['שגיאות', 'יום', 'כניסה', 'יציאה', 'כניסה', 'יציאה', 'כניסה', 'יציאה', 'הפסקה', 'רגילות']
    for c, text in enumerate(headers):
        sheet.write(HEADER_ROW, c, text, styles.header_fill)
    sheet.write(HEADER_ROW, 10, 1.25, styles.header_fill_pct)
    sheet.write(HEADER_ROW, 11, 1.5,  styles.header_fill_pct)
    sheet.write(HEADER_ROW, 12, 2.0,  styles.header_fill_pct)
    sheet.write(HEADER_ROW, 13, 'סה"כ', styles.header_fill)
    sheet.write(HEADER_ROW, 14, '+/-',  styles.header_fill)
    sheet.write(HEADER_ROW, 15, 'הערות', styles.header_fill)

    for d, r in layout.day_rows.items():
        day_name = HEBREW_WEEKDAY_LETTERS[sun_first_weekday(d)]
        sheet.write(r, 0, '', styles.default)
        sheet.write(r, 1, f"{d.day:02d}/{d.month:02d} {day_name}", styles.default)

    for r in layout.separator_rows:
        write_separator_row(sheet, r, styles)

    # Total row: header-filled across the whole row; process_day never writes
    # here, write_summary_rows fills cols 9-14 in afterward.
    for c in range(16):
        sheet.write(layout.total_row, c, '', styles.header_fill)
    sheet.write(layout.total_row, 7, 'סה"כ', styles.header_fill)
    sheet.write_merge(layout.total_row, layout.total_row, 14, 15, '', styles.monthly_total_fill_right)

    for r in (layout.total_row + 1, layout.total_row + 2):
        for c in range(16):
            sheet.write(r, c, '', styles.blank_spacer)

    sub_r = layout.rows['subheader']
    sheet.write(sub_r, 0, '', styles.header_fill)
    sheet.write(sub_r, 15, '', styles.header_fill)
    _write_zone_row(sheet, sub_r, SUBHEADER_MERGE_ZONES, styles.header_fill, {
        4: 'סה"כ שעות בחודש', 9: 'סה"כ שעות', 11: 'ימי עבודה', 13: 'דיווחים',
    })

    def _write_data_row(r, texts):
        sheet.write(r, 0, '', styles.default)
        sheet.write(r, 15, '', styles.default)
        _write_zone_row(sheet, r, DATA_ROW_MERGE_ZONES, styles.default, texts)

    _write_data_row(layout.rows['row_100_paid'], {4: 'שעות 100%', 7: 'משולמות', 13: 'ימי חופש'})
    _write_data_row(layout.rows['row_125'], {4: 'נוספות125%'})
    _write_data_row(layout.rows['row_150'], {4: 'נוספות150%', 7: 'תקן'})
    _write_data_row(layout.rows['row_200'], {4: 'נוספות200%'})

    for r in range(layout.rows['row_200'] + 1, layout.rows['row_sum_ot']):
        for c in range(16):
            sheet.write(r, c, '', styles.blank_spacer)

    _write_data_row(layout.rows['row_sum_ot'], {4: 'סה"כ נוספות'})
    _write_data_row(layout.rows['row_deficit'], {4: '-חוסר ל 100%'})
    _write_data_row(layout.rows['row_surplus'], {})

    r_add = layout.rows['row_additions']
    sheet.write(r_add, 0, '', styles.default)
    sheet.write(r_add, 15, '', styles.default)
    _write_zone_row(sheet, r_add, LABEL_ONLY_MERGE_ZONES, styles.default, {7: 'תוספות'})

    r_sig = layout.rows['row_signature']
    sheet.write(r_sig, 0, '', styles.default)
    sheet.write(r_sig, 15, '', styles.default)
    _write_zone_row(sheet, r_sig, LABEL_ONLY_MERGE_ZONES, styles.default, {11: 'חתימת העובד'})

    for c in range(16):
        sheet.write(layout.rows['row_signature'] + 1, c, '', styles.blank_spacer)

    r_footer = layout.rows['row_footer']
    sheet.write(r_footer, 0, '', styles.default)
    sheet.write_merge(r_footer, r_footer, 1, 2, '', styles.default)
    sheet.write_merge(r_footer, r_footer, 3, 12,
        f"הודפס בתאריך {print_date_str} JBClock         גירסה 2.55", styles.default)
    sheet.write_merge(r_footer, r_footer, 13, 15, '', styles.default)
