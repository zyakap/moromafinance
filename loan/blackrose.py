"""Read a Blackrose LMS client statement (PDF) and turn it into a loanmasta loan.

Blackrose prints one statement per client account: a header block with the
client's name/code/employer/address, then one row per event with a running
balance:

    Date  Code  Loan  Rrepayable  PNO  PayDate  Repayment  Refund  Default Fee  Balance

    04/07/2024 Lon 3,000.00 5,400.00                 0.00 0.00  0.00 5,400.00
    23/07/2024 Rep     0.00     0.00 15/24 24/07/2024 270.00 0.00  0.00 5,130.00
    03/09/2024 Def     0.00     0.00 18/24 04/09/2024   0.00 0.00 27.00 4,617.00

Three codes matter:

  ``Lon``  an advance — the *repayable* (principal + interest) is added to the balance
  ``Rep``  a repayment — reduces the balance
  ``Def``  a missed repayment — the default fee is added to the balance

so the running balance is ``+ repayable - repayment + default_fee + refund``.
That identity is re-computed on every row and any drift from the printed
Balance column is reported as a warning rather than silently accepted.

A Blackrose account rolls: a second ``Lon`` is simply added on top of whatever
was still owing, and the repayment stream is never allocated between the two
advances. One statement therefore becomes **one** loanmasta loan whose ledger
replays every printed row, with later advances recorded as top-up credit lines.
That reproduces the client's balance exactly at every line of the statement,
which is what the migration has to get right.

Parsing is done from word coordinates (:func:`parse_pdf`) so blank cells cannot
shift a value into the wrong column; :func:`parse_text` is a token-order
fallback for text that has already been flattened.

The module is deliberately free of view/request code — :func:`parse_pdf`,
:func:`derive` and :func:`import_statement` are the three entry points.
"""
import datetime
import hashlib
import logging
import random
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

logger = logging.getLogger(__name__)

ZERO = Decimal('0.00')

#: Blackrose transaction codes we understand.
CODE_ADVANCE = 'Lon'
CODE_REPAYMENT = 'Rep'
CODE_DEFAULT = 'Def'

#: Canonical column keys, in printed order.
COLUMN_KEYS = ['date', 'code', 'loan', 'repayable', 'pno', 'paydate',
               'repayment', 'refund', 'default_fee', 'balance', 'remarks']

#: Header text (lower-cased, punctuation-free) -> canonical key. Two-word
#: headings are matched before one-word ones. "Rrepayable" is Blackrose's own
#: typo and appears on every install we have seen.
_HEADER_ALIASES = {
    'default fee': 'default_fee',
    'pay date': 'paydate',
    'pay no': 'pno',
    'date': 'date',
    'code': 'code',
    'loan': 'loan',
    'rrepayable': 'repayable',
    'repayable': 'repayable',
    'pno': 'pno',
    'paydate': 'paydate',
    'repayment': 'repayment',
    'repaid': 'repayment',
    'refund': 'refund',
    'fee': 'default_fee',
    'balance': 'balance',
    'remarks': 'remarks',
}

_MONEY_RE = re.compile(r'^-?[\d,]*\.?\d+$')
_DATE_RE = re.compile(r'^(\d{1,2})/(\d{1,2})/(\d{4})$')
#: The same shape, found anywhere in a blob of text (used to sniff the order
#: the statement prints its dates in).
_DATE_SCAN_RE = re.compile(r'(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)')
_PNO_RE = re.compile(r'^\d{1,3}/\d{2,4}$')
#: A standalone client code: mostly digits, optionally prefixed, no separators
#: (which is what keeps the lender's "70392811/76525470/72246391" phone line out).
_CLIENT_CODE_RE = re.compile(r'^[A-Za-z]{0,4}\d{3,}[A-Za-z]{0,2}$')

#: Rows within this many points of each other belong to the same printed line.
_ROW_TOLERANCE = 3.0
#: A page carrying fewer real words than this is treated as a scan and OCR'd.
_MIN_WORDS_PER_PAGE = 5
#: Render scanned pages at this DPI before handing them to tesseract.
_OCR_DPI = 300
#: Drop OCR words tesseract is less sure about than this (0-100).
_OCR_MIN_CONF = 40.0
#: A horizontal gap this wide inside a header line means a new column block.
_COLUMN_GAP = 40.0


class BlackroseError(Exception):
    """The upload is not a statement we can read."""


# ── small parsers ────────────────────────────────────────────────────────────

def to_decimal(text, default=ZERO):
    """'5,400.00' -> Decimal('5400.00'). Unparseable/blank -> ``default``."""
    if text is None:
        return default
    text = str(text).strip().replace(',', '').replace('K', '')
    if not text or not _MONEY_RE.match(text):
        return default
    try:
        return Decimal(text).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return default


def to_date(text, day_first=True):
    """'04/07/2024' -> date(2024, 7, 4) when day-first, date(2024, 4, 7) when not.

    Blackrose prints either order depending on the regional settings of the
    machine the report was run on, so the caller passes what
    :func:`detect_day_first` worked out for the statement as a whole. Returns
    None when the text is not a date, or names a day that does not exist.
    """
    if not text:
        return None
    m = _DATE_RE.match(str(text).strip())
    if not m:
        return None
    first, second, year = (int(g) for g in m.groups())
    day, month = (first, second) if day_first else (second, first)
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def detect_day_first(text):
    """Work out which way round a statement prints its dates.

    A component above 12 can only be a day, so a single unambiguous date
    settles the whole document. Statements where every date could be read
    either way fall back to day-first, which is what the older exports use.

    This matters more than it looks: read the wrong way round, '10/31/2025'
    is not a wrong date but *no* date, and the row it sits on is dropped
    without complaint -- so half a ledger can go missing quietly.
    """
    day_first_hits = month_first_hits = 0
    for first, second, _year in _DATE_SCAN_RE.findall(str(text or '')):
        first, second = int(first), int(second)
        if first > 12 >= second:
            day_first_hits += 1
        elif second > 12 >= first:
            month_first_hits += 1
    return month_first_hits <= day_first_hits


def money(value):
    return Decimal(str(value or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


# ── the parsed statement ─────────────────────────────────────────────────────

class Txn:
    """One printed statement row."""

    __slots__ = ('date', 'code', 'loan', 'repayable', 'pno', 'paydate', 'repayment',
                 'refund', 'default_fee', 'balance', 'remarks', 'line_no')

    def __init__(self, date=None, code='', loan=ZERO, repayable=ZERO, pno='', paydate=None,
                 repayment=ZERO, refund=ZERO, default_fee=ZERO, balance=ZERO, remarks='',
                 line_no=0):
        self.date = date
        self.code = code
        self.loan = loan
        self.repayable = repayable
        self.pno = pno
        self.paydate = paydate
        self.repayment = repayment
        self.refund = refund
        self.default_fee = default_fee
        self.balance = balance
        self.remarks = remarks
        self.line_no = line_no

    @property
    def kind(self):
        """ADVANCE / REPAYMENT / DEFAULT / REFUND / UNKNOWN.

        The printed code wins; when it is something this Blackrose install
        spells differently, fall back to whichever money column is non-zero.
        """
        code = (self.code or '').strip().lower()[:3]
        if code == 'lon':
            return 'ADVANCE'
        if code == 'rep':
            return 'REPAYMENT'
        if code == 'def':
            return 'DEFAULT'
        if self.repayable > 0 or self.loan > 0:
            return 'ADVANCE'
        if self.repayment > 0:
            return 'REPAYMENT'
        if self.default_fee > 0:
            return 'DEFAULT'
        if self.refund > 0:
            return 'REFUND'
        return 'UNKNOWN'

    @property
    def effect(self):
        """What this row does to the running balance."""
        return self.repayable - self.repayment + self.default_fee + self.refund

    def as_dict(self):
        return {
            'date': self.date.isoformat() if self.date else None,
            'code': self.code,
            'loan': str(self.loan),
            'repayable': str(self.repayable),
            'pno': self.pno,
            'paydate': self.paydate.isoformat() if self.paydate else None,
            'repayment': str(self.repayment),
            'refund': str(self.refund),
            'default_fee': str(self.default_fee),
            'balance': str(self.balance),
            'remarks': self.remarks,
            'kind': self.kind,
            'line_no': self.line_no,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            date=to_date_iso(data.get('date')), code=data.get('code') or '',
            loan=to_decimal(data.get('loan')), repayable=to_decimal(data.get('repayable')),
            pno=data.get('pno') or '', paydate=to_date_iso(data.get('paydate')),
            repayment=to_decimal(data.get('repayment')), refund=to_decimal(data.get('refund')),
            default_fee=to_decimal(data.get('default_fee')), balance=to_decimal(data.get('balance')),
            remarks=data.get('remarks') or '', line_no=data.get('line_no') or 0,
        )


def to_date_iso(text):
    """'2024-07-04' -> date. Used when re-reading a stored parse."""
    if not text:
        return None
    if isinstance(text, datetime.date):
        return text
    try:
        return datetime.date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


class Statement:
    """A parsed Blackrose statement: who it belongs to, and every printed row."""

    def __init__(self):
        self.lender_name = ''
        self.client_name = ''
        self.client_code = ''
        self.employer = ''
        self.address = ''
        self.phone = ''
        self.txns = []
        self.warnings = []

    def as_dict(self):
        return {
            'lender_name': self.lender_name,
            'client_name': self.client_name,
            'client_code': self.client_code,
            'employer': self.employer,
            'address': self.address,
            'phone': self.phone,
            'warnings': list(self.warnings),
            'txns': [t.as_dict() for t in self.txns],
        }

    @classmethod
    def from_dict(cls, data):
        s = cls()
        s.lender_name = data.get('lender_name') or ''
        s.client_name = data.get('client_name') or ''
        s.client_code = data.get('client_code') or ''
        s.employer = data.get('employer') or ''
        s.address = data.get('address') or ''
        s.phone = data.get('phone') or ''
        s.warnings = list(data.get('warnings') or [])
        s.txns = [Txn.from_dict(t) for t in (data.get('txns') or [])]
        return s

    @property
    def first_name(self):
        return (self.client_name or '').split(' ')[0] if self.client_name else ''

    @property
    def last_name(self):
        parts = (self.client_name or '').split(' ')
        return parts[-1] if len(parts) > 1 else ''


# ── coordinate-based PDF parsing ─────────────────────────────────────────────

def _group_rows(words, tolerance=_ROW_TOLERANCE):
    """Cluster words into printed lines by their ``top`` coordinate.

    Columns of the same visual line are not always laid out on exactly the same
    baseline (a right-hand address block typically sits a point or two off), so
    a tolerance is used rather than an exact match. Each row is returned sorted
    left-to-right.
    """
    rows = []
    for word in sorted(words, key=lambda w: (w['top'], w['x0'])):
        if rows and abs(word['top'] - rows[-1][0]['top']) <= tolerance:
            rows[-1].append(word)
        else:
            rows.append([word])
    return [sorted(r, key=lambda w: w['x0']) for r in rows]


def _match_header(row):
    """Map a candidate header row to ``[(key, x0, x1), ...]``, or None.

    Header words are consumed greedily so a two-word heading ("Default Fee")
    becomes one column spanning both words.
    """
    columns, i = [], 0
    while i < len(row):
        one = re.sub(r'[^a-z ]', '', row[i]['text'].lower()).strip()
        two = None
        if i + 1 < len(row):
            two = f"{one} {re.sub(r'[^a-z ]', '', row[i + 1]['text'].lower()).strip()}".strip()

        if two and two in _HEADER_ALIASES:
            columns.append((_HEADER_ALIASES[two], row[i]['x0'], row[i + 1]['x1']))
            i += 2
        elif one in _HEADER_ALIASES:
            columns.append((_HEADER_ALIASES[one], row[i]['x0'], row[i]['x1']))
            i += 1
        else:
            return None  # a word we don't recognise -> not the header row
    keys = {c[0] for c in columns}
    if not {'date', 'code', 'balance'}.issubset(keys):
        return None
    return columns


def _find_header(pages):
    """The first table-header row across all pages, or None."""
    for page_rows in pages:
        for row in page_rows:
            columns = _match_header(row)
            if columns:
                return columns, row
    return None, None


def _assign_columns(row, columns):
    """Bucket a row's words into ``{column_key: text}`` by horizontal overlap.

    Overlap (rather than "nearest edge") is what makes a blank cell harmless:
    a value can only land in a column whose printed heading it sits under.
    Words that overlap nothing — an over-wide Remarks note, say — fall back to
    the nearest column centre.
    """
    cells = {key: [] for key in COLUMN_KEYS}
    for word in row:
        best_key, best_overlap = None, 0.0
        for key, x0, x1 in columns:
            overlap = min(word['x1'], x1) - max(word['x0'], x0)
            if overlap > best_overlap:
                best_key, best_overlap = key, overlap
        if best_key is None:
            centre = (word['x0'] + word['x1']) / 2
            best_key = min(columns, key=lambda c: abs((c[1] + c[2]) / 2 - centre))[0]
        cells.setdefault(best_key, []).append(word['text'])
    return {key: ' '.join(parts).strip() for key, parts in cells.items()}


def _cells_to_txn(cells, line_no, day_first=True):
    """A column dict -> Txn, or None when the row is not a transaction."""
    date = to_date(cells.get('date'), day_first)
    if date is None:
        return None
    return Txn(
        date=date,
        code=(cells.get('code') or '').strip(),
        loan=to_decimal(cells.get('loan')),
        repayable=to_decimal(cells.get('repayable')),
        pno=(cells.get('pno') or '').strip(),
        paydate=to_date(cells.get('paydate'), day_first),
        repayment=to_decimal(cells.get('repayment')),
        refund=to_decimal(cells.get('refund')),
        default_fee=to_decimal(cells.get('default_fee')),
        balance=to_decimal(cells.get('balance')),
        remarks=(cells.get('remarks') or '').strip(),
        line_no=line_no,
    )


def _column_split(rows):
    """The x that separates the client block's left and right columns.

    Blackrose prints the client's name/code/employer on the left and their
    postal address on the right. Wherever a line has a wide horizontal gap that
    gap *is* the column boundary, so the leftmost such gap across the block is
    used — the narrowest reading, which keeps right-hand text (an address line
    with no left-hand partner) out of the name/employer fields.
    """
    boundaries = []
    for row in rows:
        for left, right in zip(row, row[1:]):
            gap = right['x0'] - left['x1']
            if gap >= _COLUMN_GAP:
                boundaries.append((left['x1'] + right['x0']) / 2)
    return min(boundaries) if boundaries else None


def _parse_client_block(rows, statement):
    """Pull name / code / employer / address / phone out of the rows above the table.

    The client's code is the anchor: it is the last standalone mostly-numeric
    token in the block (the lender's own phone line is separator-laden and so
    never matches). The name is printed directly above it and the employer
    directly below.
    """
    if not rows:
        statement.warnings.append('No header block found — enter the client details by hand.')
        return

    code_index = None
    for i, row in enumerate(rows):
        if row and _CLIENT_CODE_RE.match(row[0]['text'].strip()):
            code_index = i
    if code_index is None:
        statement.warnings.append(
            'Could not find the client code in the statement header — check the client details below.')
        block = rows
    else:
        block = rows[max(0, code_index - 1):]
        code_index -= max(0, code_index - 1)

    split_x = _column_split(block)
    left, right = [], []
    for row in block:
        l = ' '.join(w['text'] for w in row if split_x is None or w['x0'] < split_x).strip()
        r = ' '.join(w['text'] for w in row if split_x is not None and w['x0'] >= split_x).strip()
        left.append(l)
        right.append(r)

    if code_index is not None:
        statement.client_code = left[code_index]
        statement.client_name = left[code_index - 1] if code_index >= 1 else ''
        statement.employer = ' '.join(x for x in left[code_index + 1:] if x).strip()
    else:
        statement.client_name = next((x for x in left if x), '')
        statement.employer = ' '.join(x for x in left[1:] if x).strip()

    address_lines = []
    for line in right:
        if not line:
            continue
        if line.lower().startswith('phone'):
            phone = re.sub(r'(?i)fax:?.*$', '', line)
            phone = re.sub(r'(?i)^phone:?', '', phone).strip()
            statement.phone = phone
            continue
        address_lines.append(line)
    statement.address = ', '.join(address_lines)

    if not statement.client_name:
        statement.warnings.append('Client name could not be read — enter it by hand.')


def _ocr_words(image, scale):
    """A rendered page image -> pdfplumber-shaped word dicts.

    Tesseract reports pixel boxes at whatever scale the page was rendered at;
    dividing by that scale puts them back into PDF points, so ``_ROW_TOLERANCE``
    and ``_COLUMN_GAP`` keep meaning what they mean everywhere else.
    """
    import pytesseract

    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    words = []
    for index, text in enumerate(data['text']):
        text = (text or '').strip()
        if not text:
            continue
        try:
            confidence = float(data['conf'][index])
        except (TypeError, ValueError):
            confidence = -1.0
        if confidence < _OCR_MIN_CONF:
            continue
        left, top = data['left'][index], data['top'][index]
        words.append({
            'text': text,
            'x0': left / scale,
            'x1': (left + data['width'][index]) / scale,
            'top': top / scale,
            'bottom': (top + data['height'][index]) / scale,
        })
    return words


def _ocr_pages(fileobj, page_numbers):
    """OCR the given pages of a scanned statement -> ``{number: [row, ...]}``."""
    try:
        import pypdfium2
        import pytesseract
    except ImportError as exc:
        raise BlackroseError(
            'This statement is a scan with no text layer, so it has to be read '
            'with OCR. Install the "pytesseract" package and the tesseract-ocr '
            'engine, then try again.') from exc

    try:
        fileobj.seek(0)
    except (AttributeError, OSError):
        pass
    data = fileobj.read()

    scale = _OCR_DPI / 72.0
    rows_by_page = {}
    document = pypdfium2.PdfDocument(data)
    try:
        for number in page_numbers:
            image = document[number].render(scale=scale).to_pil()
            try:
                rows_by_page[number] = _group_rows(_ocr_words(image, scale))
            except pytesseract.TesseractNotFoundError as exc:
                raise BlackroseError(
                    'This statement is a scan, and the tesseract OCR engine is '
                    'not installed on the server (apt install tesseract-ocr).'
                ) from exc
    finally:
        document.close()
    return rows_by_page


def _extract_pages(fileobj):
    """``([[row, ...], ...], {ocr'd page numbers})`` -- one row list per page.

    Statements printed straight out of Blackrose carry a text layer. Ones that
    have been through a scanner do not, and pdfplumber reads nothing off them,
    so those pages are rendered and passed through OCR instead.
    """
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - depends on the deployment
        raise BlackroseError(
            'Reading Blackrose PDF statements needs the "pdfplumber" package. '
            'Install it (pip install pdfplumber) and try again.') from exc

    try:
        fileobj.seek(0)
    except (AttributeError, OSError):
        pass
    pages = []
    scanned = []
    with pdfplumber.open(fileobj) as pdf:
        for number, page in enumerate(pdf.pages):
            words = page.extract_words()
            if len(words) < _MIN_WORDS_PER_PAGE:
                scanned.append(number)
                words = []
            pages.append(_group_rows(words))

    if scanned:
        for number, rows in _ocr_pages(fileobj, scanned).items():
            pages[number] = rows
    return pages, set(scanned)


def parse_pdf(fileobj):
    """Parse an uploaded Blackrose statement PDF into a :class:`Statement`."""
    pages, ocr_pages = _extract_pages(fileobj)
    if not pages:
        raise BlackroseError('The PDF has no pages.')

    columns, header_row = _find_header(pages)
    if not columns:
        raise BlackroseError(
            'This does not look like a Blackrose statement — no '
            '"Date / Code / ... / Balance" table header was found.')

    statement = Statement()
    if ocr_pages:
        statement.warnings.append(
            f'{"Page" if len(ocr_pages) == 1 else "Pages"} '
            f'{", ".join(str(n + 1) for n in sorted(ocr_pages))} had no text layer and '
            'was read with OCR — check every figure against the paper copy.')
    if pages[0] and pages[0][0]:
        statement.lender_name = ' '.join(
            w['text'] for w in pages[0][0] if w['text'].strip().lower() != 'statement').strip()

    header_top = header_row[0]['top']
    _parse_client_block([r for r in pages[0] if r[0]['top'] < header_top - _ROW_TOLERANCE],
                        statement)

    day_first = detect_day_first(
        ' '.join(w['text'] for page in pages for row in page for w in row))

    line_no = 0
    for page_rows in pages:
        for row in page_rows:
            if row is header_row:
                continue
            line_no += 1
            txn = _cells_to_txn(_assign_columns(row, columns), line_no, day_first)
            if txn is not None:
                statement.txns.append(txn)

    _finish(statement)
    return statement


# ── text fallback ────────────────────────────────────────────────────────────

def parse_text(text):
    """Parse statement rows out of already-flattened text.

    Used when a PDF's words carry no usable coordinates. Only the transaction
    table is recovered — the header block cannot be split into name/address
    columns without them, so the client details are left for staff to enter.
    """
    statement = Statement()
    statement.warnings.append(
        'Read without column positions — check every row, and enter the client details by hand.')

    day_first = detect_day_first(text)
    for line_no, line in enumerate(text.splitlines(), start=1):
        txn = _text_line_to_txn(line, line_no, day_first)
        if txn is not None:
            statement.txns.append(txn)

    _finish(statement)
    return statement


def _text_line_to_txn(line, line_no, day_first=True):
    """One flattened line -> Txn, relying on the printed column order.

    Blackrose always prints all four money columns (as 0.00 when empty) but
    omits PNO/PayDate on advance rows, so those two are matched by shape.
    """
    tokens = line.split()
    if len(tokens) < 8:
        return None
    date = to_date(tokens[0], day_first)
    if date is None:
        return None

    code = tokens[1]
    if not re.match(r'^[A-Za-z]{2,10}$', code):
        return None

    i = 2
    if len(tokens) - i < 6:
        return None
    loan, repayable = to_decimal(tokens[i]), to_decimal(tokens[i + 1])
    i += 2

    pno = ''
    if i < len(tokens) and _PNO_RE.match(tokens[i]):
        pno, i = tokens[i], i + 1
    paydate = None
    if i < len(tokens) and to_date(tokens[i], day_first):
        paydate, i = to_date(tokens[i], day_first), i + 1

    if len(tokens) - i < 4:
        return None
    repayment, refund, default_fee, balance = (to_decimal(t) for t in tokens[i:i + 4])
    remarks = ' '.join(tokens[i + 4:]).strip()

    return Txn(date=date, code=code, loan=loan, repayable=repayable, pno=pno, paydate=paydate,
               repayment=repayment, refund=refund, default_fee=default_fee, balance=balance,
               remarks=remarks, line_no=line_no)


# ── integrity check ──────────────────────────────────────────────────────────

def _finish(statement):
    """Validate the parse: rows present, dates ascending, running balance intact."""
    txns = statement.txns
    if not txns:
        statement.warnings.append('No transaction rows were found in this statement.')
        return

    unknown = {t.code for t in txns if t.kind == 'UNKNOWN'}
    if unknown:
        statement.warnings.append(
            f"Unrecognised transaction code(s): {', '.join(sorted(unknown))} — these rows were skipped.")
    statement.txns = [t for t in txns if t.kind != 'UNKNOWN']
    txns = statement.txns
    if not txns:
        return

    dates = [t.date for t in txns]
    if dates != sorted(dates):
        statement.warnings.append('Statement rows are not in date order — check the ordering below.')

    running = ZERO
    for txn in txns:
        running += txn.effect
        if running != txn.balance:
            statement.warnings.append(
                f'Balance mismatch on line {txn.line_no} ({txn.date:%d/%m/%Y}): the statement shows '
                f'K{txn.balance:,.2f} but the running total is K{running:,.2f}. '
                'The printed balance was used.')
            running = txn.balance

    if any(t.refund > 0 for t in txns):
        statement.warnings.append(
            'This statement contains a Refund — it is treated as increasing the balance. '
            'Check the closing balance before importing.')


# ── deriving a loanmasta loan ────────────────────────────────────────────────

def _scheduled_amount_at(txns, index):
    """The fortnightly repayment in force at ``index``.

    Blackrose does not print the scheduled deduction, so the most recent actual
    repayment is used (falling back to the next one for a default that lands
    before any payment).
    """
    for txn in reversed(txns[:index]):
        if txn.kind == 'REPAYMENT' and txn.repayment > 0:
            return txn.repayment
    for txn in txns[index:]:
        if txn.kind == 'REPAYMENT' and txn.repayment > 0:
            return txn.repayment
    return ZERO


def _current_repayment(txns):
    """The client's present fortnightly deduction.

    Only repayments made after the most recent advance count — an earlier
    advance's smaller deduction is history. The most common amount wins (a
    one-off catch-up or payout shouldn't set the schedule); ties go to the
    latest.
    """
    last_advance = max((i for i, t in enumerate(txns) if t.kind == 'ADVANCE'), default=-1)
    recent = [t.repayment for t in txns[last_advance + 1:]
              if t.kind == 'REPAYMENT' and t.repayment > 0]
    if not recent:
        recent = [t.repayment for t in txns if t.kind == 'REPAYMENT' and t.repayment > 0]
    if not recent:
        return ZERO
    counts = {}
    for i, amount in enumerate(recent):
        count, _ = counts.get(amount, (0, 0))
        counts[amount] = (count + 1, i)
    return max(counts, key=lambda a: counts[a])


def next_fortnight_on_or_after(last_paydate, today=None):
    """Roll ``last_paydate`` forward in 14-day steps until it is not in the past.

    A migrated statement is usually a few pay periods stale; anchoring the new
    schedule to a date that has already passed would have the default runner
    default the loan the moment it is imported.
    """
    today = today or datetime.date.today()
    if last_paydate is None:
        return today
    nxt = last_paydate + datetime.timedelta(days=14)
    if nxt < today:
        periods = ((today - nxt).days + 13) // 14
        nxt += datetime.timedelta(days=14 * periods)
    return nxt


def derive(statement, today=None):
    """Work out the loanmasta loan a statement describes.

    Returns a plan dict of everything the loan needs plus the totals shown on
    the review screen. Nothing here touches the database.
    """
    today = today or datetime.date.today()
    txns = statement.txns
    if not txns:
        raise BlackroseError('This statement has no transactions to import.')

    total_advanced = sum((t.loan for t in txns if t.kind == 'ADVANCE'), ZERO)
    total_repayable = sum((t.repayable for t in txns if t.kind == 'ADVANCE'), ZERO)
    total_repaid = sum((t.repayment for t in txns), ZERO)
    total_default_fees = sum((t.default_fee for t in txns), ZERO)
    closing_balance = txns[-1].balance

    repayment_amount = _current_repayment(txns)

    # Each distinct PayDate is one scheduled fortnight, however many rows
    # Blackrose printed against it (catch-up payments repeat the pay number).
    history = []
    for txn in txns:
        if txn.kind in ('REPAYMENT', 'DEFAULT') and txn.paydate and txn.paydate not in history:
            history.append(txn.paydate)
    history.sort()

    if closing_balance > 0 and repayment_amount > 0:
        remaining = int((closing_balance / repayment_amount).to_integral_value(rounding='ROUND_CEILING'))
        remaining = max(1, remaining)
    else:
        remaining = 0

    last_paydate = history[-1] if history else txns[-1].date
    next_payment_date = next_fortnight_on_or_after(last_paydate, today)

    return {
        'total_advanced': total_advanced,
        'total_repayable': total_repayable,
        'total_interest': total_repayable - total_advanced,
        'total_repaid': total_repaid,
        'total_default_fees': total_default_fees,
        'closing_balance': closing_balance,
        'advance_count': sum(1 for t in txns if t.kind == 'ADVANCE'),
        'repayment_count': sum(1 for t in txns if t.kind == 'REPAYMENT' and t.repayment > 0),
        'default_count': sum(1 for t in txns if t.kind == 'DEFAULT'),
        'repayment_amount': repayment_amount,
        'history_dates': history,
        'fortnights_settled': len(history),
        'remaining_fortnights': remaining,
        'number_of_fortnights': len(history) + remaining,
        'first_date': txns[0].date,
        'last_date': txns[-1].date,
        'last_paydate': last_paydate,
        'next_payment_date': next_payment_date,
        'row_count': len(txns),
    }


# ── writing it to the database ───────────────────────────────────────────────

def file_digest(fileobj):
    """sha256 of an upload, used to spot the same statement being loaded twice."""
    try:
        fileobj.seek(0)
    except (AttributeError, OSError):
        pass
    digest = hashlib.sha256()
    for chunk in iter(lambda: fileobj.read(65536), b''):
        digest.update(chunk if isinstance(chunk, bytes) else chunk.encode())
    try:
        fileobj.seek(0)
    except (AttributeError, OSError):
        pass
    return digest.hexdigest()


def find_client(statement):
    """An existing client this statement belongs to, or None.

    Matched on the Blackrose code first (it doubles as the payroll file number
    on every PNG install we have seen, and is unique), then on full name.
    """
    from accounts.models import UserProfile

    code = (statement.client_code or '').strip()
    if code:
        match = UserProfile.objects.filter(employee_file_number=code).first()
        if match:
            return match
    first, last = statement.first_name, statement.last_name
    if first and last:
        return UserProfile.objects.filter(first_name__iexact=first, last_name__iexact=last).first()
    return None


def _create_client(statement, location=None):
    """Create the User + UserProfile for a migrated client.

    The account is created active with a generated login so the client can be
    invited later; no welcome email is sent from the import.
    """
    from django.conf import settings
    from accounts.models import User, UserProfile
    from admin1.models import AdminSettings
    from custom.functions import id_generator

    first, last = statement.first_name[:20], statement.last_name[:20]
    if not first:
        raise BlackroseError('A client name is required to create the account.')

    random_num = random.randint(1000, 9999)
    stub = f"{first[0]}{(last or first)[0]}{random_num}".lower()
    email = f'{stub}@{settings.DOMAIN_DNS}'
    user = User.objects.create_user(email=email, is_active=True, is_confirmed=True,
                                    password=f'{stub}{id_generator(3).lower()}')
    user.active = True
    user.confirmed = True
    user.save()

    prefix = settings.PREFIX
    admin_settings = AdminSettings.objects.filter(settings_name='setting1').first()
    if admin_settings and admin_settings.loanref_prefix:
        prefix = admin_settings.loanref_prefix

    profile = UserProfile.objects.create(
        user=user, first_name=first, last_name=last or first, email=email,
        uid=f'{prefix}{random_num}', luid=settings.LUID, modeofregistration='OTC',
        activation=1, location=location,
    )
    return profile


def _apply_client_details(profile, statement, phone=None):
    """Fill in the details the statement carries, without overwriting better data.

    Consent is recorded rather than merged: a client carrying a loan signed the
    terms and agreed to the credit check on paper before it was advanced, which
    is what these two flags exist to record. The same thing happens when a loan
    is funded through the normal route (see admin1/views/loansView.py).
    """
    profile.terms_consent = 'YES'
    profile.credit_consent = 'YES'
    if statement.employer and not profile.employer:
        profile.employer = statement.employer[:50]
    if statement.address and not profile.residential_address:
        profile.residential_address = statement.address
    if statement.client_code and not profile.employee_file_number:
        profile.employee_file_number = statement.client_code[:20]
    digits = re.sub(r'\D', '', str(phone if phone is not None else statement.phone or ''))
    if digits and not profile.mobile1:
        try:
            profile.mobile1 = int(digits[:9])
        except ValueError:
            pass
    profile.save()
    return profile


def _make_loan_ref(profile):
    """A loan reference in the house style: prefix + client id + initials + loan id."""
    from django.conf import settings
    from loan.models import Loan

    prefix = settings.PREFIX
    initials = f'{(profile.first_name or "X")[0]}{(profile.last_name or "X")[0]}'.upper()
    stem = f'{prefix}{profile.id}{initials}'
    loan = Loan.objects.create(ref=stem, owner=profile)
    loan.ref = f'{stem}{loan.id}'
    return loan


def import_statement(statement, plan, *, officer=None, location=None, profile=None,
                     repayment_amount=None, next_payment_date=None,
                     remaining_fortnights=None, notes=''):
    """Create (or reuse) the client and build the loan + full ledger.

    Every printed row is replayed in order, using the same money rules the rest
    of the system uses — advances add their repayable to the balance, defaults
    add their fee and their missed repayment to arrears, and repayments are
    split across principal / interest / default interest in proportion to what
    is still owed on each (see ``loan.functions.process_repayment``). The
    closing balance therefore lands on the statement's own figure.

    The caller is responsible for the surrounding transaction.
    """
    from django.conf import settings
    from loan.models import Loan, LoanFile, Statement as StatementLine, Payment

    txns = statement.txns
    if not txns:
        raise BlackroseError('This statement has no transactions to import.')

    repayment_amount = money(repayment_amount if repayment_amount is not None
                             else plan['repayment_amount'])
    next_payment_date = next_payment_date or plan['next_payment_date']
    remaining = plan['remaining_fortnights'] if remaining_fortnights is None else int(remaining_fortnights)
    remaining = max(0, remaining)

    created_client = profile is None
    if created_client:
        profile = _create_client(statement, location=location)
    _apply_client_details(profile, statement)

    loan = _make_loan_ref(profile)
    loan.uid = profile.uid
    loan.luid = settings.LUID
    loan.existing_code = (statement.client_code or '')[:30]
    loan.officer = officer
    loan.location = location or profile.location
    loan.loan_type = 'PERSONAL'
    # 'OLD' is the marker the existing-loan screens filter on for migrated loans.
    loan.classification = 'OLD'
    loan.category = 'FUNDED'
    loan.repayment_frequency = 'FORTNIGHTLY'
    loan.tc_agreement = 'YES'
    loan.amount = plan['total_advanced']
    loan.interest = plan['total_interest']
    loan.total_loan_amount = plan['total_repayable']
    loan.repayment_amount = repayment_amount
    loan.funding_date = plan['first_date']
    loan.notes = notes or f'Migrated from Blackrose statement (client code {statement.client_code}).'
    loan.save()

    LoanFile.objects.get_or_create(loan=loan)

    # ── replay the printed ledger ────────────────────────────────────────────
    balance = ZERO
    arrears = ZERO
    principal_receivable = ZERO
    interest_receivable = ZERO
    default_receivable = ZERO
    principal_paid = ZERO
    interest_paid = ZERO
    default_paid = ZERO
    total_paid = ZERO
    repayments = 0
    defaults = 0
    last_repayment_date = last_repayment_amount = None
    last_default_date = last_default_amount = None
    lines = []
    payments = []

    for index, txn in enumerate(txns):
        kind = txn.kind
        count = index + 1
        if kind == 'ADVANCE':
            balance += txn.repayable
            principal_receivable += txn.loan
            interest_receivable += (txn.repayable - txn.loan)
            first = not any(t.kind == 'ADVANCE' for t in txns[:index])
            label = ('Loan Created' if first else 'Additional Advance') + \
                    f' — Blackrose migration (principal K{txn.loan:,.2f}, repayable K{txn.repayable:,.2f})'
            lines.append(StatementLine(
                owner=profile, loanref=loan, uid=profile.uid, luid=settings.LUID,
                ref=f'{loan.ref}SO{count}', s_count=count, type='OTHER', statement=label,
                date=txn.date, debit=0, credit=txn.repayable,
                arrears=arrears, balance=balance))

        elif kind == 'DEFAULT':
            missed = _scheduled_amount_at(txns, index)
            balance += txn.default_fee
            default_receivable += txn.default_fee
            arrears += missed
            defaults += 1
            last_default_date, last_default_amount = txn.date, missed
            lines.append(StatementLine(
                owner=profile, loanref=loan, uid=profile.uid, luid=settings.LUID,
                ref=f'{loan.ref}SD{count}', s_count=count, type='DEFAULT',
                statement='Loan Defaulted — Blackrose migration',
                date=txn.date, debit=0, credit=txn.default_fee,
                default_amount=missed, default_interest=txn.default_fee,
                arrears=arrears, balance=balance))

        elif kind == 'REPAYMENT':
            amount = txn.repayment
            # Pro-rata across what is still owed on each component, exactly as
            # a repayment entered through the payment screen is split.
            if balance > 0:
                p_share = amount * (principal_receivable / balance)
                i_share = amount * (interest_receivable / balance)
                d_share = amount * (default_receivable / balance)
            else:
                p_share = i_share = d_share = ZERO
            p_share, i_share, d_share = money(p_share), money(i_share), money(d_share)
            principal_receivable -= p_share
            interest_receivable -= i_share
            default_receivable -= d_share
            principal_paid += p_share
            interest_paid += i_share
            default_paid += d_share

            arrears = ZERO if arrears < amount else arrears - amount
            balance -= amount
            total_paid += amount
            repayments += 1
            last_repayment_date, last_repayment_amount = txn.date, amount

            lines.append(StatementLine(
                owner=profile, loanref=loan, uid=profile.uid, luid=settings.LUID,
                ref=f'{loan.ref}SP{count}', s_count=count, type='PAYMENT',
                statement=f'Fortnightly Salary Deduction — Blackrose migration{_pno_suffix(txn)}',
                date=txn.date, debit=amount, credit=0,
                principal_collected=p_share, interest_collected=i_share,
                default_interest_collected=d_share,
                arrears=arrears, balance=balance))
            payments.append(Payment(
                owner=profile, loanref=loan, ref=f'{loan.ref}P{repayments}', p_count=repayments,
                date=txn.date, amount=amount, type='NORMAL REPAYMENT',
                mode='PAYROLL DEDUCTION' if txn.pno else 'BANK DEPOSIT',
                statement=f'Blackrose migration{_pno_suffix(txn)}', officer=officer))

        elif kind == 'REFUND':
            balance += txn.refund
            principal_receivable += txn.refund
            lines.append(StatementLine(
                owner=profile, loanref=loan, uid=profile.uid, luid=settings.LUID,
                ref=f'{loan.ref}SO{count}', s_count=count, type='OTHER',
                statement='Refund — Blackrose migration',
                date=txn.date, debit=0, credit=txn.refund,
                arrears=arrears, balance=balance))

    StatementLine.objects.bulk_create(lines)
    Payment.objects.bulk_create(payments)

    # ── schedule: the pay dates already served, then the fortnights still to run ──
    dates = list(plan['history_dates'])
    for step in range(remaining):
        dates.append(next_payment_date + datetime.timedelta(days=14 * step))

    loan.set_repayment_dates([d.isoformat() for d in dates])
    loan.number_of_fortnights = len(dates)
    loan.fortnights_settled = len(plan['history_dates'])
    # Blackrose pay dates rarely sit on a clean 14-day grid, so the schedule is
    # marked custom to stop the canonical rebuild tools flattening the history.
    loan.custom_schedule = True
    loan.repayment_start_date = dates[0] if dates else next_payment_date
    loan.expected_end_date = dates[-1] if dates else next_payment_date
    loan.next_payment_date = next_payment_date if remaining else None

    receivable = _reconcile([principal_receivable, interest_receivable, default_receivable],
                            balance)
    paid = _reconcile([principal_paid, interest_paid, default_paid], total_paid)
    loan.principal_loan_receivable, loan.ordinary_interest_receivable, \
        loan.default_interest_receivable = receivable
    loan.total_outstanding = money(balance)
    loan.principal_loan_paid, loan.interest_paid, loan.default_interest_paid = paid
    loan.total_paid = money(total_paid)
    loan.total_arrears = money(arrears)
    loan.number_of_repayments = repayments
    loan.fortnights_paid = len(plan['history_dates'])
    loan.last_repayment_date = last_repayment_date
    loan.last_repayment_amount = money(last_repayment_amount)
    loan.number_of_defaults = defaults
    loan.last_default_date = last_default_date
    loan.last_default_amount = money(last_default_amount)

    if loan.total_outstanding <= 0:
        loan.status = 'COMPLETED'
        loan.funded_category = 'COMPLETED'
    else:
        loan.status = 'DEFAULTED' if loan.total_arrears > 0 else 'RUNNING'
        loan.funded_category = 'ACTIVE'
    loan.save()

    profile.has_loan = loan.funded_category == 'ACTIVE'
    profile.number_of_loans = Loan.objects.filter(owner=profile).count()
    if loan.total_arrears > 0:
        profile.has_arrears = True
    if not profile.repayment_limit or profile.repayment_limit < repayment_amount:
        profile.repayment_limit = repayment_amount + Decimal('100.00')
    profile.save()

    logger.info('BLACKROSE-IMPORT loan=%s client=%s rows=%s balance=%s arrears=%s',
                loan.ref, profile.uid, len(txns), loan.total_outstanding, loan.total_arrears)
    return loan, profile, created_client


def _pno_suffix(txn):
    return f' (pay {txn.pno})' if txn.pno else ''


def _reconcile(parts, target):
    """Nudge ``parts`` so they add up to ``target`` exactly.

    Splitting a hundred-odd repayments pro-rata leaves a few toea of rounding
    drift between the three receivable buckets and the statement's balance. The
    balance is the figure the client has been shown, so it wins: the residual
    goes onto the largest bucket, which is always big enough to absorb it.
    """
    parts = [money(p) for p in parts]
    drift = money(target) - sum(parts)
    if drift and parts:
        biggest = max(range(len(parts)), key=lambda i: parts[i])
        parts[biggest] += drift
    return parts
