#!/usr/bin/env python3
"""
Load the real, already-exported per-table CSVs (raw_tables/) into the real
PostgreSQL (bcdr_framework_data) and MariaDB (bcdr_framework, single combined
database) infrastructure on THIS server, using the exact schema verified from
benchmark_50q.py's DDL. Adapts VARCHAR lengths and numeric precision per engine
since MariaDB requires explicit VARCHAR lengths and the fin_transactions PCA
columns need high floating-point precision, not plain DECIMAL(10,0).
"""
import os, csv, sys
import psycopg2
import mysql.connector

RAW = "/home/bcdr/phd/PhD/phd/papers/Project/datasets/raw_tables"

PG_CONN = dict(host=os.environ["POSTGRES_HOST"], port=5432,
               dbname=os.environ["POSTGRES_DB"],
               user=os.environ["POSTGRES_USER"],
               password=os.environ["POSTGRES_PASSWORD"])
MY_CONN = dict(host=os.environ["MARIADB_HOST"], port=3306,
               database=os.environ["MARIADB_DB"],
               user=os.environ["MARIADB_USER"],
               password=os.environ["MARIADB_PASSWORD"],
               allow_local_infile=True)

# ── PostgreSQL: 8 fact tables (public schema) ──────────────────────────────
PG_TABLES = {
    "olist_orders": """
        order_id VARCHAR, customer_id VARCHAR, order_status VARCHAR,
        order_purchase_timestamp TIMESTAMP, order_approved_at TIMESTAMP,
        order_delivered_carrier_date TIMESTAMP, order_delivered_customer_date TIMESTAMP,
        order_estimated_delivery_date TIMESTAMP""",
    "olist_order_items": """
        order_id VARCHAR, order_item_id INTEGER, product_id VARCHAR, seller_id VARCHAR,
        shipping_limit_date TIMESTAMP, price DECIMAL(12,2), freight_value DECIMAL(12,2)""",
    "olist_order_payments": """
        order_id VARCHAR, payment_sequential INTEGER, payment_type VARCHAR,
        payment_installments INTEGER, payment_value DECIMAL(12,2)""",
    "olist_order_reviews": """
        review_id VARCHAR, order_id VARCHAR, review_score INTEGER,
        review_comment_title VARCHAR, review_comment_message VARCHAR,
        review_creation_date TIMESTAMP, review_answer_timestamp TIMESTAMP""",
    "hc_admissions": """
        admission_id INTEGER, patient_name VARCHAR, age INTEGER, gender VARCHAR,
        blood_type VARCHAR, condition_id INTEGER, doctor_id INTEGER, hospital_id INTEGER,
        insurance_id INTEGER, billing_amount DECIMAL(12,2), room_number INTEGER,
        admission_type VARCHAR, date_of_admission DATE, discharge_date DATE,
        medication VARCHAR, test_results VARCHAR""",
    "rt_invoices": """
        invoice_id INTEGER, invoice_no VARCHAR(20), stock_code VARCHAR(20),
        quantity INTEGER, invoice_date TIMESTAMP, unit_price DECIMAL(10,4),
        customer_id VARCHAR(20)""",
    "fin_transactions": """
        transaction_id INTEGER, time_elapsed DOUBLE PRECISION,
        v1 DOUBLE PRECISION, v2 DOUBLE PRECISION, v3 DOUBLE PRECISION, v4 DOUBLE PRECISION,
        v5 DOUBLE PRECISION, v6 DOUBLE PRECISION, v7 DOUBLE PRECISION, v8 DOUBLE PRECISION,
        v9 DOUBLE PRECISION, v10 DOUBLE PRECISION, v11 DOUBLE PRECISION, v12 DOUBLE PRECISION,
        v13 DOUBLE PRECISION, v14 DOUBLE PRECISION, v15 DOUBLE PRECISION, v16 DOUBLE PRECISION,
        v17 DOUBLE PRECISION, v18 DOUBLE PRECISION, v19 DOUBLE PRECISION, v20 DOUBLE PRECISION,
        v21 DOUBLE PRECISION, v22 DOUBLE PRECISION, v23 DOUBLE PRECISION, v24 DOUBLE PRECISION,
        v25 DOUBLE PRECISION, v26 DOUBLE PRECISION, v27 DOUBLE PRECISION, v28 DOUBLE PRECISION,
        amount DOUBLE PRECISION, class_id INTEGER, time_hour INTEGER""",
    "sc_orders": """
        order_row_id INTEGER, order_id INTEGER, order_item_id INTEGER,
        order_date VARCHAR(30), shipping_date VARCHAR(30), type VARCHAR(20),
        days_shipping_real INTEGER, days_shipment_scheduled INTEGER,
        delivery_status VARCHAR, late_delivery_risk INTEGER, customer_id INTEGER,
        product_id INTEGER, department_id INTEGER, category_id INTEGER,
        order_item_quantity INTEGER, order_item_discount DECIMAL(12,4),
        order_item_discount_rate DECIMAL(12,4), order_item_product_price DECIMAL(12,4),
        sales DECIMAL(12,4), order_item_total DECIMAL(12,4), order_profit DECIMAL(12,4),
        benefit_per_order DECIMAL(12,4), sales_per_customer DECIMAL(12,4),
        shipping_mode VARCHAR, market VARCHAR, order_city VARCHAR, order_country VARCHAR,
        order_region VARCHAR, order_state VARCHAR""",
}
PG_CSV_DIR = os.path.join(RAW, "postgresql", "public")

# ── MariaDB: 17 dimension tables, single combined database ────────────────
MY_TABLES = {
    "olist_customers": """
        customer_id VARCHAR(64), customer_unique_id VARCHAR(64),
        customer_zip_code_prefix VARCHAR(10), customer_city VARCHAR(128),
        customer_state VARCHAR(4)""",
    "olist_products": """
        product_id VARCHAR(64), product_category_name VARCHAR(128),
        product_name_lenght INTEGER, product_description_lenght INTEGER,
        product_photos_qty INTEGER, product_weight_g INTEGER,
        product_length_cm INTEGER, product_height_cm INTEGER, product_width_cm INTEGER""",
    "olist_sellers": """
        seller_id VARCHAR(64), seller_zip_code_prefix VARCHAR(10),
        seller_city VARCHAR(128), seller_state VARCHAR(4)""",
    "olist_geolocation": """
        geolocation_zip_code_prefix INTEGER, geolocation_lat DOUBLE, geolocation_lng DOUBLE,
        geolocation_city VARCHAR(128), geolocation_state VARCHAR(4)""",
    "product_category_translation": """
        product_category_name VARCHAR(128), product_category_name_english VARCHAR(128)""",
    "hc_conditions": "condition_id INTEGER, condition_name VARCHAR(128)",
    "hc_insurance": "insurance_id INTEGER, provider_name VARCHAR(128)",
    "hc_hospitals": "hospital_id INTEGER, hospital_name VARCHAR(128)",
    "hc_doctors": "doctor_id INTEGER, doctor_name VARCHAR(128)",
    "rt_customers": "customer_id VARCHAR(20), country VARCHAR(50)",
    "rt_products": "stock_code VARCHAR(20), description VARCHAR(255)",
    "fin_fraud_classes": "class_id INTEGER, class_name VARCHAR(64), description VARCHAR(255)",
    "fin_time_buckets": """
        bucket_id INTEGER, bucket_name VARCHAR(64), hour_start INTEGER,
        hour_end INTEGER, description VARCHAR(255)""",
    "sc_customers": """
        customer_id INTEGER, first_name VARCHAR(64), last_name VARCHAR(64),
        email VARCHAR(128), segment VARCHAR(64), city VARCHAR(128),
        country VARCHAR(64), state VARCHAR(64), zipcode VARCHAR(20)""",
    "sc_products": """
        product_id INTEGER, product_name VARCHAR(255), product_price DECIMAL(12,2),
        category_id INTEGER, product_status INTEGER""",
    "sc_departments": "department_id INTEGER, department_name VARCHAR(128)",
    "sc_categories": "category_id INTEGER, category_name VARCHAR(128)",
}
MY_CSV_DIRS = {
    "olist_customers": "olist_ecommerce", "olist_products": "olist_ecommerce",
    "olist_sellers": "olist_ecommerce", "olist_geolocation": "olist_ecommerce",
    "product_category_translation": "olist_ecommerce",
    "hc_conditions": "healthcare", "hc_insurance": "healthcare",
    "hc_hospitals": "healthcare", "hc_doctors": "healthcare",
    "rt_customers": "retail", "rt_products": "retail",
    "fin_fraud_classes": "financial", "fin_time_buckets": "financial",
    "sc_customers": "supply_chain", "sc_products": "supply_chain",
    "sc_departments": "supply_chain", "sc_categories": "supply_chain",
}


def load_postgres():
    conn = psycopg2.connect(**PG_CONN)
    conn.autocommit = True
    cur = conn.cursor()
    for table, cols in PG_TABLES.items():
        csv_path = os.path.join(PG_CSV_DIR, f"{table}.csv")
        if not os.path.exists(csv_path):
            print(f"  [PG] SKIP {table}: {csv_path} not found")
            continue
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute(f"CREATE TABLE {table} ({cols})")
        with open(csv_path) as f:
            cur.copy_expert(f"COPY {table} FROM STDIN WITH CSV HEADER", f)
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        n = cur.fetchone()[0]
        print(f"  [PG] {table}: {n} rows loaded")
    conn.close()


def load_mariadb():
    conn = mysql.connector.connect(**MY_CONN)
    cur = conn.cursor()
    for table, cols in MY_TABLES.items():
        domain = MY_CSV_DIRS[table]
        csv_path = os.path.join(RAW, "mysql", domain, f"{table}.csv")
        if not os.path.exists(csv_path):
            print(f"  [MY] SKIP {table}: {csv_path} not found")
            continue
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute(f"CREATE TABLE {table} ({cols})")
        cur.execute(
            f"LOAD DATA LOCAL INFILE %s INTO TABLE {table} "
            f"FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '\"' "
            f"LINES TERMINATED BY '\\n' IGNORE 1 LINES",
            (csv_path,)
        )
        conn.commit()
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        n = cur.fetchone()[0]
        print(f"  [MY] {table}: {n} rows loaded")
    conn.close()


if __name__ == "__main__":
    print("=== Loading PostgreSQL (8 fact tables) ===")
    load_postgres()
    print("\n=== Loading MariaDB (17 dimension tables, single database) ===")
    load_mariadb()
    print("\nDone.")
