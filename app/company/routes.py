from flask import Blueprint, render_template, request, redirect, url_for, jsonify,flash,send_file,Response
from flask_login import current_user, login_required
from datetime import date
from .. import db
from ..models import Company, SaleInvoice , SaleItem,Invoice,InventoryItem,Quotation, QuotationItem,generate_quotation_number
from ..models import Company, SaleInvoice, PurchaseInvoice,DeletionRequest,SalesPayment,PurchaseItem, PurchasePayment,update_inventory_from_purchase
from sqlalchemy import func,or_
from decimal import Decimal
from math import ceil
from flask import current_app
from datetime import datetime
from num2words import num2words
import pandas as pd
import os
import io
backup_bp = Blueprint("backup", __name__, url_prefix="/backup")
company_bp = Blueprint('company', __name__, url_prefix='/')
sales_bp = Blueprint('sales', __name__, url_prefix='/')
purchase_bp = Blueprint('purchase', __name__, url_prefix='/')

# ============ COMPANY ROUTES ============

@company_bp.route('/')
def home():
    """Home page - show all companies"""
    companies = Company.query.all()
    return render_template('home.html', companies=companies)

@company_bp.route('/create-company', methods=['GET', 'POST'])
@login_required
def create_company():
    """Create a new company"""
    if request.method == 'POST':
        company_name = request.form.get('company_name')
        location = request.form.get('location')
        state_code = request.form.get('state_code')
        state = request.form.get('state')
        gst_no = request.form.get('gst_no')
        email = request.form.get('email')
        mobile_no = request.form.get('mobile_no')              # ✅ new
        website = request.form.get('website')                  # ✅ new
        bank_account_name = request.form.get('bank_account_name')  # ✅ new
        bank_name = request.form.get('bank_name')
        account_no = request.form.get('account_no')
        ifsc_code = request.form.get('ifsc_code')
        msme_no=request.form.get("msme_no")
        # Check for duplicate GST
        if Company.query.filter_by(gst_no=gst_no).first():
            return render_template('create_company.html', error="GST number already exists")

        company = Company(
            company_name=company_name,
            location=location,
            state_code=state_code,
            state=state,
            gst_no=gst_no,
            email=email,
            mobile_no=mobile_no,
            website=website,
            bank_account_name=bank_account_name,
            created_by=current_user.id,
            bank_name=bank_name,
            account_no=account_no,
            ifsc_code=ifsc_code,
            msme_no=msme_no
        )

        db.session.add(company)
        db.session.commit()

        return redirect(url_for('company.view_all_companies'))

    return render_template('create_company.html')


@company_bp.route('/company/<int:company_id>')
def view_company(company_id):
    """View single company details"""
    company = Company.query.get_or_404(company_id)
    return render_template('view_company.html', company=company)

@company_bp.route('/company/<int:company_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_company(company_id):
    """Edit company details"""
    company = Company.query.get_or_404(company_id)
    
    
    if request.method == 'POST':
        company.company_name = request.form.get('company_name')
        company.location = request.form.get('location')
        company.state_code = request.form.get('state_code')
        company.state = request.form.get('state')
        company.gst_no = request.form.get('gst_no')
        company.email = request.form.get('email')
        company.mobile_no = request.form.get('mobile_no')              # ✅ new
        company.website = request.form.get('website')                  # ✅ new
        company.bank_account_name = request.form.get('bank_account_name')  # ✅ new
        company.bank_name = request.form.get('bank_name')
        company.account_no = request.form.get('account_no')
        company.ifsc_code = request.form.get('ifsc_code')
        company.company_type = request.form.get('company_type')
        company.msme_no = request.form.get("msme_no") 
        db.session.commit()
        return redirect(url_for('company.view_company', company_id=company.id))
    
    return render_template('edit_company.html', company=company)



@company_bp.route('/company/<int:company_id>/delete', methods=['POST'])
@login_required
def delete_company(company_id):
    """Delete a company"""
    company = Company.query.get_or_404(company_id)
    
    if company.created_by != current_user.id and not current_user.is_admin:
        return render_template('error.html', error="You don't have permission to delete this company"), 403
    
    db.session.delete(company)
    db.session.commit()
    
    return redirect(url_for('company.view_all_companies'))


@company_bp.route('/view-all-companies')
def view_all_companies():
    """View all companies with search and sort"""
    search_query = request.args.get('search', '').strip()
    
    if search_query:
        companies = Company.query.filter(
            Company.company_name.ilike(f'%{search_query}%')
        ).all()
    else:
        companies = Company.query.all()
    
    companies = sorted(companies, key=lambda x: x.company_name.lower())
    
    return render_template('view_all_companies.html', companies=companies, search_query=search_query)


@company_bp.route('/api/companies')
def get_companies_api():
    """API endpoint to get all companies as JSON"""
    companies = Company.query.all()
    return jsonify([{
        'id': c.id,
        'company_name': c.company_name,
        'location': c.location,
        'state': c.state,
        'state_code': c.state_code,
        'gst_no': c.gst_no,
        'email': c.email,
        'mobile_no': c.mobile_no,                # ✅ new
        'website': c.website,                    # ✅ new
        'bank_account_name': c.bank_account_name, # ✅ new
        'bank_name': c.bank_name,
        'account_no': c.account_no,
        'ifsc_code': c.ifsc_code,
        'company_type': c.company_type,
        'created_at': c.created_at.isoformat()
    } for c in companies])



# ============ SALES ROUTES ============



@sales_bp.route('/sales')
@login_required
def sales_home():
    """Sales home page with stats"""
    # Total invoices
    total_sales = db.session.query(func.count(SaleInvoice.id)).scalar() or 0
    
    # Total revenue
    total_amount = db.session.query(func.coalesce(func.sum(SaleInvoice.total_amount), 0)).scalar()
    
    # This month's invoices
    today = date.today()
    first_day = today.replace(day=1)
    this_month_sales = db.session.query(func.count(SaleInvoice.id))\
        .filter(SaleInvoice.invoice_date >= first_day).scalar() or 0
    
    # This month's revenue
    this_month_revenue = db.session.query(func.coalesce(func.sum(SaleInvoice.total_amount), 0))\
        .filter(SaleInvoice.invoice_date >= first_day).scalar()
    
    return render_template(
        'sales_home.html',
        total_sales=total_sales,
        total_amount=total_amount,
        this_month_sales=this_month_sales,
        this_month_revenue=this_month_revenue
    )

@sales_bp.route('/sales/create', methods=['GET', 'POST'])
@login_required
def create_sale():
    """Create new sale invoice"""
    companies = Company.query.order_by(Company.company_name.asc()).all()
    my_company = None

    if request.method == 'POST':
        try:
            # Required numeric fields
            my_company_id_raw = request.form.get('my_company_id')
            customer_company_id_raw = request.form.get('customer_company_id')
            invoice_number = (request.form.get('invoice_number') or '').strip()

            # Auto-generate if empty
            if not invoice_number:
                invoice_number = SaleInvoice.generate_invoice_number()

            if not my_company_id_raw or not customer_company_id_raw:
                raise ValueError("Please select both 'My Company' and 'Customer'.")

            my_company_id = int(my_company_id_raw)
            customer_company_id = int(customer_company_id_raw)

            # Prevent duplicate invoice numbers for the same my_company
            existing = SaleInvoice.query.filter_by(
                my_company_id=my_company_id,
                invoice_number=invoice_number
            ).first()
            if existing:
                raise ValueError("An invoice with this number already exists for the selected company.")

            # Optional numeric fields with safe defaults
            invoice_date_raw = request.form.get('invoice_date')
            invoice_date = date.fromisoformat(invoice_date_raw) if invoice_date_raw else date.today()

            subtotal = Decimal(request.form.get('subtotal', 0) or 0)
            cgst = Decimal(request.form.get('cgst') or 0)
            sgst = Decimal(request.form.get('sgst') or 0)
            igst = Decimal(request.form.get('igst') or 0)
            total_tax = Decimal(request.form.get('total_tax', 0) or 0)
            total_amount = Decimal(request.form.get('total_amount', 0) or 0)

            # Convert to words
            rupees = int(total_amount)
            paise = int(round((total_amount - rupees) * 100))
            words_rupees = num2words(rupees, lang='en_IN').title()
            if paise > 0:
                words_paise = num2words(paise, lang='en_IN').title()
                total_amount_in_words = f"{words_rupees} Rupees And {words_paise} Paise Only"
            else:
                total_amount_in_words = f"{words_rupees} Rupees Only"

            # Extra fields
            po_number = (request.form.get('po_number') or '').strip()
            po_date_raw = request.form.get('po_date')
            po_date = date.fromisoformat(po_date_raw) if po_date_raw else None

            challan_no = (request.form.get('challan_no') or '').strip()
            challan_date_raw = request.form.get('challan_date')
            challan_date = date.fromisoformat(challan_date_raw) if challan_date_raw else None

            supply_datetime_raw = request.form.get('supply_datetime')
            supply_datetime = datetime.fromisoformat(supply_datetime_raw) if supply_datetime_raw else None

            eway_bill = (request.form.get('eway_bill') or '').strip()
            freight_charges = float(request.form.get('freight_charges') or 0)

            sale = SaleInvoice(
                my_company_id=my_company_id,
                customer_company_id=customer_company_id,
                invoice_number=invoice_number,
                invoice_date=invoice_date,
                subtotal=subtotal,
                cgst=cgst,
                sgst=sgst,
                igst=igst,
                total_tax=total_tax,
                total_amount=total_amount,
                created_by=current_user.id if current_user.is_authenticated else None,
                total_amount_in_words=total_amount_in_words,
                po_number=po_number,
                po_date=po_date,
                challan_no=challan_no,
                challan_date=challan_date,
                supply_datetime=supply_datetime,
                eway_bill=eway_bill,
                freight_charges=freight_charges
            )

            # Items loop
            i = 1
            while True:
                desc = request.form.get(f'items[{i}][description]')
                if not desc:
                    break
                qty = Decimal(request.form.get(f'items[{i}][qty]', 0) or 0)
                price = Decimal(request.form.get(f'items[{i}][price]', 0) or 0)
                taxable = qty * price
                item = SaleItem(
                    description=desc,
                    hsn_no=request.form.get(f'items[{i}][hsn_no]') or None,
                    qty=qty,
                    price=price,
                    taxable_amount=taxable
                )
                sale.items.append(item)
                i += 1

            db.session.add(sale)
            db.session.commit()

            return redirect(url_for('sales.view_sale', sale_id=sale.id))

        except ValueError as ve:
            return render_template('create_sale.html', companies=companies, my_company=my_company, error=str(ve))
        except Exception as e:
            db.session.rollback()
            return render_template('create_sale.html', companies=companies, my_company=my_company, error="Unexpected error: " + str(e))

    # GET request → pre-fill invoice number
    suggested_invoice_number = SaleInvoice.generate_invoice_number()
    return render_template(
        'create_sale.html',
        companies=companies,
        my_company=my_company,
        suggested_invoice_number=suggested_invoice_number
    )

@sales_bp.route('/sales/report/gst', methods=['GET'])
@login_required
def gst_tax_report():
    """Generate GST Tax Report (IGST, CGST, SGST) month & year wise"""
    # Query invoices grouped by month/year
    results = db.session.query(
        func.extract('month', SaleInvoice.invoice_date).label('month'),
        func.extract('year', SaleInvoice.invoice_date).label('year'),
        func.sum(SaleInvoice.igst).label('total_igst'),
        func.sum(SaleInvoice.cgst).label('total_cgst'),
        func.sum(SaleInvoice.sgst).label('total_sgst')
    ).group_by('year', 'month').order_by('year', 'month').all()

    return render_template('gst_tax_report.html', results=results)


@sales_bp.route('/sales/report/base', methods=['GET'])
@login_required
def base_billing_report():
    """Generate Base Billing Report (excluding GST) month & year wise"""
    results = db.session.query(
        func.extract('month', SaleInvoice.invoice_date).label('month'),
        func.extract('year', SaleInvoice.invoice_date).label('year'),
        func.sum(SaleInvoice.subtotal).label('base_total')
    ).group_by('year', 'month').order_by('year', 'month').all()

    return render_template('base_billing_report.html', results=results)

@sales_bp.route('/sales/list')
@login_required
def list_sales():
    sort = request.args.get('sort', 'desc')  # default newest first
    """List all sales invoices with search and pagination"""
    search = request.args.get('search', '').strip()
    try:
        page = max(int(request.args.get('page', 1)), 1)
    except ValueError:
        page = 1
    per_page = 20

    # Base query: join customer company for searching by name
    q = SaleInvoice.query.join(Company, SaleInvoice.customer_company)

    if search:
        like = f"%{search}%"
        q = q.filter(
            or_(
                SaleInvoice.invoice_number.ilike(like),
                Company.company_name.ilike(like)
            )
        )
     # Apply sort order
    if sort == 'asc':
        q = q.order_by(SaleInvoice.invoice_date.asc())
    else:
        q = q.order_by(SaleInvoice.invoice_date.desc())

   

    # Pagination: try built-in paginate, fallback to manual
    try:
        pagination = q.paginate(page=page, per_page=per_page, error_out=False)
        sales = pagination.items
    except Exception:
        total = q.count()
        pages = ceil(total / per_page) if total else 1
        sales = q.offset((page - 1) * per_page).limit(per_page).all()

        class SimplePagination:
            def __init__(self, items, page, per_page, total, pages):
                self.items = items
                self.page = page
                self.per_page = per_page
                self.total = total
                self.pages = pages

            @property
            def has_prev(self):
                return self.page > 1

            @property
            def has_next(self):
                return self.page < self.pages

            @property
            def prev_num(self):
                return self.page - 1

            @property
            def next_num(self):
                return self.page + 1

        pagination = SimplePagination(sales, page, per_page, total, pages)

    return render_template(
        'list_sales.html',
        sales=pagination.items,
        pagination=pagination,
        search=search,
        sort=sort
    )


@sales_bp.route('/sales/<int:sale_id>')
@login_required
def view_sale(sale_id):
    sale = SaleInvoice.query.get_or_404(sale_id)
    return render_template('view_sale.html', sale=sale)

@sales_bp.route('/sales/<int:sale_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_sale(sale_id):
    sale = SaleInvoice.query.get_or_404(sale_id)

    # permission: only creator or admin can edit
    if getattr(sale, 'created_by', None) is not None and sale.created_by != current_user.id and not current_user.is_admin:
        return render_template('error.html', error="You don't have permission to edit this invoice"), 403

    companies = Company.query.order_by(Company.company_name.asc()).all()

    if request.method == 'POST':
        try:
            sale.my_company_id = int(request.form.get('my_company_id'))
            sale.customer_company_id = int(request.form.get('customer_company_id'))
            sale.invoice_number = (request.form.get('invoice_number') or sale.invoice_number).strip()

            invoice_date_raw = request.form.get('invoice_date')
            if invoice_date_raw:
                sale.invoice_date = date.fromisoformat(invoice_date_raw)

            sale.subtotal = Decimal(request.form.get('subtotal', sale.subtotal or 0) or 0)
            sale.cgst = Decimal(request.form.get('cgst') or request.form.get('cgst_amount') or sale.cgst or 0)
            sale.sgst = Decimal(request.form.get('sgst') or request.form.get('sgst_amount') or sale.sgst or 0)
            sale.igst = Decimal(request.form.get('igst') or request.form.get('igst_amount') or sale.igst or 0)
            sale.total_tax = Decimal(request.form.get('total_tax', sale.total_tax or 0) or 0)
            sale.total_amount = Decimal(request.form.get('total_amount', sale.total_amount or 0) or 0)
            rupees = int(sale.total_amount)
            paise = int(round((sale.total_amount - rupees) * 100))
            words_rupees = num2words(rupees, lang='en_IN').title()
            if paise > 0:
                words_paise = num2words(paise, lang='en_IN').title()
                sale.total_amount_in_words = f"{words_rupees} Rupees And {words_paise} Paise Only"
            else:
                sale.total_amount_in_words = f"{words_rupees} Rupees Only"
            # ✅ New fields
            sale.po_number = (request.form.get('po_number') or sale.po_number or '').strip()
            po_date_raw = request.form.get('po_date')
            if po_date_raw:
                sale.po_date = date.fromisoformat(po_date_raw)

            sale.challan_no = (request.form.get('challan_no') or sale.challan_no or '').strip()
            challan_date_raw = request.form.get('challan_date')
            if challan_date_raw:
                sale.challan_date = date.fromisoformat(challan_date_raw)

            supply_datetime_raw = request.form.get('supply_datetime')
            if supply_datetime_raw:
                sale.supply_datetime = datetime.fromisoformat(supply_datetime_raw)

            sale.eway_bill = (request.form.get('eway_bill') or sale.eway_bill or '').strip()
            sale.freight_charges = Decimal(request.form.get('freight_charges') or sale.freight_charges or 0)

            # Handle new payment entry if provided
            pay_amount = request.form.get("payment_amount")
            pay_method = request.form.get("payment_method")
            pay_date = request.form.get("payment_date")

            if pay_amount and pay_method and pay_date:
                pay_amount = Decimal(pay_amount)
                pending = sale.pending_amount

                if pay_amount > pending:
                    flash(f"Payment exceeds pending amount (₹{pending:.2f}). Please enter a valid amount.", "danger")
                    return redirect(url_for('sales.edit_sale', sale_id=sale.id))

                payment = SalesPayment(
                    sales_id=sale.id,
                    amount=pay_amount,
                    method=pay_method,
                    date=datetime.strptime(pay_date, "%Y-%m-%d").date()
                )
                db.session.add(payment)

            # replace items: clear existing and add new ones
            sale.items[:] = []
            i = 1
            while True:
                desc = request.form.get(f'items[{i}][description]')
                if not desc:
                    break
                qty = Decimal(request.form.get(f'items[{i}][qty]', 0) or 0)
                price = Decimal(request.form.get(f'items[{i}][price]', 0) or 0)
                taxable = qty * price
                item = SaleItem(
                    description=desc,
                    hsn_no=request.form.get(f'items[{i}][hsn_no]') or None,
                    qty=qty,
                    price=price,
                    taxable_amount=taxable
                )
                sale.items.append(item)
                i += 1

            db.session.commit()
            return redirect(url_for('sales.view_sale', sale_id=sale.id))
        except Exception as e:
            db.session.rollback()
            return render_template('edit_sale.html', sale=sale, companies=companies, error=str(e))

    return render_template('edit_sale.html', sale=sale, companies=companies)




@sales_bp.route('/sales/<int:sale_id>/delete', methods=['POST'])
@login_required
def delete_sale(sale_id):
    """Direct delete route for admins/owners"""
    sale = SaleInvoice.query.get_or_404(sale_id)

    if not (getattr(current_user, 'is_admin', False) or sale.created_by == current_user.id):
        flash("You don't have permission to delete this invoice directly.", "danger")
        return redirect(url_for('sales.view_sale', sale_id=sale_id))

    try:
        db.session.delete(sale)
        db.session.commit()
        flash("Sale invoice deleted successfully.", "success")
        return redirect(url_for('company.list_sales'))
    except Exception as e:
        db.session.rollback()
        flash("Error deleting sale: {}".format(e), "danger")
        return redirect(url_for('sales.list_sales'))
    
    
@sales_bp.route('/sales/<int:sale_id>/request-delete', methods=['POST'])
@login_required
def request_delete_sale(sale_id):
    """Deletion request route for non‑owners"""
    sale = SaleInvoice.query.get_or_404(sale_id)
    owner_id = getattr(sale, 'created_by', None)

    # Owners/admins should use direct delete
    if getattr(current_user, 'is_admin', False) or owner_id == current_user.id:
        flash('You can delete this invoice directly.', 'info')
        return redirect(url_for('sales.list_sales'))
    # Ensure DeletionRequest model exists
    try:
        DeletionRequest
    except NameError:
        flash('Deletion requests are not enabled.', 'danger')
        return redirect(url_for('sales.list_sales'))
    # Prevent duplicate pending requests
    existing = DeletionRequest.query.filter_by(
        sale_invoice_id=sale.id,
        requested_by=current_user.id,
        status='pending'
    ).first()
    if existing:
        flash('You already have a pending deletion request for this invoice.', 'warning')
        return redirect(url_for('sales.list_sales'))
    try:
        req = DeletionRequest(sale_invoice_id=sale.id, requested_by=current_user.id)
        db.session.add(req)
        db.session.commit()
        flash('Deletion request submitted. An admin will review it shortly.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(e)
        flash('Could not submit deletion request: {}'.format(e), 'danger')

        return redirect(url_for('sales.list_sales'))
    
    
@sales_bp.route('/sales/stats')
@login_required
def sales_stats():
    # Total invoices
    total_sales = db.session.query(func.count(SaleInvoice.id)).scalar() or 0

    # Total revenue
    total_amount = db.session.query(func.coalesce(func.sum(SaleInvoice.total_amount), 0)).scalar()

    # This month’s invoices
    today = date.today()
    first_day = today.replace(day=1)
    this_month_sales = db.session.query(func.count(SaleInvoice.id))\
        .filter(SaleInvoice.invoice_date >= first_day).scalar() or 0

    # This month’s revenue (optional extra stat)
    this_month_revenue = db.session.query(func.coalesce(func.sum(SaleInvoice.total_amount), 0))\
        .filter(SaleInvoice.invoice_date >= first_day).scalar()

    return render_template(
        "stats.html",
        total_sales=total_sales,
        total_amount=total_amount,
        this_month_sales=this_month_sales,
        this_month_revenue=this_month_revenue
    )

@sales_bp.route('/<int:sale_id>/add_payment', methods=['POST'])
@login_required
def add_payment(sale_id):
    sale = SaleInvoice.query.get_or_404(sale_id)
    amount = request.form.get('amount')
    method = request.form.get('method')
    if amount:
        payment = SalesPayment(sale=sale, amount=amount, method=method)
        db.session.add(payment)
        db.session.commit()
    return redirect(url_for('sales.view_sale', sale_id=sale.id))

# ============ PURCHASE ROUTES ============

@purchase_bp.route('/purchases')
@login_required
def purchases_home():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    sort = request.args.get('sort', 'desc')

    query = PurchaseInvoice.query
    if search:
        query = query.join(Company).filter(
            (PurchaseInvoice.invoice_number.ilike(f"%{search}%")) |
            (Company.company_name.ilike(f"%{search}%"))
        )

    if sort == 'asc':
        query = query.order_by(PurchaseInvoice.invoice_date.asc())
    else:
        query = query.order_by(PurchaseInvoice.invoice_date.desc())

    pagination = query.paginate(page=page, per_page=10)
    purchases = pagination.items

    return render_template(
        'purchases_home.html',
        purchases=purchases,
        owner_id=current_user.id,
        pagination=pagination,
        search=search,
        sort=sort
    )


@purchase_bp.route('/purchases/create', methods=['GET', 'POST'])
@login_required
def create_purchase():
    if request.method == 'POST':
        from datetime import datetime

        # Parse invoice date safely
        date_str = request.form.get('invoice_date')
        invoice_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None
        po_date_raw = request.form.get('po_date')
        # Create the invoice
        purchase = PurchaseInvoice(
            invoice_number=request.form['invoice_number'],
            my_company_id=int(request.form['my_company_id']),
            supplier_company_id=int(request.form['supplier_company_id']),
            invoice_date=invoice_date,
            subtotal=Decimal(request.form.get('subtotal', 0) or 0),
            cgst=Decimal(request.form.get('cgst_amount', 0) or 0),
            sgst=Decimal(request.form.get('sgst_amount', 0) or 0),
            igst=Decimal(request.form.get('igst_amount', 0) or 0),
            total_tax=Decimal(request.form.get('total_tax', 0) or 0),
            total_amount=Decimal(request.form.get('total_amount', 0) or 0),
            po_number = (request.form.get('po_number') or '').strip(),
         
            po_date = date.fromisoformat(po_date_raw) if po_date_raw else None,

            transporter = (request.form.get('transporter') or '').strip(),
            booking = (request.form.get('booking') or '').strip(),
            msme_registration_no = (request.form.get('msme_registration_no') or '').strip(),
            ack_no = (request.form.get('ack_no') or '').strip(),
            irn_no = (request.form.get('irn_no') or '').strip(),
            freight_charges = Decimal(request.form.get('freight_charges') or 0),
        )
        db.session.add(purchase)
        db.session.flush()  # ensures purchase.id is available

        # Collect items from form without regex
        items_dict = {}
        for key, value in request.form.items():
            if key.startswith("items["):
                # Example key: items[0][description]
                parts = key.replace("items[", "").replace("]", "").split("[")
                if len(parts) == 2:
                    idx, field = parts
                    items_dict.setdefault(idx, {})[field] = value

        # Create PurchaseItem records
        for idx, data in items_dict.items():
            item = PurchaseItem(
                purchase_id=purchase.id,
                description=data.get("description"),
                hsn_no=data.get("hsn_no"),
                qty=Decimal(data.get("qty") or 0),
                price=Decimal(data.get("price") or 0),
                taxable_amount=Decimal(data.get("taxable_amount") or 0)
            )
            db.session.add(item)
            update_inventory_from_purchase(item)
        db.session.commit()
        return redirect(url_for('purchase.purchases_home'))

    companies = Company.query.all()
    return render_template('create_purchase.html', companies=companies)

@purchase_bp.route('/purchases/<int:purchase_id>')
@login_required
def view_purchase(purchase_id):
    """View purchase invoice"""
    purchase = PurchaseInvoice.query.get_or_404(purchase_id)
    return render_template('view_purchase.html', purchase=purchase)


@purchase_bp.route('/purchases/list')
@login_required
def list_purchases():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    sort = request.args.get('sort', 'desc')

    query = PurchaseInvoice.query
    if search:
        query = query.join(Company).filter(
            (PurchaseInvoice.invoice_number.ilike(f"%{search}%")) |
            (Company.company_name.ilike(f"%{search}%"))
        )

    if sort == 'asc':
        query = query.order_by(PurchaseInvoice.invoice_date.asc())
    else:
        query = query.order_by(PurchaseInvoice.invoice_date.desc())

    pagination = query.paginate(page=page, per_page=10)
    purchases = pagination.items

    return render_template(
        'purchase_list.html',
        purchases=purchases,
        pagination=pagination,
        search=search,
        sort=sort
    )

@purchase_bp.route("/invoices")
def invoices():
    invoices = Invoice.query.all()
    total_revenue = sum(inv.total_amount for inv in invoices)
    return render_template("invoices.html", invoices=invoices, total_revenue=total_revenue)

@purchase_bp.route('/purchases/<int:purchase_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_purchase(purchase_id):
    from datetime import datetime

    purchase = PurchaseInvoice.query.get_or_404(purchase_id)

    if request.method == 'POST':
        # Update invoice fields
        purchase.invoice_number = request.form['invoice_number']
        purchase.my_company_id = int(request.form['my_company_id'])
        purchase.supplier_company_id = int(request.form['supplier_company_id'])

        date_str = request.form.get('invoice_date')
        purchase.invoice_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None

        purchase.subtotal = Decimal(request.form.get('subtotal', "0") or "0")
        purchase.cgst = Decimal(request.form.get('cgst_amount', "0") or "0")
        purchase.sgst = Decimal(request.form.get('sgst_amount', "0") or "0")
        purchase.igst = Decimal(request.form.get('igst_amount', "0") or "0")
        purchase.total_tax = Decimal(request.form.get('total_tax', "0") or "0")
        purchase.total_amount = Decimal(request.form.get('total_amount', "0") or "0")
        purchase.po_number = (request.form.get('po_number') or purchase.po_number or '').strip()
        po_date_raw = request.form.get('po_date')
        if po_date_raw:
            purchase.po_date = date.fromisoformat(po_date_raw)

        purchase.transporter = (request.form.get('transporter') or purchase.transporter or '').strip()
        purchase.booking = (request.form.get('booking') or purchase.booking or '').strip()
        purchase.msme_registration_no = (request.form.get('msme_registration_no') or purchase.msme_registration_no or '').strip()
        purchase.ack_no = (request.form.get('ack_no') or purchase.ack_no or '').strip()
        purchase.irn_no = (request.form.get('irn_no') or purchase.irn_no or '').strip()
        purchase.freight_charges = Decimal(request.form.get('freight_charges') or purchase.freight_charges or 0)

        # Clear existing items
        purchase.items.clear()

        # Collect items
        items_dict = {}
        for key, value in request.form.items():
            if key.startswith("items["):
                parts = key.replace("items[", "").replace("]", "").split("[")
                if len(parts) == 2:
                    idx, field = parts
                    items_dict.setdefault(idx, {})[field] = value

        for idx, data in items_dict.items():
            item = PurchaseItem(
                purchase_id=purchase.id,
                description=data.get("description"),
                hsn_no=data.get("hsn_code"),
                qty=Decimal(data.get("qty") or 0),
                price=Decimal(data.get("price") or "0"),
                taxable_amount=Decimal(data.get("taxable_amount") or "0")
            )
            db.session.add(item)
            update_inventory_from_purchase(item)
        # Handle new payment
        pay_amount = request.form.get("payment_amount")
        pay_method = request.form.get("payment_method")
        pay_date = request.form.get("payment_date")

        if pay_amount and pay_method and pay_date:
            pay_amount = Decimal(pay_amount)
            pending = purchase.pending_amount

            if pay_amount > pending:
                flash(f"Payment exceeds pending amount (₹{pending:.2f}). Please enter a valid amount.", "danger")
                return redirect(url_for('purchase.edit_purchase', purchase_id=purchase.id))

            payment = PurchasePayment(
                purchase_id=purchase.id,
                amount=pay_amount,
                method=pay_method,
                date=datetime.strptime(pay_date, "%Y-%m-%d").date()
            )
            db.session.add(payment)

        db.session.commit()
        flash("Purchase updated successfully!", "success")
        return redirect(url_for('purchase.view_purchase', purchase_id=purchase.id))

    companies = Company.query.all()
    return render_template('purchase_edit.html', purchase=purchase, companies=companies)

@purchase_bp.route('/purchases/<int:purchase_id>/delete', methods=['POST'])
@login_required
def delete_purchase(purchase_id):
    purchase = PurchaseInvoice.query.get_or_404(purchase_id)
    db.session.delete(purchase)
    db.session.commit()
    flash("Purchase deleted successfully!", "success")
    return redirect(url_for('purchase.purchases_home'))

@purchase_bp.route('/purchases/<int:purchase_id>/request_delete', methods=['POST'])
@login_required
def request_delete_purchase(purchase_id):
    """Send a deletion request for a purchase invoice"""
    purchase = PurchaseInvoice.query.get_or_404(purchase_id)
    db.session.delete(purchase)
    db.session.commit()
    flash("Purchase deleted successfully!", "success")
    flash(f"Deletion request for Purchase #{purchase.invoice_number} has been sent to admins.", "info")

    return redirect(url_for('purchase.purchases_home'))


from sqlalchemy import func

@sales_bp.route('/reports', methods=['GET'])
@login_required
def sales_reports():
    # Monthly GST totals
    monthly_gst = (
        db.session.query(
            func.date_format(SaleInvoice.invoice_date, "%Y-%m").label("month"),
            func.sum(SaleInvoice.cgst + SaleInvoice.sgst + SaleInvoice.igst).label("gst_total")
        )
        .group_by("month")
        .order_by("month")
        .all()
    )

    # Quarterly profit analysis (sales - purchases)
    quarterly_profit = (
        db.session.query(
            func.concat(
                func.year(SaleInvoice.invoice_date),
                "-Q",
                func.quarter(SaleInvoice.invoice_date)
            ).label("quarter"),
            (func.sum(SaleInvoice.total_amount) - func.sum(PurchaseInvoice.total_amount)).label("profit")
        )
        .group_by("quarter")
        .order_by("quarter")
        .all()
    )

    # Customer-wise sales summary
    customer_sales = (
        db.session.query(
            Company.company_name,
            func.sum(SaleInvoice.total_amount).label("total_sales")
        )
        .join(Company, SaleInvoice.customer_company_id == Company.id)
        .group_by(Company.company_name)
        .order_by(func.sum(SaleInvoice.total_amount).desc())
        .all()
    )

    return render_template(
        "sales_reports.html",
        monthly_gst=monthly_gst,
        quarterly_profit=quarterly_profit,
        customer_sales=customer_sales
    )


@purchase_bp.route('/inventory')
@login_required
def inventory():
    items = InventoryItem.query.order_by(InventoryItem.product_name.asc()).all()
    return render_template("inventory.html", items=items)

######################################################################################################################
@sales_bp.route('/quotation/create', methods=['GET', 'POST'])
def create_quotation():
    if request.method == 'POST':
        import datetime
        supply_date = datetime.date.fromisoformat(request.form['supply_date'])

        quotation_number = request.form['quotation_number']  # prefilled, readonly
        quotation = Quotation(
            quotation_number=quotation_number,
            supply_date=supply_date,
            customer_company_id=request.form.get('customer_company_id'),
            own_company_id=request.form.get('own_company_id'),
            terms_and_conditions=request.form.get('terms_and_conditions')
        )
        db.session.add(quotation)
        db.session.flush()  # ensures quotation.id is available before commit

        # ✅ Handle quotation items
        descriptions = request.form.getlist('item_description')
        qtys = request.form.getlist('item_qty')
        prices = request.form.getlist('item_price')
        hsns = request.form.getlist('item_hsn')

        for i in range(len(descriptions)):
            if descriptions[i].strip():  # skip empty rows
                qty = float(qtys[i]) if qtys[i] else 0
                price = float(prices[i]) if prices[i] else 0
                taxable_amount = qty * price

                item = QuotationItem(
                    quotation_id=quotation.id,
                    description=descriptions[i],
                    qty=qty,
                    price=price,
                    taxable_amount=taxable_amount,
                    hsn_no=hsns[i] if i < len(hsns) else None
                )
                db.session.add(item)

        db.session.commit()
        flash(f"Quotation {quotation_number} created successfully!", "success")
        return redirect(url_for('sales.view_quotation', quotation_id=quotation.id))

    # Pre‑generate next quotation number
    next_number = generate_quotation_number()

    own_companies = Company.query.filter_by(company_type="own").all()
    customers = Company.query.filter_by(company_type="customer").all()
    return render_template(
        "create_quotation.html",
        own_companies=own_companies,
        customers=customers,
        next_number=next_number
    )


# View a single quotation
@sales_bp.route("/quotation/<int:quotation_id>")
def view_quotation(quotation_id):
    quotation = Quotation.query.get_or_404(quotation_id)
    return render_template("view_quotation.html", quotation=quotation)


# List all quotations
@sales_bp.route("/quotations")
def list_quotations():
    quotations = (
        db.session.query(Quotation)
        .join(Company, Quotation.customer_company_id == Company.id)
        .order_by(Company.company_name.asc())   # ✅ sort by company_name
        .all()
    )
    return render_template("list_quotations.html", quotations=quotations)


# Edit quotation
@sales_bp.route("/quotation/<int:quotation_id>/edit", methods=["GET", "POST"])
def edit_quotation(quotation_id):
    quotation = Quotation.query.get_or_404(quotation_id)

    if request.method == "POST":
        import datetime

        # ✅ Update header fields
        quotation.supply_date = datetime.date.fromisoformat(request.form.get("supply_date")) \
            if request.form.get("supply_date") else quotation.supply_date
        quotation.terms_and_conditions = request.form.get("terms_and_conditions", quotation.terms_and_conditions)
        quotation.customer_company_id = request.form.get("customer_company_id", quotation.customer_company_id)
        quotation.own_company_id = request.form.get("own_company_id", quotation.own_company_id)

        # ✅ Update status (Draft / Accepted / Rejected)
        quotation.status = request.form.get("status", quotation.status)

        # ✅ Update items
        descriptions = request.form.getlist("item_description")
        qtys = request.form.getlist("item_qty")
        prices = request.form.getlist("item_price")
        hsns = request.form.getlist("item_hsn")

        # Clear existing items
        quotation.items.clear()

        for i in range(len(descriptions)):
            if descriptions[i].strip():
                qty = float(qtys[i]) if qtys[i] else 0
                price = float(prices[i]) if prices[i] else 0
                taxable_amount = qty * price

                item = QuotationItem(
                    quotation_id=quotation.id,
                    description=descriptions[i],
                    qty=qty,
                    price=price,
                    taxable_amount=taxable_amount,
                    hsn_no=hsns[i] if i < len(hsns) else None
                )
                quotation.items.append(item)

        db.session.commit()
        flash("Quotation updated successfully!", "success")
        return redirect(url_for("sales.view_quotation", quotation_id=quotation.id))

    own_companies = Company.query.filter_by(company_type="own").all()
    customers = Company.query.filter_by(company_type="customer").all()

    return render_template(
        "edit_quotation.html",
        quotation=quotation,
        own_companies=own_companies,
        customers=customers
    )


# Convert quotation → Purchase Order
@sales_bp.route("/quotation/<int:quotation_id>/convert_po", methods=["POST"])
def convert_to_po(quotation_id):
    quotation = Quotation.query.get_or_404(quotation_id)
    customer_po_number = request.form.get("po_number")

    from ..models import PurchaseOrder
    import datetime
    po = PurchaseOrder(
        po_number=customer_po_number,
        quotation_id=quotation.id,
        date=datetime.date.today()
    )
    db.session.add(po)
    db.session.commit()

    flash("Quotation converted to Purchase Order!", "success")
    return redirect(url_for("sales.view_po", po_id=po.id))


# Quotation home
@sales_bp.route("/quotation/home")
def quotation_home():
    return render_template("quotation_home.html")


@sales_bp.route("/quotation/<int:quotation_id>/delete", methods=["POST"])
def delete_quotation(quotation_id):
    quotation = Quotation.query.get_or_404(quotation_id)

    # Delete quotation and cascade to items
    db.session.delete(quotation)
    db.session.commit()

    flash(f"Quotation {quotation.quotation_number} deleted successfully!", "success")
    return redirect(url_for("sales.list_quotations"))