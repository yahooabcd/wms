from datetime import datetime

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user

from auth import permission_required
from dao import change_inventory, to_float, to_int, write_stock_log
from db import get_db, transaction

bp = Blueprint('stock_in', __name__, url_prefix='/stock-in')


def _gen_code(db):
    prefix = 'IN' + datetime.now().strftime('%Y%m%d')
    row = db.execute(
        'SELECT code FROM stock_in WHERE code LIKE ? ORDER BY code DESC LIMIT 1',
        (prefix + '%',)).fetchone()
    seq = int(row['code'][-4:]) + 1 if row else 1
    return f'{prefix}{seq:04d}'


def _form_data():
    db = get_db()
    warehouses = db.execute('SELECT * FROM warehouses ORDER BY id').fetchall()
    suppliers = db.execute('SELECT * FROM suppliers ORDER BY id').fetchall()
    products = [dict(r) for r in db.execute(
        'SELECT id, sku, name, spec, unit, price FROM products ORDER BY id').fetchall()]
    return warehouses, suppliers, products


def _parse_items(f):
    """解析明细行数组，返回 [{product_id, quantity, unit_price, subtotal}]，非法则抛 ValueError。"""
    product_ids = f.getlist('product_id')
    quantities = f.getlist('quantity')
    prices = f.getlist('unit_price')
    if not product_ids:
        raise ValueError('请至少添加一行商品明细')
    if not (len(product_ids) == len(quantities) == len(prices)):
        raise ValueError('明细数据不完整，请重新提交')
    items = []
    for pid, qty, price in zip(product_ids, quantities, prices):
        qty_i, price_f = to_int(qty), to_float(price)
        if not to_int(pid) or qty_i <= 0 or price_f < 0:
            raise ValueError('明细中存在无效的商品、数量或单价')
        items.append({'product_id': to_int(pid), 'quantity': qty_i,
                      'unit_price': price_f, 'subtotal': round(qty_i * price_f, 2)})
    return items


def _get_order(db, oid):
    return db.execute(
        '''SELECT o.*, w.name AS warehouse_name, s.name AS supplier_name, COALESCE(NULLIF(u.real_name, ''), u.username) AS operator_name
           FROM stock_in o
           LEFT JOIN warehouses w ON w.id = o.warehouse_id
           LEFT JOIN suppliers s ON s.id = o.supplier_id
           LEFT JOIN users u ON u.id = o.operator_id
           WHERE o.id = ?''', (oid,)).fetchone()


def _get_items(db, oid):
    return db.execute(
        '''SELECT i.*, p.sku, p.name AS product_name, p.spec, p.unit
           FROM stock_in_items i JOIN products p ON p.id = i.product_id
           WHERE i.stock_in_id = ? ORDER BY i.id''', (oid,)).fetchall()


@bp.route('/')
@permission_required('stock_in:view')
def index():
    status = request.args.get('status', '')
    sql = '''SELECT o.*, w.name AS warehouse_name, s.name AS supplier_name, COALESCE(NULLIF(u.real_name, ''), u.username) AS operator_name
             FROM stock_in o
             LEFT JOIN warehouses w ON w.id = o.warehouse_id
             LEFT JOIN suppliers s ON s.id = o.supplier_id
             LEFT JOIN users u ON u.id = o.operator_id'''
    params = []
    if status in ('pending', 'approved'):
        sql += ' WHERE o.status = ?'
        params.append(status)
    sql += ' ORDER BY o.id DESC'
    orders = get_db().execute(sql, params).fetchall()
    return render_template('stock_in_list.html', orders=orders, status=status)


@bp.route('/create', methods=['GET', 'POST'])
@permission_required('stock_in:create')
def create():
    if request.method == 'POST':
        f = request.form
        try:
            if not f.get('warehouse_id'):
                raise ValueError('请选择入库仓库')
            items = _parse_items(f)
        except ValueError as e:
            flash(str(e), 'danger')
        else:
            total = round(sum(i['subtotal'] for i in items), 2)
            with transaction() as tx:
                code = _gen_code(tx)
                cur = tx.execute(
                    '''INSERT INTO stock_in (code, warehouse_id, supplier_id, operator_id, total_amount, status, remark)
                       VALUES (?, ?, ?, ?, ?, 'pending', ?)''',
                    (code, f['warehouse_id'], to_int(f.get('supplier_id')) or None,
                     current_user.id, total, f.get('remark', '').strip()))
                oid = cur.lastrowid
                for it in items:
                    tx.execute(
                        '''INSERT INTO stock_in_items (stock_in_id, product_id, quantity, unit_price, subtotal)
                           VALUES (?, ?, ?, ?, ?)''',
                        (oid, it['product_id'], it['quantity'], it['unit_price'], it['subtotal']))
            flash(f'入库单 {code} 创建成功，等待审核', 'success')
            return redirect(url_for('stock_in.detail', oid=oid))
    warehouses, suppliers, products = _form_data()
    return render_template('stock_in_form.html', warehouses=warehouses, suppliers=suppliers,
                           products=products, order=None, items=[])


@bp.route('/<int:oid>')
@permission_required('stock_in:view')
def detail(oid):
    db = get_db()
    order = _get_order(db, oid)
    if not order:
        abort(404)
    return render_template('stock_in_detail.html', order=order, items=_get_items(db, oid))


@bp.route('/<int:oid>/print')
@permission_required('stock_in:view')
def print_order(oid):
    """打印视图：独立页面，自动唤起打印对话框。"""
    db = get_db()
    order = _get_order(db, oid)
    if not order:
        abort(404)
    return render_template('print_order.html', order=order, items=_get_items(db, oid),
                           doc_title='入库单', party_label='供应商',
                           party_name=order['supplier_name'] or '—')


@bp.route('/<int:oid>/edit', methods=['GET', 'POST'])
@permission_required('stock_in:edit')
def edit(oid):
    db = get_db()
    order = db.execute('SELECT * FROM stock_in WHERE id = ?', (oid,)).fetchone()
    if not order:
        abort(404)
    if order['status'] != 'pending':
        flash('只有待审核的单据可以编辑', 'warning')
        return redirect(url_for('stock_in.detail', oid=oid))
    if request.method == 'POST':
        f = request.form
        try:
            if not f.get('warehouse_id'):
                raise ValueError('请选择入库仓库')
            items = _parse_items(f)
        except ValueError as e:
            flash(str(e), 'danger')
        else:
            total = round(sum(i['subtotal'] for i in items), 2)
            with transaction() as tx:
                tx.execute(
                    '''UPDATE stock_in SET warehouse_id = ?, supplier_id = ?, total_amount = ?, remark = ?
                       WHERE id = ?''',
                    (f['warehouse_id'], to_int(f.get('supplier_id')) or None, total,
                     f.get('remark', '').strip(), oid))
                tx.execute('DELETE FROM stock_in_items WHERE stock_in_id = ?', (oid,))
                for it in items:
                    tx.execute(
                        '''INSERT INTO stock_in_items (stock_in_id, product_id, quantity, unit_price, subtotal)
                           VALUES (?, ?, ?, ?, ?)''',
                        (oid, it['product_id'], it['quantity'], it['unit_price'], it['subtotal']))
            flash('入库单已更新', 'success')
            return redirect(url_for('stock_in.detail', oid=oid))
    warehouses, suppliers, products = _form_data()
    items = [dict(r) for r in db.execute(
        'SELECT product_id, quantity, unit_price FROM stock_in_items WHERE stock_in_id = ? ORDER BY id',
        (oid,)).fetchall()]
    return render_template('stock_in_form.html', warehouses=warehouses, suppliers=suppliers,
                           products=products, order=order, items=items)


@bp.route('/<int:oid>/audit', methods=['POST'])
@permission_required('stock_in:audit')
def audit(oid):
    db = get_db()
    order = db.execute('SELECT * FROM stock_in WHERE id = ?', (oid,)).fetchone()
    if not order:
        abort(404)
    if order['status'] != 'pending':
        flash('该单据已审核，不能重复操作', 'warning')
        return redirect(url_for('stock_in.detail', oid=oid))
    items = db.execute('SELECT * FROM stock_in_items WHERE stock_in_id = ?', (oid,)).fetchall()
    try:
        with transaction() as tx:
            for it in items:
                balance = change_inventory(tx, it['product_id'], order['warehouse_id'], it['quantity'])
                write_stock_log(tx, 'in', oid, it['product_id'], order['warehouse_id'],
                                it['quantity'], balance, current_user.id)
            tx.execute("UPDATE stock_in SET status = 'approved' WHERE id = ?", (oid,))
    except ValueError as e:
        flash(str(e), 'danger')
        return redirect(url_for('stock_in.detail', oid=oid))
    flash('审核通过，库存已更新', 'success')
    return redirect(url_for('stock_in.detail', oid=oid))


@bp.route('/<int:oid>/delete', methods=['POST'])
@permission_required('stock_in:delete')
def delete(oid):
    db = get_db()
    order = db.execute('SELECT status FROM stock_in WHERE id = ?', (oid,)).fetchone()
    if not order:
        abort(404)
    if order['status'] != 'pending':
        flash('已审核的单据不能删除', 'warning')
    else:
        db.execute('DELETE FROM stock_in WHERE id = ?', (oid,))
        db.commit()
        flash('入库单已删除', 'success')
    return redirect(url_for('stock_in.index'))
