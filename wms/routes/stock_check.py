from datetime import datetime

from flask import (Blueprint, abort, flash, jsonify, redirect, render_template,
                   request, url_for)
from flask_login import current_user

from auth import permission_required
from dao import change_inventory, to_int, write_stock_log
from db import get_db, transaction

bp = Blueprint('stock_check', __name__, url_prefix='/stock-check')


def _gen_code(db):
    prefix = 'CK' + datetime.now().strftime('%Y%m%d')
    row = db.execute(
        'SELECT code FROM stock_check WHERE code LIKE ? ORDER BY code DESC LIMIT 1',
        (prefix + '%',)).fetchone()
    seq = int(row['code'][-4:]) + 1 if row else 1
    return f'{prefix}{seq:04d}'


def _get_order(db, cid):
    return db.execute(
        '''SELECT c.*, w.name AS warehouse_name, COALESCE(NULLIF(u.real_name, ''), u.username) AS operator_name
           FROM stock_check c
           LEFT JOIN warehouses w ON w.id = c.warehouse_id
           LEFT JOIN users u ON u.id = c.operator_id
           WHERE c.id = ?''', (cid,)).fetchone()


def _get_items(db, cid):
    return db.execute(
        '''SELECT i.*, p.sku, p.name AS product_name, p.spec, p.unit, p.price
           FROM stock_check_items i JOIN products p ON p.id = i.product_id
           WHERE i.stock_check_id = ? ORDER BY i.id''', (cid,)).fetchall()


@bp.route('/')
@permission_required('stock_check:view')
def index():
    status = request.args.get('status', '')
    sql = '''SELECT c.*, w.name AS warehouse_name, COALESCE(NULLIF(u.real_name, ''), u.username) AS operator_name,
                    (SELECT COALESCE(SUM(CASE WHEN i.diff > 0 THEN i.diff ELSE 0 END), 0)
                     FROM stock_check_items i WHERE i.stock_check_id = c.id) AS total_profit,
                    (SELECT COALESCE(SUM(CASE WHEN i.diff < 0 THEN -i.diff ELSE 0 END), 0)
                     FROM stock_check_items i WHERE i.stock_check_id = c.id) AS total_loss
             FROM stock_check c
             LEFT JOIN warehouses w ON w.id = c.warehouse_id
             LEFT JOIN users u ON u.id = c.operator_id'''
    params = []
    if status in ('pending', 'approved'):
        sql += ' WHERE c.status = ?'
        params.append(status)
    sql += ' ORDER BY c.id DESC'
    orders = get_db().execute(sql, params).fetchall()
    return render_template('stock_check_list.html', orders=orders, status=status)


@bp.route('/api/items')
@permission_required('stock_check:create')
def api_items():
    """加载指定仓库的现有库存，作为盘点单明细（system_qty）。"""
    wid = request.args.get('warehouse_id', type=int)
    rows = get_db().execute(
        '''SELECT i.product_id, p.sku, p.name, p.spec, p.unit, i.quantity AS system_qty
           FROM inventory i JOIN products p ON p.id = i.product_id
           WHERE i.warehouse_id = ? ORDER BY p.id''', (wid,)).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/create', methods=['GET', 'POST'])
@permission_required('stock_check:create')
def create():
    db = get_db()
    if request.method == 'POST':
        f = request.form
        wid = to_int(f.get('warehouse_id'))
        product_ids = f.getlist('product_id')
        system_qtys = f.getlist('system_qty')
        actual_qtys = f.getlist('actual_qty')
        if not wid or not product_ids:
            flash('请选择仓库并加载盘点商品', 'danger')
        else:
            with transaction() as tx:
                code = _gen_code(tx)
                cur = tx.execute(
                    '''INSERT INTO stock_check (code, warehouse_id, operator_id, status, remark)
                       VALUES (?, ?, ?, 'pending', ?)''',
                    (code, wid, current_user.id, f.get('remark', '').strip()))
                cid = cur.lastrowid
                for pid, sq, aq in zip(product_ids, system_qtys, actual_qtys):
                    s, a = to_int(sq), to_int(aq)
                    tx.execute(
                        '''INSERT INTO stock_check_items (stock_check_id, product_id, system_qty, actual_qty, diff)
                           VALUES (?, ?, ?, ?, ?)''',
                        (cid, to_int(pid), s, a, a - s))
            flash(f'盘点单 {code} 创建成功，等待审核', 'success')
            return redirect(url_for('stock_check.detail', cid=cid))
    warehouses = db.execute('SELECT * FROM warehouses ORDER BY id').fetchall()
    return render_template('stock_check_form.html', warehouses=warehouses, order=None, items=[])


@bp.route('/<int:cid>')
@permission_required('stock_check:view')
def detail(cid):
    db = get_db()
    order = _get_order(db, cid)
    if not order:
        abort(404)
    return render_template('stock_check_detail.html', order=order, items=_get_items(db, cid))


@bp.route('/<int:cid>/edit', methods=['GET', 'POST'])
@permission_required('stock_check:edit')
def edit(cid):
    db = get_db()
    order = db.execute('SELECT * FROM stock_check WHERE id = ?', (cid,)).fetchone()
    if not order:
        abort(404)
    if order['status'] != 'pending':
        flash('只有待审核的盘点单可以编辑', 'warning')
        return redirect(url_for('stock_check.detail', cid=cid))
    if request.method == 'POST':
        f = request.form
        product_ids = f.getlist('product_id')
        system_qtys = f.getlist('system_qty')
        actual_qtys = f.getlist('actual_qty')
        if not product_ids:
            flash('盘点明细不能为空', 'danger')
        else:
            with transaction() as tx:
                tx.execute('UPDATE stock_check SET remark = ? WHERE id = ?',
                           (f.get('remark', '').strip(), cid))
                tx.execute('DELETE FROM stock_check_items WHERE stock_check_id = ?', (cid,))
                for pid, sq, aq in zip(product_ids, system_qtys, actual_qtys):
                    s, a = to_int(sq), to_int(aq)
                    tx.execute(
                        '''INSERT INTO stock_check_items (stock_check_id, product_id, system_qty, actual_qty, diff)
                           VALUES (?, ?, ?, ?, ?)''',
                        (cid, to_int(pid), s, a, a - s))
            flash('盘点单已更新', 'success')
            return redirect(url_for('stock_check.detail', cid=cid))
    warehouses = db.execute('SELECT * FROM warehouses ORDER BY id').fetchall()
    items = [dict(r) for r in _get_items(db, cid)]
    return render_template('stock_check_form.html', warehouses=warehouses, order=order, items=items)


@bp.route('/<int:cid>/audit', methods=['POST'])
@permission_required('stock_check:audit')
def audit(cid):
    db = get_db()
    order = db.execute('SELECT * FROM stock_check WHERE id = ?', (cid,)).fetchone()
    if not order:
        abort(404)
    if order['status'] != 'pending':
        flash('该盘点单已审核，不能重复操作', 'warning')
        return redirect(url_for('stock_check.detail', cid=cid))
    items = db.execute('SELECT * FROM stock_check_items WHERE stock_check_id = ?', (cid,)).fetchall()
    try:
        with transaction() as tx:
            for it in items:
                if it['diff'] != 0:
                    balance = change_inventory(tx, it['product_id'], order['warehouse_id'], it['diff'])
                    write_stock_log(tx, 'check', cid, it['product_id'], order['warehouse_id'],
                                    it['diff'], balance, current_user.id)
            tx.execute("UPDATE stock_check SET status = 'approved' WHERE id = ?", (cid,))
    except ValueError as e:
        flash(str(e), 'danger')
        return redirect(url_for('stock_check.detail', cid=cid))
    flash('审核通过，库存已按盘点差异调整', 'success')
    return redirect(url_for('stock_check.detail', cid=cid))


@bp.route('/<int:cid>/delete', methods=['POST'])
@permission_required('stock_check:delete')
def delete(cid):
    db = get_db()
    order = db.execute('SELECT status FROM stock_check WHERE id = ?', (cid,)).fetchone()
    if not order:
        abort(404)
    if order['status'] != 'pending':
        flash('已审核的盘点单不能删除', 'warning')
    else:
        db.execute('DELETE FROM stock_check WHERE id = ?', (cid,))
        db.commit()
        flash('盘点单已删除', 'success')
    return redirect(url_for('stock_check.index'))
