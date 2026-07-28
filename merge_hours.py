import xlrd
import xlrd.compdoc
import xlutils.copy
import xlwt
import json
import sys
import os
import re


# ── Cell colour constants (xlwt colour_index from the standard palette) ──────
# Defaults for JBClock-style sheets; overridden per workbook by detect_colours().
COLOUR_DEFAULT  = 8   # Black       — regular office / data cells
COLOUR_POSITIVE = 17  # Dark Green  — surplus / overtime
COLOUR_NEGATIVE = 10  # Red         — deficit
COLOUR_VACATION = 12  # Blue        — vacation (חופש)
COLOUR_HOME     = 49  # Teal/Cyan   — optional colour for inserted home intervals
COLOUR_OFFICE_GAP = 46  # Orange     — office hours backfilled from the app, not yet
                        # confirmed by the company's own attendance system


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
    # Copy font and override colour
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

    # ── Number format ───────────────────────────────
    # Without this, cells default to 'General' when rewritten — an hour-fraction
    # value like 0.375 would then render as the raw decimal "0.375" instead of
    # "9:00", since the original 'h:mm'-style format is otherwise lost.
    num_fmt = rb.format_map.get(xf.format_key)
    style.num_format_str = num_fmt.format_str if num_fmt else 'General'

    # ── Font ────────────────────────────────────────
    f = xlwt.Font()
    f.name          = font.name
    f.height        = font.height       # in 1/20 pt units
    f.bold          = font.bold
    f.colour_index  = font.colour_index
    f.italic        = font.italic
    f.underline     = font.underline_type != 0
    style.font = f

    # ── Background / pattern ────────────────────────
    p = xlwt.Pattern()
    p.pattern             = bg.fill_pattern
    p.pattern_fore_colour = bg.pattern_colour_index
    p.pattern_back_colour = bg.background_colour_index
    style.pattern = p

    # ── Borders ─────────────────────────────────────
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

    # ── Alignment ───────────────────────────────────
    a = xlwt.Alignment()
    a.horz = align.hor_align
    a.vert = align.vert_align
    style.alignment = a

    return style

# Monkey-patch xlrd to ignore size limit checking issues in OLE streams
original_locate_stream = xlrd.compdoc.CompDoc._locate_stream

def patched_locate_stream(self, mem, base, sat, sec_size, start_sid, expected_stream_size, qname, seen_id):
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

xlrd.compdoc.CompDoc._locate_stream = patched_locate_stream

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
    logs_by_date = {}
    if os.path.exists(logs_json_path):
        try:
            with open(logs_json_path, 'r', encoding='utf-8') as f:
                logs = json.load(f)
            for log in logs:
                date = log.get("date")
                if date:
                    if date not in logs_by_date:
                        logs_by_date[date] = []
                    logs_by_date[date].append(log)
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

    colour_pos, colour_neg, colour_vac = detect_colours(rb, sheet_read)
    hour_fmt = detect_hour_format(rb, sheet_read)
    monthly_hour_fmt = to_elapsed_hour_format(hour_fmt)

    # Build a per-(row, col) style cache. Most cells in a row share the same
    # formatting, but some (e.g. a 'חופש'-marked col 2) can carry their own
    # colour — so the cache key must include col, not just row.
    _style_cache = {}
    def row_style(r, col=1):
        key = (r, col)
        if key not in _style_cache:
            try:
                xf_idx = sheet_read.cell_xf_index(r, col)
            except Exception:
                xf_idx = sheet_read.cell_xf_index(r, 0)
            _style_cache[key] = make_style_from_xf(rb, xf_idx)
        return _style_cache[key]

    def hour_style(r, col):
        # Like row_style(), but forces the elapsed-hours number format — the
        # source cell may have been blank (and thus 'General') if this is the
        # first time this row/column ever holds an hour value.
        return style_with_number_format(row_style(r, col), hour_fmt)

    def monthly_hour_style(r, col):
        # Like hour_style(), but uses the non-wrapping '[h]:mm' form — a
        # monthly-aggregate cell (total 125%/150%/200% overtime, etc.) can
        # exceed 24 hours, and a plain 'h:mm' format would silently drop
        # whole days from the display.
        return style_with_number_format(row_style(r, col), monthly_hour_fmt)

    # 3. Parse month/year from Row 1
    month = 7
    year = 2026
    m_text = sheet_read.cell_value(1, 0)
    match = re.search(r'(\d{2})/(\d{2})', m_text)
    if match:
        month = int(match.group(1))
        year = 2000 + int(match.group(2))

    # 4. Process each row
    rows_to_recalc = []
    
    # Store daily values for final totals
    daily_regular_vals = []
    daily_125_vals = []
    daily_150_vals = []
    daily_200_vals = []
    daily_total_vals = []
    
    total_deficit_minutes = 0
    total_surplus_minutes = 0
    
    vacation_days_count = 0
    days_worked_count = 0
    standard_weekdays_count = 0

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

        xls_is_vac = (sheet_read.cell_value(r, 2) == 'חופש')
        # If the app supplied per-date overrides, they decide whether this day is
        # 'חופש' — otherwise fall back to whatever the company's XLS already had.
        if day_overrides_provided:
            is_vac = day_overrides.get(date_str) == 'off'
        else:
            is_vac = xls_is_vac

        if is_vac:
            vacation_days_count += 1
            days_worked_count += 1 # Vacation counts as active work/vacation day in Col 11
            # Keep original values for vacation day; (re-)write col 2 in blue to mark it
            vac_st = style_with_colour(row_style(r, 2), colour_vac)
            sheet_write.write(r, 2, 'חופש', vac_st)
            reg_val = sheet_read.cell_value(r, 9)
            daily_regular_vals.append(reg_val)
            daily_125_vals.append(sheet_read.cell_value(r, 10))
            daily_150_vals.append(sheet_read.cell_value(r, 11))
            daily_200_vals.append(sheet_read.cell_value(r, 12))
            daily_total_vals.append(sheet_read.cell_value(r, 13))

            if not is_off_day(day_name):
                standard_weekdays_count += 1
            continue

        # Not a vacation day per the app — erase a stale 'חופש' marking the company
        # sheet had, so column 2 is free to receive normal entry-time processing below.
        if xls_is_vac:
            sheet_write.write(r, 2, '', row_style(r, 2))

        # Non-vacation day: process intervals
        # Read existing Office intervals. Detect which of the 3 slots are genuinely
        # occupied by keying on slot index rather than assuming they're filled
        # compactly from slot 0 — the company's sheet can leave a gap (e.g. slot 1
        # filled, slot 0 blank), and treating "count of filled slots" as "next free
        # slot" would silently overwrite real office data sitting in a later slot.
        occupied = {}  # slot index (0, 1, 2) -> (ent, ex) float tuple
        for p in range(3):
            ent_val = sheet_read.cell_value(r, 2 + 2*p)
            ex_val = sheet_read.cell_value(r, 3 + 2*p)
            if is_placeholder_time(ent_val) or is_placeholder_time(ex_val):
                # A חופש day's nominal default shift (e.g. '*08:00'/'*17:00'). Once
                # this day isn't vacation, that placeholder is stale — clear it so
                # it doesn't sit there colliding with, or block a slot needed by,
                # the real logged data merged in below.
                sheet_write.write(r, 2 + 2*p, '', row_style(r, 2 + 2*p))
                sheet_write.write(r, 3 + 2*p, '', row_style(r, 3 + 2*p))
                continue
            ent = parse_xls_time(ent_val)
            ex = parse_xls_time(ex_val)
            if ent is not None and ex is not None:
                occupied[p] = (ent, ex)

        free_slots = [p for p in range(3) if p not in occupied]
        # Whole-day check: did the company's own file have ANY real time entry for
        # this day at all, before we touched anything? If so, we leave office
        # backfill alone entirely — even a different/partial session recorded by
        # them means we don't try to reconcile or duplicate what they already have.
        company_had_any_data = len(occupied) > 0

        # Read this day's app logs, split by platform.
        day_logs_all = logs_by_date.get(date_str, [])
        day_home_logs = sorted(
            (log for log in day_logs_all if log.get("platform") == "home" and log.get("start") and log.get("end")),
            key=lambda x: x["start"]
        )
        day_office_logs = sorted(
            (log for log in day_logs_all if log.get("platform") == "office" and log.get("start") and log.get("end")),
            key=lambda x: x["start"]
        )

        # Candidates to merge into free slots, in chronological order. Home logs
        # are always eligible. Office logs are only eligible when the company's
        # sheet has nothing at all for this day (fill_missing_office) — a
        # self-reported office session that isn't yet in the official record,
        # flagged with a distinct colour so HR notices and can confirm it.
        candidates = [dict(log, _source="home") for log in day_home_logs]
        if fill_missing_office and not company_had_any_data:
            candidates += [dict(log, _source="office_backfill") for log in day_office_logs]
        candidates.sort(key=lambda x: x["start"])

        # Fill only the genuinely-free slots, in chronological order — never the
        # company's own occupied ones. Track which slots we personally wrote (and
        # their source) so overflow below can only ever extend our own data, never
        # a slot the company already filled.
        self_filled_source = {}  # slot index -> "home" | "office_backfill"
        placed_count = min(len(free_slots), len(candidates))

        def write_slot(p, start_str, end_str, source):
            col_ent = 2 + 2 * p
            col_ex = 3 + 2 * p
            ent_style = row_style(r, col_ent)
            ex_style = row_style(r, col_ex)
            if source == "office_backfill":
                ent_style = style_with_colour(ent_style, COLOUR_OFFICE_GAP)
                ex_style = style_with_colour(ex_style, COLOUR_OFFICE_GAP)
            elif color_home_hours:
                ent_style = style_with_colour(ent_style, COLOUR_HOME)
                ex_style = style_with_colour(ex_style, COLOUR_HOME)
            sheet_write.write(r, col_ent, start_str, ent_style)
            sheet_write.write(r, col_ex,  end_str,   ex_style)
            occupied[p] = (time_str_to_float(start_str), time_str_to_float(end_str))
            self_filled_source[p] = source

        for i in range(placed_count):
            p = free_slots[i]
            log = candidates[i]
            write_slot(p, log["start"], log["end"], log["_source"])

        # Overflow: more real work intervals than the sheet's fixed 3 entry/exit
        # slots can show (e.g. several short fragmented home sessions on a fast
        # day, or a home + backfilled-office day that's already full). The sheet
        # has no room for a 4th column pair, so each overflow session's duration
        # is folded into the boundary of whichever slot we ourselves just wrote
        # that sits closest to it in time — extending that slot's displayed entry
        # or exit to actually cover the extra minutes. This keeps every minute in
        # the day's total physically present in a visible cell (nothing is added
        # to the total that isn't backed by a shown log time), and never touches
        # a slot holding the company's own pre-existing data.
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
                # Overflow session's time overlaps the span of our own slots in a
                # way with no clean chronological attachment point — skip rather
                # than fabricate an inverted or overlapping time.
                continue

            attach_candidates.sort(key=lambda c: c[0])
            _, best_p, extend_forward = attach_candidates[0]
            s_ent, s_ex = occupied[best_p]
            new_ent, new_ex = (s_ent, s_ex + ov_dur) if extend_forward else (s_ent - ov_dur, s_ex)
            write_slot(best_p, float_to_time_str(new_ent), float_to_time_str(new_ex), self_filled_source[best_p])

        xls_intervals = list(occupied.values())

        # Calculate daily totals
        net_total = sum(ex - ent for ent, ex in xls_intervals)
        
        # Update weekday count
        if not is_off_day(day_name):
            standard_weekdays_count += 1

        if net_total <= 0:
            # Deficit day or weekend with no work
            sheet_write.write(r,  9, '', row_style(r, 9))
            sheet_write.write(r, 10, '', row_style(r, 10))
            sheet_write.write(r, 11, '', row_style(r, 11))
            sheet_write.write(r, 12, '', row_style(r, 12))
            sheet_write.write(r, 13, '', row_style(r, 13))

            if not is_off_day(day_name):
                # Deficit day — write -09:00 in red
                neg_st = style_with_colour(row_style(r, 14), colour_neg)
                sheet_write.write(r, 14, '-09:00', neg_st)
                total_deficit_minutes += 9 * 60
            else:
                sheet_write.write(r, 14, '', row_style(r, 14))
            continue

        # Worked day!
        days_worked_count += 1
        total_hours = net_total * 24.0

        if is_off_day(day_name):
            # Weekend work: all hours are overtime!
            sheet_write.write(r,  9, '',        row_style(r, 9))
            sheet_write.write(r, 10, '',        row_style(r, 10))
            sheet_write.write(r, 11, net_total, hour_style(r, 11))
            sheet_write.write(r, 12, '',        row_style(r, 12))
            sheet_write.write(r, 13, net_total, hour_style(r, 13))

            daily_regular_vals.append('')
            daily_125_vals.append('')
            daily_150_vals.append(net_total)
            daily_200_vals.append('')
            daily_total_vals.append(net_total)

            mins = int(round(total_hours * 60))
            # Weekend overtime → always positive, shown in green
            pos_st = style_with_colour(row_style(r, 14), colour_pos)
            sheet_write.write(r, 14, f"+{fmt_minutes(mins)}", pos_st)
            total_surplus_minutes += mins
        else:
            # Regular weekday work
            target_hours = 9.0
            regular_hours = min(total_hours, target_hours)
            ot_hours = max(0.0, total_hours - target_hours)

            ot_125 = min(ot_hours, 2.0)
            ot_150 = max(0.0, ot_hours - 2.0)

            reg_f    = regular_hours / 24.0
            ot_125_f = ot_125 / 24.0 if ot_125 > 0 else ''
            ot_150_f = ot_150 / 24.0 if ot_150 > 0 else ''

            sheet_write.write(r,  9, reg_f,    hour_style(r, 9))
            sheet_write.write(r, 10, ot_125_f, hour_style(r, 10))
            sheet_write.write(r, 11, ot_150_f, hour_style(r, 11))
            sheet_write.write(r, 12, '',        row_style(r, 12))
            sheet_write.write(r, 13, net_total, hour_style(r, 13))

            daily_regular_vals.append(reg_f)
            daily_125_vals.append(ot_125_f)
            daily_150_vals.append(ot_150_f)
            daily_200_vals.append('')
            daily_total_vals.append(net_total)

            diff_hours = total_hours - target_hours
            diff_mins  = int(round(diff_hours * 60))
            if diff_mins > 0:
                pos_st = style_with_colour(row_style(r, 14), colour_pos)
                sheet_write.write(r, 14, f"+{fmt_minutes(diff_mins)}", pos_st)
                total_surplus_minutes += diff_mins
            elif diff_mins < 0:
                neg_st = style_with_colour(row_style(r, 14), colour_neg)
                sheet_write.write(r, 14, f"-{fmt_minutes(abs(diff_mins))}", neg_st)
                total_deficit_minutes += abs(diff_mins)
            else:
                sheet_write.write(r, 14, '+00:00', row_style(r, 14))

    # 5. Write row 41 totals
    sum_regular_f = sum(val for val in daily_regular_vals if isinstance(val, float))
    sum_125_f = sum(val for val in daily_125_vals if isinstance(val, float))
    sum_150_f = sum(val for val in daily_150_vals if isinstance(val, float))
    sum_200_f = sum(val for val in daily_200_vals if isinstance(val, float))
    sum_total_f = sum(val for val in daily_total_vals if isinstance(val, float))
    
    # Formatted sum regular and total
    sum_regular_mins = int(round(sum_regular_f * 24 * 60))
    sum_total_mins = int(round(sum_total_f * 24 * 60))
    
    reg_sum_str = f"{sum_regular_mins // 60}:{sum_regular_mins % 60:02d}"
    tot_sum_str = f"{sum_total_mins // 60}:{sum_total_mins % 60:02d}"
    
    cum_diff_str = f"-{fmt_minutes(total_deficit_minutes)}/+{fmt_minutes(total_surplus_minutes)}"

    sheet_write.write(41,  9, reg_sum_str,                        row_style(41, 9))
    sheet_write.write(41, 10, sum_125_f if sum_125_f > 0 else '', monthly_hour_style(41, 10))
    sheet_write.write(41, 11, sum_150_f if sum_150_f > 0 else '', monthly_hour_style(41, 11))
    sheet_write.write(41, 12, sum_200_f if sum_200_f > 0 else '', monthly_hour_style(41, 12))
    sheet_write.write(41, 13, tot_sum_str,                        row_style(41, 13))
    sheet_write.write(41, 14, cum_diff_str,                       row_style(41, 14))

    # 6. Write bottom table rows
    # Row 45
    sheet_write.write(45,  6, reg_sum_str,       row_style(45,  6))
    sheet_write.write(45,  9, tot_sum_str,        row_style(45,  9))
    sheet_write.write(45, 11, days_worked_count,  row_style(45, 11))
    sheet_write.write(45, 15, vacation_days_count,row_style(45, 15))

    # Row 46
    sheet_write.write(46, 6, sum_125_f if sum_125_f > 0 else 0.0, monthly_hour_style(46, 6))

    # Row 47
    target_hours_mins = standard_weekdays_count * 9 * 60
    target_hours_str  = f"{target_hours_mins // 60}:{target_hours_mins % 60:02d}"
    sheet_write.write(47,  6, sum_150_f if sum_150_f > 0 else 0.0, monthly_hour_style(47,  6))
    sheet_write.write(47,  9, target_hours_str,                     row_style(47,  9))
    sheet_write.write(47, 11, standard_weekdays_count,               row_style(47, 11))

    # Row 48
    sheet_write.write(48, 6, sum_200_f if sum_200_f > 0 else 0.0, monthly_hour_style(48, 6))

    # Row 52
    sum_ot_f = sum_125_f + sum_150_f + sum_200_f
    sheet_write.write(52, 6, sum_ot_f if sum_ot_f > 0 else 0.0, monthly_hour_style(52, 6))

    # Row 53 — cumulative deficit (red)
    sheet_write.write(53, 6, f"-{fmt_minutes(total_deficit_minutes)}",
                      style_with_colour(row_style(53, 6), colour_neg))

    # Row 54 — cumulative surplus (green), when present in the template
    if sheet_read.nrows > 54:
        sheet_write.write(54, 6, f"+{fmt_minutes(total_surplus_minutes)}",
                          style_with_colour(row_style(54, 6), colour_pos))

    # 7. Save workbook
    wb.save(output_xls_path)
    print("Successfully processed and saved workbook.")

if __name__ == "__main__":
    main()
