from datetime import datetime

from flask import Blueprint, render_template, request

from auth import permission_required
from db import get_db
from export import csv_response

bp = Blueprint('report', __name__, url_prefix='/reports')

BIZ_TYPES = {'in': '入库', 'out': '出库', 'check': '盘点'}


def _query_logs(db, date_from, date_to, warehouse_id, biz_type, kw, limit=500):
    sql = '''SELECT l.*, p.sku, p.name AS product_name, p.unit,
                    w.name AS warehouse_name, COALESCE(NULLIF(u.real_name, ''), u.username) AS operator_name
             FROM stock_log l
             JOIN products p ON p.id = l.product_id
             JOIN warehouses w ON w.id = l.warehouse_id
             LEFT JOIN users u ON u.id = l.operator_id
             WHERE 1 = 1'''
    params = []
    if date_from:
        sql += ' AND date(l.created_at) >= ?'
        params.append(date_from)
    if date_to:
        sql += ' AND date(l.created_at) <= ?'
        params.append(date_to)
    if warehouse_id:
        sql += ' AND l.warehouse_id = ?'
        params.append(warehouse_id)
    if biz_type in BIZ_TYPES:
        sql += ' AND l.biz_type = ?'
        params.append(biz_type)
    if kw:
        sql += ' AND (p.name LIKE ? OR p.sku LIKE ?)'
        params += [f'%{kw}%', f'%{kw}%']
    sql += ' ORDER BY l.id DESC LIMIT ?'
    params.append(limit)
    return db.execute(sql, params).fetchall()


def _value_rows(db):
    return db.execute(
        '''SELECT w.name AS warehouse_name, p.sku, p.name AS product_name, p.spec, p.unit,
                  i.quantity, p.price, ROUND(i.quantity * p.price, 2) AS total_value
           FROM inventory i
           JOIN products p ON p.id = i.product_id
           JOIN warehouses w ON w.id = i.warehouse_id
           ORDER BY w.id, total_value DESC''').fetchall()


def _check_rows(db, limit=500):
    return db.execute(
        '''SELECT c.code, c.created_at, w.name AS warehouse_name, COALESCE(NULLIF(u.real_name, ''), u.username) AS operator_name,
                  p.sku, p.name AS product_name, ci.system_qty, ci.actual_qty, ci.diff,
                  ROUND(ci.diff * p.price, 2) AS diff_value
           FROM stock_check_items ci
           JOIN stock_check c ON c.id = ci.stock_check_id
           JOIN warehouses w ON w.id = c.warehouse_id
           JOIN products p ON p.id = ci.product_id
           LEFT JOIN users u ON u.id = c.operator_id
           WHERE c.status = 'approved' AND ci.diff != 0
           ORDER BY ci.id DESC LIMIT ?''', (limit,)).fetchall()


@bp.route('/')
@permission_required('report:view')
def index():
    db = get_db()
    tab = request.args.get('tab', 'flow')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    warehouse_id = request.args.get('warehouse_id', '')
    biz_type = request.args.get('biz_type', '')
    kw = request.args.get('kw', '').strip()

    warehouses = db.execute('SELECT * FROM warehouses ORDER BY id').fetchall()

    logs = []
    if tab == 'flow':
        logs = _query_logs(db, date_from, date_to, warehouse_id, biz_type, kw)

    value_rows = value_summary = None
    if tab == 'value':
        value_rows = _value_rows(db)
        value_summary = db.execute(
            '''SELECT COALESCE(SUM(i.quantity), 0) AS total_qty,
                      ROUND(COALESCE(SUM(i.quantity * p.price), 0), 2) AS total_value
               FROM inventory i JOIN products p ON p.id = i.product_id''').fetchone()

    check_rows = check_summary = None
    if tab == 'check':
        check_rows = _check_rows(db)
        check_summary = db.execute(
            '''SELECT ROUND(COALESCE(SUM(CASE WHEN ci.diff > 0 THEN ci.diff * p.price END), 0), 2) AS profit,
                      ROUND(COALESCE(SUM(CASE WHEN ci.diff < 0 THEN -ci.diff * p.price END), 0), 2) AS loss
               FROM stock_check_items ci
               JOIN stock_check c ON c.id = ci.stock_check_id
               JOIN products p ON p.id = ci.product_id
               WHERE c.status = 'approved' ''').fetchone()

    return render_template('reports.html', tab=tab, warehouses=warehouses, biz_types=BIZ_TYPES,
                           logs=logs, value_rows=value_rows, value_summary=value_summary,
                           check_rows=check_rows, check_summary=check_summary,
                           date_from=date_from, date_to=date_to,
                           warehouse_id=warehouse_id, biz_type=biz_type, kw=kw)


@bp.route('/export')
@permission_required('report:view')
def export():
    """按当前 Tab 导出报表 CSV，流水报表沿用页面筛选条件。"""
    db = get_db()
    tab = request.args.get('tab', 'flow')
    ts = datetime.now().strftime('%Y%m%d%H%M')

    if tab == 'value':
        rows = _value_rows(db)
        return csv_response(
            f'库存价值_{ts}.csv',
            ['仓库', 'SKU', '商品', '规格', '单位', '数量', '单价', '价值'],
            ([r['warehouse_name'], r['sku'], r['product_name'], r['spec'], r['unit'],
              r['quantity'], f"{r['price']:.2f}", f"{r['total_value']:.2f}"] for r in rows))

    if tab == 'check':
        rows = _check_rows(db, limit=10000)
        return csv_response(
            f'盘点盈亏_{ts}.csv',
            ['盘点单号', '时间', '仓库', 'SKU', '商品', '账面数量', '实盘数量',
             '差异', '差异价值', '经办人'],
            ([r['code'], r['created_at'], r['warehouse_name'], r['sku'],
              r['product_name'], r['system_qty'], r['actual_qty'], r['diff'],
              f"{r['diff_value']:.2f}", r['operator_name'] or ''] for r in rows))

    logs = _query_logs(db,
                       request.args.get('date_from', ''),
                       request.args.get('date_to', ''),
                       request.args.get('warehouse_id', ''),
                       request.args.get('biz_type', ''),
                       request.args.get('kw', '').strip(),
                       limit=10000)
    return csv_response(
        f'出入库流水_{ts}.csv',
        ['时间', '类型', '仓库', 'SKU', '商品', '变动数量', '结存', '经办人'],
        ([l['created_at'], BIZ_TYPES.get(l['biz_type'], l['biz_type']),
          l['warehouse_name'], l['sku'], l['product_name'],
          l['quantity_change'], l['balance_after'],
          l['operator_name'] or ''] for l in logs))
