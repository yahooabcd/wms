@echo off
cd /d %~dp0
if not exist wms.db (
  echo 首次运行，正在初始化数据库...
  python init_db.py
)
python app.py
