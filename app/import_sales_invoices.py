import pandas as pd
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Numeric, ForeignKey, UniqueConstraint, Text
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# --- Database setup ---
DATABASE_URL = "mariadb+mariadbconnector://nohria_user:telly123@localhost/Nohria_dies_and_Technology"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()
Base = declarative_base()

# --- Models ---
class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String(255), nullable=False)
    location = Column(String(255))
    state = Column(String(100))
    state_code = Column(String(10))
    gst_no = Column(String(50), unique=True)

class SaleInvoice(Base):
    __tablename__ = "sale_invoice"
    __table_args__ = (UniqueConstraint("my_company_id", "invoice_number", name="uq_mycompany_invoice_number"),)
    id = Column(Integer, primary_key=True)
    invoice_number = Column(String(50), nullable=False)
    my_company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    customer_company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    invoice_date = Column(DateTime, nullable=False)
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    cgst = Column(Numeric(8, 2), default=0)
    sgst = Column(Numeric(8, 2), default=0)
    igst = Column(Numeric(8, 2), default=0)
    total_tax = Column(Numeric(12, 2), nullable=False, default=0)
    total_amount = Column(Numeric(12, 2), nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    eway_bill = Column(String(50))
    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")

class SaleItem(Base):
    __tablename__ = "sale_item"
    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey("sale_invoice.id", ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=False)
    qty = Column(Numeric(12, 2), nullable=False, default=0)
    price = Column(Numeric(12, 2), nullable=False, default=0)
    taxable_amount = Column(Numeric(12, 2), nullable=False, default=0)
    hsn_no = Column(String(50))   # NEW FIELD
    sale = relationship("SaleInvoice", back_populates="items")


Base.metadata.create_all(engine)

# --- Helpers ---
def parse_date(value):
    if not value or pd.isna(value):
        return None
    val = str(value).strip()
    try:
        return datetime.strptime(val.replace("Z", ""), "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError:
        try:
            return datetime.strptime(val, "%Y-%m-%d")
        except ValueError:
            return None

def safe_number(val, default=0):
    try:
        if val is None or pd.isna(val):
            return default
        return float(val)
    except Exception:
        return default

def safe_string(val, default="NA"):
    if val is None or pd.isna(val):
        return default
    return str(val).strip()

# --- Import function ---
def import_sales_invoices_from_csv(csv_path):
    df = pd.read_csv(csv_path)

    # Ensure seller exists
    seller = session.query(Company).filter_by(gst_no="06AATPN3168K123").first()
    if not seller:
        seller = Company(
            company_name="Nohria Dies and Technology",
            location="MAIN ROAD, Mujessar, Opp. Escorts Kubota, Sector 24 Faridabad",
            state="Haryana",
            state_code="06",
            gst_no="06AATPN3168K123",
        )
        session.add(seller)
        session.commit()

    for _, row in df.iterrows():
        invoice_number = safe_string(row.get("orderNumber"))

        # --- Merge GSTN from both columns ---
        gstn_part1 = safe_string(row.get("GSTN"))
        gstn_part2 = safe_string(row.get("Gstn"))  # lowercase column
        gstn = (gstn_part1 + gstn_part2).replace("NA", "").strip()

        company_name = safe_string(row.get("name"))

        # Lookup by GSTN if available, otherwise by company name
        if gstn:
            customer = session.query(Company).filter_by(gst_no=gstn).first()
        else:
            customer = session.query(Company).filter_by(company_name=company_name).first()

        if not customer:
            customer = Company(
                company_name=company_name,
                location=safe_string(row.get("address")),
                state=safe_string(row.get("state")),
                state_code=safe_string(row.get("stateCode")),
                gst_no=gstn if gstn else None,
            )
            session.add(customer)
            session.commit()

        # --- Create or update invoice ---
        existing = session.query(SaleInvoice).filter_by(
            my_company_id=seller.id,
            invoice_number=invoice_number
        ).first()

        if existing:
            invoice = existing
            invoice.items.clear()
        else:
            invoice = SaleInvoice(
                invoice_number=invoice_number,
                my_company_id=seller.id,
                customer_company_id=customer.id,
                invoice_date=parse_date(row.get("date")) or datetime.now(timezone.utc),
                subtotal=safe_number(row.get("taxableAmount")),
                cgst=safe_number(row.get("cgstamount")),
                sgst=safe_number(row.get("sgstamount")),
                igst=safe_number(row.get("igstamount")),
                total_tax=safe_number(row.get("cgstamount")) + safe_number(row.get("sgstamount")) + safe_number(row.get("igstamount")),
                total_amount=safe_number(row.get("total")),
                eway_bill=safe_string(row.get("Eway")),
                created_at=parse_date(row.get("createdAt")) or datetime.now(timezone.utc),
            )
            session.add(invoice)
            session.flush()

        for i in range(5):
            desc = safe_string(row.get(f"items[{i}].description"))
            qty = safe_number(row.get(f"items[{i}].quantity"), 0)   # keep float
            price = safe_number(row.get(f"items[{i}].price"), 0)
            amount = safe_number(row.get(f"items[{i}].amount"), 0)
            hsn = safe_string(row.get(f"items[{i}].hsnCode"))

    # Skip only if ALL fields are empty/NA/zero
            if (not desc or desc == "NA") and qty == 0 and price == 0 and amount == 0:
                continue

            item = SaleItem(
        sale=invoice,
        description=desc if desc != "NA" else "",
        qty=(qty),
        price=price,
        taxable_amount=amount,
        hsn_no=hsn if hsn != "NA" else None,
    )
            session.add(item)
            print("Added item:", item.description, item.qty, item.price, item.taxable_amount, item.hsn_no)


        session.commit()
        print(f"Imported/Updated invoice {invoice_number} for {customer.company_name} with GSTN {customer.gst_no} and total {invoice.total_amount}")

# --- Run ---
if __name__ == "__main__":
    import_sales_invoices_from_csv("C:/Users/vibhu/Downloads/Backup_mern.orders.csv")
