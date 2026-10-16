from datetime import datetime

from flask import Blueprint, render_template
from flask_login import login_required

from db import get_db

bp = Blueprint('dashboard', __name__)


@bp.route('/')
@login_required
def index():
    db = get_db()
    today = datetime.now().strftime('%Y-%m-%d')
    in_today = db.execute(
        """SELECT COUNT(*) AS c, COALESCE(SUM(total_amount), 0) AS s FROM stock_in
           WHERE status = 'approved' AND date(created_at) = ?""", (today,)).fetchone()
    out_today = db.execute(
        """SELECT COUNT(*) AS c, COALESCE(SUM(total_amount), 0) AS s FROM stock_out
           WHERE status = 'approved' AND date(created_at) = ?""", (today,)).fetchone()
    inv = db.execute(
        """SELECT COALESCE(SUM(i.quantity * p.price), 0) AS v, COALESCE(SUM(i.quantity), 0) AS q
           FROM inventory i JOIN products p ON p.id = i.product_id""").fetchone()
    pending_in = db.execute("SELECT COUNT(*) AS c FROM stock_in WHERE status = 'pending'").fetchone()['c']
    pending_out = db.execute("SELECT COUNT(*) AS c FROM stock_out WHERE status = 'pending'").fetchone()['c']
    pending_check = db.execute("SELECT COUNT(*) AS c FROM stock_check WHERE status = 'pending'").fetchone()['c']
    low_stock = db.execute(
        """SELECT p.sku, p.name, p.unit, p.warning_low, i.quantity, w.name AS warehouse_name
           FROM inventory i
           JOIN products p ON p.id = i.product_id
           JOIN warehouses w ON w.id = i.warehouse_id
           WHERE i.quantity < p.warning_low
           ORDER BY (p.warning_low - i.quantity) DESC LIMIT 10""").fetchall()
    high_stock = db.execute(
        """SELECT p.sku, p.name, p.unit, p.warning_high, i.quantity, w.name AS warehouse_name
           FROM inventory i
           JOIN products p ON p.id = i.product_id
           JOIN warehouses w ON w.id = i.warehouse_id
           WHERE i.quantity > p.warning_high
           ORDER BY (i.quantity - p.warning_high) DESC LIMIT 5""").fetchall()
    recent_logs = db.execute(
        """SELECT l.*, p.name AS product_name, w.name AS warehouse_name, COALESCE(NULLIF(u.real_name, ''), u.username) AS operator_name
           FROM stock_log l
           JOIN products p ON p.id = l.product_id
           JOIN warehouses w ON w.id = l.warehouse_id
           LEFT JOIN users u ON u.id = l.operator_id
           ORDER BY l.id DESC LIMIT 8""").fetchall()
    return render_template('dashboard.html', in_today=in_today, out_today=out_today, inv=inv,
                           pending_in=pending_in, pending_out=pending_out,
                           pending_check=pending_check, low_stock=low_stock,
                           high_stock=high_stock, recent_logs=recent_logs)
