from . import (customer, dashboard, inventory, product, report, role, stock_check,
               stock_in, stock_out, supplier, user, warehouse)


def register_blueprints(app):
    for m in (dashboard, user, role, product, supplier, customer, warehouse,
              stock_in, stock_out, inventory, stock_check, report):
        app.register_blueprint(m.bp)
