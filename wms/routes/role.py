from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)

from auth import permission_required
from dao import CRUDDAO
from db import get_db, transaction


class RoleDAO(CRUDDAO):
    table = 'roles'
    fields = ('name', 'description')


bp = Blueprint('role', __name__, url_prefix='/roles')

ADMIN_ROLE_ID = 1  # 初始化脚本中的「管理员」角色，禁止删除


def _save_permissions(db, rid, perm_ids):
    db.execute('DELETE FROM role_permissions WHERE role_id = ?', (rid,))
    for pid in perm_ids:
        db.execute('INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)',
                   (rid, pid))


@bp.route('/')
@permission_required('role:view')
def index():
    roles = get_db().execute(
        '''SELECT r.*,
                  (SELECT COUNT(*) FROM role_permissions rp WHERE rp.role_id = r.id) AS perm_count,
                  (SELECT COUNT(*) FROM user_roles ur WHERE ur.role_id = r.id) AS user_count
           FROM roles r ORDER BY r.id''').fetchall()
    return render_template('roles.html', roles=roles, admin_role_id=ADMIN_ROLE_ID)


@bp.route('/create', methods=['GET', 'POST'])
@permission_required('role:create')
def create():
    if request.method == 'POST':
        f = request.form
        name = f.get('name', '').strip()
        if not name:
            flash('角色名称不能为空', 'danger')
        elif get_db().execute('SELECT id FROM roles WHERE name = ?', (name,)).fetchone():
            flash('角色名称已存在', 'danger')
        else:
            with transaction() as db:
                rid = RoleDAO.create({'name': name, 'description': f.get('description', '').strip()})
                _save_permissions(db, rid, f.getlist('perm_ids'))
            flash('角色创建成功', 'success')
            return redirect(url_for('role.index'))
    permissions = get_db().execute('SELECT * FROM permissions ORDER BY id').fetchall()
    return render_template('role_form.html', role=None, permissions=permissions, role_perm_ids=set())


@bp.route('/<int:rid>/edit', methods=['GET', 'POST'])
@permission_required('role:edit')
def edit(rid):
    db = get_db()
    role = RoleDAO.get(rid)
    if not role:
        abort(404)
    if request.method == 'POST':
        f = request.form
        name = f.get('name', '').strip()
        if not name:
            flash('角色名称不能为空', 'danger')
        else:
            with transaction() as tx:
                RoleDAO.update(rid, {'name': name, 'description': f.get('description', '').strip()})
                _save_permissions(tx, rid, f.getlist('perm_ids'))
            flash('角色已更新', 'success')
            return redirect(url_for('role.index'))
    permissions = db.execute('SELECT * FROM permissions ORDER BY id').fetchall()
    role_perm_ids = {r['permission_id'] for r in db.execute(
        'SELECT permission_id FROM role_permissions WHERE role_id = ?', (rid,)).fetchall()}
    return render_template('role_form.html', role=role, permissions=permissions, role_perm_ids=role_perm_ids)


@bp.route('/<int:rid>/delete', methods=['POST'])
@permission_required('role:delete')
def delete(rid):
    db = get_db()
    role = RoleDAO.get(rid)
    if not role:
        abort(404)
    if rid == ADMIN_ROLE_ID:
        flash('内置「管理员」角色不允许删除', 'danger')
    elif db.execute('SELECT COUNT(*) AS c FROM user_roles WHERE role_id = ?', (rid,)).fetchone()['c']:
        flash('该角色已分配给用户，请先解除分配', 'danger')
    else:
        RoleDAO.delete(rid)
        db.commit()
        flash('角色已删除', 'success')
    return redirect(url_for('role.index'))
