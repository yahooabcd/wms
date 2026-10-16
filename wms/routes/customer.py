import sqlite3

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)

from auth import permission_required
from dao import CRUDDAO
from db import get_db


class CustomerDAO(CRUDDAO):
    table = 'customers'
    fields = ('name', 'contact', 'phone', 'address', 'remark')


bp = Blueprint('customer', __name__, url_prefix='/customers')


@bp.route('/')
@permission_required('customer:view')
def index():
    kw = request.args.get('kw', '').strip()
    if kw:
        customers = CustomerDAO.list('name LIKE ? OR contact LIKE ?', (f'%{kw}%', f'%{kw}%'))
    else:
        customers = CustomerDAO.list()
    return render_template('customers.html', customers=customers, kw=kw)


@bp.route('/create', methods=['GET', 'POST'])
@permission_required('customer:create')
def create():
    if request.method == 'POST':
        f = request.form
        if not f.get('name', '').strip():
            flash('客户名称不能为空', 'danger')
        else:
            CustomerDAO.create({k: f.get(k, '').strip() for k in CustomerDAO.fields})
            get_db().commit()
            flash('客户创建成功', 'success')
            return redirect(url_for('customer.index'))
    return render_template('customer_form.html', customer=None)


@bp.route('/<int:cid>/edit', methods=['GET', 'POST'])
@permission_required('customer:edit')
def edit(cid):
    customer = CustomerDAO.get(cid)
    if not customer:
        abort(404)
    if request.method == 'POST':
        f = request.form
        if not f.get('name', '').strip():
            flash('客户名称不能为空', 'danger')
        else:
            CustomerDAO.update(cid, {k: f.get(k, '').strip() for k in CustomerDAO.fields})
            get_db().commit()
            flash('客户已更新', 'success')
            return redirect(url_for('customer.index'))
    return render_template('customer_form.html', customer=customer)


@bp.route('/<int:cid>/delete', methods=['POST'])
@permission_required('customer:delete')
def delete(cid):
    if not CustomerDAO.get(cid):
        abort(404)
    try:
        CustomerDAO.delete(cid)
        get_db().commit()
        flash('客户已删除', 'success')
    except sqlite3.IntegrityError:
        flash('该客户已被出库单引用，无法删除', 'danger')
    return redirect(url_for('customer.index'))
