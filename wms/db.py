import sqlite3
from contextlib import contextmanager

from flask import current_app, g


def get_db():
    """获取当前请求内的 SQLite 连接（懒创建，随请求关闭）。"""
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)


@contextmanager
def transaction():
    """事务上下文：正常结束自动 commit，抛异常自动 rollback。"""
    db = get_db()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
