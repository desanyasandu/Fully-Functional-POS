import json
import os
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
    current_app,
    send_file,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import extract, func

from .extensions import db
from .models import (
    CreditEntry,
    CreditPayment,
    Customer,
    DeviceSetting,
    EXPENSE_CATEGORIES,
    Expense,
    Item,
    LoginHistory,
    Sale,
    SaleItem,
    ShopSetting,
    UOM_CHOICES,
    User,
)
from .utils import generate_bill_no, to_decimal, role_required, backup_db

main_bp = Blueprint("main", __name__)


def _parse_date(raw):
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


@main_bp.route("/")
def home():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("main.login"))


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter(func.lower(User.username) == username.lower()).first()
        is_valid = bool(user and user.check_password(password) and user.is_active_user)

        if user:
            db.session.add(LoginHistory(user_id=user.id, success=is_valid))
            db.session.commit()

        if is_valid:
            login_user(user)
            flash("Login successful.", "success")
            return redirect(url_for("main.dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@main_bp.route("/api/user-role")
def user_role():
    username = request.args.get("username", "").strip()
    if not username:
        return jsonify({"role": ""})
    user = User.query.filter(func.lower(User.username) == username.lower()).first()
    return jsonify({"role": user.role if user else ""})


@main_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for("main.login"))


@main_bp.route("/dashboard")
@login_required
def dashboard():
    sales_total = db.session.query(func.coalesce(func.sum(Sale.total_amount), 0)).scalar() or 0
    sales_due = (
        db.session.query(func.coalesce(func.sum(CreditEntry.amount - CreditEntry.paid_amount), 0))
        .filter(CreditEntry.status != "Paid")
        .scalar()
        or 0
    )
    expense_total = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).scalar() or 0
    purchase_due = (
        db.session.query(func.coalesce(func.sum(Expense.balance), 0))
        .filter(Expense.is_long_term.is_(True))
        .scalar()
        or 0
    )

    customers_count = Customer.query.count()
    suppliers_count = (
        db.session.query(func.count(func.distinct(Item.supplier_name)))
        .filter(Item.supplier_name.isnot(None), Item.supplier_name != "")
        .scalar()
        or 0
    )
    purchases_count = Item.query.count()
    invoices_count = Sale.query.count()

    recent_sales = Sale.query.order_by(Sale.sale_datetime.desc()).limit(8).all()
    recent_items = Item.query.order_by(Item.id.desc()).limit(8).all()

    trending_rows = (
        db.session.query(
            SaleItem.description,
            func.coalesce(func.sum(SaleItem.qty - SaleItem.return_qty), 0).label("qty_sold"),
        )
        .group_by(SaleItem.description)
        .order_by(func.sum(SaleItem.qty - SaleItem.return_qty).desc())
        .limit(10)
        .all()
    )
    trending_labels = [row.description for row in trending_rows]
    trending_values = [float(row.qty_sold or 0) for row in trending_rows]

    debtors = (
        db.session.query(
            Customer.name.label("customer_name"),
            func.sum(CreditEntry.amount - CreditEntry.paid_amount).label("due"),
        )
        .join(CreditEntry, CreditEntry.customer_id == Customer.id)
        .filter(CreditEntry.status != "Paid")
        .group_by(Customer.name)
        .order_by(func.sum(CreditEntry.amount - CreditEntry.paid_amount).desc())
        .all()
    )

    today = date.today()
    month_sales = (
        db.session.query(
            extract("day", Sale.sale_datetime).label("d"),
            func.sum(Sale.total_amount).label("amount"),
        )
        .filter(
            extract("month", Sale.sale_datetime) == today.month,
            extract("year", Sale.sale_datetime) == today.year,
        )
        .group_by("d")
        .order_by("d")
        .all()
    )
    chart_days = [int(row.d) for row in month_sales]
    chart_values = [float(row.amount or 0) for row in month_sales]

    return render_template(
        "dashboard.html",
        sales_total=Decimal(sales_total),
        sales_due=Decimal(sales_due),
        expense_total=Decimal(expense_total),
        purchase_due=Decimal(purchase_due),
        customers_count=customers_count,
        suppliers_count=suppliers_count,
        purchases_count=purchases_count,
        invoices_count=invoices_count,
        recent_sales=recent_sales,
        recent_items=recent_items,
        trending_rows=trending_rows,
        trending_labels=trending_labels,
        trending_values=trending_values,
        debtors=debtors,
        chart_days=chart_days,
        chart_values=chart_values,
    )


@main_bp.route("/sales", methods=["GET", "POST"])
@login_required
def sales():
    customers = Customer.query.order_by(Customer.name.asc()).all()
    items = Item.query.filter_by(is_active=True).order_by(Item.name.asc()).all()

    if request.method == "POST":
        customer_id = request.form.get("customer_id") or None
        payment_type = request.form.get("payment_type", "Cash")
        discount_percent = to_decimal(request.form.get("discount_percent", "0"))
        paid_amount = to_decimal(request.form.get("paid_amount", "0"))
        credit_bill_no = request.form.get("credit_bill_no", "").strip() or None

        try:
            lines = json.loads(request.form.get("lines", "[]"))
        except json.JSONDecodeError:
            lines = []

        if not lines:
            flash("Please add at least one item line.", "warning")
            return redirect(url_for("main.sales"))

        sale = Sale(
            bill_no=generate_bill_no(),
            customer_id=int(customer_id) if customer_id else None,
            payment_type=payment_type,
            discount_percent=discount_percent,
            paid_amount=paid_amount,
            credit_bill_no=credit_bill_no,
            created_by_id=current_user.id,
        )

        subtotal = Decimal("0")
        for line in lines:
            item = db.session.get(Item, int(line.get("item_id", 0)))
            if not item:
                continue

            qty = to_decimal(line.get("qty", "0"))
            return_qty = to_decimal(line.get("return_qty", "0"))
            unit_price = to_decimal(line.get("unit_price", item.selling_price))
            line_discount = to_decimal(line.get("discount", "0"))

            sold_qty = qty - return_qty
            if sold_qty < 0:
                sold_qty = Decimal("0")

            line_total = (sold_qty * unit_price) - line_discount
            if line_total < 0:
                line_total = Decimal("0")

            subtotal += line_total
            item.current_stock = Decimal(item.current_stock or 0) - sold_qty

            sale.items.append(
                SaleItem(
                    item_id=item.id,
                    barcode=item.barcode,
                    description=line.get("description", item.name),
                    qty=qty,
                    return_qty=return_qty,
                    unit_price=unit_price,
                    discount=line_discount,
                    line_total=line_total,
                )
            )

        if not sale.items:
            flash("No valid item lines selected.", "warning")
            return redirect(url_for("main.sales"))

        discount_amount = (subtotal * discount_percent) / Decimal("100")
        total = subtotal - discount_amount
        if total < 0:
            total = Decimal("0")

        if paid_amount > total:
            paid_amount = total

        balance = total - paid_amount
        if payment_type.lower() == "credit" and paid_amount == 0:
            credit_bill_no = credit_bill_no or f"CR-{sale.bill_no}"
            sale.credit_bill_no = credit_bill_no

        sale.subtotal = subtotal
        sale.discount_amount = discount_amount
        sale.total_amount = total
        sale.paid_amount = paid_amount
        sale.balance_amount = balance

        db.session.add(sale)
        db.session.flush()

        if sale.customer_id and balance > 0:
            db.session.add(
                CreditEntry(
                    sale_id=sale.id,
                    customer_id=sale.customer_id,
                    bill_no=sale.credit_bill_no or sale.bill_no,
                    amount=balance,
                    paid_amount=0,
                    status="Unpaid",
                )
            )

        db.session.commit()
        flash(f"Sale saved successfully. Bill No: {sale.bill_no}", "success")
        return redirect(url_for("main.sales"))

    recent_sales = Sale.query.order_by(Sale.sale_datetime.desc()).limit(12).all()
    return render_template(
        "sales.html",
        customers=customers,
        items=items,
        next_bill_no=generate_bill_no(),
        recent_sales=recent_sales,
    )


@main_bp.route("/sales/list")
@login_required
def sales_list():
    sales = Sale.query.order_by(Sale.sale_datetime.desc()).all()
    return render_template("sales_list.html", sales=sales)


@main_bp.route("/sales/print/<int:sale_id>")
@login_required
def print_sale(sale_id):
    sale = db.session.get(Sale, sale_id)
    if not sale:
        flash("Sale not found.", "danger")
        return redirect(url_for("main.sales"))
    return render_template("print_bill.html", sale=sale)


@main_bp.route("/credit", methods=["GET", "POST"])
@login_required
def credit():
    if request.method == "POST":
        credit_entry_id = request.form.get("credit_entry_id")
        settle_amount = to_decimal(request.form.get("settle_amount", "0"))
        note = request.form.get("note", "").strip()

        credit_entry = db.session.get(CreditEntry, int(credit_entry_id)) if credit_entry_id else None
        if not credit_entry:
            flash("Credit entry not found.", "danger")
            return redirect(url_for("main.credit"))

        remaining = credit_entry.remaining_balance
        if settle_amount <= 0:
            flash("Settlement amount should be greater than zero.", "warning")
            return redirect(url_for("main.credit"))

        if settle_amount > remaining:
            settle_amount = remaining

        credit_entry.paid_amount = Decimal(credit_entry.paid_amount or 0) + settle_amount
        credit_entry.status = "Paid" if credit_entry.remaining_balance <= 0 else "Partial"

        db.session.add(
            CreditPayment(
                credit_entry_id=credit_entry.id,
                customer_id=credit_entry.customer_id,
                amount=settle_amount,
                note=note or f"Settlement against {credit_entry.bill_no}",
            )
        )
        db.session.commit()
        flash("Credit payment recorded.", "success")
        return redirect(url_for("main.credit"))

    outstanding_credits = (
        CreditEntry.query.filter(CreditEntry.status != "Paid")
        .order_by(CreditEntry.created_at.desc())
        .all()
    )
    recent_payments = CreditPayment.query.order_by(CreditPayment.created_at.desc()).limit(20).all()
    return render_template(
        "credit.html",
        outstanding_credits=outstanding_credits,
        recent_payments=recent_payments,
    )


@main_bp.route("/inventory", methods=["GET", "POST"])
@login_required
@role_required("Owner", "Technician")
def inventory():
    if request.method == "POST":
        action = request.form.get("action", "add")
        item_id = request.form.get("item_id")

        if action == "delete" and item_id:
            item = db.session.get(Item, int(item_id))
            if item:
                db.session.delete(item)
                db.session.commit()
                flash("Item deleted.", "info")
            return redirect(url_for("main.inventory"))

        item = db.session.get(Item, int(item_id)) if item_id else Item()
        item.barcode = request.form.get("barcode", "").strip()
        item.name = request.form.get("name", "").strip()
        item.description = request.form.get("description", "").strip()
        item.selling_price = to_decimal(request.form.get("selling_price", "0"))
        item.current_stock = to_decimal(request.form.get("current_stock", "0"))
        item.buying_price = to_decimal(request.form.get("buying_price", "0"))
        item.mfd = _parse_date(request.form.get("mfd"))
        item.exp = _parse_date(request.form.get("exp"))
        item.date_added = _parse_date(request.form.get("date_added")) or date.today()
        item.uom = request.form.get("uom", "Unit")
        item.supplier_name = request.form.get("supplier_name", "").strip()
        item.supplier_contact = request.form.get("supplier_contact", "").strip()
        item.other_suppliers = request.form.get("other_suppliers", "").strip()
        item.is_active = True

        if not item_id:
            db.session.add(item)
        db.session.commit()
        flash("Inventory item saved.", "success")
        return redirect(url_for("main.inventory"))

    edit_id = request.args.get("edit_id", type=int)
    editing_item = db.session.get(Item, edit_id) if edit_id else None
    items = Item.query.order_by(Item.id.desc()).all()
    return render_template(
        "inventory.html",
        items=items,
        uom_choices=UOM_CHOICES,
        editing_item=editing_item,
    )


@main_bp.route("/tracking", methods=["GET", "POST"])
@login_required
def tracking():
    if request.method == "POST":
        action = request.form.get("action", "save")
        customer_id = request.form.get("customer_id")

        if action == "delete" and customer_id:
            customer = db.session.get(Customer, int(customer_id))
            if customer:
                db.session.delete(customer)
                db.session.commit()
                flash("Customer deleted.", "info")
            return redirect(url_for("main.tracking"))

        customer = db.session.get(Customer, int(customer_id)) if customer_id else Customer()
        customer.barcode = request.form.get("barcode", "").strip() or f"CUS{Customer.query.count() + 1:03d}"
        customer.name = request.form.get("name", "").strip()
        customer.address = request.form.get("address", "").strip()
        customer.phone = request.form.get("phone", "").strip()
        customer.nic = request.form.get("nic", "").strip()
        customer.friend_name = request.form.get("friend_name", "").strip()
        customer.friend_phone = request.form.get("friend_phone", "").strip()
        customer.friend_address = request.form.get("friend_address", "").strip()
        customer.other_details = request.form.get("other_details", "").strip()

        if not customer_id:
            db.session.add(customer)
        db.session.commit()
        flash("Customer profile saved.", "success")
        return redirect(url_for("main.tracking"))

    edit_id = request.args.get("edit_id", type=int)
    editing_customer = db.session.get(Customer, edit_id) if edit_id else None
    customers = Customer.query.order_by(Customer.id.desc()).all()
    return render_template(
        "tracking.html",
        customers=customers,
        editing_customer=editing_customer,
    )


@main_bp.route("/expenses", methods=["GET", "POST"])
@login_required
@role_required("Owner", "Technician")
def expenses():
    if request.method == "POST":
        action = request.form.get("action", "add")
        expense_id = request.form.get("expense_id")

        if action == "delete" and expense_id:
            expense = db.session.get(Expense, int(expense_id))
            if expense:
                db.session.delete(expense)
                db.session.commit()
                flash("Expense deleted.", "info")
            return redirect(url_for("main.expenses"))

        is_long_term = bool(request.form.get("is_long_term"))
        amount = to_decimal(request.form.get("amount", "0"))
        balance = to_decimal(request.form.get("balance", str(amount)))

        expense = db.session.get(Expense, int(expense_id)) if expense_id else Expense()
        expense.bill_no = request.form.get("bill_no", "").strip()
        expense.category = request.form.get("category", "Other")
        expense.expense_date = _parse_date(request.form.get("expense_date")) or date.today()
        expense.amount = amount
        expense.payment_type = request.form.get("payment_type", "Cash")
        expense.is_long_term = is_long_term
        expense.company_account_phone = request.form.get("company_account_phone", "").strip()
        expense.installments = int(request.form.get("installments") or 0) or None
        expense.balance = balance if is_long_term else Decimal("0")
        expense.notes = request.form.get("notes", "").strip()

        if not expense_id:
            db.session.add(expense)
        db.session.commit()
        flash("Expense saved.", "success")
        return redirect(url_for("main.expenses"))

    today = date.today()
    monthly_expenses = (
        Expense.query.filter(
            extract("month", Expense.expense_date) == today.month,
            extract("year", Expense.expense_date) == today.year,
        )
        .order_by(Expense.expense_date.desc())
        .all()
    )
    long_term_expenses = (
        Expense.query.filter(Expense.is_long_term.is_(True))
        .order_by(Expense.expense_date.desc())
        .all()
    )
    monthly_total = sum([Decimal(e.amount or 0) for e in monthly_expenses], Decimal("0"))
    long_term_total = sum([Decimal(e.balance or 0) for e in long_term_expenses], Decimal("0"))

    return render_template(
        "expenses.html",
        monthly_expenses=monthly_expenses,
        long_term_expenses=long_term_expenses,
        monthly_total=monthly_total,
        long_term_total=long_term_total,
        categories=EXPENSE_CATEGORIES,
    )


@main_bp.route("/reports")
@login_required
@role_required("Owner", "Technician")
def reports():
    bill_no = request.args.get("bill_no", "").strip()
    today = date.today()
    month_start = date(today.year, today.month, 1)

    bill_sale = Sale.query.filter_by(bill_no=bill_no).first() if bill_no else None
    daily_sales = (
        db.session.query(func.coalesce(func.sum(Sale.total_amount), 0))
        .filter(func.date(Sale.sale_datetime) == today)
        .scalar()
    )
    monthly_sales = (
        db.session.query(func.coalesce(func.sum(Sale.total_amount), 0))
        .filter(Sale.sale_datetime >= month_start)
        .scalar()
    )
    low_stock_items = Item.query.filter(Item.current_stock <= 5).order_by(Item.current_stock.asc()).all()
    expiring_items = Item.query.filter(
        Item.exp.isnot(None), Item.exp <= (today + timedelta(days=30))
    ).order_by(Item.exp.asc()).all()
    monthly_expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.expense_date >= month_start)
        .scalar()
    )
    stock_summary = db.session.query(func.coalesce(func.sum(Item.current_stock), 0)).scalar() or 0
    sale_analysis = (
        db.session.query(
            SaleItem.description,
            func.coalesce(func.sum(SaleItem.qty - SaleItem.return_qty), 0).label("qty"),
            func.coalesce(func.sum(SaleItem.line_total), 0).label("total"),
        )
        .group_by(SaleItem.description)
        .order_by(func.sum(SaleItem.line_total).desc())
        .limit(10)
        .all()
    )
    supplier_details = (
        db.session.query(Item.supplier_name, func.count(Item.id).label("item_count"))
        .filter(Item.supplier_name.isnot(None), Item.supplier_name != "")
        .group_by(Item.supplier_name)
        .all()
    )
    credit_list = (
        CreditEntry.query.filter(CreditEntry.status != "Paid")
        .order_by(CreditEntry.created_at.desc())
        .all()
    )
    customer_list = Customer.query.order_by(Customer.created_at.desc()).all()
    login_history = LoginHistory.query.order_by(LoginHistory.login_time.desc()).limit(30).all()
    cashier_summary = (
        db.session.query(
            User.username,
            func.coalesce(func.sum(Sale.total_amount), 0).label("total"),
            func.count(Sale.id).label("invoice_count"),
        )
        .join(Sale, Sale.created_by_id == User.id)
        .filter(User.role == "Cashier")
        .group_by(User.username)
        .all()
    )

    return render_template(
        "reports.html",
        bill_sale=bill_sale,
        bill_no=bill_no,
        daily_sales=Decimal(daily_sales or 0),
        monthly_sales=Decimal(monthly_sales or 0),
        low_stock_items=low_stock_items,
        expiring_items=expiring_items,
        monthly_expenses=Decimal(monthly_expenses or 0),
        stock_summary=Decimal(stock_summary or 0),
        sale_analysis=sale_analysis,
        supplier_details=supplier_details,
        credit_list=credit_list,
        customer_list=customer_list,
        login_history=login_history,
        cashier_summary=cashier_summary,
    )


@main_bp.route("/settings", methods=["GET", "POST"])
@login_required
@role_required("Owner", "Technician")
def settings():
    setting = ShopSetting.query.first()
    if not setting:
        setting = ShopSetting(shop_name="JP SUPER CENTER")
        db.session.add(setting)
        db.session.commit()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "shop_profile":
            if current_user.role != "Technician":
                flash("Only Technician can change shop profile.", "danger")
                return redirect(url_for("main.settings"))
            
            setting.shop_name = request.form.get("shop_name", "").strip()
            setting.address = request.form.get("address", "").strip()
            setting.phone = request.form.get("phone", "").strip()
            setting.email = request.form.get("email", "").strip()
            setting.bill_message = request.form.get("bill_message", "").strip()
            db.session.commit()
            flash("Shop profile updated.", "success")

        elif action == "add_user":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            role = request.form.get("role", "Cashier")
            
            # Security: Owner can only add Cashiers
            if current_user.role == "Owner" and role != "Cashier":
                flash("Owners can only create Cashier accounts.", "danger")
                return redirect(url_for("main.settings"))

            if username and password:
                exists = User.query.filter(func.lower(User.username) == username.lower()).first()
                if exists:
                    flash("Username already exists.", "warning")
                else:
                    user = User(username=username, role=role, full_name=username)
                    user.set_password(password)
                    db.session.add(user)
                    db.session.commit()
                    flash("User account created.", "success")
            else:
                flash("Username and password are required.", "warning")

        elif action == "delete_user":
            user_id = request.form.get("user_id")
            user = db.session.get(User, int(user_id)) if user_id else None
            
            if user:
                # Security: Owner cannot delete Technician or another Owner
                if current_user.role == "Owner" and user.role != "Cashier":
                    flash("Owners can only delete Cashier accounts.", "danger")
                    return redirect(url_for("main.settings"))
                
                if user.id != current_user.id:
                    db.session.delete(user)
                    db.session.commit()
                    flash("User removed.", "info")
                else:
                    flash("Cannot remove yourself.", "warning")
            else:
                flash("User not found.", "warning")

        elif action == "add_device":
            if current_user.role != "Technician":
                flash("Only Technician can manage devices.", "danger")
                return redirect(url_for("main.settings"))
                
            device_type = request.form.get("device_type", "").strip()
            device_name = request.form.get("device_name", "").strip()
            description = request.form.get("description", "").strip()
            if device_type and device_name:
                db.session.add(
                    DeviceSetting(
                        device_type=device_type, device_name=device_name, description=description
                    )
                )
                db.session.commit()
                flash("Device setting added.", "success")
            else:
                flash("Device type and device name are required.", "warning")

        elif action == "delete_device":
            device_id = request.form.get("device_id")
            device = db.session.get(DeviceSetting, int(device_id)) if device_id else None
            if device:
                db.session.delete(device)
                db.session.commit()
                flash("Device removed.", "info")

        return redirect(url_for("main.settings"))

    users = User.query.order_by(User.created_at.desc()).all()
    devices = DeviceSetting.query.order_by(DeviceSetting.created_at.desc()).all()
    return render_template("settings.html", users=users, devices=devices)


@main_bp.route("/backup")
@login_required
@role_required("Owner", "Technician")
def backup():
    db_path = current_app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
    backup_folder = os.path.join(current_app.instance_path, "backups")
    
    try:
        backup_file = backup_db(db_path, backup_folder)
        return send_file(backup_file, as_attachment=True)
    except Exception as e:
        flash(f"Backup failed: {str(e)}", "danger")
        return redirect(url_for("main.dashboard"))


@main_bp.route("/restore", methods=["POST"])
@login_required
@role_required("Technician")
def restore():
    if "backup_file" not in request.files:
        flash("No file part", "warning")
        return redirect(url_for("main.settings"))
    
    file = request.files["backup_file"]
    if file.filename == "":
        flash("No selected file", "warning")
        return redirect(url_for("main.settings"))
    
    if file and file.filename.endswith(".db"):
        db_path = current_app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
        
        try:
            # Close all database connections before replacing the file
            db.session.remove()
            db.engine.dispose()
            
            file.save(db_path)
            flash("Database restored successfully. Please refresh the page.", "success")
        except Exception as e:
            flash(f"Restore failed: {str(e)}", "danger")
    else:
        flash("Invalid file type. Please upload a .db file.", "warning")
        
    return redirect(url_for("main.settings"))


@main_bp.route("/coming-soon/<feature>")
@login_required
def coming_soon(feature):
    return render_template("coming_soon.html", feature=feature.replace("-", " ").title())

