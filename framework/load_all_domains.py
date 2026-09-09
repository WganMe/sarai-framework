#!/usr/bin/env python3
"""Load 4 domain datasets into PostgreSQL (facts) and MariaDB (dimensions)."""

import csv
import psycopg2
import mysql.connector
import os

PG_CONN = dict(host=os.environ.get('POSTGRES_HOST', '127.0.0.1'), port=5432,
               dbname=os.environ.get('POSTGRES_DB', os.environ.get('POSTGRES_DB_FRAMEWORK', 'framework_data')),
               user=os.environ.get('POSTGRES_USER', 'framework'),
               password=os.environ.get('POSTGRES_PASSWORD', ''))
MY_CONN = dict(host=os.environ.get('MARIADB_HOST', '127.0.0.1'), port=3306,
               user=os.environ.get('MARIADB_USER', 'framework'),
               password=os.environ.get('MARIADB_PASSWORD', ''))
# Single combined MariaDB database holding all domain tables (table names are
# already domain-prefixed: hc_, fin_, rt_, sc_, olist_ - no collisions).
MARIADB_DB = os.environ.get('MARIADB_DB', 'framework')

BASE = '/var/www/datasets'

def pg_execute(sql, data=None):
    conn = psycopg2.connect(**PG_CONN)
    conn.autocommit = True
    cur = conn.cursor()
    if data:
        cur.executemany(sql, data)
    else:
        cur.execute(sql)
    conn.close()

def pg_query(sql):
    conn = psycopg2.connect(**PG_CONN)
    cur = conn.cursor()
    cur.execute(sql)
    result = cur.fetchall()
    conn.close()
    return result

def my_execute(db, sql, data=None):
    # `db` (domain name) is kept as a parameter for call-site clarity/logging
    # only; all domains share one real MariaDB database (MARIADB_DB).
    conn = mysql.connector.connect(database=MARIADB_DB, **MY_CONN)
    cur = conn.cursor()
    if data:
        cur.executemany(sql, data)
    else:
        cur.execute(sql)
    conn.commit()
    conn.close()

def read_csv(path, encoding='utf-8'):
    with open(path, 'r', encoding=encoding, errors='replace') as f:
        reader = csv.DictReader(f)
        return list(reader)

def safe_float(v, default=0.0):
    try:
        return float(v) if v and v.strip() else default
    except:
        return default

def safe_int(v, default=0):
    try:
        return int(float(v)) if v and v.strip() else default
    except:
        return default

# ========================================================================
# DOMAIN 1: HEALTHCARE
# ========================================================================
def load_healthcare():
    print("\n" + "="*60)
    print("LOADING HEALTHCARE DOMAIN")
    print("="*60)
    
    rows = read_csv(os.path.join(BASE, 'healthcare/healthcare_dataset.csv'))
    print(f"  Read {len(rows)} rows")
    
    # Extract dimensions
    doctors = sorted(set(r['Doctor'] for r in rows if r.get('Doctor')))
    hospitals = sorted(set(r['Hospital'] for r in rows if r.get('Hospital')))
    insurances = sorted(set(r['Insurance Provider'] for r in rows if r.get('Insurance Provider')))
    conditions = sorted(set(r['Medical Condition'] for r in rows if r.get('Medical Condition')))
    
    doctor_map = {name: i+1 for i, name in enumerate(doctors)}
    hospital_map = {name: i+1 for i, name in enumerate(hospitals)}
    insurance_map = {name: i+1 for i, name in enumerate(insurances)}
    condition_map = {name: i+1 for i, name in enumerate(conditions)}
    
    # MariaDB dimension tables
    my_execute('healthcare', "DROP TABLE IF EXISTS hc_doctors")
    my_execute('healthcare', """CREATE TABLE hc_doctors (
        doctor_id INT PRIMARY KEY, doctor_name VARCHAR(100))""")
    my_execute('healthcare', "INSERT INTO hc_doctors VALUES (%s, %s)",
               [(v, k) for k, v in doctor_map.items()])
    print(f"  MariaDB hc_doctors: {len(doctors)} rows")
    
    my_execute('healthcare', "DROP TABLE IF EXISTS hc_hospitals")
    my_execute('healthcare', """CREATE TABLE hc_hospitals (
        hospital_id INT PRIMARY KEY, hospital_name VARCHAR(200))""")
    my_execute('healthcare', "INSERT INTO hc_hospitals VALUES (%s, %s)",
               [(v, k) for k, v in hospital_map.items()])
    print(f"  MariaDB hc_hospitals: {len(hospitals)} rows")
    
    my_execute('healthcare', "DROP TABLE IF EXISTS hc_insurance")
    my_execute('healthcare', """CREATE TABLE hc_insurance (
        insurance_id INT PRIMARY KEY, provider_name VARCHAR(100))""")
    my_execute('healthcare', "INSERT INTO hc_insurance VALUES (%s, %s)",
               [(v, k) for k, v in insurance_map.items()])
    print(f"  MariaDB hc_insurance: {len(insurances)} rows")
    
    my_execute('healthcare', "DROP TABLE IF EXISTS hc_conditions")
    my_execute('healthcare', """CREATE TABLE hc_conditions (
        condition_id INT PRIMARY KEY, condition_name VARCHAR(100))""")
    my_execute('healthcare', "INSERT INTO hc_conditions VALUES (%s, %s)",
               [(v, k) for k, v in condition_map.items()])
    print(f"  MariaDB hc_conditions: {len(conditions)} rows")
    
    # PostgreSQL fact table
    pg_execute("DROP TABLE IF EXISTS hc_admissions")
    pg_execute("""CREATE TABLE hc_admissions (
        admission_id SERIAL PRIMARY KEY,
        patient_name VARCHAR(100),
        age INT,
        gender VARCHAR(10),
        blood_type VARCHAR(5),
        condition_id INT,
        doctor_id INT,
        hospital_id INT,
        insurance_id INT,
        billing_amount DECIMAL(12,2),
        room_number INT,
        admission_type VARCHAR(20),
        date_of_admission DATE,
        discharge_date DATE,
        medication VARCHAR(50),
        test_results VARCHAR(20)
    )""")
    
    batch = []
    for r in rows:
        batch.append((
            r.get('Name',''), safe_int(r.get('Age',0)), r.get('Gender',''),
            r.get('Blood Type',''), condition_map.get(r.get('Medical Condition',''), 0),
            doctor_map.get(r.get('Doctor',''), 0), hospital_map.get(r.get('Hospital',''), 0),
            insurance_map.get(r.get('Insurance Provider',''), 0),
            safe_float(r.get('Billing Amount',0)), safe_int(r.get('Room Number',0)),
            r.get('Admission Type',''),
            r.get('Date of Admission','') or None, r.get('Discharge Date','') or None,
            r.get('Medication',''), r.get('Test Results','')
        ))
    
    conn = psycopg2.connect(**PG_CONN)
    conn.autocommit = True
    cur = conn.cursor()
    from psycopg2.extras import execute_batch
    execute_batch(cur, """INSERT INTO hc_admissions 
        (patient_name, age, gender, blood_type, condition_id, doctor_id, hospital_id,
         insurance_id, billing_amount, room_number, admission_type, date_of_admission,
         discharge_date, medication, test_results)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", batch, page_size=5000)
    conn.close()
    
    count = pg_query("SELECT count(*) FROM hc_admissions")[0][0]
    print(f"  PostgreSQL hc_admissions: {count} rows")


# ========================================================================
# DOMAIN 2: RETAIL (Online Retail / E-Commerce UK)
# ========================================================================
def load_retail():
    print("\n" + "="*60)
    print("LOADING RETAIL DOMAIN")
    print("="*60)
    
    rows = read_csv(os.path.join(BASE, 'retail/data.csv'), encoding='latin-1')
    print(f"  Read {len(rows)} rows")
    
    # Extract dimensions
    products = {}
    customers = {}
    for r in rows:
        sc = r.get('StockCode','').strip()
        desc = r.get('Description','').strip()
        if sc and sc not in products:
            products[sc] = desc
        cid = r.get('CustomerID','').strip()
        country = r.get('Country','').strip()
        if cid and cid not in customers:
            customers[cid] = country
    
    # MariaDB dimension tables
    my_execute('retail', "DROP TABLE IF EXISTS rt_products")
    my_execute('retail', """CREATE TABLE rt_products (
        stock_code VARCHAR(20) PRIMARY KEY, description VARCHAR(255))""")
    prod_data = [(k, v[:255]) for k, v in products.items()]
    # batch insert in chunks — use IGNORE for case-insensitive dupes
    for i in range(0, len(prod_data), 5000):
        my_execute('retail', "INSERT IGNORE INTO rt_products VALUES (%s, %s)", prod_data[i:i+5000])
    print(f"  MariaDB rt_products: {len(products)} rows")
    
    my_execute('retail', "DROP TABLE IF EXISTS rt_customers")
    my_execute('retail', """CREATE TABLE rt_customers (
        customer_id VARCHAR(20) PRIMARY KEY, country VARCHAR(50))""")
    cust_data = [(k, v) for k, v in customers.items()]
    my_execute('retail', "INSERT INTO rt_customers VALUES (%s, %s)", cust_data)
    print(f"  MariaDB rt_customers: {len(customers)} rows")
    
    # PostgreSQL fact table
    pg_execute("DROP TABLE IF EXISTS rt_invoices")
    pg_execute("""CREATE TABLE rt_invoices (
        invoice_id SERIAL PRIMARY KEY,
        invoice_no VARCHAR(20),
        stock_code VARCHAR(20),
        quantity INT,
        invoice_date TIMESTAMP,
        unit_price DECIMAL(10,4),
        customer_id VARCHAR(20)
    )""")
    
    batch = []
    for r in rows:
        inv_date = r.get('InvoiceDate','').strip() or None
        batch.append((
            r.get('InvoiceNo','').strip(),
            r.get('StockCode','').strip(),
            safe_int(r.get('Quantity',0)),
            inv_date,
            safe_float(r.get('UnitPrice',0)),
            r.get('CustomerID','').strip() or None
        ))
    
    conn = psycopg2.connect(**PG_CONN)
    conn.autocommit = True
    cur = conn.cursor()
    from psycopg2.extras import execute_batch
    execute_batch(cur, """INSERT INTO rt_invoices (invoice_no, stock_code, quantity, invoice_date, unit_price, customer_id)
        VALUES (%s,%s,%s,%s,%s,%s)""", batch, page_size=5000)
    conn.close()
    
    count = pg_query("SELECT count(*) FROM rt_invoices")[0][0]
    print(f"  PostgreSQL rt_invoices: {count} rows")


# ========================================================================
# DOMAIN 3: FINANCIAL (Credit Card Fraud Detection)
# ========================================================================
def load_financial():
    print("\n" + "="*60)
    print("LOADING FINANCIAL DOMAIN")
    print("="*60)
    
    rows = read_csv(os.path.join(BASE, 'financial/creditcard.csv'))
    print(f"  Read {len(rows)} rows")
    
    # MariaDB dimension table — fraud classification reference
    my_execute('financial', "DROP TABLE IF EXISTS fin_fraud_classes")
    my_execute('financial', """CREATE TABLE fin_fraud_classes (
        class_id INT PRIMARY KEY,
        class_name VARCHAR(20),
        description VARCHAR(200))""")
    my_execute('financial', "INSERT INTO fin_fraud_classes VALUES (%s, %s, %s)", [
        (0, 'Legitimate', 'Normal credit card transaction - no fraud detected'),
        (1, 'Fraudulent', 'Confirmed fraudulent credit card transaction')
    ])
    print(f"  MariaDB fin_fraud_classes: 2 rows")
    
    # Also create a time-bucket dimension for temporal analysis
    my_execute('financial', "DROP TABLE IF EXISTS fin_time_buckets")
    my_execute('financial', """CREATE TABLE fin_time_buckets (
        bucket_id INT PRIMARY KEY,
        bucket_name VARCHAR(30),
        hour_start INT,
        hour_end INT,
        description VARCHAR(100))""")
    my_execute('financial', "INSERT INTO fin_time_buckets VALUES (%s, %s, %s, %s, %s)", [
        (1, 'Night', 0, 6, 'Late night/early morning (12AM-6AM)'),
        (2, 'Morning', 6, 12, 'Morning hours (6AM-12PM)'),
        (3, 'Afternoon', 12, 18, 'Afternoon hours (12PM-6PM)'),
        (4, 'Evening', 18, 24, 'Evening hours (6PM-12AM)')
    ])
    print(f"  MariaDB fin_time_buckets: 4 rows")
    
    # PostgreSQL fact table — transactions with PCA components
    pg_execute("DROP TABLE IF EXISTS fin_transactions")
    pg_execute("""CREATE TABLE fin_transactions (
        transaction_id SERIAL PRIMARY KEY,
        time_elapsed DECIMAL(12,2),
        v1 DECIMAL(20,15), v2 DECIMAL(20,15), v3 DECIMAL(20,15), v4 DECIMAL(20,15),
        v5 DECIMAL(20,15), v6 DECIMAL(20,15), v7 DECIMAL(20,15), v8 DECIMAL(20,15),
        v9 DECIMAL(20,15), v10 DECIMAL(20,15), v11 DECIMAL(20,15), v12 DECIMAL(20,15),
        v13 DECIMAL(20,15), v14 DECIMAL(20,15), v15 DECIMAL(20,15), v16 DECIMAL(20,15),
        v17 DECIMAL(20,15), v18 DECIMAL(20,15), v19 DECIMAL(20,15), v20 DECIMAL(20,15),
        v21 DECIMAL(20,15), v22 DECIMAL(20,15), v23 DECIMAL(20,15), v24 DECIMAL(20,15),
        v25 DECIMAL(20,15), v26 DECIMAL(20,15), v27 DECIMAL(20,15), v28 DECIMAL(20,15),
        amount DECIMAL(12,2),
        class_id INT,
        time_hour INT
    )""")
    
    batch = []
    for r in rows:
        time_val = safe_float(r.get('Time', 0))
        hour = int((time_val % 86400) / 3600)  # seconds to hour of day
        vals = [safe_float(r.get(f'V{i}', 0)) for i in range(1, 29)]
        batch.append((
            time_val, *vals,
            safe_float(r.get('Amount', 0)),
            safe_int(r.get('Class', 0)),
            hour
        ))
    
    conn = psycopg2.connect(**PG_CONN)
    conn.autocommit = True
    cur = conn.cursor()
    from psycopg2.extras import execute_batch
    placeholders = ','.join(['%s'] * 32)
    execute_batch(cur, f"""INSERT INTO fin_transactions 
        (time_elapsed, v1,v2,v3,v4,v5,v6,v7,v8,v9,v10,v11,v12,v13,v14,v15,v16,v17,v18,v19,v20,v21,v22,v23,v24,v25,v26,v27,v28,
         amount, class_id, time_hour)
        VALUES ({placeholders})""", batch, page_size=5000)
    conn.close()
    
    count = pg_query("SELECT count(*) FROM fin_transactions")[0][0]
    print(f"  PostgreSQL fin_transactions: {count} rows")


# ========================================================================
# DOMAIN 4: SUPPLY CHAIN
# ========================================================================
def load_supply_chain():
    print("\n" + "="*60)
    print("LOADING SUPPLY CHAIN DOMAIN")
    print("="*60)
    
    rows = read_csv(os.path.join(BASE, 'supply_chain/DataCoSupplyChainDataset.csv'), encoding='latin-1')
    print(f"  Read {len(rows)} rows")
    
    # Extract dimensions
    customers = {}
    products = {}
    departments = {}
    categories = {}
    
    for r in rows:
        cid = safe_int(r.get('Customer Id', 0))
        if cid and cid not in customers:
            customers[cid] = {
                'fname': r.get('Customer Fname', ''),
                'lname': r.get('Customer Lname', ''),
                'email': r.get('Customer Email', ''),
                'segment': r.get('Customer Segment', ''),
                'city': r.get('Customer City', ''),
                'country': r.get('Customer Country', ''),
                'state': r.get('Customer State', ''),
                'zipcode': r.get('Customer Zipcode', '')
            }
        
        pid = safe_int(r.get('Product Card Id', 0))
        if pid and pid not in products:
            products[pid] = {
                'name': r.get('Product Name', ''),
                'price': safe_float(r.get('Product Price', 0)),
                'category_id': safe_int(r.get('Product Category Id', 0)),
                'status': safe_int(r.get('Product Status', 0)),
                'description': (r.get('Product Description', '') or '')[:255]
            }
        
        did = safe_int(r.get('Department Id', 0))
        if did and did not in departments:
            departments[did] = r.get('Department Name', '')
        
        catid = safe_int(r.get('Category Id', 0))
        if catid and catid not in categories:
            categories[catid] = r.get('Category Name', '')
    
    # MariaDB dimension tables
    my_execute('supply_chain', "DROP TABLE IF EXISTS sc_customers")
    my_execute('supply_chain', """CREATE TABLE sc_customers (
        customer_id INT PRIMARY KEY,
        first_name VARCHAR(50), last_name VARCHAR(50),
        email VARCHAR(100), segment VARCHAR(30),
        city VARCHAR(50), country VARCHAR(50),
        state VARCHAR(50), zipcode VARCHAR(20))""")
    cust_data = [(cid, c['fname'], c['lname'], c['email'], c['segment'],
                  c['city'], c['country'], c['state'], c['zipcode'])
                 for cid, c in customers.items()]
    for i in range(0, len(cust_data), 5000):
        my_execute('supply_chain', "INSERT INTO sc_customers VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                   cust_data[i:i+5000])
    print(f"  MariaDB sc_customers: {len(customers)} rows")
    
    my_execute('supply_chain', "DROP TABLE IF EXISTS sc_products")
    my_execute('supply_chain', """CREATE TABLE sc_products (
        product_id INT PRIMARY KEY,
        product_name VARCHAR(200), product_price DECIMAL(10,2),
        category_id INT, product_status INT)""")
    prod_data = [(pid, p['name'][:200], p['price'], p['category_id'], p['status'])
                 for pid, p in products.items()]
    my_execute('supply_chain', "INSERT INTO sc_products VALUES (%s,%s,%s,%s,%s)", prod_data)
    print(f"  MariaDB sc_products: {len(products)} rows")
    
    my_execute('supply_chain', "DROP TABLE IF EXISTS sc_departments")
    my_execute('supply_chain', """CREATE TABLE sc_departments (
        department_id INT PRIMARY KEY, department_name VARCHAR(50))""")
    my_execute('supply_chain', "INSERT INTO sc_departments VALUES (%s, %s)",
               [(k, v) for k, v in departments.items()])
    print(f"  MariaDB sc_departments: {len(departments)} rows")
    
    my_execute('supply_chain', "DROP TABLE IF EXISTS sc_categories")
    my_execute('supply_chain', """CREATE TABLE sc_categories (
        category_id INT PRIMARY KEY, category_name VARCHAR(50))""")
    my_execute('supply_chain', "INSERT INTO sc_categories VALUES (%s, %s)",
               [(k, v) for k, v in categories.items()])
    print(f"  MariaDB sc_categories: {len(categories)} rows")
    
    # PostgreSQL fact table
    pg_execute("DROP TABLE IF EXISTS sc_orders")
    pg_execute("""CREATE TABLE sc_orders (
        order_row_id SERIAL PRIMARY KEY,
        order_id INT,
        order_item_id INT,
        order_date VARCHAR(30),
        shipping_date VARCHAR(30),
        type VARCHAR(20),
        days_shipping_real INT,
        days_shipment_scheduled INT,
        delivery_status VARCHAR(30),
        late_delivery_risk INT,
        customer_id INT,
        product_id INT,
        department_id INT,
        category_id INT,
        order_item_quantity INT,
        order_item_discount DECIMAL(10,2),
        order_item_discount_rate DECIMAL(5,2),
        order_item_product_price DECIMAL(10,2),
        sales DECIMAL(12,2),
        order_item_total DECIMAL(12,2),
        order_profit DECIMAL(12,2),
        benefit_per_order DECIMAL(12,2),
        sales_per_customer DECIMAL(12,2),
        shipping_mode VARCHAR(30),
        market VARCHAR(30),
        order_city VARCHAR(50),
        order_country VARCHAR(50),
        order_region VARCHAR(50),
        order_state VARCHAR(50)
    )""")
    
    batch = []
    for r in rows:
        batch.append((
            safe_int(r.get('Order Id', 0)),
            safe_int(r.get('Order Item Id', 0)),
            r.get('order date (DateOrders)', ''),
            r.get('shipping date (DateOrders)', ''),
            r.get('Type', ''),
            safe_int(r.get('Days for shipping (real)', 0)),
            safe_int(r.get('Days for shipment (scheduled)', 0)),
            r.get('Delivery Status', ''),
            safe_int(r.get('Late_delivery_risk', 0)),
            safe_int(r.get('Customer Id', 0)),
            safe_int(r.get('Product Card Id', 0)),
            safe_int(r.get('Department Id', 0)),
            safe_int(r.get('Category Id', 0)),
            safe_int(r.get('Order Item Quantity', 0)),
            safe_float(r.get('Order Item Discount', 0)),
            safe_float(r.get('Order Item Discount Rate', 0)),
            safe_float(r.get('Order Item Product Price', 0)),
            safe_float(r.get('Sales', 0)),
            safe_float(r.get('Order Item Total', 0)),
            safe_float(r.get('Order Profit Per Order', 0)),
            safe_float(r.get('Benefit per order', 0)),
            safe_float(r.get('Sales per customer', 0)),
            r.get('Shipping Mode', ''),
            r.get('Market', ''),
            r.get('Order City', ''),
            r.get('Order Country', ''),
            r.get('Order Region', ''),
            r.get('Order State', '')
        ))
    
    conn = psycopg2.connect(**PG_CONN)
    conn.autocommit = True
    cur = conn.cursor()
    from psycopg2.extras import execute_batch
    execute_batch(cur, """INSERT INTO sc_orders 
        (order_id, order_item_id, order_date, shipping_date, type,
         days_shipping_real, days_shipment_scheduled, delivery_status, late_delivery_risk,
         customer_id, product_id, department_id, category_id,
         order_item_quantity, order_item_discount, order_item_discount_rate,
         order_item_product_price, sales, order_item_total, order_profit,
         benefit_per_order, sales_per_customer, shipping_mode, market,
         order_city, order_country, order_region, order_state)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        batch, page_size=5000)
    conn.close()
    
    count = pg_query("SELECT count(*) FROM sc_orders")[0][0]
    print(f"  PostgreSQL sc_orders: {count} rows")


# ========================================================================
# MAIN
# ========================================================================
if __name__ == '__main__':
    print("Multi-Domain Dataset Loader")
    print("PostgreSQL: facts | MariaDB: dimensions")
    
    load_healthcare()
    load_retail()
    load_financial()
    load_supply_chain()
    
    print("\n" + "="*60)
    print("ALL DOMAINS LOADED SUCCESSFULLY")
    print("="*60)
    
    # Summary
    pg_tables = pg_query("""SELECT tablename FROM pg_tables 
        WHERE schemaname='public' ORDER BY tablename""")
    print(f"\nPostgreSQL tables: {[t[0] for t in pg_tables]}")
    
    conn = mysql.connector.connect(database=MARIADB_DB, **MY_CONN)
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    tables = [t[0] for t in cur.fetchall()]
    conn.close()
    print(f"MariaDB {MARIADB_DB}: {tables}")
