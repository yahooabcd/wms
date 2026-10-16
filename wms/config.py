import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('WMS_SECRET_KEY', 'wms-dev-secret-key-change-me')
    DATABASE = os.path.join(BASE_DIR, 'wms.db')
