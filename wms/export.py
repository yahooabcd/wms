import csv
import io
from urllib.parse import quote

from flask import Response


def csv_response(filename, headers, rows):
    """生成 CSV 下载响应。带 UTF-8 BOM，Excel 直接打开中文不乱码。

    filename: 下载文件名（支持中文）；headers: 表头列表；rows: 数据行可迭代对象。
    """
    buf = io.StringIO()
    buf.write('﻿')
    writer = csv.writer(buf)
    writer.writerow(headers)
    for r in rows:
        writer.writerow(r)
    resp = Response(buf.getvalue(), content_type='text/csv; charset=utf-8')
    resp.headers['Content-Disposition'] = (
        f"attachment; filename=export.csv; filename*=UTF-8''{quote(filename)}")
    return resp
