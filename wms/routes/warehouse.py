import sqlite3

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)

from auth import permission_required
from dao import CRUDDAO
from db import get_db


class WarehouseDAO(CRUDDAO):
    table = 'warehouses'
    fields = ('name', 'location', 'remark')


bp = Blueprint('warehouse', __name__, url_prefix='/warehouses')


@bp.route('/')
@permission_required('warehouse:view')
def index():
    warehouses = get_db().execute(
        '''SELECT w.*,
                  (SELECT COUNT(*) FROM inventory i WHERE i.warehouse_id = w.id) AS sku_count,
                  (SELECT COALESCE(SUM(quantity), 0) FROM inventory i WHERE i.warehouse_id = w.id) AS total_qty
           FROM warehouses w ORDER BY w.id''').fetchall()
    return render_template('warehouses.html', warehouses=warehouses)


@bp.route('/create', methods=['POST'])
@permission_required('warehouse:create')
def create():
    f = request.form
    if not f.get('name', '').strip():
        flash('仓库名称不能为空', 'danger')
    else:
        WarehouseDAO.create({k: f.get(k, '').strip() for k in WarehouseDAO.fields})
        get_db().commit()
        flash('仓库创建成功', 'success')
    return redirect(url_for('warehouse.index'))


@bp.route('/<int:wid>/edit', methods=['POST'])
@permission_required('warehouse:edit')
def edit(wid):
    if not WarehouseDAO.get(wid):
        abort(404)
    f = request.form
    if not f.get('name', '').strip():
        flash('仓库名称不能为空', 'danger')
    else:
        WarehouseDAO.update(wid, {k: f.get(k, '').strip() for k in WarehouseDAO.fields})
        get_db().commit()
        flash('仓库已更新', 'success')
    return redirect(url_for('warehouse.index'))


@bp.route('/<int:wid>/delete', methods=['POST'])
@permission_required('warehouse:delete')
def delete(wid):
    if not WarehouseDAO.get(wid):
        abort(404)
    try:
        WarehouseDAO.delete(wid)
        get_db().commit()
        flash('仓库已删除', 'success')
    except sqlite3.IntegrityError:
        flash('该仓库下存在库存或单据，无法删除', 'danger')
    return redirect(url_for('warehouse.index'))
