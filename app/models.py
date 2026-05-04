from datetime import datetime
from . import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import UniqueConstraint
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from decimal import Decimal
from sqlalchemy import Numeric
from num2words import num2words
from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, Text,Date
import datetime

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    companies = db.relationship('Company', back_populates='creator')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


import datetime
from app import db

class Company(db.Model):
    __tablename__ = 'companies'

    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(200), nullable=False)
    state_code = db.Column(db.String(10), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    gst_no = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), nullable=True)
    mobile_no = db.Column(db.String(20), nullable=True)        # ✅ new field
    website = db.Column(db.String(120), nullable=True)         # ✅ new field
    bank_account_name = db.Column(db.String(150), nullable=True)  # ✅ new field
    msme_no = db.Column(db.String(50), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    bank_name = db.Column(db.String(100))
    account_no = db.Column(db.String(50))
    ifsc_code = db.Column(db.String(20))
    company_type = db.Column(db.String(20), default="customer")

    
    creator = db.relationship('User', back_populates='companies')
    sales_as_buyer = db.relationship('SaleInvoice', foreign_keys='SaleInvoice.my_company_id', back_populates='my_company', cascade='all, delete-orphan')
    sales_as_seller = db.relationship('SaleInvoice', foreign_keys='SaleInvoice.customer_company_id', back_populates='customer_company', cascade='all, delete-orphan')
    purchases_as_buyer = db.relationship('PurchaseInvoice', foreign_keys='PurchaseInvoice.my_company_id', back_populates='my_company', cascade='all, delete-orphan')
    purchases_as_seller = db.relationship('PurchaseInvoice', foreign_keys='PurchaseInvoice.supplier_company_id', back_populates='supplier_company', cascade='all, delete-orphan')



class SaleInvoice(db.Model):
    __tablename__ = 'sale_invoice'
    __table_args__ = (UniqueConstraint('my_company_id', 'invoice_number', name='uq_mycompany_invoice_number'),)

    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50),unique = True ,nullable=False)
    @staticmethod
    def generate_invoice_number():
        today = datetime.date.today()

        # Financial year starts in April
        if today.month >= 4:
            fy_start = today.year
            fy_end = today.year + 1
        else:
            fy_start = today.year - 1
            fy_end = today.year

        fy_string = f"{fy_start}-{fy_end}"

        # Find the last invoice for this financial year
        last_invoice = (
            db.session.query(SaleInvoice)
            .filter(SaleInvoice.invoice_number.like(f"{fy_string}-%"))
            .order_by(SaleInvoice.id.desc())
            .first()
        )

        if last_invoice:
            last_seq = int(last_invoice.invoice_number.split("-")[-1])
            new_seq = last_seq + 1
        else:
            new_seq = 1

        return f"{fy_string}-{new_seq:04d}"
    my_company_id = db.Column(db.Integer, db.ForeignKey('companies.id', ondelete='RESTRICT'), nullable=False)
    customer_company_id = db.Column(db.Integer, db.ForeignKey('companies.id', ondelete='RESTRICT'), nullable=False)
    invoice_date = db.Column(db.Date, default=datetime.date.today)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    cgst = db.Column(db.Numeric(8, 2), default=0)
    sgst = db.Column(db.Numeric(8, 2), default=0)
    igst = db.Column(db.Numeric(8, 2), default=0)
    total_tax = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    po_number = db.Column(db.String(50))
    po_date = db.Column(db.Date)
    challan_no = db.Column(db.String(50))
    challan_date = db.Column(db.Date)
    supply_datetime = db.Column(db.DateTime, default=datetime.datetime.now)
    eway_bill = db.Column(db.String(50))
    freight_charges = db.Column(db.Numeric(10, 2), default=0.00)
    def total_amount_in_words(self):
        rupees = int(self.total_amount or 0)
        paise = int(round(((self.total_amount or 0) - rupees) * 100))
        words_rupees = num2words(rupees, lang='en_IN').title()
        if paise > 0:
            words_paise = num2words(paise, lang='en_IN').title()
            return f"{words_rupees} Rupees And {words_paise} Paise Only"
        return f"{words_rupees} Rupees Only"
    creator = db.relationship('User', backref='sale_invoices')
    my_company = db.relationship('Company', foreign_keys=[my_company_id], back_populates='sales_as_buyer')
    customer_company = db.relationship('Company', foreign_keys=[customer_company_id], back_populates='sales_as_seller')

    items = db.relationship('SaleItem', back_populates='sale', cascade='all, delete-orphan')
    payments = db.relationship('SalesPayment', back_populates='sale', cascade="all, delete-orphan")

    @property
    def amount_received (self):
        return sum(Decimal(p.amount) for p in self.payments)

    @property
    def pending_amount(self):
        return Decimal(self.total_amount or 0) - self.amount_received

    @property
    def payment_status(self):
        if self.amount_received >= (self.total_amount or Decimal("0.00")):
            return "Completed"
        elif self.amount_received > 0:
            return "Partially Paid"
        else:
            return "Pending"


class SalesPayment(db.Model):
    __tablename__ = "sales_payment"
    id = db.Column(db.Integer, primary_key=True)
    sales_id = db.Column(db.Integer, db.ForeignKey("sale_invoice.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    method = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False)

    sale = db.relationship("SaleInvoice", back_populates="payments")


class SaleItem(db.Model):
    __tablename__ = 'sale_item'
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sale_invoice.id', ondelete='CASCADE'), nullable=False)
    description = db.Column(db.Text, nullable=False)
    hsn_no = db.Column(db.String(20))
    qty = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    taxable_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    sale = db.relationship('SaleInvoice', back_populates='items')


class PurchaseInvoice(db.Model):
    __tablename__ = 'purchase_invoices'
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), nullable=False)

    # Foreign keys
    my_company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    supplier_company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)

    # Relationships
    my_company = db.relationship('Company', foreign_keys=[my_company_id], back_populates='purchases_as_buyer')
    supplier_company = db.relationship('Company', foreign_keys=[supplier_company_id], back_populates='purchases_as_seller')

    invoice_date = db.Column(db.Date)

    # Totals
    subtotal = db.Column(db.Numeric(10, 2), default=0)
    cgst = db.Column(db.Numeric(10, 2), default=0)
    sgst = db.Column(db.Numeric(10, 2), default=0)
    igst = db.Column(db.Numeric(10, 2), default=0)
    total_tax = db.Column(db.Numeric(10, 2), default=0)
    total_amount = db.Column(db.Numeric(10, 2), default=0)
    po_number = db.Column(db.String(50))
    po_date = db.Column(db.Date)
    transporter = db.Column(db.String(100))
    booking = db.Column(db.String(100))
    msme_registration_no = db.Column(db.String(50))
    ack_no = db.Column(db.String(50))
    irn_no = db.Column(db.String(50))
    freight_charges = db.Column(db.Numeric(12, 2), default=0)
    # Relationships
    items = db.relationship('PurchaseItem', back_populates='purchase', cascade="all, delete-orphan")
    payments = db.relationship('PurchasePayment', back_populates='purchase', cascade="all, delete-orphan")

    # Calculated properties
    @property
    def amount_paid(self):
        return sum(Decimal(str(p.amount)) for p in self.payments)

    @property
    def pending_amount(self):
        return Decimal(str(self.total_amount or 0)) - self.amount_paid
    @property
    def payment_status(self):
        if self.amount_paid >= (self.total_amount or Decimal("0.00")):
            return "Completed"
        elif self.amount_paid > 0:
            return "Partially Paid"
        else:
            return "Pending"



class PurchaseItem(db.Model):
    __tablename__ = 'purchase_items'
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchase_invoices.id'), nullable=False)
    description = db.Column(db.String(200))
    hsn_no = db.Column(db.String(50))
    qty = db.Column(db.Numeric(10, 2))
    price = db.Column(db.Numeric(10, 2))
    taxable_amount = db.Column(db.Numeric(10, 2))

    purchase = db.relationship('PurchaseInvoice', back_populates='items')


class PurchasePayment(db.Model):
    __tablename__ = 'purchase_payments'
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchase_invoices.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    method = db.Column(db.String(50))  # Cash, Cheque, Bank Transfer, etc.
    date = db.Column(db.DateTime, default=db.func.now())

    purchase = db.relationship('PurchaseInvoice', back_populates='payments')

class DeletionRequest(db.Model):
    __tablename__ = 'deletion_requests'
    id = db.Column(db.Integer, primary_key=True)
    sale_invoice_id = db.Column(db.Integer, nullable=False)
    requested_by = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    status = db.Column(db.String(32), default='pending')  # pending, approved, rejected
    
    
    
class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100))
    date = db.Column(db.Date, nullable=False)
    items = db.relationship('InvoiceItem', backref='invoice', lazy=True)

    @property
    def total_amount(self):
        return sum(item.total_price for item in self.items)


class InvoiceItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=False)
    description = db.Column(db.String(200))
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Float, default=0.0)

    @property
    def total_price(self):
        return self.quantity * self.unit_price


class InventoryItem(db.Model):
    __tablename__ = "inventory_items"

    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(100), nullable=False)
    hsn_no = db.Column(db.String(20))
    qty_in_stock = db.Column(db.Integer, nullable=False, default=0)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    last_updated = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    
def update_inventory_from_purchase(purchase_item):
    """Update inventory when a purchase item is added."""
    inv_item = InventoryItem.query.filter_by(product_name=purchase_item.description).first()
    if inv_item:
        inv_item.qty_in_stock += purchase_item.qty
        inv_item.unit_price = purchase_item.price
    else:
        inv_item = InventoryItem(
            product_name=purchase_item.description,
            hsn_no=purchase_item.hsn_no,
            qty_in_stock=purchase_item.qty,
            unit_price=purchase_item.price
        )
        db.session.add(inv_item)


class Quotation(db.Model):
    __tablename__ = "quotations"

    id = Column(Integer, primary_key=True)
    quotation_number = Column(String(50), unique=True, nullable=False)
    own_company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    supply_date = db.Column(db.Date, nullable=False)
    customer_company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    date = Column(Date, default=datetime.date.today)
    status = Column(String(20), default="draft")  # draft, sent, accepted, rejected
    terms_and_conditions = db.Column(db.Text)
    # Relationships
    items = relationship(
        "QuotationItem",
        back_populates="quotation",
        cascade="all, delete-orphan"
    )
    customer = relationship("Company", foreign_keys=[customer_company_id])
    own_company = db.relationship("Company", foreign_keys=[own_company_id])
    customer_company = db.relationship("Company", foreign_keys=[customer_company_id])
    def __repr__(self):
        return f"<Quotation {self.quotation_number} - {self.status}>"

class QuotationItem(db.Model):
    __tablename__ = "quotation_items"

    id = Column(Integer, primary_key=True)
    quotation_id = Column(Integer, ForeignKey("quotations.id"), nullable=False)
    description = Column(Text, nullable=False)
    qty = Column(Numeric(12, 2), nullable=False, default=0)
    price = Column(Numeric(12, 2), nullable=False, default=0)
    taxable_amount = Column(Numeric(12, 2), nullable=False, default=0)
    hsn_no = Column(String(50)) 
    # Relationship back to quotation
    quotation = relationship("Quotation", back_populates="items")
    
    def __repr__(self):
        return f"<QuotationItem {self.description} x {self.qty}>"
    
    
def generate_quotation_number():
    from datetime import date
    today = date.today()
    year = today.year

    # Financial year starts in April
    if today.month < 4:  # Jan–Mar belongs to previous FY
        start_year = year - 1
        end_year = year
    else:
        start_year = year
        end_year = year + 1

    fy_string = f"{start_year}-{end_year}"

    # Find last quotation in this FY
    last_quotation = Quotation.query.filter(
        Quotation.quotation_number.like(f"{fy_string}-%")
    ).order_by(Quotation.id.desc()).first()

    if last_quotation:
        last_number = int(last_quotation.quotation_number.split("-")[-1])
        new_number = last_number + 1
    else:
        new_number = 1

    # ✅ Always pad to 3 digits
    return f"{fy_string}-{new_number:03d}"
