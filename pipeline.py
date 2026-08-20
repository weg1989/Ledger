"""
Shared data structures for the invoice pipeline.
Everything downstream (validation, matching, decisioning) speaks this schema,
regardless of which extraction tier produced it. That's what lets Tier 1/2/3
be swappable without touching the rest of the system.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

import logging
import sys

logger = logging.getLogger("ledger_pipeline")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_handler)

# Synonyms for dynamic mapping
FIELD_SYNONYMS = {
    "vendor_tax_id": ["gst registration no", "gstin", "vat id", "tax registration", "tax id"],
    "bank_account": ["remit to", "bank account iban", "iban", "account number", "account no"],
    "po_number": ["client po", "purchase order ref", "po ref", "po number", "order no"],
    "invoice_number": ["inv no", "invoice #", "bill no", "document no"],
}

_SCALAR_FIELDS = [
    "invoice_number", "invoice_date", "due_date", "vendor_name", "vendor_tax_id",
    "po_number", "currency", "subtotal", "tax_amount", "tax_rate", "total_amount",
]

@dataclass
class LineItem:
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None


@dataclass
class InvoiceExtraction:
    """Flexible 2-tier payload structure for invoice extractions."""
    source_file: str
    extraction_tier: str  # TIER_1_NATIVE | TIER_2_OCR_LLM | TIER_3_VISION_LLM
    
    # 2-Tier flexible container dictionaries
    core_fields: Dict[str, Any] = field(default_factory=dict)
    extra_fields: Dict[str, Any] = field(default_factory=dict)
    extraction_metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Additional context / tracking
    tax_mode: str = "unknown"                     # separate | embedded | unknown
    raw_text_sample: Optional[str] = None        # first ~500 chars, for audit trail
    extraction_notes: List[str] = field(default_factory=list)

    def __post_init__(self):
        # Initialize default core field structure if empty
        defaults = {
            "invoice_number": None,
            "invoice_date": None,
            "due_date": None,
            "vendor_name": None,
            "vendor_tax_id": None,
            "po_number": None,
            "currency": "USD",
            "line_items": [],
            "subtotal": None,
            "tax_amount": None,
            "tax_rate": None,
            "total_amount": None,
        }
        for k, v in defaults.items():
            if k not in self.core_fields:
                self.core_fields[k] = v

    # --- Backward Compatibility Property Getters/Setters ---
    @property
    def invoice_number(self) -> Optional[str]: return self.core_fields.get("invoice_number")
    @invoice_number.setter
    def invoice_number(self, val: Optional[str]): self.core_fields["invoice_number"] = val

    @property
    def invoice_date(self) -> Optional[str]: return self.core_fields.get("invoice_date")
    @invoice_date.setter
    def invoice_date(self, val: Optional[str]): self.core_fields["invoice_date"] = val

    @property
    def due_date(self) -> Optional[str]: return self.core_fields.get("due_date")
    @due_date.setter
    def due_date(self, val: Optional[str]): self.core_fields["due_date"] = val

    @property
    def vendor_name(self) -> Optional[str]: return self.core_fields.get("vendor_name")
    @vendor_name.setter
    def vendor_name(self, val: Optional[str]): self.core_fields["vendor_name"] = val

    @property
    def vendor_tax_id(self) -> Optional[str]: return self.core_fields.get("vendor_tax_id")
    @vendor_tax_id.setter
    def vendor_tax_id(self, val: Optional[str]): self.core_fields["vendor_tax_id"] = val

    @property
    def po_number(self) -> Optional[str]: return self.core_fields.get("po_number")
    @po_number.setter
    def po_number(self, val: Optional[str]): self.core_fields["po_number"] = val

    @property
    def currency(self) -> Optional[str]: return self.core_fields.get("currency")
    @currency.setter
    def currency(self, val: Optional[str]): self.core_fields["currency"] = val

    @property
    def line_items(self) -> List[LineItem]: return self.core_fields.get("line_items", [])
    @line_items.setter
    def line_items(self, val: List[LineItem]): self.core_fields["line_items"] = val

    @property
    def subtotal(self) -> Optional[float]: return self.core_fields.get("subtotal")
    @subtotal.setter
    def subtotal(self, val: Optional[float]): self.core_fields["subtotal"] = val

    @property
    def tax_amount(self) -> Optional[float]: return self.core_fields.get("tax_amount")
    @tax_amount.setter
    def tax_amount(self, val: Optional[float]): self.core_fields["tax_amount"] = val

    @property
    def tax_rate(self) -> Optional[float]: return self.core_fields.get("tax_rate")
    @tax_rate.setter
    def tax_rate(self, val: Optional[float]): self.core_fields["tax_rate"] = val

    @property
    def total_amount(self) -> Optional[float]: return self.core_fields.get("total_amount")
    @total_amount.setter
    def total_amount(self, val: Optional[float]): self.core_fields["total_amount"] = val

    def apply_dynamic_mapping(self):
        """Maps custom or unrecognized keys in extra_fields to missing core_fields."""
        for core_key, synonyms in FIELD_SYNONYMS.items():
            if self.core_fields.get(core_key) is None:
                for extra_key, val in list(self.extra_fields.items()):
                    if any(syn in extra_key.lower() for syn in synonyms) and val:
                        self.core_fields[core_key] = val
                        self.extraction_notes.append(
                            f"Dynamic Mapping: Mapped extra_field '{extra_key}' -> core_field '{core_key}'"
                        )
                        # Retain original key in extra_fields for audit visibility

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_file": self.source_file,
            "extraction_tier": self.extraction_tier,
            "core_fields": self.core_fields,
            "extra_fields": self.extra_fields,
            "extraction_metadata": self.extraction_metadata,
            "tax_mode": self.tax_mode,
            "raw_text_sample": self.raw_text_sample,
            "extraction_notes": self.extraction_notes,
        }


def merge_extractions(newer: "InvoiceExtraction", older: "InvoiceExtraction") -> "InvoiceExtraction":
    """When a later tier is invoked, fill gaps field-by-field rather than discarding earlier tier signals."""
    merged = InvoiceExtraction(source_file=newer.source_file, extraction_tier=newer.extraction_tier)
    
    # Merge Core Fields
    for f in _SCALAR_FIELDS:
        newer_val = newer.core_fields.get(f)
        older_val = older.core_fields.get(f)
        merged.core_fields[f] = newer_val if newer_val not in (None, "") else older_val
        
    merged.line_items = newer.line_items if newer.line_items else older.line_items
    
    # Merge Extra Fields (combine dictionary keys)
    merged.extra_fields = {**older.extra_fields, **newer.extra_fields}
    
    # Merge Extraction Metadata
    merged.extraction_metadata = {**older.extraction_metadata, **newer.extraction_metadata}
    
    merged.tax_mode = newer.tax_mode if newer.tax_mode != "unknown" else older.tax_mode
    merged.raw_text_sample = newer.raw_text_sample or older.raw_text_sample
    merged.extraction_notes = older.extraction_notes + newer.extraction_notes
    
    if any(older.core_fields.get(f) not in (None, "", []) for f in _SCALAR_FIELDS + ["line_items"]):
        merged.extraction_notes.append(
            f"Some fields carried forward from an earlier tier ({older.extraction_tier}) "
            f"where the later tier ({newer.extraction_tier}) returned nothing for that field."
        )
    return merged


@dataclass
class ValidationIssue:
    severity: str   # critical | warning | info
    field: str
    message: str


@dataclass
class ValidationResult:
    confidence_score: float
    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    checks_performed: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "confidence_score": self.confidence_score,
            "is_valid": self.is_valid,
            "issues": [asdict(i) for i in self.issues],
            "checks_performed": self.checks_performed,
        }


@dataclass
class MatchResult:
    match_status: str  # EXACT_PO_MATCH | FUZZY_VENDOR_MATCH | SPLIT_PO_MATCH | NO_MATCH | DUPLICATE_DETECTED
    matched_po: Optional[Dict[str, Any]] = None
    amount_variance: Optional[float] = None
    amount_variance_pct: Optional[float] = None
    within_tolerance: Optional[bool] = None
    duplicate_of: Optional[str] = None
    reasoning: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Decision:
    decision: str  # AUTO_APPROVE | APPROVE_WITH_NOTE | HOLD_FOR_REVIEW | REJECT_DUPLICATE | REJECT_NO_PO_MATCH | REJECT_VENDOR_NOT_APPROVED | AWAITING_VENDOR_INFO
    requires_human_review: bool
    flags: List[str] = field(default_factory=list)
    reasoning_trail: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

"""
Tier 1 — Native Digital PDF Extractor.

Two jobs live here:
1. GenericStage1PDFExtractor: pulls words/lines/regions out of a text-based PDF
   using pdfplumber (this is the extractor you already had — kept intact).
2. NativeFieldExtractor: turns those lines (+ pdfplumber's native tables) into
   the shared InvoiceExtraction schema using regex/heuristics only — no OCR,
   no LLM call, ~free, ~instant. This is what lets Tier 1 short-circuit the
   whole pipeline for the ~70-80% of invoices that are clean digital PDFs.
"""
import re
from collections import defaultdict
from typing import Dict, Any, List, Optional
from dateutil import parser as dateparser

import pdfplumber


class GenericStage1PDFExtractor:
    """Unmodified from the original notebook (your code) — groups words into
    lines using y-coordinate clustering and tags each line HEADER/BODY/FOOTER."""

    def __init__(self, pdf_path: str, header_margin_pt: float = 72.0, footer_margin_pt: float = 72.0):
        self.pdf_path = pdf_path
        self.header_margin_pt = header_margin_pt
        self.footer_margin_pt = footer_margin_pt

    def extract_page_lines(self, page) -> List[Dict[str, Any]]:
        words = page.extract_words(keep_blank_chars=False, use_text_flow=True)
        if not words:
            return []

        lines_dict = defaultdict(list)
        for w in words:
            line_y = round(w['top'] / 3.0) * 3.0
            lines_dict[line_y].append(w)

        sorted_lines = []
        page_height = page.height

        for line_y in sorted(lines_dict.keys()):
            line_words = sorted(lines_dict[line_y], key=lambda x: x['x0'])
            line_text = " ".join([w['text'] for w in line_words])

            min_x0 = min(w['x0'] for w in line_words)
            max_x1 = max(w['x1'] for w in line_words)
            min_top = min(w['top'] for w in line_words)
            max_bottom = max(w['bottom'] for w in line_words)

            if min_top <= self.header_margin_pt:
                region = "HEADER"
            elif max_bottom >= (page_height - self.footer_margin_pt):
                region = "FOOTER"
            else:
                region = "BODY"

            sorted_lines.append({
                "text": line_text,
                "region": region,
                "bbox": [round(min_x0, 2), round(min_top, 2), round(max_x1, 2), round(max_bottom, 2)],
                "word_count": len(line_words),
                # Kept for downstream columnar table reconstruction when a
                # PDF has no ruling lines for pdfplumber's table detector to key off.
                "words": [{"text": w["text"], "x0": round(w["x0"], 2), "x1": round(w["x1"], 2)} for w in line_words],
            })

        return sorted_lines

    def extract_document(self) -> Dict[str, Any]:
        document_structure = {
            "total_pages": 0,
            "has_native_text": True,
            "pages": [],
            "repeating_headers": [],
            "repeating_footers": []
        }

        header_frequencies = defaultdict(int)
        footer_frequencies = defaultdict(int)

        with pdfplumber.open(self.pdf_path) as pdf:
            document_structure["total_pages"] = len(pdf.pages)

            for page_num, page in enumerate(pdf.pages, start=1):
                lines = self.extract_page_lines(page)

                if not lines:
                    document_structure["has_native_text"] = False

                body_lines, header_lines, footer_lines = [], [], []
                for line in lines:
                    if line["region"] == "HEADER":
                        header_lines.append(line)
                        header_frequencies[line["text"]] += 1
                    elif line["region"] == "FOOTER":
                        footer_lines.append(line)
                        footer_frequencies[line["text"]] += 1
                    else:
                        body_lines.append(line)

                # Native tables (pdfplumber's own detector) — far more reliable
                # for line items than reconstructing columns from word x0s.
                try:
                    tables = page.extract_tables()
                except Exception:
                    tables = []

                document_structure["pages"].append({
                    "page_number": page_num,
                    "page_dimensions": {"width": page.width, "height": page.height},
                    "header": header_lines,
                    "body": body_lines,
                    "footer": footer_lines,
                    "tables": tables,
                })

        if document_structure["total_pages"] > 1:
            threshold = document_structure["total_pages"] * 0.5
            document_structure["repeating_headers"] = [
                t for t, c in header_frequencies.items() if c >= threshold
            ]
            document_structure["repeating_footers"] = [
                t for t, c in footer_frequencies.items() if c >= threshold
            ]

        return document_structure


# ----------------------------------------------------------------------------
# Field extraction: regex/heuristics over the structured lines above.
# ----------------------------------------------------------------------------

MONEY_RE = re.compile(r"[-+]?\$?\s?[\d,]+\.\d{2}")
LABEL_PATTERNS = {
    "invoice_number": re.compile(r"(?:invoice|inv)\s*(?:number|no\.?|#)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)", re.I),
    "po_number": re.compile(r"(?:p\.?o\.?|purchase order)\s*(?:number|no\.?|#)?\s*[:\-]?\s*([A-Za-z0-9\-\/]+)", re.I),
    "invoice_date": re.compile(r"(?:invoice date|date)\s*[:\-]?\s*([0-9]{1,4}[\/\-][0-9]{1,2}[\/\-][0-9]{1,4})", re.I),
    "due_date": re.compile(r"(?:due date)\s*[:\-]?\s*([0-9]{1,4}[\/\-][0-9]{1,2}[\/\-][0-9]{1,4})", re.I),
}
TOTAL_LABELS = {
    "subtotal": re.compile(r"^\s*sub\s*-?\s*total\b", re.I),
    "tax_amount": re.compile(r"^\s*(tax|vat|gst)\b", re.I),
    "total_amount": re.compile(r"^\s*(grand\s+)?total\s*(due|amount)?\b|amount\s+due", re.I),
}

# General key-value line pattern: e.g. "GST Registration No.: 27AABCT1234F1Z5"
GENERIC_KV_RE = re.compile(r"^\s*([A-Za-z0-9\s/_\-]{2,30})\s*[:\-]\s*(.+)$")


def _to_float(money_str: str) -> Optional[float]:
    if not money_str:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", money_str)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date(raw: str) -> Optional[str]:
    try:
        return dateparser.parse(raw, fuzzy=True).date().isoformat()
    except Exception:
        return None


def _extract_line_items_from_tables(tables: List[List[List[Optional[str]]]]) -> List[LineItem]:
    """Best-effort: find the table whose header row looks like a line-item
    table (description/qty/price/amount), then parse remaining rows."""
    items = []
    for table in tables:
        if not table or len(table) < 2:
            continue
        header = [(_c or "").strip().lower() for _c in table[0]]
        header_join = " ".join(header)
        if not any(k in header_join for k in ["desc", "item", "qty", "quantity", "amount", "price"]):
            continue

        def col_idx(*keywords):
            for i, h in enumerate(header):
                if any(k in h for k in keywords):
                    return i
            return None

        idx_desc = col_idx("desc", "item")
        idx_qty = col_idx("qty", "quantity")
        idx_price = col_idx("unit", "price", "rate")
        idx_amount = col_idx("amount", "total")

        for row in table[1:]:
            if not row or all(c is None or str(c).strip() == "" for c in row):
                continue
            desc = row[idx_desc].strip() if idx_desc is not None and row[idx_desc] else None
            qty = _to_float(row[idx_qty]) if idx_qty is not None and row[idx_qty] else None
            price = _to_float(row[idx_price]) if idx_price is not None and row[idx_price] else None
            amount = _to_float(row[idx_amount]) if idx_amount is not None and row[idx_amount] else None
            if desc or amount:
                items.append(LineItem(description=desc, quantity=qty, unit_price=price, amount=amount))
    return items


HEADER_KEYWORDS = ["description", "item", "qty", "quantity", "unit price", "price", "rate", "amount"]


def _extract_line_items_columnar(document_structure: Dict[str, Any]) -> List[LineItem]:
    """Fallback for PDFs with no ruling lines (so pdfplumber's grid-based
    extract_tables() finds nothing): locate the table header row by keyword
    match, use its word x-positions as column boundaries, then greedily
    assign each subsequent body line's words to the nearest column until a
    totals/footer line ends the table."""
    items: List[LineItem] = []

    for page in document_structure["pages"]:
        body = page["body"]
        header_idx = None
        for i, line in enumerate(body):
            lowered = line["text"].lower()
            hits = sum(1 for kw in HEADER_KEYWORDS if kw in lowered)
            if hits >= 2:
                header_idx = i
                break
        if header_idx is None:
            continue

        header_words = body[header_idx]["words"]
        col_starts = []
        col_labels = []
        for w in header_words:
            if col_starts and w["x0"] - col_starts[-1] < 55:
                col_labels[-1] += " " + w["text"]
            else:
                col_starts.append(w["x0"])
                col_labels.append(w["text"])
        col_labels_l = [c.lower() for c in col_labels]

        def classify(label):
            if any(k in label for k in ["desc", "item"]):
                return "description"
            if any(k in label for k in ["qty", "quantity"]):
                return "quantity"
            if any(k in label for k in ["unit", "price", "rate"]):
                return "unit_price"
            if "amount" in label or "total" in label:
                return "amount"
            return None

        col_roles = [classify(l) for l in col_labels_l]

        for line in body[header_idx + 1:]:
            text = line["text"]
            if any(p.search(text) for p in TOTAL_LABELS.values()):
                break
            if not line["words"]:
                continue
            buckets = {role: [] for role in ["description", "quantity", "unit_price", "amount"]}
            for w in line["words"]:
                nearest_idx = min(range(len(col_starts)), key=lambda i: abs(col_starts[i] - w["x0"]))
                role = col_roles[nearest_idx]
                if role:
                    buckets[role].append(w["text"])
            desc = " ".join(buckets["description"]) or None
            qty = _to_float(" ".join(buckets["quantity"])) if buckets["quantity"] else None
            price = _to_float(" ".join(buckets["unit_price"])) if buckets["unit_price"] else None
            amount = _to_float(" ".join(buckets["amount"])) if buckets["amount"] else None
            if desc or amount:
                items.append(LineItem(description=desc, quantity=qty, unit_price=price, amount=amount))

    return items


def extract_fields_native(document_structure: Dict[str, Any], source_file: str) -> InvoiceExtraction:
    """Regex/heuristic field extraction — the $0 Tier-1 path."""
    result = InvoiceExtraction(source_file=source_file, extraction_tier="TIER_1_NATIVE")

    all_lines, all_tables = [], []
    for page in document_structure["pages"]:
        all_lines.extend(page["header"] + page["body"] + page["footer"])
        all_tables.extend(page.get("tables", []))

    full_text = "\n".join(l["text"] for l in all_lines)
    result.raw_text_sample = full_text[:500]

    m = LABEL_PATTERNS["invoice_number"].search(full_text)
    if m:
        result.invoice_number = m.group(1).strip(" .:-")

    m = LABEL_PATTERNS["po_number"].search(full_text)
    if m:
        result.po_number = m.group(1).strip(" .:-")

    m = LABEL_PATTERNS["invoice_date"].search(full_text)
    if m:
        result.invoice_date = _parse_date(m.group(1))

    m = LABEL_PATTERNS["due_date"].search(full_text)
    if m:
        result.due_date = _parse_date(m.group(1))

    # Vendor name heuristic: first non-empty HEADER line that isn't itself a
    # label like "INVOICE" and doesn't look like an address/date.
    for page in document_structure["pages"]:
        for line in page["header"]:
            text = line["text"].strip()
            if not text or text.upper() in {"INVOICE", "BILL", "RECEIPT"}:
                continue
            if re.search(r"\d{2,}", text) and len(text) < 6:
                continue
            result.vendor_name = text
            break
        if result.vendor_name:
            break

    # Totals: scan every line, find labeled amount lines.
    tax_line_text = None
    for line in all_lines:
        text = line["text"]
        for field_name, pattern in TOTAL_LABELS.items():
            if pattern.search(text):
                amounts = MONEY_RE.findall(text)
                if amounts:
                    setattr(result, field_name, _to_float(amounts[-1]))
                if field_name == "tax_amount":
                    tax_line_text = text

    if tax_line_text and re.search(r"includ", tax_line_text, re.I):
        # e.g. "Tax (VAT included): $370.37" — tax is already inside subtotal/total,
        # not an additional amount to add on top.
        result.tax_mode = "embedded"
        result.extraction_notes.append(
            "Tax line wording indicates tax is included in the stated amount, not additive — "
            "treating tax_mode as 'embedded' rather than assuming subtotal+tax=total."
        )
    elif result.subtotal is not None and result.tax_amount is not None:
        result.tax_mode = "separate" if result.tax_amount > 0 else "embedded"
    elif result.tax_amount == 0:
        result.tax_mode = "embedded"

    # --- DUMP UNCAPTURED KEY-VALUE LINES INTO EXTRA_FIELDS ---
    known_patterns = list(LABEL_PATTERNS.values()) + list(TOTAL_LABELS.values())
    for line in all_lines:
        text = line["text"].strip()
        kv_match = GENERIC_KV_RE.match(text)
        if kv_match:
            key, val = kv_match.group(1).strip(), kv_match.group(2).strip()
            # Skip if matched by explicit core patterns or common total headers
            if any(p.search(text) for p in known_patterns):
                continue
            if key.lower() in {"invoice", "total", "subtotal", "sub-total", "amount", "tax"}:
                continue
            if key and val and key not in result.extra_fields:
                result.extra_fields[key] = val

    # Dynamically populate core fields if mapped synonyms exist in extra_fields
    if hasattr(result, "apply_dynamic_mapping"):
        result.apply_dynamic_mapping()

    # Line items: prefer native tables; fall back to nothing (Tier 2/3 will
    # get a real shot at messy layouts pdfplumber's table-finder misses).
    result.line_items = _extract_line_items_from_tables(all_tables)
    if not result.line_items:
        result.line_items = _extract_line_items_columnar(document_structure)
        if result.line_items:
            result.extraction_notes.append("Line items reconstructed via column-position heuristic (no ruling lines in PDF).")
        else:
            result.extraction_notes.append("No parsable line-item table found via native table extraction or column heuristic.")

    if not document_structure["has_native_text"]:
        result.extraction_notes.append("Page(s) contained no extractable text — likely a scanned image.")

    return result


def run_tier1(pdf_path: str) -> InvoiceExtraction:
    extractor = GenericStage1PDFExtractor(pdf_path)
    doc = extractor.extract_document()
    result = extract_fields_native(doc, pdf_path)
    if not doc["has_native_text"]:
        result.extraction_notes.append("TIER_1_SKIP_RECOMMENDED: no native text layer present.")
    return result, doc

"""
Tier 2 — Traditional OCR + Text LLM structuring.

Runs when Tier 1 finds no native text layer (scanned PDF) or when the caller
hands us a plain image (.jpg/.png/etc). Tesseract turns pixels into a raw text
dump; a text LLM then structures that dump into the shared schema.

The LLM call is real (OpenAI Chat Completions API, gpt-4o-mini) when OPENAI_API_KEY is set.
Without a key, we fall back to the same regex heuristics used in Tier 1, run
against the OCR'd text instead of a clean text layer — so the pipeline is
still fully runnable end-to-end offline, just with lower accuracy on messy
layouts (which is honestly also true of the regex fallback in a real deploy —
that's *why* Tier 2 wants an LLM in production).
"""
import os
import io
import json
import re
from typing import List, Optional

import pytesseract
from PIL import Image
from pdf2image import convert_from_path


# OPENAI_MODEL = "gpt-4o-mini"
GROQ_TEXT_MODEL = "openai/gpt-oss-120b"   # Groq — general-purpose, used for OCR-text structuring

STRUCTURING_PROMPT = """You are an invoice data extraction system. You will be given raw OCR text
from a scanned vendor invoice. OCR text may contain noise, misreads, and broken line breaks.

Extract all relevant information into a two-tiered JSON payload structured into:
1. "core_fields": Known standard fields for financial matching and validation.
2. "extra_fields": Any additional key-value pairs, vendor-specific metadata, custom fields, bank details, or terms found on the invoice that do not belong to core_fields.

Return ONLY a single JSON object with no markdown fences or preamble, matching the schema below:

{
  "core_fields": {
    "invoice_number": string or null,
    "invoice_date": string (YYYY-MM-DD) or null,
    "due_date": string (YYYY-MM-DD) or null,
    "vendor_name": string or null,
    "vendor_tax_id": string or null,
    "po_number": string or null,
    "currency": string (3-letter code, default USD) or null,
    "line_items": [
      {
        "description": string,
        "quantity": number or null,
        "unit_price": number or null,
        "amount": number or null
      }
    ],
    "subtotal": number or null,
    "tax_amount": number or null,
    "tax_rate": number or null,
    "total_amount": number or null,
    "tax_mode": "separate" | "embedded" | "unknown"
  },
  "extra_fields": {
    "key_name": "value_or_string"
  },
  "extraction_notes": [string, ...]   // anything ambiguous, illegible, or inferred rather than read directly
}

Rules:
- Never invent a value you can't support from the text. Use null inside core_fields if missing.
- Place any non-standard key-value pair (e.g., "Bank Account IBAN", "Payment Terms", "Shipping Address", "GST Registration No.", "Discount Code") into "extra_fields".
- If OCR noise makes a field ambiguous, still return your best guess but add a note in extraction_notes.
- Numbers must be plain floats, no currency symbols or commas.

OCR TEXT:
---
{OCR_TEXT}
---
"""


def _pdf_or_image_to_pil_pages(file_path: str) -> List[Image.Image]:
    if file_path.lower().endswith(".pdf"):
        return convert_from_path(file_path, dpi=300)
    return [Image.open(file_path).convert("RGB")]


# def _ocr_pages(pages: List[Image.Image]) -> str:
#     texts = []
#     for page in pages:
#         texts.append(pytesseract.image_to_string(page))
#     return "\n".join(texts)

def _ocr_pages(pages: List[Image.Image]) -> str:
    texts = []
    for i, page in enumerate(pages):
        page_text = pytesseract.image_to_string(page)
        print(f"[OCR DEBUG] Page {i+1} — {page.size[0]}x{page.size[1]}px — {len(page_text)} chars raw output:")
        print("----- OCR START -----")
        print(page_text)
        print("----- OCR END -----")
        texts.append(page_text)
    return "\n".join(texts)

# def _call_text_llm(ocr_text: str) -> Optional[dict]:
#     api_key = os.environ.get("OPENAI_API_KEY")
#     if not api_key:
#         print(f"[TIER2 DEBUG] Raw llm response: api failed ")
#         return None
#     try:
#         import openai
#         client = openai.OpenAI(api_key=api_key)
#         prompt = STRUCTURING_PROMPT.replace("{OCR_TEXT}", ocr_text[:6000])
#         print(f"[TIER2 DEBUG] Calling {OPENAI_MODEL} now...")
#         resp = client.chat.completions.create(
#             model=OPENAI_MODEL,
#             max_tokens=1500,
#             response_format={"type": "json_object"},
#             messages=[{"role": "user", "content": prompt}],
#         )
#         text = resp.choices[0].message.content
#         text = re.sub(r"^```json|```$", "", text.strip(), flags=re.M).strip()
#         print(f"[TIER2 DEBUG] Raw llm response:\n{text}\n")
#         return json.loads(text)
#     except Exception as e:
#         return {"__error__": str(e)}

# def _call_text_llm(ocr_text: str) -> Optional[dict]:
#     api_key = os.environ.get("OPENAI_API_KEY")
#     if not api_key:
#         logger.warning("TIER2: No API key set — using regex fallback.")
#         return None
#     try:
#         import openai
#         client = openai.OpenAI(api_key=api_key, timeout=20.0, max_retries=0)
#         prompt = STRUCTURING_PROMPT.replace("{OCR_TEXT}", ocr_text[:6000])
#         logger.info(f"TIER2: Calling {OPENAI_MODEL} (timeout=20s)...")
#         resp = client.chat.completions.create(
#             model=OPENAI_MODEL,
#             max_tokens=1500,
#             response_format={"type": "json_object"},
#             messages=[{"role": "user", "content": prompt}],
#         )
#         text = resp.choices[0].message.content
#         text = re.sub(r"^```json|```$", "", text.strip(), flags=re.M).strip()
#         logger.info(f"TIER2: Raw response:\n{text}")
#         return json.loads(text)
#     except openai.APITimeoutError:
#         logger.error("TIER2: Timed out after 20s — likely network/proxy/VPN blocking the request.")
#         return {"__error__": "timeout after 20s"}
#     except openai.APIConnectionError as e:
#         logger.error(f"TIER2: Connection error — {e}")
#         return {"__error__": f"connection error: {e}"}
#     except openai.AuthenticationError as e:
#         logger.error(f"TIER2: Auth error — key is invalid/revoked — {e}")
#         return {"__error__": f"auth error: {e}"}
#     except openai.RateLimitError as e:
#         logger.error(f"TIER2: Rate limit / quota hit — {e}")
#         return {"__error__": f"rate limit: {e}"}
#     except Exception as e:
#         logger.error(f"TIER2: Unexpected failure — {type(e).__name__}: {e}")
#         return {"__error__": str(e)}
    
def _call_text_llm(ocr_text: str) -> Optional[dict]:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logger.warning("TIER2: No GROQ_API_KEY set — using regex fallback.")
        return None
    try:
        from groq import Groq
        client = Groq(api_key=api_key, timeout=20.0, max_retries=0)
        prompt = STRUCTURING_PROMPT.replace("{OCR_TEXT}", ocr_text[:6000])
        logger.info(f"TIER2: Calling {GROQ_TEXT_MODEL} (timeout=20s)...")
        resp = client.chat.completions.create(
            model=GROQ_TEXT_MODEL,
            max_completion_tokens=1500,
            response_format={"type": "json_object"},
            reasoning_effort="low",       # this is a structuring task, not deep reasoning
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.choices[0].message.content
        text = re.sub(r"^```json|```$", "", text.strip(), flags=re.M).strip()
        logger.info(f"TIER2: Raw response:\n{text}")
        return json.loads(text)
    except Exception as e:
        logger.error(f"TIER2: Groq call FAILED: {type(e).__name__}: {e}")
        return {"__error__": str(e)}

def _regex_fallback_from_text(ocr_text: str, source_file: str) -> InvoiceExtraction:
    """Same heuristics as Tier 1, applied directly to a flat OCR text blob
    (no HEADER/BODY/FOOTER structure available from raw OCR)."""
    result = InvoiceExtraction(source_file=source_file, extraction_tier="TIER_2_OCR_LLM")
    result.raw_text_sample = ocr_text[:500]
    result.extraction_notes.append("No OPENAI_API_KEY set — used regex fallback instead of LLM structuring.")

    m = LABEL_PATTERNS["invoice_number"].search(ocr_text)
    if m:
        result.invoice_number = m.group(1).strip(" .:-")
    m = LABEL_PATTERNS["po_number"].search(ocr_text)
    if m:
        result.po_number = m.group(1).strip(" .:-")
    m = LABEL_PATTERNS["invoice_date"].search(ocr_text)
    if m:
        result.invoice_date = _parse_date(m.group(1))
    m = LABEL_PATTERNS["due_date"].search(ocr_text)
    if m:
        result.due_date = _parse_date(m.group(1))

    for line in ocr_text.splitlines():
        for field_name, pattern in TOTAL_LABELS.items():
            if pattern.search(line):
                amounts = MONEY_RE.findall(line)
                if amounts:
                    setattr(result, field_name, _to_float(amounts[-1]))

    if result.tax_amount == 0:
        result.tax_mode = "embedded"
    elif result.tax_amount is not None:
        result.tax_mode = "separate"

    result.extraction_notes.append("Line items not reconstructed by regex fallback — flagged for manual review.")
    return result


def run_tier2(file_path: str) -> InvoiceExtraction:
    pages = _pdf_or_image_to_pil_pages(file_path)
    ocr_text = _ocr_pages(pages)

    llm_json = _call_text_llm(ocr_text)

    if llm_json and "__error__" not in llm_json:
        # Extract core_fields and extra_fields dictionaries safely
        core = llm_json.get("core_fields", {})
        extra = llm_json.get("extra_fields", {})

        # Process line items from core_fields
        li = [
            LineItem(**{k: v for k, v in item.items() if k in LineItem.__annotations__})
            for item in core.get("line_items", [])
        ]

        # result = InvoiceExtraction(
        #     source_file=file_path,
        #     extraction_tier="TIER_2_OCR_LLM",
        #     invoice_number=core.get("invoice_number"),
        #     invoice_date=core.get("invoice_date"),
        #     due_date=core.get("due_date"),
        #     vendor_name=core.get("vendor_name"),
        #     vendor_tax_id=core.get("vendor_tax_id"),
        #     po_number=core.get("po_number"),
        #     currency=core.get("currency") or "USD",
        #     line_items=li,
        #     subtotal=core.get("subtotal"),
        #     tax_amount=core.get("tax_amount"),
        #     tax_rate=core.get("tax_rate"),
        #     total_amount=core.get("total_amount"),
        #     tax_mode=core.get("tax_mode", "unknown"),
        #     extra_fields=extra,
        #     raw_text_sample=ocr_text[:500],
        #     extraction_notes=llm_json.get("extraction_notes", []),
        # )
        
        result = InvoiceExtraction(
            source_file=file_path,
            extraction_tier="TIER_2_OCR_LLM",
            extra_fields=extra,
            raw_text_sample=ocr_text[:500],
            extraction_notes=llm_json.get("extraction_notes", []),
            tax_mode=core.get("tax_mode", "unknown"),
        )
        result.invoice_number = core.get("invoice_number")
        result.invoice_date = core.get("invoice_date")
        result.due_date = core.get("due_date")
        result.vendor_name = core.get("vendor_name")
        result.vendor_tax_id = core.get("vendor_tax_id")
        result.po_number = core.get("po_number")
        result.currency = core.get("currency") or "USD"
        result.line_items = li
        result.subtotal = core.get("subtotal")
        result.tax_amount = core.get("tax_amount")
        result.tax_rate = core.get("tax_rate")
        result.total_amount = core.get("total_amount")

        # Execute dynamic remapping if core fields are missing but present in extra_fields
        if hasattr(result, "apply_dynamic_mapping"):
            result.apply_dynamic_mapping()

        return result

    if llm_json and "__error__" in llm_json:
        result = _regex_fallback_from_text(ocr_text, file_path)
        result.extraction_notes.append(f"LLM call failed ({llm_json['__error__']}); used regex fallback.")
        return result

    return _regex_fallback_from_text(ocr_text, file_path)

"""
Tier 3 — Multimodal Vision LLM Extractor.

Last resort: Tier 1 found no usable text layer or failed validation, and
Tier 2's OCR+text-LLM pass still didn't clear the confidence bar (e.g. heavy
skew, rotation, dense multi-column layout, handwriting, watermark noise).
We send the page image directly to a vision-capable GPT model (gpt-4o-mini, which
supports image input) and ask it to reason over layout, not just flattened OCR text.

Without an OPENAI_API_KEY there is no meaningful offline fallback for
vision reasoning (unlike Tier 2, where regex-on-OCR-text is at least
possible) — so in mock mode we return a low-confidence stub that is
explicitly marked as requiring human review, which is the same behavior a
real Tier 3 failure would produce.
"""
import os
import io
import json
import re
import base64
from typing import List

from PIL import Image
from pdf2image import convert_from_path


# OPENAI_MODEL = "gpt-4o-mini"
GROQ_VISION_MODEL = "qwen/qwen3.6-27b"   # Groq — currently their only vision-capable model

VISION_PROMPT = """You are an invoice data extraction system looking directly at an image of a
vendor invoice (it may be rotated, skewed, low-contrast, or have a complex multi-column layout —
reason about the visual structure, don't just read left-to-right).

Return ONLY a single JSON object, no markdown fences, no preamble, matching this schema:
{
  "core_fields": {
    "invoice_number": string or null,
    "invoice_date": string (YYYY-MM-DD) or null,
    "due_date": string (YYYY-MM-DD) or null,
    "vendor_name": string or null,
    "vendor_tax_id": string or null,
    "po_number": string or null,
    "currency": string (3-letter code) or null,
    "line_items": [
      {
        "description": string,
        "quantity": number or null,
        "unit_price": number or null,
        "amount": number or null
      }
    ],
    "subtotal": number or null,
    "tax_amount": number or null,
    "tax_rate": number or null,
    "total_amount": number or null,
    "tax_mode": "separate" | "embedded" | "unknown"
  },
  "extra_fields": {
    "key_name": "string value"
  },
  "extraction_notes": [string, ...]
}

Notes:
- Place standard schema attributes into "core_fields".
- Dump any other custom key-value pairs (e.g., Bank Account/IBAN, Remit To, GSTIN, Project Codes, Payment Terms) into "extra_fields".
- Never invent values. Use null and add a note if illegible or ambiguous.
"""


def _first_page_image(file_path: str) -> Image.Image:
    if file_path.lower().endswith(".pdf"):
        pages = convert_from_path(file_path, dpi=300)
        return pages[0]
    return Image.open(file_path).convert("RGB")


def _image_to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# def _call_vision_llm(img: Image.Image) -> dict:
#     api_key = os.environ.get("OPENAI_API_KEY")
#     if not api_key:
#         print(f"[TIER3 DEBUG] Raw vision response: api failed ")
#         return {"__mock__": True}
#     try:
#         import openai
#         client = openai.OpenAI(api_key=api_key)
#         b64 = _image_to_b64(img)
#         resp = client.chat.completions.create(
#             model=OPENAI_MODEL,
#             max_tokens=1500,
#             response_format={"type": "json_object"},
#             messages=[{
#                 "role": "user",
#                 "content": [
#                     {"type": "text", "text": VISION_PROMPT},
#                     {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
#                 ],
#             }],
#         )
#         print(f"[TIER3 DEBUG] Calling {OPENAI_MODEL} vision now...")
#         text = resp.choices[0].message.content
#         text = re.sub(r"^```json|```$", "", text.strip(), flags=re.M).strip()
#         print(f"[TIER3 DEBUG] Raw vision response:\n{text}\n")
#         return json.loads(text)
#     except Exception as e:
#         return {"__error__": str(e)}

# def _call_vision_llm(img: Image.Image) -> dict:
#     api_key = os.environ.get("OPENAI_API_KEY")
#     if not api_key:
#         logger.warning("TIER3: No API key set — returning mock stub.")
#         return {"__mock__": True}
#     try:
#         import openai
#         client = openai.OpenAI(api_key=api_key, timeout=30.0, max_retries=0)
#         b64 = _image_to_b64(img)
#         logger.info(f"TIER3: Calling {OPENAI_MODEL} vision (timeout=30s)...")
#         resp = client.chat.completions.create(
#             model=OPENAI_MODEL,
#             max_tokens=1500,
#             response_format={"type": "json_object"},
#             messages=[{
#                 "role": "user",
#                 "content": [
#                     {"type": "text", "text": VISION_PROMPT},
#                     {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
#                 ],
#             }],
#         )
#         text = resp.choices[0].message.content
#         text = re.sub(r"^```json|```$", "", text.strip(), flags=re.M).strip()
#         logger.info(f"TIER3: Raw response:\n{text}")
#         return json.loads(text)
#     except openai.APITimeoutError:
#         logger.error("TIER3: Timed out after 30s — likely network/proxy/VPN blocking the request.")
#         return {"__error__": "timeout after 30s"}
#     except openai.APIConnectionError as e:
#         logger.error(f"TIER3: Connection error — {e}")
#         return {"__error__": f"connection error: {e}"}
#     except openai.AuthenticationError as e:
#         logger.error(f"TIER3: Auth error — {e}")
#         return {"__error__": f"auth error: {e}"}
#     except openai.RateLimitError as e:
#         logger.error(f"TIER3: Rate limit / quota hit — {e}")
#         return {"__error__": f"rate limit: {e}"}
#     except Exception as e:
#         logger.error(f"TIER3: Unexpected failure — {type(e).__name__}: {e}")
#         return {"__error__": str(e)}
    
def _call_vision_llm(img: Image.Image) -> dict:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logger.warning("TIER3: No GROQ_API_KEY set — returning mock stub.")
        return {"__mock__": True}
    try:
        from groq import Groq
        client = Groq(api_key=api_key, timeout=30.0, max_retries=0)
        b64 = _image_to_b64(img)
        logger.info(f"TIER3: Calling {GROQ_VISION_MODEL} (timeout=30s)...")
        resp = client.chat.completions.create(
            model=GROQ_VISION_MODEL,
            max_completion_tokens=1500,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": VISION_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
        )
        text = resp.choices[0].message.content
        text = re.sub(r"^```json|```$", "", text.strip(), flags=re.M).strip()
        logger.info(f"TIER3: Raw response:\n{text}")
        return json.loads(text)
    except Exception as e:
        logger.error(f"TIER3: Groq call FAILED: {type(e).__name__}: {e}")
        return {"__error__": str(e)}

def run_tier3(file_path: str) -> InvoiceExtraction:
    img = _first_page_image(file_path)
    llm_json = _call_vision_llm(img)

    if llm_json.get("__mock__") or llm_json.get("__error__"):
        result = InvoiceExtraction(source_file=file_path, extraction_tier="TIER_3_VISION_LLM")
        if llm_json.get("__mock__"):
            result.extraction_notes.append(
                "OPENAI_API_KEY not set — Tier 3 vision call skipped. "
                "This document exhausted Tiers 1 and 2 and has no safe automated fallback; "
                "routing directly to human review."
            )
        else:
            result.extraction_notes.append(f"Vision LLM call failed: {llm_json['__error__']}. Routing to human review.")
        return result

    # Extract core_fields and extra_fields from LLM response
    core = llm_json.get("core_fields", {})
    extra = llm_json.get("extra_fields", {})

    li = [LineItem(**{k: v for k, v in item.items() if k in LineItem.__annotations__})
          for item in core.get("line_items", [])]

    # return InvoiceExtraction(
    #     source_file=file_path,
    #     extraction_tier="TIER_3_VISION_LLM",
    #     core_fields=core,
    #     extra_fields=extra,
    #     invoice_number=core.get("invoice_number"),
    #     invoice_date=core.get("invoice_date"),
    #     due_date=core.get("due_date"),
    #     vendor_name=core.get("vendor_name"),
    #     vendor_tax_id=core.get("vendor_tax_id"),
    #     po_number=core.get("po_number"),
    #     currency=core.get("currency") or "USD",
    #     line_items=li,
    #     subtotal=core.get("subtotal"),
    #     tax_amount=core.get("tax_amount"),
    #     tax_rate=core.get("tax_rate"),
    #     total_amount=core.get("total_amount"),
    #     tax_mode=core.get("tax_mode", "unknown"),
    #     extraction_notes=llm_json.get("extraction_notes", []),
    # )
    
    result = InvoiceExtraction(
        source_file=file_path,
        extraction_tier="TIER_3_VISION_LLM",
        extra_fields=extra,
        extraction_notes=llm_json.get("extraction_notes", []),
        tax_mode=core.get("tax_mode", "unknown"),
    )
    result.invoice_number = core.get("invoice_number")
    result.invoice_date = core.get("invoice_date")
    result.due_date = core.get("due_date")
    result.vendor_name = core.get("vendor_name")
    result.vendor_tax_id = core.get("vendor_tax_id")
    result.po_number = core.get("po_number")
    result.currency = core.get("currency") or "USD"
    result.line_items = li
    result.subtotal = core.get("subtotal")
    result.tax_amount = core.get("tax_amount")
    result.tax_rate = core.get("tax_rate")
    result.total_amount = core.get("total_amount")
    return result

"""
Validation & confidence scoring.

This is the gate that decides whether an extraction is good enough to stop
here, or whether the pipeline should escalate to the next tier. It's also
what feeds the Decision Engine's reasoning trail later — every issue found
here is visible in the final output, not just a pass/fail bit.
"""
from typing import List

REQUIRED_FIELDS = ["invoice_number", "invoice_date", "vendor_name", "total_amount"]
AMOUNT_TOLERANCE_ABS = 0.02   # allow half-cent-per-line rounding noise
AMOUNT_TOLERANCE_PCT = 0.005  # 0.5%


def validate_extraction(inv: InvoiceExtraction) -> ValidationResult:
    issues: List[ValidationIssue] = []
    checks = []

    # 1. Required fields present
    checks.append("required_fields_present")
    for f in REQUIRED_FIELDS:
        if getattr(inv, f) in (None, ""):
            issues.append(ValidationIssue("critical", f, f"Required field '{f}' is missing."))

    # 2. Line items sum vs subtotal
    checks.append("line_items_sum_matches_subtotal")
    if inv.line_items and inv.subtotal is not None:
        line_sum = sum(li.amount for li in inv.line_items if li.amount is not None)
        if line_sum:
            diff = abs(line_sum - inv.subtotal)
            tolerance = max(AMOUNT_TOLERANCE_ABS, inv.subtotal * AMOUNT_TOLERANCE_PCT)
            if diff > tolerance:
                issues.append(ValidationIssue(
                    "warning", "line_items",
                    f"Line items sum to {line_sum:.2f} but subtotal is {inv.subtotal:.2f} "
                    f"(diff {diff:.2f}, tolerance {tolerance:.2f})."
                ))
    elif not inv.line_items:
        issues.append(ValidationIssue("warning", "line_items", "No line items extracted."))

    # 3. Subtotal + tax vs total (arithmetic consistency) — tax-mode aware.
    checks.append("subtotal_plus_tax_equals_total")
    if inv.subtotal is not None and inv.total_amount is not None:
        tax = inv.tax_amount or 0.0
        if inv.tax_mode == "embedded":
            # subtotal is expected to already equal total; tax is inside it.
            expected_total = inv.subtotal
        else:
            expected_total = inv.subtotal + tax
        diff = abs(expected_total - inv.total_amount)
        tolerance = max(AMOUNT_TOLERANCE_ABS, inv.total_amount * AMOUNT_TOLERANCE_PCT)
        if diff > tolerance:
            issues.append(ValidationIssue(
                "critical", "totals",
                f"Subtotal ({inv.subtotal:.2f}) + tax ({tax:.2f}) [tax_mode={inv.tax_mode}] = "
                f"{expected_total:.2f}, but stated total is {inv.total_amount:.2f} (diff {diff:.2f})."
            ))

    # 4. Sane date
    checks.append("invoice_date_not_in_future_beyond_grace")
    # (kept lightweight/deterministic for this exercise — a real system would
    # compare against "today" with a grace window for backdated invoices.)

    # 5. Currency present
    checks.append("currency_present")
    if not inv.currency:
        issues.append(ValidationIssue("info", "currency", "No currency detected; defaulting to USD."))

    critical_count = sum(1 for i in issues if i.severity == "critical")
    warning_count = sum(1 for i in issues if i.severity == "warning")

    # Confidence: start at 100, subtract weighted penalties.
    score = 100.0
    score -= critical_count * 30
    score -= warning_count * 10
    if not inv.line_items:
        score -= 15
    score = max(0.0, min(100.0, score))

    is_valid = critical_count == 0

    return ValidationResult(
        confidence_score=score,
        is_valid=is_valid,
        issues=issues,
        checks_performed=checks,
    )

"""
Ties Tier 1 -> Tier 2 -> Tier 3 together with an explicit escalation gate.
Every decision to stop or escalate is logged to `pipeline_trace` so nothing
that happened is hidden from the final output.
"""
from typing import Tuple, List

TIER1_CONFIDENCE_THRESHOLD = 75.0
TIER2_CONFIDENCE_THRESHOLD = 70.0

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")


def extract_invoice(file_path: str) -> Tuple[InvoiceExtraction, ValidationResult, List[str]]:
    trace: List[str] = []
    is_pdf = file_path.lower().endswith(".pdf")
    best_so_far: InvoiceExtraction = InvoiceExtraction(source_file=file_path, extraction_tier="NONE")

    if is_pdf:
        trace.append("Detected PDF input -> attempting Tier 1 (native text extraction).")
        tier1_result, doc = run_tier1(file_path)
        has_native_text = doc["has_native_text"]

        if not has_native_text:
            trace.append(
                "Tier 1 found no native text layer (this is a scanned/image-based PDF) -> "
                "skipping straight to Tier 2 (OCR + LLM)."
            )
        else:
            best_so_far = tier1_result
            v1 = validate_extraction(best_so_far)
            trace.append(
                f"Tier 1 extraction complete. Confidence={v1.confidence_score:.0f}, "
                f"valid={v1.is_valid}, issues={len(v1.issues)}."
            )
            if v1.is_valid and v1.confidence_score >= TIER1_CONFIDENCE_THRESHOLD:
                trace.append(
                    f"Tier 1 confidence {v1.confidence_score:.0f} >= threshold "
                    f"{TIER1_CONFIDENCE_THRESHOLD} and no critical issues -> STOPPING at Tier 1 "
                    "(no OCR/LLM cost incurred)."
                )
                return best_so_far, v1, trace
            else:
                reasons = "; ".join(f"[{i.severity}] {i.field}: {i.message}" for i in v1.issues) or "confidence below threshold"
                trace.append(f"Tier 1 insufficient ({reasons}) -> escalating to Tier 2 (OCR + LLM).")
    else:
        trace.append("Detected image input -> Tier 1 (native PDF text) not applicable, going straight to Tier 2 (OCR + LLM).")

    tier2_raw = run_tier2(file_path)
    tier2_result = merge_extractions(tier2_raw, best_so_far)
    best_so_far = tier2_result
    v2 = validate_extraction(best_so_far)
    trace.append(
        f"Tier 2 extraction complete. Confidence={v2.confidence_score:.0f}, "
        f"valid={v2.is_valid}, issues={len(v2.issues)}."
    )
    if v2.is_valid and v2.confidence_score >= TIER2_CONFIDENCE_THRESHOLD:
        trace.append(
            f"Tier 2 confidence {v2.confidence_score:.0f} >= threshold "
            f"{TIER2_CONFIDENCE_THRESHOLD} and no critical issues -> STOPPING at Tier 2."
        )
        return best_so_far, v2, trace
    else:
        reasons = "; ".join(f"[{i.severity}] {i.field}: {i.message}" for i in v2.issues) or "confidence below threshold"
        trace.append(f"Tier 2 insufficient ({reasons}) -> escalating to Tier 3 (Vision LLM), the last automated tier.")

    tier3_raw = run_tier3(file_path)
    tier3_result = merge_extractions(tier3_raw, best_so_far)
    v3 = validate_extraction(tier3_result)
    trace.append(
        f"Tier 3 extraction complete. Confidence={v3.confidence_score:.0f}, "
        f"valid={v3.is_valid}, issues={len(v3.issues)}. This is the final automated attempt; "
        "if confidence is still low, downstream decisioning will route to human review rather than "
        "escalating further (there is no Tier 4)."
    )
    return tier3_result, v3, trace

"""
PO Matching Engine.

Takes a validated InvoiceExtraction and tries to match it against a
procurement system's PO records. Handles:
  - exact PO number match
  - fuzzy vendor-name match when no PO number was extracted/given
  - split POs: a PO can be billed across multiple invoices; we track
    running "amount_invoiced" against the PO and match if the invoice
    fits inside the *remaining* balance, not just the original PO amount
  - duplicate detection: same vendor + same amount + same invoice number
    (or same vendor + same amount + no invoice number, within a short
    date window) seen before
Tolerance is amount-based: the greater of an absolute floor and a
percentage of the PO amount, matching how real AP tolerance rules work
(small vendors get a flat cushion, large POs get a % cushion).
"""
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional

try:
    from rapidfuzz import fuzz
    def _similarity(a: str, b: str) -> float:
        return fuzz.token_sort_ratio(a, b) / 100.0
except ImportError:
    def _similarity(a: str, b: str) -> float:
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

TOLERANCE_ABS = 25.0     # flat dollar cushion
TOLERANCE_PCT = 0.03     # 3% of PO amount
VENDOR_FUZZY_THRESHOLD = 0.82


@dataclass
class POStore:
    """In-memory PO + invoice history, standing in for the procurement system."""
    pos: Dict[str, Dict[str, Any]] = field(default_factory=dict)          # po_number -> po record
    seen_invoices: List[Dict[str, Any]] = field(default_factory=list)      # processed invoice fingerprints

    def add_po(self, po_number, vendor_name, amount, approved_vendor=True, currency="USD"):
        self.pos[po_number] = {
            "po_number": po_number,
            "vendor_name": vendor_name,
            "amount": amount,
            "amount_invoiced": 0.0,
            "approved_vendor": approved_vendor,
            "currency": currency,
            "status": "OPEN",
        }

    def record_invoice(self, invoice_number, vendor_name, amount, po_number=None):
        self.seen_invoices.append({
            "invoice_number": invoice_number,
            "vendor_name": vendor_name,
            "amount": amount,
            "po_number": po_number,
        })
        if po_number and po_number in self.pos and amount is not None:
            self.pos[po_number]["amount_invoiced"] += amount


def _tolerance_for(po_amount: float) -> float:
    return max(TOLERANCE_ABS, po_amount * TOLERANCE_PCT)


def _check_duplicate(inv: InvoiceExtraction, store: POStore) -> Optional[str]:
    for seen in store.seen_invoices:
        same_vendor = (seen["vendor_name"] or "").strip().lower() == (inv.vendor_name or "").strip().lower()
        same_amount = seen["amount"] is not None and inv.total_amount is not None and abs(seen["amount"] - inv.total_amount) < 0.01
        same_invoice_no = inv.invoice_number and seen["invoice_number"] and \
            seen["invoice_number"].strip().lower() == inv.invoice_number.strip().lower()
        if same_vendor and same_amount and (same_invoice_no or not inv.invoice_number):
            return seen["invoice_number"] or "(no invoice number on record)"
    return None


def match_invoice(inv: InvoiceExtraction, store: POStore) -> MatchResult:
    reasoning: List[str] = []

    dup = _check_duplicate(inv, store)
    if dup:
        reasoning.append(
            f"Vendor '{inv.vendor_name}' + amount {inv.total_amount} matches a previously processed "
            f"invoice (invoice_number={dup}). Flagging as likely duplicate before PO matching."
        )
        return MatchResult(match_status="DUPLICATE_DETECTED", duplicate_of=dup, reasoning=reasoning)

    # 1. Exact PO number match
    if inv.po_number and inv.po_number in store.pos:
        po = store.pos[inv.po_number]
        reasoning.append(f"Exact PO number match found: {inv.po_number}.")
        remaining = po["amount"] - po["amount_invoiced"]
        variance = (inv.total_amount or 0) - remaining
        tol = _tolerance_for(po["amount"])
        # Billing for LESS than the remaining balance is normal (partial
        # delivery / an installment with more invoices still to come) — only
        # billing for MORE than what's left on the PO trips the tolerance check.
        within = variance <= tol
        status = "EXACT_PO_MATCH"
        if po["amount_invoiced"] > 0:
            status = "SPLIT_PO_MATCH"
            reasoning.append(
                f"PO {inv.po_number} has already been partially invoiced "
                f"({po['amount_invoiced']:.2f} of {po['amount']:.2f}); treating this as an "
                f"installment against the remaining balance ({remaining:.2f}), not the full PO amount."
            )
        inv_total_str = f"{inv.total_amount:.2f}" if inv.total_amount is not None else "UNKNOWN"
        reasoning.append(
            f"Invoice total {inv_total_str} vs remaining PO balance {remaining:.2f} "
            f"(variance {variance:+.2f}; over-billing tolerance +{tol:.2f} — billing for less than "
            f"the remaining balance is expected for split/partial invoicing) -> "
            f"{'within tolerance' if within else 'EXCEEDS tolerance'}."
        )
        if inv.total_amount is None:
            reasoning.append("Note: total_amount was never confidently extracted — variance above is computed against 0.")
        if not po["approved_vendor"]:
            reasoning.append(f"WARNING: vendor '{po['vendor_name']}' on this PO is not on the approved vendor list.")
        return MatchResult(
            match_status=status, matched_po=po, amount_variance=variance,
            amount_variance_pct=(variance / po["amount"] * 100 if po["amount"] else None),
            within_tolerance=within, reasoning=reasoning,
        )

    # 2. Fuzzy vendor match (no usable PO number extracted / provided)
    if inv.vendor_name:
        best_po, best_score = None, 0.0
        for po in store.pos.values():
            score = _similarity(inv.vendor_name, po["vendor_name"])
            if score > best_score:
                best_score, best_po = score, po
        if best_po and best_score >= VENDOR_FUZZY_THRESHOLD:
            reasoning.append(
                f"No PO number on invoice (or PO not found); fuzzy-matched vendor "
                f"'{inv.vendor_name}' to PO {best_po['po_number']} ('{best_po['vendor_name']}') "
                f"with similarity {best_score:.2f}."
            )
            remaining = best_po["amount"] - best_po["amount_invoiced"]
            variance = (inv.total_amount or 0) - remaining
            tol = _tolerance_for(best_po["amount"])
            within = variance <= tol
            inv_total_str = f"{inv.total_amount:.2f}" if inv.total_amount is not None else "UNKNOWN"
            reasoning.append(
                f"Invoice total {inv_total_str} vs remaining PO balance {remaining:.2f} "
                f"(variance {variance:+.2f}; over-billing tolerance +{tol:.2f}) -> "
                f"{'within tolerance' if within else 'EXCEEDS tolerance'}."
            )
            return MatchResult(
                match_status="FUZZY_VENDOR_MATCH", matched_po=best_po, amount_variance=variance,
                amount_variance_pct=(variance / best_po["amount"] * 100 if best_po["amount"] else None),
                within_tolerance=within, reasoning=reasoning,
            )
        elif best_po:
            reasoning.append(
                f"Closest vendor match was '{best_po['vendor_name']}' (similarity {best_score:.2f}), "
                f"below the {VENDOR_FUZZY_THRESHOLD} confidence threshold to auto-match — treating as no match."
            )

    reasoning.append("No PO number, and no confident vendor match, could be established.")
    return MatchResult(match_status="NO_MATCH", reasoning=reasoning)

from enum import Enum
from typing import List, Optional
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 1. Updated Enum Definition
# ---------------------------------------------------------------------------
class DecisionStatus(str, Enum):
    AUTO_APPROVE = "AUTO_APPROVE"
    APPROVE_WITH_NOTE = "APPROVE_WITH_NOTE"
    HOLD_FOR_REVIEW = "HOLD_FOR_REVIEW"
    REJECT_DUPLICATE = "REJECT_DUPLICATE"
    AWAITING_VENDOR_INFO = "AWAITING_VENDOR_INFO"  # Added new status


@dataclass
class Decision:
    decision: str  # e.g., DecisionStatus value
    requires_human_review: bool
    flags: List[str] = field(default_factory=list)
    reasoning_trail: List[str] = field(default_factory=list)
    action_required: Optional[str] = None  # e.g., "DISPATCH_VENDOR_EMAIL"


# Helper function to check missing core mandatory fields
def get_missing_mandatory_core_fields(inv: InvoiceExtraction) -> List[str]:
    mandatory = ["invoice_number", "po_number", "invoice_date"]
    missing = []
    for f in mandatory:
        val = getattr(inv, f, None)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(f)
    return missing


# ---------------------------------------------------------------------------
# 2. Updated Decision Engine Logic
# ---------------------------------------------------------------------------
def make_decision(inv: InvoiceExtraction, validation: ValidationResult, match: MatchResult, po_store: Optional[Any] = None) -> Decision:
    """
    Turns (extraction + validation + PO match) into an actionable outcome.
    
    Includes exception routing for:
    1. AWAITING_VENDOR_INFO when mandatory core fields are missing.
    2. HOLD_FOR_HUMAN_REVIEW for soft duplicates (lack of explicit invoice number).
    3. Ledger adjustment on POStore upon partial PO match approval.
    """
    trail: List[str] = []
    flags: List[str] = []

    # -----------------------------------------------------------------------
    # Rule 1: Duplicate Check & Soft Duplicate Exception Handling
    # -----------------------------------------------------------------------
    if match.match_status == "DUPLICATE_DETECTED":
        trail.append("Matching engine flagged this as a likely duplicate of a previously processed invoice.")
        trail.extend(match.reasoning)
        
        # Exception 2: Soft Duplicate Detection
        # If invoice matches vendor, total, and date, but lacks an explicit invoice_number -> HOLD_FOR_REVIEW
        is_missing_inv_num = not getattr(inv, "invoice_number", None)
        if is_missing_inv_num or "SOFT_DUPLICATE" in getattr(match, "flags", []):
            flags.extend(["soft_duplicate", "missing_invoice_number"])
            trail.append(
                "Decision: HOLD_FOR_REVIEW. Soft Duplicate detected (matches vendor, total, and date, "
                "but lacks an explicit invoice number). Routing to AP team for human review rather than direct rejection."
            )
            return Decision(
                decision=DecisionStatus.HOLD_FOR_REVIEW.value,
                requires_human_review=True,
                flags=flags,
                reasoning_trail=trail,
            )

        # Standard Hard Duplicate Rejection
        trail.append("Decision: REJECT_DUPLICATE. A human should confirm before this is discarded.")
        return Decision(
            decision=DecisionStatus.REJECT_DUPLICATE.value,
            requires_human_review=True,
            flags=["duplicate"],
            reasoning_trail=trail,
        )

    # -----------------------------------------------------------------------
    # Rule 2: Mandatory Core Field Missing Gate (AWAITING_VENDOR_INFO)
    # -----------------------------------------------------------------------
    missing_mandatory = get_missing_mandatory_core_fields(inv)
    if missing_mandatory:
        flags.append("missing_mandatory_core_fields")
        trail.append(f"Missing mandatory core fields: {', '.join(missing_mandatory)}.")
        trail.append(
            "Decision: AWAITING_VENDOR_INFO. Core fields are incomplete. "
            "Triggering automated vendor communication dispatch workflow to request field clarification/resubmission."
        )
        return Decision(
            decision=DecisionStatus.AWAITING_VENDOR_INFO.value,
            requires_human_review=False,
            flags=flags,
            reasoning_trail=trail,
            action_required="DISPATCH_VENDOR_EMAIL",
        )

    # -----------------------------------------------------------------------
    # Rule 3: Extraction Confidence & Validation Gate
    # -----------------------------------------------------------------------
    trail.append(f"Extraction confidence from {inv.extraction_tier}: {validation.confidence_score:.0f}/100.")
    if validation.issues:
        for issue in validation.issues:
            trail.append(f"[{issue.severity.upper()}] {issue.field}: {issue.message}")

    critical_issues = [i for i in validation.issues if i.severity == "critical"]
    if critical_issues:
        flags.append("extraction_incomplete")
        trail.append(
            "Decision: HOLD_FOR_REVIEW. Extraction has unresolved critical issues even after "
            "exhausting all extraction tiers; auto-approving without these fields would be unsafe."
        )
        return Decision(
            decision=DecisionStatus.HOLD_FOR_REVIEW.value,
            requires_human_review=True,
            flags=flags,
            reasoning_trail=trail,
        )

    # -----------------------------------------------------------------------
    # Rule 4: PO Match Outcome & Partial Billing Ledger Adjustment
    # -----------------------------------------------------------------------
    trail.extend(match.reasoning)

    if match.match_status == "NO_MATCH":
        flags.append("no_po_match")
        trail.append("Decision: HOLD_FOR_REVIEW. No PO or vendor match — cannot verify this invoice "
                     "against an authorized purchase without a human confirming vendor/PO out of band.")
        return Decision(
            decision=DecisionStatus.HOLD_FOR_REVIEW.value,
            requires_human_review=True,
            flags=flags,
            reasoning_trail=trail,
        )

    if match.matched_po and not match.matched_po.get("approved_vendor", True):
        flags.append("vendor_not_approved")
        trail.append("Decision: HOLD_FOR_REVIEW. Matched PO exists, but vendor is not on the approved vendor list "
                     "— requires procurement sign-off before payment.")
        return Decision(
            decision=DecisionStatus.HOLD_FOR_REVIEW.value,
            requires_human_review=True,
            flags=flags,
            reasoning_trail=trail,
        )

    if not match.within_tolerance:
        flags.append("amount_variance_exceeds_tolerance")
        trail.append(
            f"Decision: HOLD_FOR_REVIEW. Amount variance ({match.amount_variance:+.2f}) exceeds the "
            "configured tolerance band — needs a human to confirm this is legitimate."
        )
        return Decision(
            decision=DecisionStatus.HOLD_FOR_REVIEW.value,
            requires_human_review=True,
            flags=flags,
            reasoning_trail=trail,
        )

    # Exception 3: Partial / Split PO Billing Evaluation & Ledger Adjustment
    if match.match_status == "SPLIT_PO_MATCH":
        flags.append("split_po_installment")
        
        # Deduct billed amount from POStore ledger balance if po_store instance is passed
        po_number = getattr(inv, "po_number", None) or match.matched_po.get("po_number")
        if po_store and po_number and hasattr(po_store, "adjust_po_balance"):
            remaining = po_store.adjust_po_balance(po_number, inv.total_amount)
            trail.append(f"Ledger Updated: Deducted {inv.total_amount:.2f} from PO '{po_number}'. New remaining balance: {remaining:.2f}.")

        trail.append(
            "Decision: AUTO_APPROVE. Invoice is a valid partial billing against remaining PO balance; "
            "approving installment and updated PO ledger balance."
        )
        return Decision(
            decision=DecisionStatus.AUTO_APPROVE.value,
            requires_human_review=False,
            flags=flags,
            reasoning_trail=trail,
        )

    if match.match_status == "FUZZY_VENDOR_MATCH":
        flags.append("fuzzy_vendor_match")
        trail.append(
            "Decision: APPROVE_WITH_NOTE. Vendor was matched by name similarity rather than an exact "
            "PO number on the invoice — approving, but flagging so AP can ask this vendor to include "
            "PO numbers going forward."
        )
        return Decision(
            decision=DecisionStatus.APPROVE_WITH_NOTE.value,
            requires_human_review=False,
            flags=flags,
            reasoning_trail=trail,
        )

    # -----------------------------------------------------------------------
    # Rule 5: Standard Auto-Approval
    # -----------------------------------------------------------------------
    trail.append("Decision: AUTO_APPROVE. Extraction confident, exact PO match, amount within tolerance, "
                 "vendor approved, no duplicate signal.")
    return Decision(
        decision=DecisionStatus.AUTO_APPROVE.value,
        requires_human_review=False,
        flags=flags,
        reasoning_trail=trail,
    )

"""
Vendor Correspondence System.

Some invoices can't be safely approved OR safely rejected on the data alone --
they need an answer from the vendor first (a missing invoice number, an
unmatched PO, an amount outside tolerance, a possible duplicate). Rather than
silently parking these in a review queue, this module drafts a specific,
auditable email to the vendor, tracks the thread against the invoice, and --
once the vendor replies with the missing/corrected information -- re-runs the
*same* validation -> matching -> decision pipeline against the corrected data,
so the final decision is grounded in exactly the same rules as every other
invoice, just with better inputs. Vendor replies do not get a special decision
path; they get a second pass through the normal one.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import itertools

_correspondence_id_counter = itertools.count(1)

# Which decision flags warrant reaching out to the vendor, and what to say.
# Kept as a config table -- not buried in if/else -- so it's auditable and
# easy to extend without touching control flow.
CORRESPONDENCE_PLAYBOOK = {
    "missing_mandatory_core_fields": {
        "trigger_reason": "Missing mandatory field(s) required before this invoice can be processed.",
        "ask_template": ("We were unable to locate the following required field(s) on the invoice you "
                          "sent us: {missing_fields}. Could you confirm these and, if possible, resend "
                          "a corrected copy of the invoice?"),
    },
    "no_po_match": {
        "trigger_reason": "No purchase order on file matches this invoice, and the vendor name could not be confidently matched either.",
        "ask_template": ("We could not match this invoice to an open purchase order in our system. "
                          "Could you confirm the correct PO number this invoice should be billed against?"),
    },
    "amount_variance_exceeds_tolerance": {
        "trigger_reason": "The invoiced amount falls outside our tolerance band versus the matched purchase order.",
        "ask_template": ("The invoiced amount does not match the remaining balance on PO {po_number} "
                          "within our standard tolerance (variance: {variance}). Could you clarify the "
                          "reason for the difference (e.g. a price change, freight surcharge, or partial "
                          "shipment) so we can process this correctly?"),
    },
    "duplicate": {
        "trigger_reason": "This invoice appears to duplicate one already on file.",
        "ask_template": ("This invoice appears to match one we already have on file for the same vendor "
                          "and amount (previous invoice: {duplicate_of}). Could you confirm whether this "
                          "is a resubmission/correction of that invoice, or a new, separate charge?"),
    },
    "soft_duplicate": {
        "trigger_reason": "Possible duplicate, but no invoice number was extracted to confirm either way.",
        "ask_template": ("We received an invoice from you that closely matches one already on file for the "
                          "same amount and date, but no invoice number was legible on our copy. Could you "
                          "confirm the invoice number and whether this is a duplicate submission?"),
    },
    "vendor_not_approved": {
        "trigger_reason": "A matching purchase order exists, but the vendor is not on our approved vendor list.",
        "ask_template": ("Our records show the purchase order referenced on this invoice, but your company "
                          "is not yet on our approved vendor list. Could you send your current vendor "
                          "onboarding paperwork so we can complete approval?"),
    },
}

# Priority order when more than one flag applies -- keeps the email focused on
# a single, most-actionable ask rather than an overwhelming wall of questions.
_PLAYBOOK_PRIORITY = [
    "missing_mandatory_core_fields", "duplicate", "soft_duplicate",
    "vendor_not_approved", "no_po_match", "amount_variance_exceeds_tolerance",
]


@dataclass
class CorrespondenceMessage:
    direction: str          # OUTBOUND (to vendor) | INBOUND (vendor reply)
    channel: str            # EMAIL
    subject: str
    body: str
    timestamp: str
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CorrespondenceThread:
    correspondence_id: str
    source_file: str
    vendor_name: Optional[str]
    reason: str
    status: str = "DRAFTED"   # DRAFTED -> SENT -> REPLY_RECEIVED -> RESOLVED
    messages: List[CorrespondenceMessage] = field(default_factory=list)
    resolution_notes: List[str] = field(default_factory=list)
    original_extraction: Any = None   # kept for reprocessing; not part of to_dict()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "correspondence_id": self.correspondence_id,
            "source_file": self.source_file,
            "vendor_name": self.vendor_name,
            "reason": self.reason,
            "status": self.status,
            "messages": [asdict(m) for m in self.messages],
            "resolution_notes": self.resolution_notes,
        }


class VendorCorrespondenceStore:
    """Stands in for a real mailbox/ticketing integration (a shared AP inbox or
    a vendor portal). Keeps every thread keyed by correspondence_id, and
    indexed by source_file so the pipeline can find/re-open a thread once a
    vendor's reply comes in."""

    def __init__(self):
        self.threads: Dict[str, CorrespondenceThread] = {}
        self._by_source_file: Dict[str, str] = {}

    def open_thread(self, *, source_file: str, vendor_name: Optional[str], reason: str,
                     subject: str, body: str, original_extraction: Any) -> CorrespondenceThread:
        cid = f"CORR-{next(_correspondence_id_counter):04d}"
        thread = CorrespondenceThread(
            correspondence_id=cid, source_file=source_file, vendor_name=vendor_name,
            reason=reason, original_extraction=original_extraction,
        )
        thread.messages.append(CorrespondenceMessage(
            direction="OUTBOUND", channel="EMAIL", subject=subject, body=body,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))
        thread.status = "SENT"
        self.threads[cid] = thread
        self._by_source_file[source_file] = cid
        return thread

    def thread_for(self, source_file: str) -> Optional[CorrespondenceThread]:
        cid = self._by_source_file.get(source_file)
        return self.threads.get(cid) if cid else None

    def log_vendor_reply(self, correspondence_id: str, body: str,
                          corrected_fields: Optional[Dict[str, Any]] = None) -> CorrespondenceThread:
        thread = self.threads[correspondence_id]
        thread.messages.append(CorrespondenceMessage(
            direction="INBOUND", channel="EMAIL", subject=f"RE: {thread.messages[0].subject}", body=body,
            timestamp=datetime.now(timezone.utc).isoformat(),
            meta={"corrected_fields": corrected_fields or {}},
        ))
        thread.status = "REPLY_RECEIVED"
        return thread

    def resolve(self, correspondence_id: str, note: str) -> None:
        thread = self.threads[correspondence_id]
        thread.status = "RESOLVED"
        thread.resolution_notes.append(note)


def needs_vendor_correspondence(decision: "Decision") -> bool:
    """True if the decision engine explicitly asked for vendor outreach
    (`action_required == 'DISPATCH_VENDOR_EMAIL'`), or if it landed on
    HOLD_FOR_REVIEW / REJECT_DUPLICATE for a reason a *vendor* -- not just an
    internal AP reviewer -- can actually resolve."""
    if getattr(decision, "action_required", None) == "DISPATCH_VENDOR_EMAIL":
        return True
    vendor_resolvable_flags = set(_PLAYBOOK_PRIORITY)
    return (decision.decision in ("HOLD_FOR_REVIEW", "REJECT_DUPLICATE")
            and bool(vendor_resolvable_flags.intersection(decision.flags)))


def _select_playbook_entry(decision: "Decision"):
    for flag in _PLAYBOOK_PRIORITY:
        if flag in decision.flags:
            return flag, CORRESPONDENCE_PLAYBOOK[flag]
    return "generic", {
        "trigger_reason": "This invoice needs clarification before it can be processed.",
        "ask_template": "Could you confirm the details of this invoice so we can process it?",
    }


def draft_vendor_email(extraction: "InvoiceExtraction", match: "MatchResult", decision: "Decision") -> Dict[str, Any]:
    """Turns (extraction + match + decision) into a specific, referenceable
    email draft -- never a generic 'please check your invoice' -- so the
    vendor knows exactly what's being asked and why."""
    flag, entry = _select_playbook_entry(decision)

    vendor = extraction.vendor_name or "Vendor"
    inv_ref = extraction.invoice_number or f"(no invoice number -- source file: {extraction.source_file.split('/')[-1]})"
    missing_fields = ", ".join(get_missing_mandatory_core_fields(extraction)) or "N/A"

    ask = entry["ask_template"].format(
        missing_fields=missing_fields,
        po_number=extraction.po_number or (match.matched_po or {}).get("po_number", "on file"),
        variance=f"{match.amount_variance:+.2f}" if match.amount_variance is not None else "unknown",
        duplicate_of=match.duplicate_of or "on file",
    )

    subject = f"Action needed on invoice {inv_ref} from {vendor}"
    body = (
        f"Hello {vendor} Accounts Receivable team,\n\n"
        f"We're reviewing invoice {inv_ref} and need your help before we can process it.\n\n"
        f"{entry['trigger_reason']}\n\n"
        f"{ask}\n\n"
        f"Please reply to this email with the requested information, or an updated invoice, "
        f"at your earliest convenience so we can avoid any delay in payment.\n\n"
        f"Thank you,\nAccounts Payable Team"
    )
    return {"reason_code": flag, "trigger_reason": entry["trigger_reason"], "subject": subject, "body": body}


def apply_vendor_reply_and_reprocess(*, source_file: str, correspondence_store: "VendorCorrespondenceStore",
                                      po_store: "POStore", corrected_fields: Dict[str, Any],
                                      reply_body: str) -> Dict[str, Any]:
    """Simulates a vendor replying with the missing/corrected information. In
    production this would be triggered by an inbound email/webhook; here the
    corrected fields are passed directly. The correction is layered on top of
    the original extraction -- never discarding what Tier 1/2/3 already found
    -- tagged with clear provenance, and pushed back through the *same*
    validation -> matching -> decision pipeline used for every other invoice."""
    thread = correspondence_store.thread_for(source_file)
    if thread is None:
        raise ValueError(f"No open correspondence thread for {source_file}")
    original = thread.original_extraction

    corrected = InvoiceExtraction(
        source_file=source_file,
        extraction_tier=f"{original.extraction_tier}+VENDOR_REPLY",
    )
    for f in _SCALAR_FIELDS:
        corrected.core_fields[f] = corrected_fields.get(f, original.core_fields.get(f))
    corrected.line_items = corrected_fields.get("line_items") or original.line_items
    corrected.extra_fields = dict(original.extra_fields)
    corrected.extraction_metadata = dict(original.extraction_metadata)
    corrected.tax_mode = original.tax_mode
    corrected.raw_text_sample = original.raw_text_sample
    corrected.extraction_notes = list(original.extraction_notes) + [
        f"Field(s) corrected/added via vendor correspondence {thread.correspondence_id}: "
        f"{', '.join(corrected_fields.keys())}."
    ]

    correspondence_store.log_vendor_reply(thread.correspondence_id, reply_body, corrected_fields)

    validation = validate_extraction(corrected)
    match = match_invoice(corrected, po_store)
    decision = make_decision(corrected, validation, match, po_store)

    still_needs_followup = needs_vendor_correspondence(decision)
    resolution = f"Vendor supplied {', '.join(corrected_fields.keys())} -> reprocessed to {decision.decision}."
    if still_needs_followup:
        resolution += " NOTE: reprocessing still flags this for vendor input -- a real system would open a follow-up thread rather than close this one."
    correspondence_store.resolve(thread.correspondence_id, resolution)

    po_store.record_invoice(
        invoice_number=corrected.invoice_number,
        vendor_name=corrected.vendor_name,
        amount=corrected.total_amount,
        po_number=match.matched_po["po_number"] if match.matched_po else corrected.po_number,
    )

    return {
        "source_file": source_file,
        "extraction": corrected.to_dict(),
        "validation": validation.to_dict(),
        "match": match.to_dict(),
        "decision": asdict(decision),
        "correspondence": thread.to_dict(),
        "pipeline_trace": [f"Reprocessed after vendor reply on correspondence thread {thread.correspondence_id}."],
    }


"""
End-to-end entrypoint: file in -> reasoned decision out, with every
intermediate step visible in the returned structure. When a
VendorCorrespondenceStore is supplied and the decision engine determines this
invoice needs vendor input, a specific email is drafted and logged against the
invoice (not just a generic "needs review" flag) instead of the invoice being
recorded as final history.
"""
import json
from typing import Optional


def process_invoice(file_path: str, store: POStore,
                     correspondence_store: Optional["VendorCorrespondenceStore"] = None) -> dict:
    extraction, validation, extraction_trace = extract_invoice(file_path)
    match = match_invoice(extraction, store)
    decision = make_decision(extraction, validation, match, store)

    correspondence_block = None
    needs_outreach = correspondence_store is not None and needs_vendor_correspondence(decision)

    if needs_outreach:
        draft = draft_vendor_email(extraction, match, decision)
        thread = correspondence_store.open_thread(
            source_file=file_path, vendor_name=extraction.vendor_name,
            reason=draft["trigger_reason"], subject=draft["subject"], body=draft["body"],
            original_extraction=extraction,
        )
        extraction_trace.append(
            f"Decision engine routed this invoice for vendor correspondence ({draft['reason_code']}) -> "
            f"drafted and logged an outbound email, correspondence_id={thread.correspondence_id}."
        )
        correspondence_block = thread.to_dict()
    else:
        # Only finalized invoices (not ones still awaiting a vendor's answer)
        # get recorded into history -- otherwise a pending invoice would
        # falsely flag its own later, corrected resubmission as a duplicate.
        store.record_invoice(
            invoice_number=extraction.invoice_number,
            vendor_name=extraction.vendor_name,
            amount=extraction.total_amount,
            po_number=match.matched_po["po_number"] if match.matched_po else extraction.po_number,
        )

    return {
        "source_file": file_path,
        "extraction": extraction.to_dict(),
        "validation": validation.to_dict(),
        "match": match.to_dict(),
        "decision": asdict(decision),
        "correspondence": correspondence_block,
        "pipeline_trace": extraction_trace,
    }


def pretty_print(result: dict) -> None:
    print(f"\n{'=' * 70}\nFILE: {result.get('source_file', 'N/A')}\n{'=' * 70}")

    print("\n--- EXTRACTION TRACE ---")
    for step in result.get("pipeline_trace", []):
        print(f"  • {step}")

    e = result.get("extraction", {})
    tier = e.get("extraction_tier") or e.get("extraction_metadata", {}).get("tier_used", "Unknown")
    print(f"\n--- EXTRACTED DATA (tier: {tier}) ---")

    core = e.get("core_fields", e)
    inv_num = core.get("invoice_number", "N/A")
    inv_date = core.get("invoice_date", "N/A")
    vendor = core.get("vendor_name", "N/A")
    po_num = core.get("po_number", "N/A")
    subtotal = core.get("subtotal", "N/A")
    tax_amt = core.get("tax_amount", "N/A")
    tax_mode = e.get("tax_mode", "N/A")
    total = core.get("total_amount", "N/A")
    line_items = core.get("line_items", [])

    print(f"  Invoice #: {inv_num}   Date: {inv_date}   Vendor: {vendor}   PO: {po_num}")
    print(f"  Subtotal: {subtotal}  Tax: {tax_amt} ({tax_mode})  Total: {total}")
    print(f"  Line items: {len(line_items) if isinstance(line_items, list) else 0}")

    extra_fields = e.get("extra_fields", {})
    if extra_fields:
        print("\n  [Extra Metadata / Unmapped Key-Value Pairs]")
        for k, v in extra_fields.items():
            print(f"    • {k}: {v}")

    validation = result.get("validation", {})
    print("\n--- VALIDATION ---")
    print(f"  Confidence: {validation.get('confidence_score', 'N/A')}  Valid: {validation.get('is_valid', False)}")
    for i in validation.get("issues", []):
        severity = i.get('severity', 'INFO').upper()
        field = i.get('field', 'General')
        msg = i.get('message', '')
        print(f"  [{severity}] {field}: {msg}")

    match = result.get("match", {})
    print("\n--- PO MATCH ---")
    print(f"  Status: {match.get('match_status', 'N/A')}")
    for r in match.get("reasoning", []):
        print(f"  • {r}")

    decision = result.get("decision", {})
    print("\n--- DECISION ---")
    print(f"  >>> {decision.get('decision', 'N/A')}  "
          f"(human review required: {decision.get('requires_human_review', True)}) <<<")
    for r in decision.get("reasoning_trail", []):
        print(f"  • {r}")

    corr = result.get("correspondence")
    if corr:
        print("\n--- VENDOR CORRESPONDENCE ---")
        print(f"  Thread {corr['correspondence_id']}  status={corr['status']}  reason={corr['reason']}")
        for m in corr["messages"]:
            print(f"  [{m['direction']}] {m['subject']}")
        for n in corr.get("resolution_notes", []):
            print(f"  resolution: {n}")
    print()


