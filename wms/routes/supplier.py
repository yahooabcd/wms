import sqlite3

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)

from auth import permission_required
from dao import CRUDDAO
from db import get_db


class SupplierDAO(CRUDDAO):
    table = 'suppliers'
    fields = ('name', 'contact', 'phone', 'address', 'remark')


bp = Blueprint('supplier', __name__, url_prefix='/suppliers')


@bp.route('/')
@permission_required('supplier:view')
def index():
    kw = request.args.get('kw', '').strip()
    if kw:
        suppliers = SupplierDAO.list('name LIKE ? OR contact LIKE ?', (f'%{kw}%', f'%{kw}%'))
    else:
        suppliers = SupplierDAO.list()
    return render_template('suppliers.html', suppliers=suppliers, kw=kw)


@bp.route('/create', methods=['GET', 'POST'])
@permission_required('supplier:create')
def create():
    if request.method == 'POST':
        f = request.form
        if not f.get('name', '').strip():
            flash('供应商名称不能为空', 'danger')
        else:
            SupplierDAO.create({k: f.get(k, '').strip() for k in SupplierDAO.fields})
            get_db().commit()
            flash('供应商创建成功', 'success')
            return redirect(url_for('supplier.index'))
    return render_template('supplier_form.html', supplier=None)


@bp.route('/<int:sid>/edit', methods=['GET', 'POST'])
@permission_required('supplier:edit')
def edit(sid):
    supplier = SupplierDAO.get(sid)
    if not supplier:
        abort(404)
    if request.method == 'POST':
        f = request.form
        if not f.get('name', '').strip():
            flash('供应商名称不能为空', 'danger')
        else:
            SupplierDAO.update(sid, {k: f.get(k, '').strip() for k in SupplierDAO.fields})
            get_db().commit()
            flash('供应商已更新', 'success')
            return redirect(url_for('supplier.index'))
    return render_template('supplier_form.html', supplier=supplier)


@bp.route('/<int:sid>/delete', methods=['POST'])
@permission_required('supplier:delete')
def delete(sid):
    if not SupplierDAO.get(sid):
        abort(404)
    try:
        SupplierDAO.delete(sid)
        get_db().commit()
        flash('供应商已删除', 'success')
    except sqlite3.IntegrityError:
        flash('该供应商已被入库单引用，无法删除', 'danger')
    return redirect(url_for('supplier.index'))
