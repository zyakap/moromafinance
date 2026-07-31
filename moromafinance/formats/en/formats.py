"""Project-level input formats (FORMAT_MODULE_PATH = 'moromafinance.formats').

Date fields accept every format offered in Settings → Dates, so whichever
display format the tenant picks, typed entry in that format parses. ISO first
(unambiguous), then day-first variants (this market), month-first last.
"""
DATE_INPUT_FORMATS = [
    '%Y-%m-%d',      # 2026-02-21 (ISO — native pickers, APIs)
    '%d/%m/%Y',      # 21/02/2026
    '%d-%m-%Y',      # 21-02-2026
    '%b %d, %Y',     # Feb 21, 2026
    '%m/%d/%Y',      # 02/21/2026 (only unambiguous values reach this)
]
DATETIME_INPUT_FORMATS = [
    '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
    '%d/%m/%Y %H:%M', '%d/%m/%Y',
]
