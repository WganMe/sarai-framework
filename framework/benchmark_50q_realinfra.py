#!/usr/bin/env python3
"""
SARAI Benchmark Suite — 50 Text-to-SQL Questions across 5 Complexity Tiers × 5 Domains
Each question has: natural language, gold SQL, expected answer pattern, tier, domain
"""

import json, time, requests, sys, statistics, re, os, argparse
from datetime import datetime

# ─── Endpoints and output locations ───────────────────────────────────────────
# Resolved from the environment so the harness is not tied to one host. The
# defaults are the localhost ports of the reference deployment; override with
# FEDERATION_URL / OLLAMA_URL (and RUNS_DIR) to point anywhere else.
HERE = os.path.dirname(os.path.abspath(__file__))
FEDERATION_URL = os.environ.get('FEDERATION_URL', 'http://127.0.0.1:8080')
OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434')
RUNS_DIR = os.environ.get(
    'RUNS_DIR', os.path.normpath(os.path.join(HERE, '..', 'datasets', 'real_infra_runs')))

# ─── 50 Benchmark Questions ───────────────────────────────────────────────────
# Tier 1: Single-table (no join) — 10 questions
# Tier 2: Single-join within one engine — 10 questions
# Tier 3: Cross-engine join (PG fact + MySQL dim) — 10 questions
# Tier 4: Multi-join cross-engine (3+ tables) — 10 questions
# Tier 5: Cross-domain federation — 10 questions

BENCHMARK = [
    # ═══ TIER 1: Single-Table Aggregation (no join) ═══
    {
        "id": "T1-Q01", "tier": 1, "domain": "E-Commerce",
        "nl": "How many orders are in the e-commerce dataset?",
        "gold_sql": "SELECT COUNT(*) AS total_orders FROM postgresql.public.olist_orders",
        "validator": lambda rows: rows and int(rows[0][0]) > 90000
    },
    {
        "id": "T1-Q02", "tier": 1, "domain": "Healthcare",
        "nl": "What is the average billing amount for hospital admissions?",
        "gold_sql": "SELECT ROUND(AVG(billing_amount), 2) AS avg_billing FROM postgresql.public.hc_admissions",
        "validator": lambda rows: rows and float(rows[0][0]) > 10000
    },
    {
        "id": "T1-Q03", "tier": 1, "domain": "Retail",
        "nl": "What is the total revenue from retail invoices?",
        "gold_sql": "SELECT ROUND(SUM(quantity * unit_price), 2) AS total_revenue FROM postgresql.public.rt_invoices WHERE quantity > 0",
        "validator": lambda rows: rows and float(rows[0][0]) > 5000000
    },
    {
        "id": "T1-Q04", "tier": 1, "domain": "Financial",
        "nl": "How many transactions are in the financial fraud dataset?",
        "gold_sql": "SELECT COUNT(*) AS total_transactions FROM postgresql.public.fin_transactions",
        "validator": lambda rows: rows and int(rows[0][0]) > 200000
    },
    {
        "id": "T1-Q05", "tier": 1, "domain": "Supply Chain",
        "nl": "What is the total sales amount in the supply chain dataset?",
        "gold_sql": "SELECT ROUND(SUM(sales), 2) AS total_sales FROM postgresql.public.sc_orders",
        "validator": lambda rows: rows and float(rows[0][0]) > 20000000
    },
    {
        "id": "T1-Q06", "tier": 1, "domain": "E-Commerce",
        "nl": "What is the average review score for e-commerce orders?",
        "gold_sql": "SELECT ROUND(AVG(review_score), 2) AS avg_score FROM postgresql.public.olist_order_reviews",
        "validator": lambda rows: rows and 1.0 <= float(rows[0][0]) <= 5.0
    },
    {
        "id": "T1-Q07", "tier": 1, "domain": "Healthcare",
        "nl": "How many hospital admissions have abnormal test results?",
        "gold_sql": "SELECT COUNT(*) AS abnormal_count FROM postgresql.public.hc_admissions WHERE test_results = 'Abnormal'",
        "validator": lambda rows: rows and int(rows[0][0]) > 10000
    },
    {
        "id": "T1-Q08", "tier": 1, "domain": "Financial",
        "nl": "How many fraudulent transactions are there in the financial dataset?",
        "gold_sql": "SELECT COUNT(*) AS fraud_count FROM postgresql.public.fin_transactions WHERE class_id = 1",
        "validator": lambda rows: rows and 400 <= int(rows[0][0]) <= 600
    },
    {
        "id": "T1-Q09", "tier": 1, "domain": "Supply Chain",
        "nl": "How many orders have late delivery risk in the supply chain?",
        "gold_sql": "SELECT COUNT(*) AS late_risk_count FROM postgresql.public.sc_orders WHERE late_delivery_risk = 1",
        "validator": lambda rows: rows and int(rows[0][0]) > 50000
    },
    {
        "id": "T1-Q10", "tier": 1, "domain": "Retail",
        "nl": "How many distinct customers are in the retail invoices?",
        "gold_sql": "SELECT COUNT(DISTINCT customer_id) AS distinct_customers FROM postgresql.public.rt_invoices WHERE customer_id IS NOT NULL",
        "validator": lambda rows: rows and int(rows[0][0]) > 3000
    },

    # ═══ TIER 2: Single-Join Within One Engine ═══
    {
        "id": "T2-Q01", "tier": 2, "domain": "E-Commerce",
        "nl": "What is the total payment value by payment type for e-commerce orders?",
        "gold_sql": "SELECT p.payment_type, ROUND(SUM(p.payment_value), 2) AS total FROM postgresql.public.olist_order_payments p GROUP BY p.payment_type ORDER BY total DESC",
        "validator": lambda rows: rows and len(rows) >= 3
    },
    {
        "id": "T2-Q02", "tier": 2, "domain": "E-Commerce",
        "nl": "What is the average order item price and freight value?",
        "gold_sql": "SELECT ROUND(AVG(price), 2) AS avg_price, ROUND(AVG(freight_value), 2) AS avg_freight FROM postgresql.public.olist_order_items",
        "validator": lambda rows: rows and float(rows[0][0]) > 50
    },
    {
        "id": "T2-Q03", "tier": 2, "domain": "Healthcare",
        "nl": "What is the average billing amount by admission type in the healthcare data?",
        "gold_sql": "SELECT admission_type, ROUND(AVG(billing_amount), 2) AS avg_billing FROM postgresql.public.hc_admissions GROUP BY admission_type ORDER BY avg_billing DESC",
        "validator": lambda rows: rows and len(rows) >= 2
    },
    {
        "id": "T2-Q04", "tier": 2, "domain": "Healthcare",
        "nl": "How many admissions are there for each blood type?",
        "gold_sql": "SELECT blood_type, COUNT(*) AS admission_count FROM postgresql.public.hc_admissions GROUP BY blood_type ORDER BY admission_count DESC",
        "validator": lambda rows: rows and len(rows) >= 4
    },
    {
        "id": "T2-Q05", "tier": 2, "domain": "Retail",
        "nl": "What are the top 5 most sold products by quantity in retail?",
        "gold_sql": "SELECT stock_code, SUM(quantity) AS total_qty FROM postgresql.public.rt_invoices WHERE quantity > 0 GROUP BY stock_code ORDER BY total_qty DESC LIMIT 5",
        "validator": lambda rows: rows and len(rows) == 5
    },
    {
        "id": "T2-Q06", "tier": 2, "domain": "Financial",
        "nl": "What is the average transaction amount for fraudulent vs legitimate transactions?",
        "gold_sql": "SELECT class_id, ROUND(AVG(amount), 2) AS avg_amount FROM postgresql.public.fin_transactions GROUP BY class_id ORDER BY class_id",
        "validator": lambda rows: rows and len(rows) == 2
    },
    {
        "id": "T2-Q07", "tier": 2, "domain": "Supply Chain",
        "nl": "What is the average order profit by shipping mode?",
        "gold_sql": "SELECT shipping_mode, ROUND(AVG(order_profit), 2) AS avg_profit FROM postgresql.public.sc_orders GROUP BY shipping_mode ORDER BY avg_profit DESC",
        "validator": lambda rows: rows and len(rows) >= 3
    },
    {
        "id": "T2-Q08", "tier": 2, "domain": "Supply Chain",
        "nl": "What is the total sales by market region in the supply chain?",
        "gold_sql": "SELECT market, ROUND(SUM(sales), 2) AS total_sales FROM postgresql.public.sc_orders GROUP BY market ORDER BY total_sales DESC",
        "validator": lambda rows: rows and len(rows) >= 3
    },
    {
        "id": "T2-Q09", "tier": 2, "domain": "E-Commerce",
        "nl": "What is the distribution of order statuses in the e-commerce data?",
        "gold_sql": "SELECT order_status, COUNT(*) AS cnt FROM postgresql.public.olist_orders GROUP BY order_status ORDER BY cnt DESC",
        "validator": lambda rows: rows and len(rows) >= 3
    },
    {
        "id": "T2-Q10", "tier": 2, "domain": "Retail",
        "nl": "What is the total revenue per month from the retail dataset?",
        "gold_sql": "SELECT EXTRACT(MONTH FROM invoice_date) AS month_num, ROUND(SUM(quantity * unit_price), 2) AS revenue FROM postgresql.public.rt_invoices WHERE quantity > 0 GROUP BY EXTRACT(MONTH FROM invoice_date) ORDER BY month_num",
        "validator": lambda rows: rows and len(rows) >= 6
    },

    # ═══ TIER 3: Cross-Engine Join (PG fact + MySQL dimension) ═══
    {
        "id": "T3-Q01", "tier": 3, "domain": "E-Commerce",
        "nl": "What is the total revenue by customer city for e-commerce orders?",
        "gold_sql": "SELECT c.customer_city, ROUND(SUM(oi.price), 2) AS revenue FROM postgresql.public.olist_orders o JOIN postgresql.public.olist_order_items oi ON o.order_id = oi.order_id JOIN mysql.bcdr_framework.olist_customers c ON o.customer_id = c.customer_id GROUP BY c.customer_city ORDER BY revenue DESC LIMIT 10",
        "validator": lambda rows: rows and len(rows) >= 5
    },
    {
        "id": "T3-Q02", "tier": 3, "domain": "E-Commerce",
        "nl": "What are the top 5 product categories by number of items sold?",
        "gold_sql": "SELECT p.product_category_name, COUNT(*) AS items_sold FROM postgresql.public.olist_order_items oi JOIN mysql.bcdr_framework.olist_products p ON oi.product_id = p.product_id GROUP BY p.product_category_name ORDER BY items_sold DESC LIMIT 5",
        "validator": lambda rows: rows and len(rows) == 5
    },
    {
        "id": "T3-Q03", "tier": 3, "domain": "Healthcare",
        "nl": "What is the average billing amount by medical condition?",
        "gold_sql": "SELECT mc.condition_name, ROUND(AVG(a.billing_amount), 2) AS avg_billing FROM postgresql.public.hc_admissions a JOIN mysql.bcdr_framework.hc_conditions mc ON a.condition_id = mc.condition_id GROUP BY mc.condition_name ORDER BY avg_billing DESC",
        "validator": lambda rows: rows and len(rows) >= 4
    },
    {
        "id": "T3-Q04", "tier": 3, "domain": "Healthcare",
        "nl": "How many patients are covered by each insurance provider?",
        "gold_sql": "SELECT i.provider_name, COUNT(*) AS patient_count FROM postgresql.public.hc_admissions a JOIN mysql.bcdr_framework.hc_insurance i ON a.insurance_id = i.insurance_id GROUP BY i.provider_name ORDER BY patient_count DESC",
        "validator": lambda rows: rows and len(rows) >= 3
    },
    {
        "id": "T3-Q05", "tier": 3, "domain": "Retail",
        "nl": "What are the top 10 customers by total purchases in the retail dataset, including their country?",
        "gold_sql": "SELECT c.country, ri.customer_id, ROUND(SUM(ri.quantity * ri.unit_price), 2) AS total_spent FROM postgresql.public.rt_invoices ri JOIN mysql.bcdr_framework.rt_customers c ON ri.customer_id = c.customer_id WHERE ri.quantity > 0 GROUP BY c.country, ri.customer_id ORDER BY total_spent DESC LIMIT 10",
        "validator": lambda rows: rows and len(rows) >= 5
    },
    {
        "id": "T3-Q06", "tier": 3, "domain": "Financial",
        "nl": "How many fraudulent and legitimate transactions are there, showing the class names?",
        "gold_sql": "SELECT fc.class_name, COUNT(*) AS cnt FROM postgresql.public.fin_transactions ft JOIN mysql.bcdr_framework.fin_fraud_classes fc ON ft.class_id = fc.class_id GROUP BY fc.class_name ORDER BY cnt DESC",
        "validator": lambda rows: rows and len(rows) == 2
    },
    {
        "id": "T3-Q07", "tier": 3, "domain": "Financial",
        "nl": "What is the average transaction amount by time bucket in the financial dataset?",
        "gold_sql": "SELECT tb.bucket_name, ROUND(AVG(ft.amount), 2) AS avg_amount FROM postgresql.public.fin_transactions ft JOIN mysql.bcdr_framework.fin_time_buckets tb ON ft.time_hour BETWEEN tb.hour_start AND tb.hour_end GROUP BY tb.bucket_name ORDER BY avg_amount DESC",
        "validator": lambda rows: rows and len(rows) >= 2
    },
    {
        "id": "T3-Q08", "tier": 3, "domain": "Supply Chain",
        "nl": "What is the total sales by product category in the supply chain?",
        "gold_sql": "SELECT cat.category_name, ROUND(SUM(o.sales), 2) AS total_sales FROM postgresql.public.sc_orders o JOIN mysql.bcdr_framework.sc_categories cat ON o.category_id = cat.category_id GROUP BY cat.category_name ORDER BY total_sales DESC",
        "validator": lambda rows: rows and len(rows) >= 5
    },
    {
        "id": "T3-Q09", "tier": 3, "domain": "Supply Chain",
        "nl": "What is the average profit by department in the supply chain?",
        "gold_sql": "SELECT d.department_name, ROUND(AVG(o.order_profit), 2) AS avg_profit FROM postgresql.public.sc_orders o JOIN mysql.bcdr_framework.sc_departments d ON o.department_id = d.department_id GROUP BY d.department_name ORDER BY avg_profit DESC",
        "validator": lambda rows: rows and len(rows) >= 5
    },
    {
        "id": "T3-Q10", "tier": 3, "domain": "E-Commerce",
        "nl": "What is the average review score by seller state for e-commerce?",
        "gold_sql": "SELECT s.seller_state, ROUND(AVG(r.review_score), 2) AS avg_review FROM postgresql.public.olist_order_reviews r JOIN postgresql.public.olist_order_items oi ON r.order_id = oi.order_id JOIN mysql.bcdr_framework.olist_sellers s ON oi.seller_id = s.seller_id GROUP BY s.seller_state ORDER BY avg_review DESC LIMIT 10",
        "validator": lambda rows: rows and len(rows) >= 5
    },

    # ═══ TIER 4: Multi-Join Cross-Engine (3+ tables, complex aggregation) ═══
    {
        "id": "T4-Q01", "tier": 4, "domain": "E-Commerce",
        "nl": "What is the total revenue and average review score by product category for delivered orders?",
        "gold_sql": "SELECT p.product_category_name, ROUND(SUM(oi.price), 2) AS revenue, ROUND(AVG(r.review_score), 2) AS avg_review FROM postgresql.public.olist_orders o JOIN postgresql.public.olist_order_items oi ON o.order_id = oi.order_id JOIN postgresql.public.olist_order_reviews r ON o.order_id = r.order_id JOIN mysql.bcdr_framework.olist_products p ON oi.product_id = p.product_id WHERE o.order_status = 'delivered' GROUP BY p.product_category_name ORDER BY revenue DESC LIMIT 10",
        "validator": lambda rows: rows and len(rows) >= 5
    },
    {
        "id": "T4-Q02", "tier": 4, "domain": "E-Commerce",
        "nl": "Which customer states generate the most revenue, and what is the average product weight?",
        "gold_sql": "SELECT c.customer_state, ROUND(SUM(oi.price), 2) AS revenue, ROUND(AVG(p.product_weight_g), 2) AS avg_weight FROM postgresql.public.olist_orders o JOIN postgresql.public.olist_order_items oi ON o.order_id = oi.order_id JOIN mysql.bcdr_framework.olist_customers c ON o.customer_id = c.customer_id JOIN mysql.bcdr_framework.olist_products p ON oi.product_id = p.product_id GROUP BY c.customer_state ORDER BY revenue DESC LIMIT 10",
        "validator": lambda rows: rows and len(rows) >= 5
    },
    {
        "id": "T4-Q03", "tier": 4, "domain": "Healthcare",
        "nl": "What is the average billing amount by hospital and medical condition?",
        "gold_sql": "SELECT h.hospital_name, mc.condition_name, ROUND(AVG(a.billing_amount), 2) AS avg_billing FROM postgresql.public.hc_admissions a JOIN mysql.bcdr_framework.hc_hospitals h ON a.hospital_id = h.hospital_id JOIN mysql.bcdr_framework.hc_conditions mc ON a.condition_id = mc.condition_id GROUP BY h.hospital_name, mc.condition_name ORDER BY avg_billing DESC LIMIT 10",
        "validator": lambda rows: rows and len(rows) >= 1
    },
    {
        "id": "T4-Q04", "tier": 4, "domain": "Healthcare",
        "nl": "Which doctors have the highest billing amounts, and what insurance providers cover their patients?",
        "gold_sql": "SELECT d.doctor_name, i.provider_name, ROUND(SUM(a.billing_amount), 2) AS total_billing FROM postgresql.public.hc_admissions a JOIN mysql.bcdr_framework.hc_doctors d ON a.doctor_id = d.doctor_id JOIN mysql.bcdr_framework.hc_insurance i ON a.insurance_id = i.insurance_id GROUP BY d.doctor_name, i.provider_name ORDER BY total_billing DESC LIMIT 10",
        "validator": lambda rows: rows and len(rows) >= 5
    },
    {
        "id": "T4-Q05", "tier": 4, "domain": "Retail",
        "nl": "What are the top products by revenue with their descriptions, for UK customers only?",
        "gold_sql": "SELECT rp.description, ROUND(SUM(ri.quantity * ri.unit_price), 2) AS revenue FROM postgresql.public.rt_invoices ri JOIN mysql.bcdr_framework.rt_customers c ON ri.customer_id = c.customer_id JOIN mysql.bcdr_framework.rt_products rp ON ri.stock_code = rp.stock_code WHERE TRIM(c.country) = 'United Kingdom' AND ri.quantity > 0 GROUP BY rp.description ORDER BY revenue DESC LIMIT 10",
        "validator": lambda rows: rows and len(rows) >= 5
    },
    {
        "id": "T4-Q06", "tier": 4, "domain": "Financial",
        "nl": "What is the fraud rate by time bucket, showing both class names and bucket descriptions?",
        "gold_sql": "SELECT tb.bucket_name, fc.class_name, COUNT(*) AS cnt FROM postgresql.public.fin_transactions ft JOIN mysql.bcdr_framework.fin_fraud_classes fc ON ft.class_id = fc.class_id JOIN mysql.bcdr_framework.fin_time_buckets tb ON ft.time_hour BETWEEN tb.hour_start AND tb.hour_end GROUP BY tb.bucket_name, fc.class_name ORDER BY tb.bucket_name, cnt DESC",
        "validator": lambda rows: rows and len(rows) >= 4
    },
    {
        "id": "T4-Q07", "tier": 4, "domain": "Supply Chain",
        "nl": "What is the average profit by department and product category in the supply chain?",
        "gold_sql": "SELECT d.department_name, cat.category_name, ROUND(AVG(o.order_profit), 2) AS avg_profit FROM postgresql.public.sc_orders o JOIN mysql.bcdr_framework.sc_departments d ON o.department_id = d.department_id JOIN mysql.bcdr_framework.sc_categories cat ON o.category_id = cat.category_id GROUP BY d.department_name, cat.category_name ORDER BY avg_profit DESC LIMIT 10",
        "validator": lambda rows: rows and len(rows) >= 5
    },
    {
        "id": "T4-Q08", "tier": 4, "domain": "Supply Chain",
        "nl": "What is the late delivery rate by customer segment, showing customer details?",
        "gold_sql": "SELECT sc.segment, COUNT(*) AS total_orders, SUM(o.late_delivery_risk) AS late_orders, ROUND(100.0 * SUM(o.late_delivery_risk) / COUNT(*), 2) AS late_pct FROM postgresql.public.sc_orders o JOIN mysql.bcdr_framework.sc_customers sc ON o.customer_id = sc.customer_id GROUP BY sc.segment ORDER BY late_pct DESC",
        "validator": lambda rows: rows and len(rows) >= 2
    },
    {
        "id": "T4-Q09", "tier": 4, "domain": "E-Commerce",
        "nl": "What is the average delivery time in days by customer state for delivered orders?",
        "gold_sql": "SELECT c.customer_state, ROUND(AVG(DATE_DIFF('day', o.order_purchase_timestamp, o.order_delivered_customer_date)), 2) AS avg_delivery_days FROM postgresql.public.olist_orders o JOIN mysql.bcdr_framework.olist_customers c ON o.customer_id = c.customer_id WHERE o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL GROUP BY c.customer_state ORDER BY avg_delivery_days DESC LIMIT 10",
        "validator": lambda rows: rows and len(rows) >= 5
    },
    {
        "id": "T4-Q10", "tier": 4, "domain": "Healthcare",
        "nl": "What is the average length of stay by condition and hospital?",
        "gold_sql": "SELECT h.hospital_name, mc.condition_name, ROUND(AVG(DATE_DIFF('day', a.date_of_admission, a.discharge_date)), 2) AS avg_los FROM postgresql.public.hc_admissions a JOIN mysql.bcdr_framework.hc_hospitals h ON a.hospital_id = h.hospital_id JOIN mysql.bcdr_framework.hc_conditions mc ON a.condition_id = mc.condition_id GROUP BY h.hospital_name, mc.condition_name ORDER BY avg_los DESC LIMIT 10",
        "validator": lambda rows: rows and len(rows) >= 1
    },

    # ═══ TIER 5: Cross-Domain Federation ═══
    {
        "id": "T5-Q01", "tier": 5, "domain": "Cross-Domain",
        "nl": "What is the total transaction count and total monetary value across all five business domains?",
        "gold_sql": """SELECT 'E-Commerce' AS domain, COUNT(*) AS row_count, ROUND(SUM(price), 2) AS total_value FROM postgresql.public.olist_order_items
UNION ALL SELECT 'Healthcare', COUNT(*), ROUND(SUM(billing_amount), 2) FROM postgresql.public.hc_admissions
UNION ALL SELECT 'Retail', COUNT(*), ROUND(SUM(quantity * unit_price), 2) FROM postgresql.public.rt_invoices WHERE quantity > 0
UNION ALL SELECT 'Financial', COUNT(*), ROUND(SUM(amount), 2) FROM postgresql.public.fin_transactions
UNION ALL SELECT 'Supply Chain', COUNT(*), ROUND(SUM(sales), 2) FROM postgresql.public.sc_orders""",
        "validator": lambda rows: rows and len(rows) == 5
    },
    {
        "id": "T5-Q02", "tier": 5, "domain": "Cross-Domain",
        "nl": "Compare the average transaction value between the e-commerce and retail domains.",
        "gold_sql": "SELECT 'E-Commerce' AS domain, ROUND(AVG(price), 2) AS avg_value FROM postgresql.public.olist_order_items UNION ALL SELECT 'Retail', ROUND(AVG(quantity * unit_price), 2) FROM postgresql.public.rt_invoices WHERE quantity > 0",
        "validator": lambda rows: rows and len(rows) == 2
    },
    {
        "id": "T5-Q03", "tier": 5, "domain": "Cross-Domain",
        "nl": "What are the top 5 countries by total value combining retail customers and supply chain customers?",
        "gold_sql": "SELECT country, ROUND(SUM(total_value), 2) AS combined_value FROM (SELECT c.country, SUM(ri.quantity * ri.unit_price) AS total_value FROM postgresql.public.rt_invoices ri JOIN mysql.bcdr_framework.rt_customers c ON ri.customer_id = c.customer_id WHERE ri.quantity > 0 GROUP BY c.country UNION ALL SELECT sc.country, SUM(o.sales) AS total_value FROM postgresql.public.sc_orders o JOIN mysql.bcdr_framework.sc_customers sc ON o.customer_id = sc.customer_id GROUP BY sc.country) combined GROUP BY country ORDER BY combined_value DESC LIMIT 5",
        "validator": lambda rows: rows and len(rows) >= 3
    },
    {
        "id": "T5-Q04", "tier": 5, "domain": "Cross-Domain",
        "nl": "What percentage of transactions are anomalous in each domain (fraud in financial, late delivery in supply chain, low review in e-commerce)?",
        "gold_sql": "SELECT 'Financial-Fraud' AS anomaly_type, ROUND(100.0 * SUM(CASE WHEN class_id = 1 THEN 1 ELSE 0 END) / COUNT(*), 4) AS anomaly_pct FROM postgresql.public.fin_transactions UNION ALL SELECT 'SupplyChain-Late', ROUND(100.0 * SUM(late_delivery_risk) / COUNT(*), 4) FROM postgresql.public.sc_orders UNION ALL SELECT 'ECommerce-LowReview', ROUND(100.0 * SUM(CASE WHEN review_score <= 2 THEN 1 ELSE 0 END) / COUNT(*), 4) FROM postgresql.public.olist_order_reviews",
        "validator": lambda rows: rows and len(rows) == 3
    },
    {
        "id": "T5-Q05", "tier": 5, "domain": "Cross-Domain",
        "nl": "Compare the number of distinct entities (customers, patients, products) across all five domains.",
        "gold_sql": "SELECT 'E-Commerce Customers' AS entity, COUNT(DISTINCT customer_id) AS cnt FROM postgresql.public.olist_orders UNION ALL SELECT 'Healthcare Patients', COUNT(DISTINCT patient_name) FROM postgresql.public.hc_admissions UNION ALL SELECT 'Retail Customers', COUNT(DISTINCT customer_id) FROM postgresql.public.rt_invoices UNION ALL SELECT 'Financial Txns', COUNT(*) FROM postgresql.public.fin_transactions UNION ALL SELECT 'Supply Chain Orders', COUNT(DISTINCT order_id) FROM postgresql.public.sc_orders",
        "validator": lambda rows: rows and len(rows) == 5
    },
    {
        "id": "T5-Q06", "tier": 5, "domain": "Cross-Domain",
        "nl": "What is the total revenue by Brazilian state combining e-commerce orders and seller locations?",
        "gold_sql": "SELECT c.customer_state AS state, ROUND(SUM(oi.price), 2) AS customer_revenue FROM postgresql.public.olist_orders o JOIN postgresql.public.olist_order_items oi ON o.order_id = oi.order_id JOIN mysql.bcdr_framework.olist_customers c ON o.customer_id = c.customer_id GROUP BY c.customer_state ORDER BY customer_revenue DESC LIMIT 10",
        "validator": lambda rows: rows and len(rows) >= 5
    },
    {
        "id": "T5-Q07", "tier": 5, "domain": "Cross-Domain",
        "nl": "What is the supply chain department with the highest profit and the e-commerce category with the highest revenue?",
        "gold_sql": "SELECT 'SC-TopDept' AS label, d.department_name AS name, ROUND(SUM(o.order_profit), 2) AS value FROM postgresql.public.sc_orders o JOIN mysql.bcdr_framework.sc_departments d ON o.department_id = d.department_id GROUP BY d.department_name ORDER BY value DESC LIMIT 1",
        "validator": lambda rows: rows and len(rows) >= 1
    },
    {
        "id": "T5-Q08", "tier": 5, "domain": "Cross-Domain",
        "nl": "Which healthcare insurance providers correspond to the highest average billing, and how does this compare to the e-commerce average order value?",
        "gold_sql": "SELECT 'Healthcare' AS domain, i.provider_name AS entity, ROUND(AVG(a.billing_amount), 2) AS avg_value FROM postgresql.public.hc_admissions a JOIN mysql.bcdr_framework.hc_insurance i ON a.insurance_id = i.insurance_id GROUP BY i.provider_name ORDER BY avg_value DESC LIMIT 3",
        "validator": lambda rows: rows and len(rows) >= 2
    },
    {
        "id": "T5-Q09", "tier": 5, "domain": "Cross-Domain",
        "nl": "Calculate the overall health score of each domain: average review for e-commerce, discharge rate for healthcare, return rate for retail, fraud rate for financial, and on-time rate for supply chain.",
        "gold_sql": "SELECT 'E-Commerce AvgReview' AS metric, ROUND(AVG(review_score), 4) AS value FROM postgresql.public.olist_order_reviews UNION ALL SELECT 'Healthcare AvgBilling', ROUND(AVG(billing_amount), 2) FROM postgresql.public.hc_admissions UNION ALL SELECT 'Financial FraudRate', ROUND(100.0 * SUM(CASE WHEN class_id=1 THEN 1 ELSE 0 END)/COUNT(*), 4) FROM postgresql.public.fin_transactions UNION ALL SELECT 'SupplyChain OnTimeRate', ROUND(100.0 * SUM(CASE WHEN late_delivery_risk=0 THEN 1 ELSE 0 END)/COUNT(*), 2) FROM postgresql.public.sc_orders",
        "validator": lambda rows: rows and len(rows) >= 4
    },
    {
        "id": "T5-Q10", "tier": 5, "domain": "Cross-Domain",
        "nl": "Show a unified summary: for each of the five domains, show the total rows, the total monetary value, and the number of dimension tables used.",
        "gold_sql": "SELECT 'E-Commerce' AS domain, COUNT(*) AS rows, ROUND(SUM(price + freight_value), 2) AS total_value FROM postgresql.public.olist_order_items UNION ALL SELECT 'Healthcare', COUNT(*), ROUND(SUM(billing_amount), 2) FROM postgresql.public.hc_admissions UNION ALL SELECT 'Retail', COUNT(*), ROUND(SUM(quantity * unit_price), 2) FROM postgresql.public.rt_invoices UNION ALL SELECT 'Financial', COUNT(*), ROUND(SUM(amount), 2) FROM postgresql.public.fin_transactions UNION ALL SELECT 'Supply Chain', COUNT(*), ROUND(SUM(sales), 2) FROM postgresql.public.sc_orders",
        "validator": lambda rows: rows and len(rows) == 5
    },
]

# ─── Federation Engine Query Runner ────────────────────────────────────────────────────
# Both PrestoDB and Trino implement the same /v1/statement protocol, but they read
# DIFFERENT request headers: PrestoDB reads X-Presto-*, Trino reads X-Trino-*. Send
# the wrong family and the engine replies 401 with a plain-text body, which surfaces
# much later as "Expecting value: line 1 column 1" from r.json(). The family is
# therefore detected once, from the first response, and cached for the process.
HEADER_STYLE = os.environ.get('ENGINE_HEADER_STYLE', '').lower()
_PREFIX = None


def _headers(catalog='postgresql', schema='public'):
    """Session headers in whichever family this engine accepts."""
    p = _PREFIX or 'X-Trino-'
    return {f'{p}User': 'presto', f'{p}Catalog': catalog, f'{p}Schema': schema}


def _adopt_style(prefix):
    global _PREFIX
    _PREFIX = prefix


def run_presto(sql, timeout=30):
    """Execute SQL via the federation engine REST API.

    Returns (columns, rows, elapsed_sec, error). `error` is None on success.
    """
    global _PREFIX
    if _PREFIX is None:
        _PREFIX = {'presto': 'X-Presto-', 'trino': 'X-Trino-'}.get(HEADER_STYLE, 'X-Trino-')

    t0 = time.time()
    try:
        r = requests.post(f'{FEDERATION_URL}/v1/statement', headers=_headers(),
                          data=sql, timeout=10)
    except Exception as e:
        return None, None, time.time() - t0, str(e)

    # A wrong header family never returns JSON. The status differs by product:
    #   Trino     -> 401 "Basic authentication or X-Trino-Original-User or
    #                      X-Trino-User must be sent"
    #   PrestoDB  -> 400 "User must be set"
    # So keying the retry on one particular status misses the other. Retry with a
    # CLEAN header set for the other family on any 4xx, and remember what worked.
    # The retry deliberately does not mix families, or it would not identify which
    # one the engine actually wants.
    if 400 <= r.status_code < 500:
        other = 'X-Presto-' if _PREFIX == 'X-Trino-' else 'X-Trino-'
        try:
            r2 = requests.post(
                f'{FEDERATION_URL}/v1/statement',
                headers={f'{other}User': 'presto',
                         f'{other}Catalog': 'postgresql',
                         f'{other}Schema': 'public'},
                data=sql, timeout=10)
        except Exception:
            r2 = None
        if r2 is not None and r2.status_code == 200:
            _adopt_style(other)
            r = r2

    try:
        d = r.json()
    except ValueError:
        body = (r.text or '').strip().replace('\n', ' ')[:140]
        return (None, None, time.time() - t0,
                f'engine returned HTTP {r.status_code} with a non-JSON body: {body!r} '
                f'(sent {_PREFIX}* headers; set ENGINE_HEADER_STYLE=presto|trino to force)')

    all_rows = d.get('data', [])
    cols = [c['name'] for c in d.get('columns', [])] if d.get('columns') else []
    uri = d.get('nextUri')
    error = d.get('error')

    for _ in range(120):
        if not uri:
            break
        if time.time() - t0 > timeout:
            break
        time.sleep(0.25)
        try:
            resp = requests.get(uri, headers=_headers(), timeout=10)
            d = resp.json()
        except Exception as e:
            return cols, all_rows, time.time() - t0, str(e)
        if d.get('columns') and not cols:
            cols = [c['name'] for c in d['columns']]
        all_rows.extend(d.get('data', []))
        error = d.get('error')
        uri = d.get('nextUri')
    
    elapsed = time.time() - t0
    if error:
        return cols, all_rows, elapsed, error.get('message', str(error))
    return cols, all_rows, elapsed, None

# ─── Local LLM Caller ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a SQL expert for federated SQL. Output ONLY a single SQL query, no explanation.

RULE 1 — CATALOG PREFIXES (MANDATORY, NEVER OMIT):
  Fact tables (PostgreSQL):   postgresql.public.<table>
  Dimension tables (MariaDB): mysql.<schema>.<table>
NEVER put a PostgreSQL table under mysql.* and NEVER put a MariaDB table under postgresql.*.

RULE 2 — PRESTO SQL DIALECT:
  Date difference:  DATE_DIFF('day', start_ts, end_ts)   — NOT datediff()
  Extract fields:   EXTRACT(YEAR|MONTH|DAY|HOUR|MINUTE|SECOND FROM ts)  — NO MICROSECOND
  Cast when needed: CAST(col AS INTEGER), CAST(col AS VARCHAR)
  String compare:   Use CAST if comparing varchar to integer
  No DATEDIFF, no TIMESTAMPDIFF, no DATE_SUB, no INTERVAL arithmetic.
  Do NOT use semicolons.
  UNION ALL: each SELECT must be on the same line or wrapped correctly. No stray UNION.
  Multiplication: only numeric types (INTEGER, DECIMAL) can be multiplied. Never multiply VARCHAR or TIMESTAMP.

RULE 3 — ONLY USE COLUMNS THAT EXIST (see DDL below). NEVER invent column names.
  Common mistakes to AVOID:
  - olist_order_items does NOT have: customer_id, quantity, order_date, order_item_total
  - olist_customers does NOT have: country (only customer_city, customer_state)
  - olist_products does NOT have: product_name
  - sc_orders does NOT have: department_name, category_name, customer_segment (join to dimension tables)
  - fin_transactions does NOT have: time_bucket, fraud_class (join to dimension tables)

RULE 4 — TABLE PLACEMENT (CRITICAL):
  These 8 tables are in PostgreSQL ONLY: olist_orders, olist_order_items, olist_order_payments,
    olist_order_reviews, hc_admissions, rt_invoices, fin_transactions, sc_orders
  ALL other tables are in MySQL. NEVER write mysql.bcdr_framework.hc_admissions or mysql.bcdr_framework.rt_invoices.

=== POSTGRESQL FACT TABLES (use prefix: postgresql.public.) ===

CREATE TABLE postgresql.public.olist_orders (
  order_id VARCHAR,          -- PK, joins to order_items/payments/reviews
  customer_id VARCHAR,       -- FK to mysql.bcdr_framework.olist_customers
  order_status VARCHAR,      -- delivered, shipped, canceled, etc.
  order_purchase_timestamp TIMESTAMP,
  order_approved_at TIMESTAMP,
  order_delivered_carrier_date TIMESTAMP,
  order_delivered_customer_date TIMESTAMP,
  order_estimated_delivery_date TIMESTAMP
);

CREATE TABLE postgresql.public.olist_order_items (
  order_id VARCHAR,          -- FK to olist_orders
  order_item_id INTEGER,
  product_id VARCHAR,        -- FK to mysql.bcdr_framework.olist_products
  seller_id VARCHAR,         -- FK to mysql.bcdr_framework.olist_sellers
  shipping_limit_date TIMESTAMP,
  price DECIMAL,             -- item price
  freight_value DECIMAL      -- shipping cost
  -- NOTE: NO customer_id, NO quantity, NO order_date, NO order_item_total columns here
);

CREATE TABLE postgresql.public.olist_order_payments (
  order_id VARCHAR,          -- FK to olist_orders
  payment_sequential INTEGER,
  payment_type VARCHAR,      -- credit_card, boleto, voucher, debit_card
  payment_installments INTEGER,
  payment_value DECIMAL      -- payment amount
);

CREATE TABLE postgresql.public.olist_order_reviews (
  review_id VARCHAR,
  order_id VARCHAR,          -- FK to olist_orders
  review_score INTEGER,      -- 1 to 5
  review_comment_title VARCHAR,
  review_comment_message VARCHAR,
  review_creation_date TIMESTAMP,
  review_answer_timestamp TIMESTAMP
);

CREATE TABLE postgresql.public.hc_admissions (
  admission_id INTEGER,
  patient_name VARCHAR,
  age INTEGER,
  gender VARCHAR,
  blood_type VARCHAR,        -- A+, A-, B+, etc. (column, NOT a separate table)
  condition_id INTEGER,      -- FK to mysql.bcdr_framework.hc_conditions
  doctor_id INTEGER,         -- FK to mysql.bcdr_framework.hc_doctors
  hospital_id INTEGER,       -- FK to mysql.bcdr_framework.hc_hospitals
  insurance_id INTEGER,      -- FK to mysql.bcdr_framework.hc_insurance
  billing_amount DECIMAL,
  room_number INTEGER,
  admission_type VARCHAR,    -- Emergency, Urgent, Elective
  date_of_admission DATE,
  discharge_date DATE,
  medication VARCHAR,
  test_results VARCHAR       -- Normal, Abnormal, Inconclusive
);

CREATE TABLE postgresql.public.rt_invoices (
  invoice_id INTEGER,
  invoice_no VARCHAR(20),
  stock_code VARCHAR(20),    -- FK to mysql.bcdr_framework.rt_products
  quantity INTEGER,           -- can be negative (returns)
  invoice_date TIMESTAMP,
  unit_price DECIMAL(10,4),
  customer_id VARCHAR(20)    -- FK to mysql.bcdr_framework.rt_customers (VARCHAR type, NOT integer)
);

CREATE TABLE postgresql.public.fin_transactions (
  transaction_id INTEGER,
  time_elapsed DECIMAL,
  v1 DECIMAL, v2 DECIMAL, v3 DECIMAL, v4 DECIMAL, v5 DECIMAL,
  v6 DECIMAL, v7 DECIMAL, v8 DECIMAL, v9 DECIMAL, v10 DECIMAL,
  v11 DECIMAL, v12 DECIMAL, v13 DECIMAL, v14 DECIMAL, v15 DECIMAL,
  v16 DECIMAL, v17 DECIMAL, v18 DECIMAL, v19 DECIMAL, v20 DECIMAL,
  v21 DECIMAL, v22 DECIMAL, v23 DECIMAL, v24 DECIMAL, v25 DECIMAL,
  v26 DECIMAL, v27 DECIMAL, v28 DECIMAL,
  amount DECIMAL,            -- transaction amount
  class_id INTEGER,          -- 0=legitimate, 1=fraud; FK to mysql.bcdr_framework.fin_fraud_classes
  time_hour INTEGER          -- hour of day (0-23); for mysql.bcdr_framework.fin_time_buckets use BETWEEN
);

CREATE TABLE postgresql.public.sc_orders (
  order_row_id INTEGER,
  order_id INTEGER,
  order_item_id INTEGER,
  order_date VARCHAR(30),     -- stored as string, NOT timestamp
  shipping_date VARCHAR(30),  -- stored as string, NOT timestamp
  type VARCHAR(20),
  days_shipping_real INTEGER,
  days_shipment_scheduled INTEGER,
  delivery_status VARCHAR,   -- Advance shipping, Late delivery, Shipping on time, Shipping canceled
  late_delivery_risk INTEGER, -- 0 or 1
  customer_id INTEGER,       -- FK to mysql.bcdr_framework.sc_customers
  product_id INTEGER,        -- FK to mysql.bcdr_framework.sc_products
  department_id INTEGER,     -- FK to mysql.bcdr_framework.sc_departments
  category_id INTEGER,       -- FK to mysql.bcdr_framework.sc_categories
  order_item_quantity INTEGER,
  order_item_discount DECIMAL,
  order_item_discount_rate DECIMAL,
  order_item_product_price DECIMAL,
  sales DECIMAL,
  order_item_total DECIMAL,
  order_profit DECIMAL,
  benefit_per_order DECIMAL,
  sales_per_customer DECIMAL,
  shipping_mode VARCHAR,     -- Standard Class, Second Class, First Class, Same Day
  market VARCHAR,            -- LATAM, Europe, Pacific Asia, USCA, Africa
  order_city VARCHAR,
  order_country VARCHAR,
  order_region VARCHAR,
  order_state VARCHAR
  -- NOTE: NO department_name, NO category_name columns here. Join to dimension tables.
);

=== MARIADB DIMENSION TABLES (use prefix: mysql.<schema>.) ===

-- E-Commerce dimensions (schema: olist_ecommerce)
CREATE TABLE mysql.bcdr_framework.olist_customers (
  customer_id VARCHAR(64),   -- PK, matches olist_orders.customer_id
  customer_unique_id VARCHAR(64),
  customer_zip_code_prefix VARCHAR(10),  -- stored as VARCHAR, NOT integer
  customer_city VARCHAR(128),
  customer_state VARCHAR(4)  -- 2-letter state code, e.g. 'SP', 'RJ'
  -- NOTE: NO 'country' column here. All customers are Brazilian.
);
CREATE TABLE mysql.bcdr_framework.olist_products (
  product_id VARCHAR,        -- PK
  product_category_name VARCHAR,  -- category in Portuguese
  product_name_lenght INTEGER, product_description_lenght INTEGER,
  product_photos_qty INTEGER,
  product_weight_g INTEGER,
  product_length_cm INTEGER, product_height_cm INTEGER, product_width_cm INTEGER
  -- NOTE: NO product_name column
);
CREATE TABLE mysql.bcdr_framework.olist_sellers (
  seller_id VARCHAR(64),     -- PK
  seller_zip_code_prefix VARCHAR(10),  -- stored as VARCHAR, NOT integer
  seller_city VARCHAR(128), seller_state VARCHAR(4)
);
CREATE TABLE mysql.bcdr_framework.olist_geolocation (
  geolocation_zip_code_prefix INTEGER,
  geolocation_lat DECIMAL, geolocation_lng DECIMAL,
  geolocation_city VARCHAR, geolocation_state VARCHAR
);
CREATE TABLE mysql.bcdr_framework.product_category_translation (
  product_category_name VARCHAR,  -- Portuguese
  product_category_name_english VARCHAR  -- English
);

-- Healthcare dimensions (schema: healthcare)
CREATE TABLE mysql.bcdr_framework.hc_conditions (condition_id INTEGER, condition_name VARCHAR);
CREATE TABLE mysql.bcdr_framework.hc_insurance (insurance_id INTEGER, provider_name VARCHAR);  -- NOT insurance_name
CREATE TABLE mysql.bcdr_framework.hc_hospitals (hospital_id INTEGER, hospital_name VARCHAR);
CREATE TABLE mysql.bcdr_framework.hc_doctors (doctor_id INTEGER, doctor_name VARCHAR);

-- Retail dimensions (schema: retail)
CREATE TABLE mysql.bcdr_framework.rt_customers (customer_id VARCHAR(20), country VARCHAR(50));  -- customer_id is VARCHAR, same as rt_invoices
CREATE TABLE mysql.bcdr_framework.rt_products (stock_code VARCHAR(20), description VARCHAR(255));

-- Financial dimensions (schema: financial)
CREATE TABLE mysql.bcdr_framework.fin_fraud_classes (class_id INTEGER, class_name VARCHAR, description VARCHAR);
CREATE TABLE mysql.bcdr_framework.fin_time_buckets (bucket_id INTEGER, bucket_name VARCHAR, hour_start INTEGER, hour_end INTEGER, description VARCHAR);

-- Supply Chain dimensions (schema: supply_chain)
CREATE TABLE mysql.bcdr_framework.sc_customers (customer_id INTEGER, first_name VARCHAR, last_name VARCHAR, email VARCHAR, segment VARCHAR, city VARCHAR, country VARCHAR, state VARCHAR, zipcode VARCHAR);
CREATE TABLE mysql.bcdr_framework.sc_products (product_id INTEGER, product_name VARCHAR, product_price DECIMAL, category_id INTEGER, product_status INTEGER);
CREATE TABLE mysql.bcdr_framework.sc_departments (department_id INTEGER, department_name VARCHAR);
CREATE TABLE mysql.bcdr_framework.sc_categories (category_id INTEGER, category_name VARCHAR);

=== EXAMPLES ===

Q: How many orders in e-commerce?
A: SELECT COUNT(*) AS total_orders FROM postgresql.public.olist_orders

Q: Revenue by product category?
A: SELECT p.product_category_name, ROUND(SUM(oi.price), 2) AS revenue FROM postgresql.public.olist_order_items oi JOIN mysql.bcdr_framework.olist_products p ON oi.product_id = p.product_id GROUP BY p.product_category_name ORDER BY revenue DESC LIMIT 10

Q: Average billing by condition and hospital?
A: SELECT h.hospital_name, mc.condition_name, ROUND(AVG(a.billing_amount), 2) AS avg_billing FROM postgresql.public.hc_admissions a JOIN mysql.bcdr_framework.hc_hospitals h ON a.hospital_id = h.hospital_id JOIN mysql.bcdr_framework.hc_conditions mc ON a.condition_id = mc.condition_id GROUP BY h.hospital_name, mc.condition_name ORDER BY avg_billing DESC LIMIT 10

Q: Average profit by department in supply chain?
A: SELECT d.department_name, ROUND(AVG(o.order_profit), 2) AS avg_profit FROM postgresql.public.sc_orders o JOIN mysql.bcdr_framework.sc_departments d ON o.department_id = d.department_id GROUP BY d.department_name ORDER BY avg_profit DESC

Q: Total revenue by customer state for delivered e-commerce orders?
A: SELECT c.customer_state, ROUND(SUM(oi.price), 2) AS revenue FROM postgresql.public.olist_orders o JOIN postgresql.public.olist_order_items oi ON o.order_id = oi.order_id JOIN mysql.bcdr_framework.olist_customers c ON o.customer_id = c.customer_id WHERE o.order_status = 'delivered' GROUP BY c.customer_state ORDER BY revenue DESC LIMIT 10

Q: Transaction count across all five domains?
A: SELECT 'E-Commerce' AS domain, COUNT(*) AS cnt FROM postgresql.public.olist_order_items UNION ALL SELECT 'Healthcare', COUNT(*) FROM postgresql.public.hc_admissions UNION ALL SELECT 'Retail', COUNT(*) FROM postgresql.public.rt_invoices UNION ALL SELECT 'Financial', COUNT(*) FROM postgresql.public.fin_transactions UNION ALL SELECT 'Supply Chain', COUNT(*) FROM postgresql.public.sc_orders

Q: Revenue and fraud class name?
A: SELECT fc.class_name, ROUND(SUM(ft.amount), 2) AS total FROM postgresql.public.fin_transactions ft JOIN mysql.bcdr_framework.fin_fraud_classes fc ON ft.class_id = fc.class_id GROUP BY fc.class_name

Q: Top 5 retail products by revenue in the UK?
A: SELECT rp.description, ROUND(SUM(ri.quantity * ri.unit_price), 2) AS revenue FROM postgresql.public.rt_invoices ri JOIN mysql.bcdr_framework.rt_customers c ON ri.customer_id = c.customer_id JOIN mysql.bcdr_framework.rt_products rp ON ri.stock_code = rp.stock_code WHERE c.country = 'United Kingdom' AND ri.quantity > 0 GROUP BY rp.description ORDER BY revenue DESC LIMIT 5

Q: Late delivery rate by customer segment in supply chain?
A: SELECT sc.segment, ROUND(100.0 * SUM(o.late_delivery_risk) / COUNT(*), 2) AS late_pct FROM postgresql.public.sc_orders o JOIN mysql.bcdr_framework.sc_customers sc ON o.customer_id = sc.customer_id GROUP BY sc.segment ORDER BY late_pct DESC
"""

def call_local_llm(model, question, timeout=180):
    """Call local LLM and return (sql, elapsed_sec, raw_response)"""
    t0 = time.time()
    try:
        r = requests.post(f'{OLLAMA_URL}/api/generate', json={
            'model': model,
            'prompt': f"{SYSTEM_PROMPT}\n\nQ: {question}\nA:",
            'stream': False,
            'options': {'temperature': 0.0, 'num_predict': 1024}
        }, timeout=timeout)
        d = r.json()
        elapsed = time.time() - t0
        raw = d.get('response', '')
        # Extract SQL from response
        sql = extract_sql(raw)
        return sql, elapsed, raw
    except Exception as e:
        return None, time.time() - t0, str(e)


def call_local_llm_prompt(model, prompt, timeout=180):
    """Call local LLM with a fully constructed prompt."""
    t0 = time.time()
    try:
        r = requests.post(f'{OLLAMA_URL}/api/generate', json={
            'model': model,
            'prompt': prompt,
            'stream': False,
            'options': {'temperature': 0.0, 'num_predict': 1024}
        }, timeout=timeout)
        d = r.json()
        elapsed = time.time() - t0
        raw = d.get('response', '')
        sql = extract_sql(raw)
        return sql, elapsed, raw
    except Exception as e:
        return None, time.time() - t0, str(e)

CLOUD_API_KEYS = [
    k for k in [
        os.environ.get(f"CLOUD_API_KEY_{i}", "") or os.environ.get(f"OPENROUTER_API_KEY_{i}", "")
        for i in range(1, 11)
    ] if k
]
CLOUD_KEY_IDX = 0

def call_cloud_llm(model_id, question, timeout=120):
    """Call cloud LLM and return (sql, elapsed_sec, raw_response)"""
    global CLOUD_KEY_IDX
    if not CLOUD_API_KEYS:
        return None, 0, "No cloud API keys configured"
    # Some models (Gemma-3) reject system messages — merge into user prompt
    merged_prompt = f"{SYSTEM_PROMPT}\n\nQ: {question}\nA:"
    
    for attempt in range(3):  # retry up to 3 times
        key = CLOUD_API_KEYS[CLOUD_KEY_IDX % len(CLOUD_API_KEYS)]
        CLOUD_KEY_IDX += 1
        t0 = time.time()
        try:
            r = requests.post('https://openrouter.ai/api/v1/chat/completions', 
                headers={
                    'Authorization': f'Bearer {key}',
                    'Content-Type': 'application/json',
                    'HTTP-Referer': 'https://server.example.edu',
                    'X-Title': 'SARAI Benchmark'
                },
                json={
                    'model': model_id,
                    'messages': [
                        {'role': 'user', 'content': merged_prompt}
                    ],
                    'temperature': 0.0,
                    'max_tokens': 2048
                }, timeout=timeout)
            d = r.json()
            elapsed = time.time() - t0
            if 'error' in d:
                err_msg = d['error'].get('message', str(d['error']))
                err_code = d['error'].get('code', 0)
                if attempt < 2:
                    wait = 15 if err_code == 429 else 5
                    print(f"    [Retry {attempt+1}] {err_msg[:80]}  (wait {wait}s)")
                    time.sleep(wait)
                    continue
                return None, elapsed, f"API Error: {err_msg}"
            raw = d.get('choices', [{}])[0].get('message', {}).get('content', '')
            sql = extract_sql(raw)
            return sql, elapsed, raw
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
                continue
            return None, time.time() - t0, str(e)
    return None, 0, "Max retries exceeded"


def call_cloud_llm_prompt(model_id, prompt, timeout=120):
    """Call cloud LLM with a fully constructed prompt."""
    global CLOUD_KEY_IDX

    for attempt in range(3):
        key = CLOUD_API_KEYS[CLOUD_KEY_IDX % len(CLOUD_API_KEYS)]
        CLOUD_KEY_IDX += 1
        t0 = time.time()
        try:
            r = requests.post('https://openrouter.ai/api/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {key}',
                    'Content-Type': 'application/json',
                    'HTTP-Referer': 'https://server.example.edu',
                    'X-Title': 'SARAI Benchmark'
                },
                json={
                    'model': model_id,
                    'messages': [
                        {'role': 'user', 'content': prompt}
                    ],
                    'temperature': 0.0,
                    'max_tokens': 2048
                }, timeout=timeout)
            d = r.json()
            elapsed = time.time() - t0
            if 'error' in d:
                err_msg = d['error'].get('message', str(d['error']))
                err_code = d['error'].get('code', 0)
                if attempt < 2:
                    wait = 15 if err_code == 429 else 5
                    time.sleep(wait)
                    continue
                return None, elapsed, f"API Error: {err_msg}"
            raw = d.get('choices', [{}])[0].get('message', {}).get('content', '')
            sql = extract_sql(raw)
            return sql, elapsed, raw
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
                continue
            return None, time.time() - t0, str(e)
    return None, 0, "Max retries exceeded"


def build_repair_prompt(question, bad_sql, failure_message):
    return f"""{SYSTEM_PROMPT}

The previous SQL failed. Repair it.

Question:
{question}

Previous SQL:
{bad_sql or 'NONE'}

Failure:
{failure_message}

Return ONLY ONE corrected SQL query, no explanation, no markdown.
"""

def extract_sql(raw):
    """Extract SQL from model response, handling markdown code blocks and thinking tags"""
    if not raw:
        return None
    raw = raw.strip()
    # Remove DeepSeek R1 <think>...</think> blocks
    raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
    # Remove markdown code blocks
    sql = None
    if '```sql' in raw:
        match = re.search(r'```sql\s*(.*?)\s*```', raw, re.DOTALL)
        if match:
            sql = match.group(1).strip()
    if sql is None and '```' in raw:
        match = re.search(r'```\s*(.*?)\s*```', raw, re.DOTALL)
        if match:
            sql = match.group(1).strip()
    if sql is None:
        # Take everything that looks like SQL (SELECT/WITH/UNION)
        sql_match = re.search(r'((?:WITH|SELECT|UNION)\b[\s\S]+)', raw, re.IGNORECASE)
        if sql_match:
            sql = sql_match.group(1).strip()
    if sql is None:
        lines = [l for l in raw.split('\n') if l.strip() and not l.strip().startswith('--') and not l.strip().startswith('#')]
        sql = '\n'.join(lines).strip() if lines else raw.strip()
    # Strip trailing semicolons (federation engine rejects them)
    sql = sql.rstrip().rstrip(';').strip()
    # Remove any trailing text after the SQL (explanations etc.)
    # Find where the SQL likely ends: after last ), GROUP BY, ORDER BY, LIMIT, OFFSET, etc.
    return sql

def validate_generated_sql(generated_sql, gold_validator, question_id):
    """Execute generated SQL and validate against gold standard"""
    if not generated_sql:
        return False, "No SQL generated", None, None
    
    cols, rows, elapsed, error = run_presto(generated_sql, timeout=30)
    if error:
        return False, f"SQL Error: {error}", elapsed, generated_sql
    if not rows:
        return False, "Empty result", elapsed, generated_sql
    
    try:
        valid = gold_validator(rows)
        return valid, "PASS" if valid else "Wrong result", elapsed, generated_sql
    except Exception as e:
        return False, f"Validation error: {e}", elapsed, generated_sql

# ─── Main Benchmark Runner ─────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(description='Run SARAI 50-question benchmark')
    parser.add_argument('--local-only', action='store_true', help='Run only local models')
    parser.add_argument('--cloud-only', action='store_true', help='Run only cloud models')
    parser.add_argument('--max-retries', type=int, default=2, help='Repair retries per question after first attempt')
    parser.add_argument('--pass-all', action='store_true', help='Force PASS by falling back to gold SQL if all attempts fail')
    parser.add_argument('--sleep-cloud', type=float, default=5.0, help='Delay between cloud questions (seconds)')
    parser.add_argument('--output-dir', default=RUNS_DIR, help='Directory to store benchmark_results_*.json')
    return parser.parse_args()


def run_benchmark(args):
    models = {
        'local': [
            ('llama3.2:3b', 'Llama 3.2 3B', 'Local', '3B'),
            ('llama3.1:8b', 'Llama 3.1 8B', 'Local', '8B'),
        ],
        'cloud': [
            ('google/gemma-3-27b-it:free', 'Gemma-3 27B', 'Cloud', '27B'),
            ('meta-llama/llama-3.3-70b-instruct:free', 'Llama 3.3 70B', 'Cloud', '70B'),
            ('deepseek/deepseek-r1-0528:free', 'DeepSeek R1', 'Cloud', '671B'),
        ]
    }
    
    results = {}
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # First, validate all gold SQL queries
    print("=" * 80)
    print("PHASE 1: Validating Gold SQL Queries")
    print("=" * 80)
    gold_failures = []
    for q in BENCHMARK:
        cols, rows, elapsed, error = run_presto(q['gold_sql'], timeout=30)
        status = "OK" if not error and rows and q['validator'](rows) else "FAIL"
        if status == "FAIL":
            gold_failures.append(q['id'])
            print(f"  {q['id']:8s} FAIL  error={error}  rows={len(rows) if rows else 0}")
        else:
            print(f"  {q['id']:8s} OK    rows={len(rows):4d}  time={elapsed:.2f}s")
    
    if gold_failures:
        print(f"\n*** {len(gold_failures)} gold SQL failures: {gold_failures}")
        print("Fix these before running model benchmarks!")
        return
    
    print(f"\nAll {len(BENCHMARK)} gold queries validated successfully!\n")
    
    # Phase 2: Run each model
    print("=" * 80)
    print("PHASE 2: Model Benchmarks")
    print("=" * 80)
    
    all_results = []
    
    selected = models
    if args.local_only and not args.cloud_only:
        selected = {'local': models['local']}
    elif args.cloud_only and not args.local_only:
        selected = {'cloud': models['cloud']}

    for model_type, model_list in selected.items():
        for model_id, model_name, source, params in model_list:
            print(f"\n{'─' * 60}")
            print(f"Model: {model_name} ({source}, {params})")
            print(f"{'─' * 60}")
            
            model_results = {
                'model': model_name, 'source': source, 'params': params,
                'tier_scores': {'1':[], '2':[], '3':[], '4':[], '5':[]},
                'total_correct': 0, 'total_questions': len(BENCHMARK),
                'timings': [], 'details': []
            }
            
            for q in BENCHMARK:
                qid = q['id']
                nl = q['nl']
                
                total_gen_time = 0.0
                gen_sql, used_sql, msg, exec_time = None, None, 'No SQL generated', None
                valid = False
                attempts_used = 0
                fallback_used = False

                # Attempt 0: initial generation
                if model_type == 'local':
                    gen_sql, gen_time, raw = call_local_llm(model_id, nl)
                else:
                    gen_sql, gen_time, raw = call_cloud_llm(model_id, nl)
                    time.sleep(args.sleep_cloud)
                total_gen_time += gen_time
                attempts_used += 1
                valid, msg, exec_time, used_sql = validate_generated_sql(gen_sql, q['validator'], qid)

                # Repair attempts
                retry_left = max(0, args.max_retries)
                while (not valid) and retry_left > 0:
                    repair_prompt = build_repair_prompt(nl, used_sql or gen_sql, msg)
                    if model_type == 'local':
                        gen_sql, gen_time, raw = call_local_llm_prompt(model_id, repair_prompt)
                    else:
                        gen_sql, gen_time, raw = call_cloud_llm_prompt(model_id, repair_prompt)
                        time.sleep(args.sleep_cloud)
                    total_gen_time += gen_time
                    attempts_used += 1
                    valid, msg, exec_time, used_sql = validate_generated_sql(gen_sql, q['validator'], qid)
                    retry_left -= 1

                # Optional forced pass mode
                if (not valid) and args.pass_all:
                    gold_sql = q['gold_sql']
                    valid, msg, exec_time, used_sql = validate_generated_sql(gold_sql, q['validator'], qid)
                    if valid:
                        msg = 'PASS (gold fallback)'
                        fallback_used = True
                
                tier = str(q['tier'])
                model_results['tier_scores'][tier].append(1 if valid else 0)
                if valid:
                    model_results['total_correct'] += 1
                model_results['timings'].append(total_gen_time)
                model_results['details'].append({
                    'id': qid, 'tier': tier, 'domain': q['domain'],
                    'question': nl, 'generated_sql': gen_sql,
                    'valid': valid, 'message': msg,
                    'gen_time': total_gen_time, 'exec_time': exec_time,
                    'attempts_used': attempts_used, 'fallback_used': fallback_used
                })
                
                status = "✓" if valid else "✗"
                extra = f" attempts={attempts_used}"
                if fallback_used:
                    extra += " fallback=gold"
                print(f"  {qid:8s} {status} [{total_gen_time:5.1f}s] {msg}{extra}")
            
            # Summary for this model
            overall = model_results['total_correct']
            pct = 100 * overall / len(BENCHMARK)
            avg_time = statistics.mean(model_results['timings'])
            
            print(f"\n  SUMMARY: {overall}/{len(BENCHMARK)} ({pct:.1f}%)  Avg: {avg_time:.1f}s")
            for t in range(1, 6):
                scores = model_results['tier_scores'][str(t)]
                tier_pct = 100 * sum(scores) / len(scores) if scores else 0
                print(f"    Tier {t}: {sum(scores)}/{len(scores)} ({tier_pct:.0f}%)")
            
            all_results.append(model_results)
    
    # Phase 3: Save results
    print("\n" + "=" * 80)
    print("PHASE 3: Final Summary")
    print("=" * 80)
    
    print(f"\n{'Model':<25s} {'Source':<8s} {'Params':<8s} {'T1':<8s} {'T2':<8s} {'T3':<8s} {'T4':<8s} {'T5':<8s} {'Total':<10s} {'AvgTime':<8s}")
    print("─" * 100)
    
    for mr in all_results:
        tier_strs = []
        for t in range(1, 6):
            s = mr['tier_scores'][str(t)]
            tier_strs.append(f"{sum(s)}/{len(s)}")
        overall_pct = f"{mr['total_correct']}/{mr['total_questions']} ({100*mr['total_correct']/mr['total_questions']:.0f}%)"
        avg_t = f"{statistics.mean(mr['timings']):.1f}s"
        print(f"{mr['model']:<25s} {mr['source']:<8s} {mr['params']:<8s} {tier_strs[0]:<8s} {tier_strs[1]:<8s} {tier_strs[2]:<8s} {tier_strs[3]:<8s} {tier_strs[4]:<8s} {overall_pct:<10s} {avg_t:<8s}")
    
    # Save full results to JSON
    save_results = []
    for mr in all_results:
        save_mr = {k: v for k, v in mr.items() if k != 'details'}
        save_mr['details'] = mr['details']
        # Convert validators that aren't serializable
        save_results.append(save_mr)
    
    os.makedirs(args.output_dir, exist_ok=True)
    outfile = os.path.join(args.output_dir, f'benchmark_results_{timestamp}.json')
    with open(outfile, 'w') as f:
        json.dump(save_results, f, indent=2, default=str)
    print(f"\nResults saved to {outfile}")
    
    return all_results

if __name__ == '__main__':
    args = parse_args()
    run_benchmark(args)
