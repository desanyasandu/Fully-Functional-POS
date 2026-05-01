from datetime import date, datetime
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db

UOM_CHOICES = [
    "mg",
    "g",
    "Kg",
    "MT",
    "Dozen",
    "Pair",
    "Set",
    "Bundle",
    "Rim",
    "Bottle",
    "Can",
    "Carton",
    "Cup",
    "Tub",
    "Sachet",
    "Roll",
    "Tube",
    "Jar",
    "Bag",
    "Sack",
    "ft",
    "cm",
    "m",
    "Yard",
    "sheet",
    "Sq.ft",
    "Comb",
    "Pieces",
    "Unit",
    "Packet",
    "Cube",
]

EXPENSE_CATEGORIES = [
    "Shop Rent",
    "Water Bill",
    "Electricity Bill",
    "Internet/Phone Bill",
    "Loan",
    "Other",
    "Saving",
    "Long term Expenses",
]


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, default="Cashier")
    full_name = db.Column(db.String(120), nullable=True)
    is_active_user = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    sales = db.relationship("Sale", backref="cashier", lazy=True)
    login_history = db.relationship("LoginHistory", backref="user", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class LoginHistory(db.Model):
    __tablename__ = "login_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    login_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    success = db.Column(db.Boolean, nullable=False, default=True)


class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    barcode = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    nic = db.Column(db.String(30), nullable=True)
    friend_name = db.Column(db.String(120), nullable=True)
    friend_phone = db.Column(db.String(30), nullable=True)
    friend_address = db.Column(db.String(255), nullable=True)
    other_details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    sales = db.relationship("Sale", backref="customer", lazy=True)
    credits = db.relationship("CreditEntry", backref="customer", lazy=True)


class Item(db.Model):
    __tablename__ = "items"

    id = db.Column(db.Integer, primary_key=True)
    barcode = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    selling_price = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    current_stock = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    buying_price = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    mfd = db.Column(db.Date, nullable=True)
    exp = db.Column(db.Date, nullable=True)
    date_added = db.Column(db.Date, default=date.today, nullable=False)
    uom = db.Column(db.String(30), default="Unit", nullable=False)
    supplier_name = db.Column(db.String(120), nullable=True)
    supplier_contact = db.Column(db.String(60), nullable=True)
    other_suppliers = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    sale_items = db.relationship("SaleItem", backref="item", lazy=True)


class Sale(db.Model):
    __tablename__ = "sales"

    id = db.Column(db.Integer, primary_key=True)
    bill_no = db.Column(db.String(40), unique=True, nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True)
    sale_datetime = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    payment_type = db.Column(db.String(20), nullable=False, default="Cash")
    discount_percent = db.Column(db.Numeric(5, 2), default=0, nullable=False)
    discount_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    total_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    paid_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    balance_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    credit_bill_no = db.Column(db.String(40), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    items = db.relationship("SaleItem", backref="sale", lazy=True, cascade="all, delete-orphan")
    credits = db.relationship("CreditEntry", backref="sale", lazy=True)


class SaleItem(db.Model):
    __tablename__ = "sale_items"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id"), nullable=False)
    barcode = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    qty = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    return_qty = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    discount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    line_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)


class CreditEntry(db.Model):
    __tablename__ = "credit_entries"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    bill_no = db.Column(db.String(40), nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    paid_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="Unpaid")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    payments = db.relationship(
        "CreditPayment", backref="credit_entry", lazy=True, cascade="all, delete-orphan"
    )

    @property
    def remaining_balance(self):
        return Decimal(self.amount or 0) - Decimal(self.paid_amount or 0)


class CreditPayment(db.Model):
    __tablename__ = "credit_payments"

    id = db.Column(db.Integer, primary_key=True)
    credit_entry_id = db.Column(db.Integer, db.ForeignKey("credit_entries.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    note = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Expense(db.Model):
    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True)
    bill_no = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    expense_date = db.Column(db.Date, default=date.today, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    payment_type = db.Column(db.String(40), nullable=False, default="Cash")
    is_long_term = db.Column(db.Boolean, nullable=False, default=False)
    company_account_phone = db.Column(db.String(120), nullable=True)
    installments = db.Column(db.Integer, nullable=True)
    balance = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class ShopSetting(db.Model):
    __tablename__ = "shop_settings"

    id = db.Column(db.Integer, primary_key=True)
    shop_name = db.Column(db.String(120), nullable=False, default="JP SUPER CENTER")
    address = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(60), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    bill_message = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class DeviceSetting(db.Model):
    __tablename__ = "device_settings"

    id = db.Column(db.Integer, primary_key=True)
    device_type = db.Column(db.String(80), nullable=False)
    device_name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


def seed_initial_data():
    if not User.query.filter_by(username="admin").first():
        owner = User(username="admin", role="Owner", full_name="System Owner")
        owner.set_password("admin123")
        db.session.add(owner)

    if not User.query.filter_by(username="tech").first():
        tech = User(username="tech", role="Technician", full_name="System Technician")
        tech.set_password("tech123")
        db.session.add(tech)

    if not ShopSetting.query.first():
        db.session.add(
            ShopSetting(
                shop_name="JP SUPER CENTER",
                address="Front of General Hospital, Ampara",
                phone="+94 712247385",
                email="info@example.com",
                bill_message="Thank you for shopping with us.",
            )
        )

    if Customer.query.count() == 0:
        db.session.add_all(
            [
                Customer(barcode="CUS001", name="Walk-in Customer", phone="N/A"),
                Customer(barcode="CUS002", name="MG General Traders Ltd", phone="0711000000"),
            ]
        )

    if Item.query.count() == 0:
        db.session.add_all(
            [
                Item(
                    barcode="ITM001",
                    name="Pixel 1.5 Liters 2 in 1 Juice Blender - Black",
                    description="Kitchen appliance",
                    selling_price=Decimal("20.00"),
                    current_stock=Decimal("50"),
                    buying_price=Decimal("15.00"),
                    uom="Unit",
                    supplier_name="JP Supplier",
                ),
                Item(
                    barcode="ITM002",
                    name="Sundabest Flask 3 L Vacuum Stainless Steel",
                    description="Home item",
                    selling_price=Decimal("18.00"),
                    current_stock=Decimal("35"),
                    buying_price=Decimal("12.00"),
                    uom="Unit",
                    supplier_name="JP Supplier",
                ),
            ]
        )

    db.session.commit()
