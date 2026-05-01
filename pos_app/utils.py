import shutil
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import wraps
from flask import abort, send_file, flash, redirect, url_for
from flask_login import current_user

from .models import Sale


def to_decimal(value, default="0"):
    try:
        if value is None or value == "":
            return Decimal(default)
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def format_money(value):
    amount = to_decimal(value)
    return f"{amount:,.2f}"


def generate_bill_no():
    prefix = datetime.utcnow().strftime("SL/%Y/%m/")
    last_sale = Sale.query.order_by(Sale.id.desc()).first()
    next_sequence = 1
    if last_sale:
        next_sequence = last_sale.id + 1
    return f"{prefix}{next_sequence}"


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                flash("You do not have permission to access this page.", "danger")
                return redirect(url_for("main.dashboard"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def backup_db(db_path, backup_folder):
    if not os.path.exists(backup_folder):
        os.makedirs(backup_folder)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_folder, f"pos_backup_{timestamp}.db")
    shutil.copy2(db_path, backup_file)
    return backup_file
