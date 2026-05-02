from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user, login_required
from .. import db
from ..models import Company

company_bp = Blueprint('company', __name__, url_prefix='/')


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
        
        # Check if GST already exists
        if Company.query.filter_by(gst_no=gst_no).first():
            return render_template('create_company.html', error="GST number already exists")
        
        # Create new company
        company = Company(
            company_name=company_name,
            location=location,
            state_code=state_code,
            state=state,
            gst_no=gst_no,
            email=email,
            created_by=current_user.id
        )
        
        db.session.add(company)
        db.session.commit()
        
        return redirect(url_for('company.home'))
    
    return render_template('create_company.html')


@company_bp.route('/company/<int:company_id>')
def view_company(company_id):
    """View single company details"""
    company = Company.query.get_or_404(company_id)
    return render_template('view_company.html', company=company)


@company_bp.route('/api/companies')
def get_companies_api():
    """API endpoint to get all companies as JSON"""
    companies = Company.query.all()
    return jsonify([{
        'id': c.id,
        'company_name': c.company_name,
        'location': c.location,
        'state': c.state,
        'gst_no': c.gst_no,
        'email': c.email,
        'created_at': c.created_at.isoformat()
    } for c in companies])
