from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)

from auth import permission_required
from dao import CRUDDAO, to_float, to_int
from db import get_db


class ProductDAO(CRUDDAO):
    table = 'products'
    fields = ('sku', 'name', 'category_id', 'spec', 'unit', 'price',
              'warning_low', 'warning_high')


bp = Blueprint('product', __name__, url_prefix='/products')


def _categories():
    return get_db().execute(
        '''SELECT c.*, p.name AS parent_name FROM categories c
           LEFT JOIN categories p ON p.id = c.parent_id ORDER BY c.id''').fetchall()


@bp.route('/')
@permission_required('product:view')
def index():
    kw = request.args.get('kw', '').strip()
    sql = '''SELECT p.*, c.name AS category_name FROM products p
             LEFT JOIN categories c ON c.id = p.category_id'''
    params = []
    if kw:
        sql += ' WHERE p.name LIKE ? OR p.sku LIKE ?'
        params = [f'%{kw}%', f'%{kw}%']
    sql += ' ORDER BY p.id DESC'
    products = get_db().execute(sql, params).fetchall()
    return render_template('products.html', products=products,
                           categories=_categories(), kw=kw)


@bp.route('/create', methods=['GET', 'POST'])
@permission_required('product:create')
def create():
    if request.method == 'POST':
        f = request.form
        sku = f.get('sku', '').strip()
        if not sku or not f.get('name', '').strip():
            flash('SKU 和商品名称不能为空', 'danger')
        elif get_db().execute('SELECT id FROM products WHERE sku = ?', (sku,)).fetchone():
            flash('SKU 已存在', 'danger')
        else:
            ProductDAO.create({
                'sku': sku, 'name': f['name'].strip(),
                'category_id': to_int(f.get('category_id')) or None,
                'spec': f.get('spec', '').strip(), 'unit': f.get('unit', '个').strip() or '个',
                'price': to_float(f.get('price')),
                'warning_low': to_int(f.get('warning_low')),
                'warning_high': to_int(f.get('warning_high'), 999999),
            })
            get_db().commit()
            flash('商品创建成功', 'success')
            return redirect(url_for('product.index'))
    return render_template('product_form.html', product=None, categories=_categories())


@bp.route('/<int:pid>/edit', methods=['GET', 'POST'])
@permission_required('product:edit')
def edit(pid):
    product = ProductDAO.get(pid)
    if not product:
        abort(404)
    if request.method == 'POST':
        f = request.form
        if not f.get('name', '').strip():
            flash('商品名称不能为空', 'danger')
        else:
            ProductDAO.update(pid, {
                'name': f['name'].strip(),
                'category_id': to_int(f.get('category_id')) or None,
                'spec': f.get('spec', '').strip(), 'unit': f.get('unit', '个').strip() or '个',
                'price': to_float(f.get('price')),
                'warning_low': to_int(f.get('warning_low')),
                'warning_high': to_int(f.get('warning_high'), 999999),
            })
            get_db().commit()
            flash('商品已更新', 'success')
            return redirect(url_for('product.index'))
    return render_template('product_form.html', product=product, categories=_categories())


@bp.route('/<int:pid>/delete', methods=['POST'])
@permission_required('product:delete')
def delete(pid):
    db = get_db()
    if not ProductDAO.get(pid):
        abort(404)
    refs = db.execute(
        '''SELECT (SELECT COUNT(*) FROM inventory WHERE product_id = ?) +
                  (SELECT COUNT(*) FROM stock_in_items WHERE product_id = ?) +
                  (SELECT COUNT(*) FROM stock_out_items WHERE product_id = ?) +
                  (SELECT COUNT(*) FROM stock_check_items WHERE product_id = ?) AS c''',
        (pid, pid, pid, pid)).fetchone()['c']
    if refs:
        flash('该商品已被库存或单据引用，无法删除', 'danger')
    else:
        ProductDAO.delete(pid)
        db.commit()
        flash('商品已删除', 'success')
    return redirect(url_for('product.index'))


@bp.route('/categories/add', methods=['POST'])
@permission_required('product:create')
def add_category():
    name = request.form.get('name', '').strip()
    parent_id = to_int(request.form.get('parent_id')) or None
    if name:
        db = get_db()
        db.execute('INSERT INTO categories (name, parent_id) VALUES (?, ?)', (name, parent_id))
        db.commit()
        flash('分类已添加', 'success')
    return redirect(url_for('product.index'))


@bp.route('/categories/<int:cid>/delete', methods=['POST'])
@permission_required('product:delete')
def delete_category(cid):
    db = get_db()
    if db.execute('SELECT COUNT(*) AS c FROM products WHERE category_id = ?', (cid,)).fetchone()['c']:
        flash('该分类下还有商品，无法删除', 'danger')
    elif db.execute('SELECT COUNT(*) AS c FROM categories WHERE parent_id = ?', (cid,)).fetchone()['c']:
        flash('该分类存在子分类，无法删除', 'danger')
    else:
        db.execute('DELETE FROM categories WHERE id = ?', (cid,))
        db.commit()
        flash('分类已删除', 'success')
    return redirect(url_for('product.index'))
