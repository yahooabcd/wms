from datetime import datetime

from flask import Blueprint, render_template, request

from auth import permission_required
from db import get_db
from export import csv_response

bp = Blueprint('inventory', __name__, url_prefix='/inventory')


def _query(wid, kw, warn):
    sql = '''SELECT i.*, p.sku, p.name AS product_name, p.spec, p.unit, p.price,
                    p.warning_low, p.warning_high, w.name AS warehouse_name,
                    ROUND(i.quantity * p.price, 2) AS total_value
             FROM inventory i
             JOIN products p ON p.id = i.product_id
             JOIN warehouses w ON w.id = i.warehouse_id
             WHERE 1 = 1'''
    params = []
    if wid:
        sql += ' AND i.warehouse_id = ?'
        params.append(wid)
    if kw:
        sql += ' AND (p.name LIKE ? OR p.sku LIKE ?)'
        params += [f'%{kw}%', f'%{kw}%']
    if warn == 'low':
        sql += ' AND i.quantity < p.warning_low'
    elif warn == 'high':
        sql += ' AND i.quantity > p.warning_high'
    sql += ' ORDER BY w.id, p.id'
    return get_db().execute(sql, params).fetchall()


@bp.route('/')
@permission_required('inventory:view')
def index():
    wid = request.args.get('warehouse_id', '')
    kw = request.args.get('kw', '').strip()
    warn = request.args.get('warn', '')
    rows = _query(wid, kw, warn)
    warehouses = get_db().execute('SELECT * FROM warehouses ORDER BY id').fetchall()
    total_value = sum(r['total_value'] for r in rows)
    return render_template('inventory.html', rows=rows, warehouses=warehouses,
                           wid=wid, kw=kw, warn=warn, total_value=total_value)


@bp.route('/export')
@permission_required('inventory:view')
def export():
    """导出当前筛选条件下的库存清单 CSV。"""
    rows = _query(request.args.get('warehouse_id', ''),
                  request.args.get('kw', '').strip(),
                  request.args.get('warn', ''))

    def gen():
        for r in rows:
            if r['quantity'] < r['warning_low']:
                status = '低库存'
            elif r['quantity'] > r['warning_high']:
                status = '高库存'
            else:
                status = '正常'
            yield [r['warehouse_name'], r['sku'], r['product_name'], r['spec'],
                   r['unit'], r['quantity'], r['warning_low'], r['warning_high'],
                   f"{r['price']:.2f}", f"{r['total_value']:.2f}", status]

    filename = f"库存清单_{datetime.now():%Y%m%d%H%M}.csv"
    return csv_response(filename,
                        ['仓库', 'SKU', '商品', '规格', '单位', '库存数量',
                         '预警下限', '预警上限', '单价', '库存价值', '状态'],
                        gen())
