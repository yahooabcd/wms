"""初始化数据库：建表 + 写入默认角色/权限/管理员账号/基础演示数据。

用法: python init_db.py
可重复执行：若 users 表已有数据则跳过默认数据写入，不会清空业务数据。
"""
import sqlite3

from werkzeug.security import generate_password_hash

from config import Config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    real_name TEXT DEFAULT '',
    email TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    module TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    parent_id INTEGER REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category_id INTEGER REFERENCES categories(id),
    spec TEXT DEFAULT '',
    unit TEXT DEFAULT '个',
    price REAL DEFAULT 0,
    warning_low INTEGER DEFAULT 0,
    warning_high INTEGER DEFAULT 999999
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    contact TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    address TEXT DEFAULT '',
    remark TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    contact TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    address TEXT DEFAULT '',
    remark TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS warehouses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    location TEXT DEFAULT '',
    remark TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    quantity INTEGER DEFAULT 0,
    UNIQUE (product_id, warehouse_id)
);

CREATE TABLE IF NOT EXISTS stock_in (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    supplier_id INTEGER REFERENCES suppliers(id),
    operator_id INTEGER REFERENCES users(id),
    total_amount REAL DEFAULT 0,
    status TEXT DEFAULT 'pending',
    remark TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS stock_in_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_in_id INTEGER NOT NULL REFERENCES stock_in(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price REAL DEFAULT 0,
    subtotal REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS stock_out (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    customer_id INTEGER REFERENCES customers(id),
    operator_id INTEGER REFERENCES users(id),
    total_amount REAL DEFAULT 0,
    status TEXT DEFAULT 'pending',
    remark TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS stock_out_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_out_id INTEGER NOT NULL REFERENCES stock_out(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price REAL DEFAULT 0,
    subtotal REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS stock_check (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    operator_id INTEGER REFERENCES users(id),
    status TEXT DEFAULT 'pending',
    remark TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS stock_check_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_check_id INTEGER NOT NULL REFERENCES stock_check(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    system_qty INTEGER DEFAULT 0,
    actual_qty INTEGER DEFAULT 0,
    diff INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS stock_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    biz_type TEXT NOT NULL,
    biz_id INTEGER,
    product_id INTEGER NOT NULL,
    warehouse_id INTEGER NOT NULL,
    quantity_change INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    operator_id INTEGER,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
"""

PERMISSIONS = [
    ('dashboard:view', '查看仪表盘', '仪表盘'),
    ('user:view', '查看用户', '用户管理'), ('user:create', '新建用户', '用户管理'),
    ('user:edit', '编辑用户', '用户管理'), ('user:delete', '删除用户', '用户管理'),
    ('role:view', '查看角色', '角色权限'), ('role:create', '新建角色', '角色权限'),
    ('role:edit', '编辑角色', '角色权限'), ('role:delete', '删除角色', '角色权限'),
    ('product:view', '查看商品', '商品管理'), ('product:create', '新建商品', '商品管理'),
    ('product:edit', '编辑商品', '商品管理'), ('product:delete', '删除商品', '商品管理'),
    ('supplier:view', '查看供应商', '供应商'), ('supplier:create', '新建供应商', '供应商'),
    ('supplier:edit', '编辑供应商', '供应商'), ('supplier:delete', '删除供应商', '供应商'),
    ('customer:view', '查看客户', '客户'), ('customer:create', '新建客户', '客户'),
    ('customer:edit', '编辑客户', '客户'), ('customer:delete', '删除客户', '客户'),
    ('warehouse:view', '查看仓库', '仓库'), ('warehouse:create', '新建仓库', '仓库'),
    ('warehouse:edit', '编辑仓库', '仓库'), ('warehouse:delete', '删除仓库', '仓库'),
    ('stock_in:view', '查看入库单', '入库管理'), ('stock_in:create', '新建入库单', '入库管理'),
    ('stock_in:edit', '编辑入库单', '入库管理'), ('stock_in:delete', '删除入库单', '入库管理'),
    ('stock_in:audit', '审核入库单', '入库管理'),
    ('stock_out:view', '查看出库单', '出库管理'), ('stock_out:create', '新建出库单', '出库管理'),
    ('stock_out:edit', '编辑出库单', '出库管理'), ('stock_out:delete', '删除出库单', '出库管理'),
    ('stock_out:audit', '审核出库单', '出库管理'),
    ('inventory:view', '查看库存', '库存管理'),
    ('stock_check:view', '查看盘点单', '盘点管理'), ('stock_check:create', '新建盘点单', '盘点管理'),
    ('stock_check:edit', '编辑盘点单', '盘点管理'), ('stock_check:delete', '删除盘点单', '盘点管理'),
    ('stock_check:audit', '审核盘点单', '盘点管理'),
    ('report:view', '查看报表', '报表中心'),
]

ROLES = {
    '管理员': {'description': '系统管理员，拥有全部权限', 'perms': 'ALL'},
    '库管员': {'description': '负责出入库审核、盘点与库存管理', 'perms': [
        'dashboard:view', 'inventory:view', 'report:view',
        'product:view', 'warehouse:view', 'supplier:view', 'customer:view',
        'stock_in:view', 'stock_in:create', 'stock_in:edit', 'stock_in:audit',
        'stock_out:view', 'stock_out:create', 'stock_out:edit', 'stock_out:audit',
        'stock_check:view', 'stock_check:create', 'stock_check:edit', 'stock_check:audit',
    ]},
    '采购员': {'description': '负责采购入库与供应商维护', 'perms': [
        'dashboard:view', 'inventory:view', 'product:view',
        'supplier:view', 'supplier:create', 'supplier:edit',
        'stock_in:view', 'stock_in:create', 'stock_in:edit',
    ]},
    '销售员': {'description': '负责销售出库与客户维护', 'perms': [
        'dashboard:view', 'inventory:view', 'product:view',
        'customer:view', 'customer:create', 'customer:edit',
        'stock_out:view', 'stock_out:create', 'stock_out:edit',
    ]},
    '财务': {'description': '查看报表与库存价值（只读）', 'perms': [
        'dashboard:view', 'report:view', 'inventory:view',
        'stock_in:view', 'stock_out:view', 'stock_check:view',
    ]},
    '访客': {'description': '仅可查看仪表盘', 'perms': ['dashboard:view']},
}


def init():
    conn = sqlite3.connect(Config.DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.executescript(SCHEMA)

    if conn.execute('SELECT COUNT(*) AS c FROM users').fetchone()['c'] > 0:
        print('数据库已存在且包含数据，跳过默认数据写入。')
        conn.close()
        return

    # 权限
    perm_ids = {}
    for code, name, module in PERMISSIONS:
        cur = conn.execute('INSERT INTO permissions (code, name, module) VALUES (?, ?, ?)',
                           (code, name, module))
        perm_ids[code] = cur.lastrowid

    # 角色及其权限
    all_codes = [c for c, _, _ in PERMISSIONS]
    for role_name, info in ROLES.items():
        cur = conn.execute('INSERT INTO roles (name, description) VALUES (?, ?)',
                           (role_name, info['description']))
        rid = cur.lastrowid
        codes = all_codes if info['perms'] == 'ALL' else info['perms']
        for code in codes:
            conn.execute('INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)',
                         (rid, perm_ids[code]))

    # 管理员账号
    cur = conn.execute(
        'INSERT INTO users (username, password_hash, real_name) VALUES (?, ?, ?)',
        ('admin', generate_password_hash('admin123'), '系统管理员'))
    admin_role = conn.execute("SELECT id FROM roles WHERE name = '管理员'").fetchone()
    conn.execute('INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)',
                 (cur.lastrowid, admin_role['id']))

    # 基础演示数据
    conn.execute("INSERT INTO warehouses (name, location, remark) VALUES ('主仓库', '默认仓库', '')")
    for name in ('电子产品', '办公用品', '生活用品'):
        conn.execute('INSERT INTO categories (name) VALUES (?)', (name,))
    conn.execute("INSERT INTO suppliers (name, contact, phone) VALUES ('默认供应商', '张三', '13800000000')")
    conn.execute("INSERT INTO customers (name, contact, phone) VALUES ('默认客户', '李四', '13900000000')")
    conn.execute("""INSERT INTO products (sku, name, category_id, spec, unit, price, warning_low, warning_high)
                    VALUES ('P001', '无线鼠标', 1, 'M-100 黑色', '个', 59.0, 10, 500)""")
    conn.execute("""INSERT INTO products (sku, name, category_id, spec, unit, price, warning_low, warning_high)
                    VALUES ('P002', 'A4 打印纸', 2, '70g 500张/包', '包', 18.5, 20, 1000)""")

    conn.commit()
    conn.close()
    print(f'初始化完成: {Config.DATABASE}')
    print('默认管理员账号: admin / admin123')


if __name__ == '__main__':
    init()
