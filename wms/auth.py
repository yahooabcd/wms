from functools import wraps

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)
from flask_login import (LoginManager, UserMixin, current_user, login_user,
                         logout_user)
from werkzeug.security import check_password_hash

from db import get_db

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = '请先登录'
login_manager.login_message_category = 'warning'


def load_user_permissions(user_id):
    """聚合用户所有角色对应的权限码集合。"""
    rows = get_db().execute(
        '''SELECT DISTINCT p.code FROM permissions p
           JOIN role_permissions rp ON rp.permission_id = p.id
           JOIN user_roles ur ON ur.role_id = rp.role_id
           WHERE ur.user_id = ?''', (user_id,)).fetchall()
    return {r['code'] for r in rows}


class User(UserMixin):
    def __init__(self, row, permissions):
        self.id = row['id']
        self.username = row['username']
        self.real_name = row['real_name']
        self._active = bool(row['is_active'])
        self.permissions = permissions

    @property
    def is_active(self):
        return self._active

    def has_perm(self, code):
        return code in self.permissions

    def role_names(self):
        rows = get_db().execute(
            '''SELECT r.name FROM roles r
               JOIN user_roles ur ON ur.role_id = r.id
               WHERE ur.user_id = ?''', (self.id,)).fetchall()
        return '、'.join(r['name'] for r in rows) or '未分配角色'


@login_manager.user_loader
def load_user(user_id):
    row = get_db().execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if row is None or not row['is_active']:
        return None
    return User(row, load_user_permissions(row['id']))


def permission_required(code):
    """权限装饰器：未登录跳转登录页，已登录但无权限返回 403。"""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if not current_user.has_perm(code):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


bp = Blueprint('auth', __name__)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        row = get_db().execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if row and row['is_active'] and check_password_hash(row['password_hash'], password):
            login_user(User(row, load_user_permissions(row['id'])))
            next_page = request.args.get('next', '')
            if next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('dashboard.index'))
        flash('用户名或密码错误，或账号已被禁用', 'danger')
    return render_template('login.html')


@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
