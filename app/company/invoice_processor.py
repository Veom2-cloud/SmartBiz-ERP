import pytesseract
from pdf2image import convert_from_path
import requests
import json
import re
from decimal import Decimal
from dateutil import parser as date_parser
from json_repair import repair_json
from typing import Optional, Tuple
import sys
import os

sys.path.append(
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
)

from app import db, create_app
from app.models import Company, PurchaseInvoice, PurchaseItem, PurchasePayment


# =========================================================
# MY COMPANY ALIASES  — add any OCR variants here
# =========================================================

MY_COMPANY_VARIANTS = [
    "NOHRIA DIES AND TECHNOLOGIES",
    "NOHRIA DIES & TECHNOLOGIES",
    "NOHRIA DIES AND TECHNOLOGY",
    "NOHRIA DIES & TECHNOLOGY",
    "NOHRIA DIES TECHNOLOGIES",
    "NOHRIA DIES TECHNOLOGY",
    "NOHRIA DIES",
]


# =========================================================
# STEP 1 : NORMALIZE COMPANY NAME
# =========================================================

def normalize_company_name(name: str) -> str:
    """
    Upper-cases, replaces & -> AND, collapses spaces,
    strips everything except A-Z 0-9 SPACE.
    """
    if not name:
        return ""
    name = str(name).upper().strip()
    name = name.replace("&", " AND ")
    name = re.sub(r"[^A-Z0-9 ]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def is_my_company(name: str) -> bool:
    """Returns True if name matches any known variant of my company."""
    if not name:
        return False
    norm = normalize_company_name(name)
    for variant in MY_COMPANY_VARIANTS:
        if norm == normalize_company_name(variant):
            return True
    if "NOHRIA" in norm and "DIES" in norm:
        return True
    return False


# =========================================================
# STEP 2 : CLEAN INVOICE NUMBER
# =========================================================

def clean_invoice_number(value: str) -> Optional[str]:
    if not value:
        return None
    value = str(value).strip().strip("'\"` \t")
    value = re.sub(r"[^A-Za-z0-9\-\/]", "", value)
    return value if value and 3 <= len(value) <= 50 else None


# =========================================================
# STEP 3 : EXTRACT INVOICE NUMBER  (robust multi-strategy)
# =========================================================

def extract_invoice_number_from_text(text: str) -> Optional[str]:
    """
    Extract invoice number from OCR text.
    Rejects 12-digit e-way bills and non-numeric fragments.
    """
    patterns = [
        r"INVOICE\s*NO\.?\s*[:\-]?\s*(\d{3,10})",          # Invoice No. 43064
        r"TAX\s*INVOICE\s*NO\.?\s*[:\-]?\s*(\d{3,10})",
        r"BILL\s*NO\.?\s*[:\-]?\s*(\d{3,10})",
    ]

    for p in patterns:
        m = re.search(p, text.upper())
        if m:
            candidate = clean_invoice_number(m.group(1))
            if candidate and not re.fullmatch(r"\d{12}", candidate):  # reject e-way bill
                return candidate

    # Fallback: look for short numbers on lines with "Invoice"
    for line in text.splitlines():
        if "INVOICE" in line.upper():
            numbers = re.findall(r"\b(\d{3,10})\b", line)
            for num in numbers:
                candidate = clean_invoice_number(num)
                if candidate and not re.fullmatch(r"\d{12}", candidate):
                    return candidate

    return None


# =========================================================
# STEP 4 : EXTRACT E-WAY BILL NUMBER
# =========================================================

def extract_eway_bill_number(text: str) -> Optional[str]:
    """
    Handles e-way bill numbers with or without spaces:
      7716 1976 7519  ->  771619767519
      771619767519    ->  771619767519
    """

    def clean_eway(raw: str) -> Optional[str]:
        digits = re.sub(r"\s+", "", raw)
        return digits if len(digits) == 12 and digits.isdigit() else None

    # Labeled patterns -- value may have internal spaces (12-17 chars)
    patterns = [
        r"E[\-\s]?WAY\s*(?:BILL)?\s*(?:NO|NUMBER|#)?\.?\s*[:\-]?\s*([\d\s]{12,17})",
        r"EWB\s*(?:NO|NUMBER|#)?\.?\s*[:\-]?\s*([\d\s]{12,17})",
        r"EWAY\s*(?:NO|NUMBER|#)?\.?\s*[:\-]?\s*([\d\s]{12,17})",
    ]
    t = text.upper()
    for p in patterns:
        m = re.search(p, t)
        if m:
            result = clean_eway(m.group(1))
            if result:
                return result

    # Spaced 4-4-4 digit group: "7716 1976 7519"
    m = re.search(r"\b(\d{4}\s\d{4}\s\d{4})\b", text)
    if m:
        result = clean_eway(m.group(1))
        if result:
            return result

    # Solid 12-digit fallback (no spaces)
    m = re.search(r"\b(\d{12})\b", text)
    return m.group(1) if m else None


# =========================================================
# STEP 5 : EXTRACT DATE
# =========================================================

def extract_date_from_text(text: str) -> Optional[str]:
    patterns = [
        r"\b(\d{2}[\/\-]\d{2}[\/\-]\d{4})\b",         # 28/03/2026
        r"\b(\d{2}[\/\-]\d{2}[\/\-]\d{2})\b",           # 28/03/26
        r"\b(\d{1,2}[\-\s][A-Za-z]{3}[\-\s]\d{4})\b",  # 28-Mar-2026
    ]
    for pattern in patterns:
        for date_str in re.findall(pattern, text):
            try:
                return date_parser.parse(date_str, dayfirst=True).strftime("%Y-%m-%d")
            except Exception:
                continue
    return None


# =========================================================
# STEP 6 : EXTRACT GRAND TOTAL
# =========================================================

def extract_grand_total(text: str) -> str:
    """
    Extracts the grand total from invoice text.
    Handles:
      - Indian comma format:  4,72,000.00
      - Rupee symbol prefix:  Rs. 4,72,000.00  or  (non-ASCII rupee) 4,72,000.00
      - Plain "Total" row as last resort
    """
    # Work on a copy — strip ONLY non-ASCII chars (rupee symbol etc.)
    # Do NOT use a broad regex that eats letters from words like "TOTAL"
    t = re.sub(r"[^\x00-\x7F]+", " ", text).upper()

    patterns = [
        r"GRAND\s*TOTAL\s*[:\-]?\s*([\d,]+\.\d{2})",
        r"TOTAL\s*AMOUNT\s*[:\-]?\s*([\d,]+\.\d{2})",
        r"NET\s*TOTAL\s*[:\-]?\s*([\d,]+\.\d{2})",
        r"(?<!\w)TOTAL\s*[:\-]?\s*([\d,]+\.\d{2})",
    ]
    for p in patterns:
        matches = re.findall(p, t)
        if matches:
            val = matches[-1].replace(",", "")
            print(f"[grand_total] matched pattern '{p[:30]}...' -> {val}")
            return val

    # Last resort: largest number in the whole text
    numbers = re.findall(r"[\d,]+\.\d{2}", t)
    if numbers:
        cleaned = [n.replace(",", "") for n in numbers]
        best = max(cleaned, key=lambda x: float(x))
        print(f"[grand_total] fallback largest number -> {best}")
        return best

    print("[grand_total] NOTHING found, returning 0.00")
    return "0.00"


# =========================================================
# STEP 7 : EXTRACT CGST / SGST / IGST
# =========================================================

def extract_tax_amounts(text: str) -> dict:
    """Extracts tax AMOUNTS in rupees (not percentages)."""
    t = re.sub(r"[^\x00-\x7F]+", " ", text).upper()

    def find_tax(label_re):
        m = re.search(
            label_re
            + r"(?:\s*[@\(]\s*[\d\.]+\s*%\s*\)?)?"
            + r"\s*[:\-]?\s*([\d,]+\.\d{2})",
            t,
        )
        return m.group(1).replace(",", "") if m else "0.00"

    return {
        "cgst": find_tax(r"C\.?G\.?S\.?T"),
        "sgst": find_tax(r"S\.?G\.?S\.?T"),
        "igst": find_tax(r"I\.?G\.?S\.?T"),
    }


# =========================================================
# STEP 8 : EXTRACT PO / IRN / ACK
# =========================================================

def extract_po_number(text: str) -> Optional[str]:
    t = text.upper()
    for p in [
        r"P\.?O\.?\s*(?:NO|NUMBER|#)?\.?\s*[:\-]?\s*([A-Z0-9\/\-_]{3,50})",
        r"PURCHASE\s*ORDER\s*(?:NO|NUMBER|#)?\.?\s*[:\-]?\s*([A-Z0-9\/\-_]{3,50})",
    ]:
        m = re.search(p, t)
        if m:
            val = m.group(1).strip()
            if 2 <= len(val) <= 50:
                return val
    return None


def extract_irn_ack(text: str) -> Tuple[Optional[str], Optional[str]]:
    t = text.upper()
    irn = None
    ack = None
    m = re.search(r"IRN\s*[:\-]?\s*([A-Z0-9]{64})", t)
    if m:
        irn = m.group(1).strip()
    m = re.search(r"ACK\s*(?:NO|NUMBER)?\.?\s*[:\-]?\s*(\d{13,15})", t)
    if m:
        ack = m.group(1).strip()
    return irn, ack


# =========================================================
# STEP 9 : EXTRACT BANK DETAILS
# =========================================================
def extract_bank_details(text: str) -> dict:
    """
    Extracts supplier bank details from the invoice footer.
    Handles formats like:
      Bank Name  :  STATE BANK OF INDIA
      A/c No.    :  32358643890
      Branch & IFS Code : JAMA MASJID & SBIN0002366
    Returns dict: { bank_name, account_no, branch_name, ifsc_code }
    """
    t = text.upper()
    details: dict = {"bank_name": None, "account_no": None, "branch_name": None, "ifsc_code": None}

    # Bank name
    m = re.search(
        r"BANK\s*NAME\s*[:\-]\s*([A-Z][A-Z\s&OF]{3,60}?)(?:\n|A[\s\/]C|ACCOUNT|IFSC|BRANCH|IFS CODE|$)",
        t,
    )
    if m:
        details["bank_name"] = m.group(1).strip().rstrip(":").strip()

    # Account number (9–18 digits)
    m = re.search(r"(?:A[\s\/]?C|ACCOUNT)\s*(?:NO|NUMBER|#)?\.?\s*[:\-]?\s*(\d{9,18})", t)
    if m:
        details["account_no"] = m.group(1).strip()

    # Branch + IFSC together
    m = re.search(r"BRANCH\s*&?\s*IFS\s*CODE\s*[:\-]?\s*([A-Z\s]+)&\s*([A-Z]{4}0[A-Z0-9]{6})", t)
    if m:
        details["branch_name"] = m.group(1).strip()
        details["ifsc_code"] = m.group(2).strip()

    # Fallback: IFSC anywhere in text
    if not details["ifsc_code"]:
        m = re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", t)
        if m:
            details["ifsc_code"] = m.group(1).strip()

    return details



def extract_unit_prices(text: str) -> list:
    """
    Extracts unit prices from invoice text.
    Looks for patterns like 'Rate : 123.45' or 'Unit Price 500.00'.
    Returns a list of decimal strings.
    """
    t = text.upper()
    patterns = [
        r"RATE\s*[:\-]?\s*([\d,]+\.\d{2})",
        r"UNIT\s*PRICE\s*[:\-]?\s*([\d,]+\.\d{2})",
        r"PRICE\s*[:\-]?\s*([\d,]+\.\d{2})",
    ]
    results = []
    for p in patterns:
        matches = re.findall(p, t)
        for m in matches:
            results.append(m.replace(",", ""))
    return results


# =========================================================
# STEP 10 : SAFE DECIMAL CLEANER
# =========================================================

def clean_decimal(value) -> Decimal:
    """Strips currency symbols, Indian commas, spaces before converting."""
    if value is None:
        return Decimal("0.00")
    # Remove commas (Indian format: 4,72,000.00) and non-numeric chars
    value = re.sub(r"[^0-9.\-]", "", str(value).replace(",", ""))
    if not value:
        return Decimal("0.00")
    try:
        return Decimal(value)
    except Exception:
        return Decimal("0.00")


# =========================================================
# STEP 11 : SAFE DATE PARSER  ->  date object
# =========================================================

def safe_parse_date(date_str):
    if not date_str:
        return None
    try:
        return date_parser.parse(str(date_str), dayfirst=True).date()
    except Exception:
        return None


# =========================================================
# STEP 12 : VALIDATE DATA
# =========================================================

def validate_invoice_data(data: dict) -> dict:
    invoice_no = clean_invoice_number(data.get("invoice_no"))
    if not invoice_no:
        raise ValueError("Invoice number missing or could not be extracted")
    data["invoice_no"] = invoice_no

    if "items" not in data:
        data["items"] = []

    # Normalise grand_total: strip commas (Indian format) before decimal check
    raw_total = str(data.get("grand_total") or "").replace(",", "").strip()
    data["grand_total"] = raw_total  # store cleaned version for save_purchase_invoice

    if clean_decimal(raw_total) <= 0:
        raise ValueError(
            f"Grand total is 0 or missing (raw value was: '{data.get('grand_total')}')"
        )

    return data

def extract_ifsc_code(text: str) -> Optional[str]:
    """
    Extract IFSC code from invoice text.
    Handles cases like 'Branch & IFS Code: JAMA MASJID & SBIN0002366'
    """
    t = text.upper()
    # Match standard IFSC format anywhere in the text
    m = re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", t)
    if m:
        return m.group(1).strip()
    return None



# =========================================================
# STEP 13 : OCR EXTRACTION
# =========================================================

def extract_text_from_scanned_pdf(filepath: str) -> str:
    print("\n[OCR] Running OCR on PDF...")
    pages = convert_from_path(filepath, dpi=700, grayscale=True)
    text_pages = []
    for index, page in enumerate(pages):
        print(f"[OCR] Processing page {index + 1}")
        page_text = pytesseract.image_to_string(
            page, lang="eng", config=r"--oem 3 --psm 4"
        )
        text_pages.append(page_text)
    final_text = "\n".join(text_pages)
    final_text = re.sub(r"\n{3,}", "\n\n", final_text)
    final_text = re.sub(r"[ \t]+", " ", final_text)
    return final_text.strip()


# =========================================================
# STEP 14 : CLEAN LLM OUTPUT
# =========================================================

def clean_json_output(output: str) -> str:
    output = output.strip()
    output = output.replace("```json", "").replace("```", "")
    match = re.search(r"\{.*\}", output, re.DOTALL)
    return match.group(0).strip() if match else output.strip()


# =========================================================
# STEP 15 : REMOVE MY COMPANY AS SUPPLIER
# =========================================================

def remove_my_company_from_supplier(data: dict) -> dict:
    supplier = str(data.get("supplier_name") or "")
    if is_my_company(supplier):
        print(f"[WARN] Supplier '{supplier}' matched MY company -- clearing.")
        data["supplier_name"] = None
    return data


# =========================================================
# STEP 16 : REMOVE DUPLICATE ITEMS
# =========================================================

def remove_duplicate_items(data: dict) -> dict:
    seen = set()
    clean_items = []
    for item in data.get("items", []):
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("description", "")).strip(),
            str(item.get("qty", "")).strip(),
            str(item.get("total_amount", "")).strip(),
        )
        if key not in seen:
            seen.add(key)
            clean_items.append(item)
    data["items"] = clean_items
    return data


# =========================================================
# STEP 17 : SAVE PURCHASE INVOICE
# =========================================================

def save_purchase_invoice(
    data: dict,
    payment_amount=None,
    payment_method: Optional[str] = None,
) -> int:
    """
    Saves invoice + items + optional payment in one DB transaction.

    Key behaviours:
    - Looks up supplier by normalized name in company_type="supplier"
    - Creates supplier if not found (with GST + bank details from invoice)
    - ALWAYS updates supplier bank/GST details if invoice has new data
    - Handles Indian grand-total format: 4,72,000.00
    - Prevents own company being recorded as supplier
    - Prevents duplicate invoices per supplier
    """

    validate_invoice_data(data)

    # --- Normalize alternate key names from LLM ---
    if "eway_bill_no" in data and not data.get("eway_bill"):
        data["eway_bill"] = data.pop("eway_bill_no")
    if "supplier" in data and not data.get("supplier_name"):
        data["supplier_name"] = data.pop("supplier")

    invoice_no = clean_invoice_number(data.get("invoice_no"))
    if not invoice_no:
        raise ValueError("Invoice number missing or invalid")
    data["invoice_no"] = invoice_no

    supplier_name = str(data.get("supplier_name") or "").strip()
    if not supplier_name:
        supplier_name = "UNKNOWN SUPPLIER"
        data["supplier_name"] = supplier_name
        print("[WARN] Supplier missing -- defaulting to UNKNOWN SUPPLIER")

    if is_my_company(supplier_name):
        raise ValueError(
            f"Supplier '{supplier_name}' resolved to MY company -- aborting"
        )

    # --- My company ---
    my_company = Company.query.filter_by(
        company_name="NOHRIA DIES AND TECHNOLOGIES",
        company_type="own",
    ).first()
    if not my_company:
        raise ValueError("My company 'NOHRIA DIES AND TECHNOLOGIES' not found in DB")

    # --- Supplier lookup by normalized name ---
    supplier = None
    normalized_supplier = normalize_company_name(supplier_name)
    for comp in Company.query.filter_by(company_type="customer").all():
        if normalize_company_name(comp.company_name) == normalized_supplier:
            supplier = comp
            break

    # --- Create supplier if not found ---
    if not supplier:
        print(f"[INFO] '{supplier_name}' not found in DB -- creating new supplier...")
        supplier = Company(
            company_name = supplier_name,
            company_type = "supplier",
            gst_no       = data.get("supplier_gst"),
            bank_name    = data.get("bank_name"),
            account_no   = data.get("account_no"),
            ifsc_code    = data.get("ifsc_code"),
        )
        db.session.add(supplier)
        db.session.flush()
        print(f"[OK] Supplier created: '{supplier_name}' ID={supplier.id}")

    # --- ALWAYS update bank/GST details from latest invoice data ---
    # This keeps the supplier record current even if it already existed.
    bank_updated = False

    if data.get("bank_name"):
        new_bank = str(data["bank_name"]).strip()
        if not supplier.bank_name or normalize_company_name(supplier.bank_name) != normalize_company_name(new_bank):
            supplier.bank_name = new_bank
            bank_updated = True

    if data.get("account_no"):
        new_acc = str(data["account_no"]).strip()
        if supplier.account_no != new_acc:
            supplier.account_no = new_acc
            bank_updated = True

    if data.get("ifsc_code"):
        new_ifsc = str(data["ifsc_code"]).strip()
        if supplier.ifsc_code != new_ifsc:
            supplier.ifsc_code = new_ifsc
            bank_updated = True

    if data.get("supplier_gst") and not supplier.gst_no:
        supplier.gst_no = str(data["supplier_gst"]).strip()
        bank_updated = True

    if bank_updated:
        print(f"[OK] Supplier '{supplier.company_name}' bank/GST details updated")

    # --- Duplicate invoice check ---
    if PurchaseInvoice.query.filter_by(
        invoice_number=invoice_no,
        supplier_company_id=supplier.id,
    ).first():
        raise ValueError(f"Duplicate invoice: {invoice_no} for {supplier.company_name}")

    # --- Tax logic: IGST = inter-state; CGST+SGST = intra-state ---
    # --- Tax logic: IGST = inter-state; CGST+SGST = intra-state ---
    cgst_val = clean_decimal(data.get("cgst")),
    gst_val = clean_decimal(data.get("sgst"))
    igst_val = clean_decimal(data.get("igst"))

    if igst_val > 0:
    # Inter-state transaction -- zero out CGST/SGST
        cgst_val = Decimal("0.00")
        sgst_val = Decimal("0.00")

# --- Build line items and compute subtotal ---
    subtotal_val = Decimal("0.00")
    items = []
    for item in data.get("items", []):
        if not isinstance(item, dict):
            continue
        qty  = clean_decimal(item.get("qty"))
        rate = clean_decimal(item.get("unit_price"))
        taxable_amount = round(qty * rate)   # ✅ correct calculation

        subtotal_val += taxable_amount  # accumulate subtotal

        items.append(PurchaseItem(
        description    = item.get("description"),
        hsn_no         = item.get("hsn_no"),
        qty            = qty,
        price          = rate,
        taxable_amount = taxable_amount,
    ))

# --- Totals ---
    total_tax   = cgst_val + sgst_val + igst_val
    grand_total = subtotal_val + total_tax

# --- Build invoice record ---
    invoice = PurchaseInvoice(
    invoice_number       = invoice_no,
    my_company_id        = my_company.id,
    supplier_company_id  = supplier.id,
    invoice_date         = safe_parse_date(data.get("date")),
    subtotal             = subtotal_val,   # ✅ computed from items
    cgst                 = cgst_val,
    sgst                 = sgst_val,
    igst                 = igst_val,
    total_tax            = total_tax,
    total_amount         = grand_total,    # ✅ subtotal + tax
    freight_charges      = clean_decimal(data.get("freight_charges", "0.00")),
    eway_bill            = data.get("eway_bill"),
    po_number            = data.get("po_number"),
    po_date              = safe_parse_date(data.get("po_date")),
    transporter          = data.get("transporter"),
    booking              = data.get("booking"),
    msme_registration_no = data.get("msme_registration_no"),
    ack_no               = data.get("ack_no"),
    irn_no               = data.get("irn_no"),
)

# Attach items
    for item in items:
        invoice.items.append(item)



    # --- Attach payment (optional) ---
    if payment_amount is not None:
        amt = clean_decimal(payment_amount)
        if amt > 0:
            invoice.payments.append(PurchasePayment(
                amount=amt,
                method=payment_method or "Bank Transfer",
            ))
            print(f"[OK] Payment queued: Rs.{amt} via {payment_method or 'Bank Transfer'}")

    # --- Commit everything ---
    try:
        db.session.add(invoice)
        db.session.commit()
        print(f"\n[OK] Saved -- Invoice ID={invoice.id}, Items={len(invoice.items)}")
        return invoice.id
    except Exception as e:
        db.session.rollback()
        raise Exception(f"DB save failed: {e}")


# =========================================================
# STEP 18 : OCR + OLLAMA PIPELINE
# =========================================================

def process_invoice_pdf(
    filepath: str,
    ollama_base_url: str,
    ollama_model: str,
) -> dict:

    # -- OCR ------------------------------------------------
    text = extract_text_from_scanned_pdf(filepath)
    print("\n========== OCR TEXT (first 3000 chars) ==========")
    print(text[:3000])
    detected_invoice_no = extract_invoice_number_from_text(text)
    detected_eway       = extract_eway_bill_number(text)

    detected_date              = extract_date_from_text(text)
    detected_total             = extract_grand_total(text)
    detected_taxes             = extract_tax_amounts(text)
    detected_po                = extract_po_number(text)
    detected_irn, detected_ack = extract_irn_ack(text)
    detected_bank              = extract_bank_details(text)
    detected_unit_prices = extract_unit_prices(text)
    detected_ifsc        = detected_bank.get("ifsc_code")
    print("IFSC        :", detected_ifsc if detected_ifsc else "Not found")

    print("Unit Prices :", detected_unit_prices)


    print("\n========== REGEX DETECTIONS ==========")
    print("Invoice No  :", detected_invoice_no)
    print("E-Way Bill  :", detected_eway)
    print("Date        :", detected_date)
    print("Grand Total :", detected_total)
    print("CGST        :", detected_taxes["cgst"])
    print("SGST        :", detected_taxes["sgst"])
    print("IGST        :", detected_taxes["igst"])
    print("PO Number   :", detected_po)
    print("IRN         :", detected_irn)
    print("ACK No      :", detected_ack)
    print("Bank Name   :", detected_bank["bank_name"])
    print("Account No  :", detected_bank["account_no"])
    print("IFSC        :", detected_ifsc if detected_ifsc else "Not found")
    print("======================================")

    # -- LLM prompt -----------------------------------------
    prompt = f"""
You are a JSON API. Return ONLY valid JSON. No extra text, no markdown.

CRITICAL RULES:
1. "NOHRIA DIES AND TECHNOLOGIES" (or any variant like "NOHRIA DIES & TECHNOLOGIES"
   or "NOHRIA DIES AND TECHNOLOGY") is ALWAYS the BUYER / recipient.
   NEVER set it as supplier_name under any circumstances.
2. supplier_name = the company name at the TOP of the invoice as the SELLER
   (e.g. "MIDLAND TOOLS"). It is the one issuing the invoice to us.
3. invoice_no = the short invoice number in the header (e.g. 43064).
   It is NOT the e-way bill number (which is always exactly 12 digits).
4. eway_bill = the 12-digit e-way bill number only (completely separate field).
5. grand_total = the final payable amount including all taxes.
   Indian invoices use commas like 4,72,000.00 -- write it without commas: 472000.00
6. subtotal = taxable value before any tax is added.
7. cgst / sgst / igst = tax AMOUNTS in rupees (not percentages).
8. unit_price = rate per unit as shown in the "Rate" column.
9. bank_name, account_no, ifsc_code = the supplier's bank details from the
   "Company's Bank Details" section at the bottom of the invoice.
10. supplier_gst = the GSTIN of the SELLER / supplier (not the buyer).
11. Use null for any field you cannot find. Do NOT guess.
12. items must always be an array (even if empty).
13. No trailing commas. Double quotes only.

JSON FORMAT:
{{
  "invoice_no"           : "",
  "my_company_name"      : "",
  "my_company_gst"       : "",
  "supplier_name"        : "",
  "supplier_gst"         : "",
  "date"                 : "",
  "eway_bill"            : "",
  "po_number"            : "",
  "irn_no"               : "",
  "ack_no"               : "",
  "transporter"          : "",
  "booking"              : "",
  "msme_registration_no" : "",
  "freight_charges"      : "",
  "subtotal"             : "",
  "cgst"                 : "",
  "sgst"                 : "",
  "igst"                 : "",
  "grand_total"          : "",
  "bank_name"            : "",
  "account_no"           : "",
  "ifsc_code"            : "",
  "items": [
    {{
      "description"   : "",
      "hsn_no"        : "",
      "qty"           : "",
      "unit_price"    : "",
      "taxable_amount": "",
      "total_amount"  : ""
    }}
  ]
}}

OCR TEXT:
{text}
"""

    # -- Call Ollama ----------------------------------------
    try:
        print("\n[LLM] Sending to Ollama...")
        resp = requests.post(
            f"{ollama_base_url}/api/generate",
            json={"model": ollama_model, "prompt": prompt, "stream": False},
            timeout=(10, 180),
        )
    except Exception as e:
        print("\n[ERROR] Ollama connection failed:", e)
        return {"error": str(e)}

    if resp.status_code != 200:
        print("\n[ERROR] Ollama error:", resp.status_code, resp.text)
        return {"error": f"Ollama status {resp.status_code}"}

    try:
        output = resp.json().get("response", "")
    except Exception as e:
        return {"error": f"Bad Ollama response: {e}"}

    print("\n========== RAW MODEL OUTPUT ==========")
    print(output)

    output = clean_json_output(output)
    print("\n========== CLEANED OUTPUT ==========")
    print(output)

    # -- Parse JSON + override with trusted regex values ----
    try:
        parsed = json.loads(repair_json(output))

        # Regex/rule-based values override the LLM (more reliable)
        # Override invoice number
        if detected_invoice_no:
            parsed["invoice_no"] = detected_invoice_no
            print(f"[OK] Invoice No overridden by regex: {detected_invoice_no}")

# Override e-way bill
        if detected_eway:
            parsed["eway_bill"] = detected_eway

# Override IFSC
        if detected_ifsc:
            parsed["ifsc_code"] = detected_ifsc

# Override unit prices
        if detected_unit_prices and "items" in parsed:
            for idx, price in enumerate(detected_unit_prices):
                if idx < len(parsed["items"]):
                    parsed["items"][idx]["unit_price"] = price


        if detected_eway:
            parsed["eway_bill"] = detected_eway

        if detected_date:
            parsed["date"] = detected_date

        if detected_total:
            parsed["grand_total"] = detected_total
            print(f"[OK] Grand total overridden by regex: {detected_total}")
        else:
            print(f"[WARN] Regex found no grand total. LLM value: {parsed.get('grand_total')}")

        if detected_po:
            parsed["po_number"] = detected_po

        if detected_irn:
            parsed["irn_no"] = detected_irn

        if detected_ack:
            parsed["ack_no"] = detected_ack

        if clean_decimal(detected_taxes["cgst"]) > 0:
            parsed["cgst"] = detected_taxes["cgst"]

        if clean_decimal(detected_taxes["sgst"]) > 0:
            parsed["sgst"] = detected_taxes["sgst"]

        if clean_decimal(detected_taxes["igst"]) > 0:
            parsed["igst"] = detected_taxes["igst"]

        # Always override bank details with regex values (more reliable
        # than LLM for structured footer data like account numbers)
        if detected_bank["bank_name"]:
            parsed["bank_name"] = detected_bank["bank_name"]
        if detected_bank["account_no"]:
            parsed["account_no"] = detected_bank["account_no"]
        if detected_bank["ifsc_code"]:
            parsed["ifsc_code"] = detected_bank["ifsc_code"]

        # Sanitize: make sure my company is never the supplier
        parsed = remove_my_company_from_supplier(parsed)
        parsed = remove_duplicate_items(parsed)

        if not parsed.get("invoice_no"):
            print("\n[WARN] INVOICE NUMBER STILL MISSING after LLM + regex.")
            print("       First 500 chars of OCR for inspection:")
            print(text[:500])

        print("\n========== FINAL PARSED JSON ==========")
        print(json.dumps(parsed, indent=2))
        return parsed

    except Exception as e:
        print("\n[ERROR] JSON parse failed:", e)
        print("BAD OUTPUT:", output)
        return {"error": "JSON parsing failed", "raw_output": output}


# =========================================================
# STEP 19 : MAIN
# =========================================================

if __name__ == "__main__":

    filepath        = r"C:\Users\vibhu\Documents\1.pdf"
    ollama_base_url = "http://localhost:11434"
    ollama_model    = "llama3"

    payment_amount  = None   # e.g. "5000.00"
    payment_method  = None   # e.g. "Bank Transfer" / "Cash" / "Cheque"

    app = create_app()

    with app.app_context():

        result = process_invoice_pdf(filepath, ollama_base_url, ollama_model)

        if result and "error" not in result:
            try:
                invoice_id = save_purchase_invoice(
                    result,
                    payment_amount=payment_amount,
                    payment_method=payment_method,
                )
                print(f"\n[SUCCESS] Invoice saved with ID {invoice_id}")
            except Exception as e:
                print(f"\n[FAILED] Could not save invoice: {e}")
        else:
            print(f"\n[FAILED] Could not process invoice: {result.get('error')}")