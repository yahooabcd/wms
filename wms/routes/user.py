from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user
from werkzeug.security import generate_password_hash

from auth import permission_required
from dao import CRUDDAO
from db import get_db, transaction


class UserDAO(CRUDDAO):
    table = 'users'
    fields = ('username', 'password_hash', 'real_name', 'email', 'phone', 'is_active')


bp = Blueprint('user', __name__, url_prefix='/users')


def _save_roles(db, uid, role_ids):
    db.execute('DELETE FROM user_roles WHERE user_id = ?', (uid,))
    for rid in role_ids:
        db.execute('INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)',
                   (uid, rid))


@bp.route('/')
@permission_required('user:view')
def index():
    users = get_db().execute(
        '''SELECT u.*, GROUP_CONCAT(r.name, '、') AS role_names
           FROM users u
           LEFT JOIN user_roles ur ON ur.user_id = u.id
           LEFT JOIN roles r ON r.id = ur.role_id
           GROUP BY u.id ORDER BY u.id''').fetchall()
    return render_template('users.html', users=users)


@bp.route('/create', methods=['GET', 'POST'])
@permission_required('user:create')
def create():
    if request.method == 'POST':
        f = request.form
        username = f.get('username', '').strip()
        if not username or not f.get('password'):
            flash('用户名和密码不能为空', 'danger')
        elif get_db().execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
            flash('用户名已存在', 'danger')
        else:
            with transaction() as db:
                uid = UserDAO.create({
                    'username': username,
                    'password_hash': generate_password_hash(f['password']),
                    'real_name': f.get('real_name', '').strip(),
                    'email': f.get('email', '').strip(),
                    'phone': f.get('phone', '').strip(),
                    'is_active': 1 if f.get('is_active') else 0,
                })
                _save_roles(db, uid, f.getlist('role_ids'))
            flash('用户创建成功', 'success')
            return redirect(url_for('user.index'))
    roles = get_db().execute('SELECT * FROM roles ORDER BY id').fetchall()
    return render_template('user_form.html', user=None, roles=roles, user_role_ids=set())


@bp.route('/<int:uid>/edit', methods=['GET', 'POST'])
@permission_required('user:edit')
def edit(uid):
    db = get_db()
    user = UserDAO.get(uid)
    if not user:
        abort(404)
    if request.method == 'POST':
        f = request.form
        with transaction() as tx:
            data = {
                'real_name': f.get('real_name', '').strip(),
                'email': f.get('email', '').strip(),
                'phone': f.get('phone', '').strip(),
                'is_active': 1 if f.get('is_active') else 0,
            }
            if f.get('password'):
                data['password_hash'] = generate_password_hash(f['password'])
            UserDAO.update(uid, data)
            _save_roles(tx, uid, f.getlist('role_ids'))
        flash('用户已更新', 'success')
        return redirect(url_for('user.index'))
    roles = db.execute('SELECT * FROM roles ORDER BY id').fetchall()
    user_role_ids = {r['role_id'] for r in db.execute(
        'SELECT role_id FROM user_roles WHERE user_id = ?', (uid,)).fetchall()}
    return render_template('user_form.html', user=user, roles=roles, user_role_ids=user_role_ids)


@bp.route('/<int:uid>/delete', methods=['POST'])
@permission_required('user:delete')
def delete(uid):
    if uid == current_user.id:
        flash('不能删除当前登录账号', 'danger')
        return redirect(url_for('user.index'))
    if not UserDAO.get(uid):
        abort(404)
    UserDAO.delete(uid)
    get_db().commit()
    flash('用户已删除', 'success')
    return redirect(url_for('user.index'))
