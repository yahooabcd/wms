from datetime import datetime

from flask import (Blueprint, abort, flash, jsonify, redirect, render_template,
                   request, url_for)
from flask_login import current_user

from auth import permission_required
from dao import change_inventory, to_float, to_int, write_stock_log
from db import get_db, transaction

bp = Blueprint('stock_out', __name__, url_prefix='/stock-out')


def _gen_code(db):
    prefix = 'OUT' + datetime.now().strftime('%Y%m%d')
    row = db.execute(
        'SELECT code FROM stock_out WHERE code LIKE ? ORDER BY code DESC LIMIT 1',
        (prefix + '%',)).fetchone()
    seq = int(row['code'][-4:]) + 1 if row else 1
    return f'{prefix}{seq:04d}'


def _form_data():
    db = get_db()
    warehouses = db.execute('SELECT * FROM warehouses ORDER BY id').fetchall()
    customers = db.execute('SELECT * FROM customers ORDER BY id').fetchall()
    products = [dict(r) for r in db.execute(
        'SELECT id, sku, name, spec, unit, price FROM products ORDER BY id').fetchall()]
    return warehouses, customers, products


def _parse_items(f):
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


def _check_availability(db, warehouse_id, items):
    """校验出库数量不超过当前库存（按商品聚合），不足抛 ValueError。"""
    need = {}
    for it in items:
        need[it['product_id']] = need.get(it['product_id'], 0) + it['quantity']
    for pid, qty in need.items():
        row = db.execute('SELECT quantity FROM inventory WHERE product_id = ? AND warehouse_id = ?',
                         (pid, warehouse_id)).fetchone()
        avail = row['quantity'] if row else 0
        if avail < qty:
            name = db.execute('SELECT name FROM products WHERE id = ?', (pid,)).fetchone()['name']
            raise ValueError(f'商品「{name}」库存不足：当前 {avail}，需要 {qty}')


def _get_order(db, oid):
    return db.execute(
        '''SELECT o.*, w.name AS warehouse_name, c.name AS customer_name, COALESCE(NULLIF(u.real_name, ''), u.username) AS operator_name
           FROM stock_out o
           LEFT JOIN warehouses w ON w.id = o.warehouse_id
           LEFT JOIN customers c ON c.id = o.customer_id
           LEFT JOIN users u ON u.id = o.operator_id
           WHERE o.id = ?''', (oid,)).fetchone()


def _get_items(db, oid):
    return db.execute(
        '''SELECT i.*, p.sku, p.name AS product_name, p.spec, p.unit
           FROM stock_out_items i JOIN products p ON p.id = i.product_id
           WHERE i.stock_out_id = ? ORDER BY i.id''', (oid,)).fetchall()


@bp.route('/')
@permission_required('stock_out:view')
def index():
    status = request.args.get('status', '')
    sql = '''SELECT o.*, w.name AS warehouse_name, c.name AS customer_name, COALESCE(NULLIF(u.real_name, ''), u.username) AS operator_name
             FROM stock_out o
             LEFT JOIN warehouses w ON w.id = o.warehouse_id
             LEFT JOIN customers c ON c.id = o.customer_id
             LEFT JOIN users u ON u.id = o.operator_id'''
    params = []
    if status in ('pending', 'approved'):
        sql += ' WHERE o.status = ?'
        params.append(status)
    sql += ' ORDER BY o.id DESC'
    orders = get_db().execute(sql, params).fetchall()
    return render_template('stock_out_list.html', orders=orders, status=status)


@bp.route('/api/availability')
@permission_required('stock_out:create')
def api_availability():
    """返回指定仓库各商品可用库存，供前端出库校验。"""
    wid = request.args.get('warehouse_id', type=int)
    rows = get_db().execute(
        'SELECT product_id, quantity FROM inventory WHERE warehouse_id = ?', (wid,)).fetchall()
    return jsonify({r['product_id']: r['quantity'] for r in rows})


@bp.route('/create', methods=['GET', 'POST'])
@permission_required('stock_out:create')
def create():
    if request.method == 'POST':
        f = request.form
        try:
            if not f.get('warehouse_id'):
                raise ValueError('请选择出库仓库')
            items = _parse_items(f)
            _check_availability(get_db(), to_int(f['warehouse_id']), items)
        except ValueError as e:
            flash(str(e), 'danger')
        else:
            total = round(sum(i['subtotal'] for i in items), 2)
            with transaction() as tx:
                code = _gen_code(tx)
                cur = tx.execute(
                    '''INSERT INTO stock_out (code, warehouse_id, customer_id, operator_id, total_amount, status, remark)
                       VALUES (?, ?, ?, ?, ?, 'pending', ?)''',
                    (code, f['warehouse_id'], to_int(f.get('customer_id')) or None,
                     current_user.id, total, f.get('remark', '').strip()))
                oid = cur.lastrowid
                for it in items:
                    tx.execute(
                        '''INSERT INTO stock_out_items (stock_out_id, product_id, quantity, unit_price, subtotal)
                           VALUES (?, ?, ?, ?, ?)''',
                        (oid, it['product_id'], it['quantity'], it['unit_price'], it['subtotal']))
            flash(f'出库单 {code} 创建成功，等待审核', 'success')
            return redirect(url_for('stock_out.detail', oid=oid))
    warehouses, customers, products = _form_data()
    return render_template('stock_out_form.html', warehouses=warehouses, customers=customers,
                           products=products, order=None, items=[])


@bp.route('/<int:oid>')
@permission_required('stock_out:view')
def detail(oid):
    db = get_db()
    order = _get_order(db, oid)
    if not order:
        abort(404)
    return render_template('stock_out_detail.html', order=order, items=_get_items(db, oid))


@bp.route('/<int:oid>/print')
@permission_required('stock_out:view')
def print_order(oid):
    """打印视图：独立页面，自动唤起打印对话框。"""
    db = get_db()
    order = _get_order(db, oid)
    if not order:
        abort(404)
    return render_template('print_order.html', order=order, items=_get_items(db, oid),
                           doc_title='出库单', party_label='客户',
                           party_name=order['customer_name'] or '—')


@bp.route('/<int:oid>/edit', methods=['GET', 'POST'])
@permission_required('stock_out:edit')
def edit(oid):
    db = get_db()
    order = db.execute('SELECT * FROM stock_out WHERE id = ?', (oid,)).fetchone()
    if not order:
        abort(404)
    if order['status'] != 'pending':
        flash('只有待审核的单据可以编辑', 'warning')
        return redirect(url_for('stock_out.detail', oid=oid))
    if request.method == 'POST':
        f = request.form
        try:
            if not f.get('warehouse_id'):
                raise ValueError('请选择出库仓库')
            items = _parse_items(f)
            _check_availability(db, to_int(f['warehouse_id']), items)
        except ValueError as e:
            flash(str(e), 'danger')
        else:
            total = round(sum(i['subtotal'] for i in items), 2)
            with transaction() as tx:
                tx.execute(
                    '''UPDATE stock_out SET warehouse_id = ?, customer_id = ?, total_amount = ?, remark = ?
                       WHERE id = ?''',
                    (f['warehouse_id'], to_int(f.get('customer_id')) or None, total,
                     f.get('remark', '').strip(), oid))
                tx.execute('DELETE FROM stock_out_items WHERE stock_out_id = ?', (oid,))
                for it in items:
                    tx.execute(
                        '''INSERT INTO stock_out_items (stock_out_id, product_id, quantity, unit_price, subtotal)
                           VALUES (?, ?, ?, ?, ?)''',
                        (oid, it['product_id'], it['quantity'], it['unit_price'], it['subtotal']))
            flash('出库单已更新', 'success')
            return redirect(url_for('stock_out.detail', oid=oid))
    warehouses, customers, products = _form_data()
    items = [dict(r) for r in db.execute(
        'SELECT product_id, quantity, unit_price FROM stock_out_items WHERE stock_out_id = ? ORDER BY id',
        (oid,)).fetchall()]
    return render_template('stock_out_form.html', warehouses=warehouses, customers=customers,
                           products=products, order=order, items=items)


@bp.route('/<int:oid>/audit', methods=['POST'])
@permission_required('stock_out:audit')
def audit(oid):
    db = get_db()
    order = db.execute('SELECT * FROM stock_out WHERE id = ?', (oid,)).fetchone()
    if not order:
        abort(404)
    if order['status'] != 'pending':
        flash('该单据已审核，不能重复操作', 'warning')
        return redirect(url_for('stock_out.detail', oid=oid))
    items = db.execute('SELECT * FROM stock_out_items WHERE stock_out_id = ?', (oid,)).fetchall()
    try:
        _check_availability(db, order['warehouse_id'],
                            [{'product_id': i['product_id'], 'quantity': i['quantity']} for i in items])
        with transaction() as tx:
            for it in items:
                balance = change_inventory(tx, it['product_id'], order['warehouse_id'], -it['quantity'])
                write_stock_log(tx, 'out', oid, it['product_id'], order['warehouse_id'],
                                -it['quantity'], balance, current_user.id)
            tx.execute("UPDATE stock_out SET status = 'approved' WHERE id = ?", (oid,))
    except ValueError as e:
        flash(str(e), 'danger')
        return redirect(url_for('stock_out.detail', oid=oid))
    flash('审核通过，库存已扣减', 'success')
    return redirect(url_for('stock_out.detail', oid=oid))


@bp.route('/<int:oid>/delete', methods=['POST'])
@permission_required('stock_out:delete')
def delete(oid):
    db = get_db()
    order = db.execute('SELECT status FROM stock_out WHERE id = ?', (oid,)).fetchone()
    if not order:
        abort(404)
    if order['status'] != 'pending':
        flash('已审核的单据不能删除', 'warning')
    else:
        db.execute('DELETE FROM stock_out WHERE id = ?', (oid,))
        db.commit()
        flash('出库单已删除', 'success')
    return redirect(url_for('stock_out.index'))
