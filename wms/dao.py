from db import get_db


class CRUDDAO:
    """通用 CRUD 基类，业务模块通过继承指定 table 与 fields 复用。"""

    table = ''
    fields = ()

    @classmethod
    def list(cls, where='', params=(), order_by='id DESC'):
        sql = f'SELECT * FROM {cls.table}'
        if where:
            sql += f' WHERE {where}'
        if order_by:
            sql += f' ORDER BY {order_by}'
        return get_db().execute(sql, params).fetchall()

    @classmethod
    def get(cls, row_id):
        return get_db().execute(
            f'SELECT * FROM {cls.table} WHERE id = ?', (row_id,)).fetchone()

    @classmethod
    def create(cls, data):
        keys = [k for k in cls.fields if k in data and data[k] is not None]
        cols = ', '.join(keys)
        marks = ', '.join('?' for _ in keys)
        cur = get_db().execute(
            f'INSERT INTO {cls.table} ({cols}) VALUES ({marks})',
            [data[k] for k in keys])
        return cur.lastrowid

    @classmethod
    def update(cls, row_id, data):
        keys = [k for k in cls.fields if k in data]
        if not keys:
            return
        sets = ', '.join(f'{k} = ?' for k in keys)
        get_db().execute(
            f'UPDATE {cls.table} SET {sets} WHERE id = ?',
            [data[k] for k in keys] + [row_id])

    @classmethod
    def delete(cls, row_id):
        get_db().execute(f'DELETE FROM {cls.table} WHERE id = ?', (row_id,))


def to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def change_inventory(db, product_id, warehouse_id, delta):
    """调整库存（正数为增，负数为减），返回调整后的结存数量。库存不足抛 ValueError。"""
    row = db.execute(
        'SELECT id, quantity FROM inventory WHERE product_id = ? AND warehouse_id = ?',
        (product_id, warehouse_id)).fetchone()
    if row:
        new_qty = row['quantity'] + delta
        if new_qty < 0:
            raise ValueError('库存不足，无法完成出库/调整')
        db.execute('UPDATE inventory SET quantity = ? WHERE id = ?', (new_qty, row['id']))
    else:
        if delta < 0:
            raise ValueError('库存不足，无法完成出库/调整')
        new_qty = delta
        db.execute(
            'INSERT INTO inventory (product_id, warehouse_id, quantity) VALUES (?, ?, ?)',
            (product_id, warehouse_id, delta))
    return new_qty


def write_stock_log(db, biz_type, biz_id, product_id, warehouse_id,
                    quantity_change, balance_after, operator_id):
    """写入库存流水（所有库存变动的统一审计轨迹）。"""
    db.execute(
        '''INSERT INTO stock_log
           (biz_type, biz_id, product_id, warehouse_id, quantity_change, balance_after, operator_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (biz_type, biz_id, product_id, warehouse_id,
         quantity_change, balance_after, operator_id))
