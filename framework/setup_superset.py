#!/usr/bin/env python3
"""
Configure dashboard datasets and charts for all 5 federated domains via the federation engine.

Run from within the dashboard platform's virtualenv. Set DASHBOARD_CONFIG_PATH to
the platform's config module before running; there is no universal default because
it depends on how the platform was installed on your machine.
"""

import sys
import os

# Respect an existing DASHBOARD_CONFIG_PATH; only supply a conventional fallback.
os.environ.setdefault('DASHBOARD_CONFIG_PATH', '/opt/dashboard/config/dashboard_config.py')

from superset.app import create_app
app = create_app()

with app.app_context():
    from superset.models.core import Database
    from superset.connectors.sqla.models import SqlaTable, TableColumn
    from superset.extensions import db as sa_db
    from superset.models.slice import Slice
    from superset.models.dashboard import Dashboard
    import json
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger(__name__)

    # Get federation engine database connection
    presto_db = sa_db.session.query(Database).filter_by(database_name='Federation Engine').first()
    if not presto_db:
        log.error("Federation engine database connection not found!")
        sys.exit(1)
    
    log.info(f"Using federation engine connection: ID={presto_db.id}, URI={presto_db.sqlalchemy_uri}")

    # Update federation engine URI to include all catalogs properly
    # The default catalog is 'postgresql' — we need to ensure cross-catalog queries work
    if 'postgresql' in presto_db.sqlalchemy_uri and 'hive' not in presto_db.sqlalchemy_uri:
        log.info("Federation engine URI already configured for postgresql catalog")

    # =========================================================================
    # Define datasets (SQL queries that federate across engines)
    # =========================================================================
    
    DATASETS = [
        # ----- E-Commerce Domain -----
        {
            "name": "Olist: Revenue by State",
            "schema": "public",
            "sql": """
SELECT c.customer_state as state,
       COUNT(DISTINCT o.order_id) as total_orders,
       ROUND(SUM(p.payment_value), 2) as revenue,
       ROUND(AVG(p.payment_value), 2) as avg_order_value
FROM postgresql.public.olist_orders o
JOIN postgresql.public.olist_order_payments p ON o.order_id = p.order_id
JOIN mysql.olist_ecommerce.olist_customers c ON o.customer_id = c.customer_id
GROUP BY c.customer_state
ORDER BY revenue DESC
""",
        },
        {
            "name": "Olist: Category Performance",
            "schema": "public",
            "sql": """
SELECT t.product_category_name_english as category,
       COUNT(*) as items_sold,
       ROUND(SUM(oi.price), 2) as revenue,
       ROUND(AVG(CAST(r.review_score AS DOUBLE)), 2) as avg_review
FROM postgresql.public.olist_order_items oi
JOIN postgresql.public.olist_order_reviews r ON oi.order_id = r.order_id
JOIN mysql.olist_ecommerce.olist_products p ON oi.product_id = p.product_id
JOIN mysql.olist_ecommerce.product_category_translation t 
  ON p.product_category_name = t.product_category_name
GROUP BY t.product_category_name_english
ORDER BY revenue DESC
""",
        },
        
        # ----- Healthcare Domain -----
        {
            "name": "Healthcare: Billing by Condition",
            "schema": "public",
            "sql": """
SELECT c.condition_name,
       ins.provider_name as insurance,
       COUNT(*) as admissions,
       ROUND(AVG(a.billing_amount), 2) as avg_billing,
       ROUND(SUM(a.billing_amount), 2) as total_billing
FROM postgresql.public.hc_admissions a
JOIN mysql.healthcare.hc_conditions c ON a.condition_id = c.condition_id
JOIN mysql.healthcare.hc_insurance ins ON a.insurance_id = ins.insurance_id
GROUP BY c.condition_name, ins.provider_name
ORDER BY total_billing DESC
""",
        },
        {
            "name": "Healthcare: Hospital Analysis",
            "schema": "public",
            "sql": """
SELECT h.hospital_name,
       COUNT(*) as admissions,
       ROUND(AVG(a.billing_amount), 2) as avg_billing,
       ROUND(SUM(a.billing_amount), 2) as total_billing,
       a.admission_type
FROM postgresql.public.hc_admissions a
JOIN mysql.healthcare.hc_hospitals h ON a.hospital_id = h.hospital_id
GROUP BY h.hospital_name, a.admission_type
ORDER BY total_billing DESC
""",
        },
        
        # ----- Retail Domain -----
        {
            "name": "Retail: Revenue by Country",
            "schema": "public",
            "sql": """
SELECT cust.country,
       COUNT(DISTINCT i.invoice_no) as invoices,
       SUM(i.quantity) as total_items,
       ROUND(SUM(i.quantity * i.unit_price), 2) as revenue
FROM postgresql.public.rt_invoices i
JOIN mysql.retail.rt_customers cust ON i.customer_id = cust.customer_id
WHERE i.quantity > 0
GROUP BY cust.country
ORDER BY revenue DESC
""",
        },
        {
            "name": "Retail: Top Products",
            "schema": "public",
            "sql": """
SELECT p.description as product,
       cust.country,
       SUM(i.quantity) as total_qty,
       ROUND(SUM(i.quantity * i.unit_price), 2) as revenue
FROM postgresql.public.rt_invoices i
JOIN mysql.retail.rt_products p ON i.stock_code = p.stock_code
JOIN mysql.retail.rt_customers cust ON i.customer_id = cust.customer_id
WHERE i.quantity > 0
GROUP BY p.description, cust.country
ORDER BY revenue DESC
""",
        },
        
        # ----- Financial Domain -----
        {
            "name": "Financial: Fraud by Time Bucket",
            "schema": "public",
            "sql": """
SELECT tb.bucket_name as time_period,
       fc.class_name as transaction_type,
       COUNT(*) as transactions,
       ROUND(AVG(ft.amount), 2) as avg_amount,
       ROUND(SUM(ft.amount), 2) as total_amount
FROM postgresql.public.fin_transactions ft
JOIN mysql.financial.fin_fraud_classes fc ON ft.class_id = fc.class_id
JOIN mysql.financial.fin_time_buckets tb 
  ON ft.time_hour >= tb.hour_start AND ft.time_hour < tb.hour_end
GROUP BY tb.bucket_name, fc.class_name
ORDER BY tb.bucket_name
""",
        },
        {
            "name": "Financial: Amount Distribution",
            "schema": "public",
            "sql": """
SELECT fc.class_name as transaction_type,
       COUNT(*) as count,
       ROUND(AVG(ft.amount), 2) as avg_amount,
       ROUND(MIN(ft.amount), 2) as min_amount,
       ROUND(MAX(ft.amount), 2) as max_amount,
       ROUND(SUM(ft.amount), 2) as total_amount
FROM postgresql.public.fin_transactions ft
JOIN mysql.financial.fin_fraud_classes fc ON ft.class_id = fc.class_id
GROUP BY fc.class_name
""",
        },
        
        # ----- Supply Chain Domain -----
        {
            "name": "Supply Chain: Sales by Department",
            "schema": "public",
            "sql": """
SELECT d.department_name,
       cust.segment,
       COUNT(*) as orders,
       ROUND(SUM(o.sales), 2) as total_sales,
       ROUND(AVG(o.order_profit), 2) as avg_profit,
       ROUND(AVG(CAST(o.days_shipping_real - o.days_shipment_scheduled AS DOUBLE)), 2) as avg_delay_days
FROM postgresql.public.sc_orders o
JOIN mysql.supply_chain.sc_departments d ON o.department_id = d.department_id
JOIN mysql.supply_chain.sc_customers cust ON o.customer_id = cust.customer_id
GROUP BY d.department_name, cust.segment
ORDER BY total_sales DESC
""",
        },
        {
            "name": "Supply Chain: Delivery Performance",
            "schema": "public",
            "sql": """
SELECT o.delivery_status,
       o.shipping_mode,
       cat.category_name,
       COUNT(*) as orders,
       ROUND(SUM(o.sales), 2) as total_sales,
       ROUND(AVG(CAST(o.late_delivery_risk AS DOUBLE)), 2) as late_risk_rate
FROM postgresql.public.sc_orders o
JOIN mysql.supply_chain.sc_categories cat ON o.category_id = cat.category_id
GROUP BY o.delivery_status, o.shipping_mode, cat.category_name
ORDER BY total_sales DESC
""",
        },
        
        # ----- Cross-Domain -----
        {
            "name": "Cross-Domain: 5-Domain Summary",
            "schema": "public",
            "sql": """
SELECT 'E-Commerce' as domain, COUNT(*) as fact_rows, ROUND(SUM(price), 2) as total_value
FROM postgresql.public.olist_order_items
UNION ALL
SELECT 'Healthcare', COUNT(*), ROUND(SUM(billing_amount), 2)
FROM postgresql.public.hc_admissions
UNION ALL
SELECT 'Retail', COUNT(*), ROUND(SUM(quantity * unit_price), 2)
FROM postgresql.public.rt_invoices WHERE quantity > 0
UNION ALL
SELECT 'Financial', COUNT(*), ROUND(SUM(amount), 2)
FROM postgresql.public.fin_transactions
UNION ALL
SELECT 'Supply Chain', COUNT(*), ROUND(SUM(sales), 2)
FROM postgresql.public.sc_orders
""",
        },
    ]

    # =========================================================================
    # Create SQL Lab saved queries / virtual datasets
    # =========================================================================
    
    created = 0
    skipped = 0
    
    for ds in DATASETS:
        # Check if dataset already exists
        existing = sa_db.session.query(SqlaTable).filter_by(
            table_name=ds['name'],
            database_id=presto_db.id
        ).first()
        
        if existing:
            log.info(f"  SKIP (exists): {ds['name']}")
            skipped += 1
            continue
        
        table = SqlaTable(
            table_name=ds['name'],
            database_id=presto_db.id,
            schema=ds.get('schema', 'public'),
            sql=ds['sql'].strip(),
        )
        sa_db.session.add(table)
        sa_db.session.flush()
        log.info(f"  CREATED: {ds['name']} (ID={table.id})")
        created += 1
    
    sa_db.session.commit()
    
    print(f"\n{'='*60}")
    print(f"DASHBOARD DATASETS CONFIGURED")
    print(f"{'='*60}")
    print(f"  Created: {created}")
    print(f"  Skipped: {skipped}")
    print(f"  Total datasets: {created + skipped}")
    print(f"\n  Access dashboard at: https://server.example.edu/")
    print(f"  Login: admin / <DASHBOARD_ADMIN_PASSWORD>")
    print(f"  Go to: SQL Lab → Saved Queries or Datasets tab")
