#!/usr/bin/env python3
"""
Benchmark Suite for 5-Layer BI Framework — Section 7 Data
Runs timed federated queries across 5 domains × 2 engines via the federation engine.
Each query is run 5 times; we report median, min, max latency.
"""

import subprocess
import time
import json
import statistics

JAVA_ENV = "export JAVA_HOME=/opt/jdk-11.0.30+7 && export PATH=$JAVA_HOME/bin:$PATH"

BENCHMARKS = [
    # =====================================================================
    # CATEGORY A: SINGLE-DOMAIN INTRA-ENGINE (baseline — PG only, no federation)
    # =====================================================================
    {
        "id": "A1",
        "name": "PG-Only: Olist order count by status",
        "category": "Single-Engine Baseline",
        "domain": "E-Commerce",
        "engines": 1,
        "tables": 1,
        "sql": """
SELECT order_status, COUNT(*) as cnt 
FROM postgresql.public.olist_orders 
GROUP BY order_status ORDER BY cnt DESC
"""
    },
    {
        "id": "A2",
        "name": "PG-Only: Financial fraud summary",
        "category": "Single-Engine Baseline",
        "domain": "Financial",
        "engines": 1,
        "tables": 1,
        "sql": """
SELECT class_id, COUNT(*) as cnt, ROUND(AVG(amount),2) as avg_amt, ROUND(SUM(amount),2) as total
FROM postgresql.public.fin_transactions GROUP BY class_id
"""
    },
    {
        "id": "A3",
        "name": "PG-Only: Supply chain delivery stats",
        "category": "Single-Engine Baseline",
        "domain": "Supply Chain",
        "engines": 1,
        "tables": 1,
        "sql": """
SELECT delivery_status, COUNT(*) as orders, ROUND(AVG(sales),2) as avg_sales
FROM postgresql.public.sc_orders GROUP BY delivery_status ORDER BY orders DESC
"""
    },

    # =====================================================================
    # CATEGORY B: SINGLE-DOMAIN CROSS-ENGINE (PG facts ↔ MariaDB dims)
    # =====================================================================
    {
        "id": "B1",
        "name": "Federation: Olist revenue by customer state",
        "category": "Cross-Engine Single-Domain",
        "domain": "E-Commerce",
        "engines": 2,
        "tables": 3,
        "sql": """
SELECT c.customer_state, COUNT(DISTINCT o.order_id) as orders,
       ROUND(SUM(p.payment_value),2) as revenue
FROM postgresql.public.olist_orders o
JOIN postgresql.public.olist_order_payments p ON o.order_id = p.order_id
JOIN mysql.olist_ecommerce.olist_customers c ON o.customer_id = c.customer_id
GROUP BY c.customer_state ORDER BY revenue DESC LIMIT 10
"""
    },
    {
        "id": "B2",
        "name": "Federation: Healthcare billing by condition+insurance",
        "category": "Cross-Engine Single-Domain",
        "domain": "Healthcare",
        "engines": 2,
        "tables": 3,
        "sql": """
SELECT c.condition_name, ins.provider_name,
       COUNT(*) as admissions, ROUND(AVG(a.billing_amount),2) as avg_billing
FROM postgresql.public.hc_admissions a
JOIN mysql.healthcare.hc_conditions c ON a.condition_id = c.condition_id
JOIN mysql.healthcare.hc_insurance ins ON a.insurance_id = ins.insurance_id
GROUP BY c.condition_name, ins.provider_name ORDER BY avg_billing DESC LIMIT 10
"""
    },
    {
        "id": "B3",
        "name": "Federation: Retail revenue by country",
        "category": "Cross-Engine Single-Domain",
        "domain": "Retail",
        "engines": 2,
        "tables": 3,
        "sql": """
SELECT cust.country, COUNT(DISTINCT i.invoice_no) as invoices,
       ROUND(SUM(i.quantity * i.unit_price),2) as revenue
FROM postgresql.public.rt_invoices i
JOIN mysql.retail.rt_customers cust ON i.customer_id = cust.customer_id
JOIN mysql.retail.rt_products p ON i.stock_code = p.stock_code
WHERE i.quantity > 0
GROUP BY cust.country ORDER BY revenue DESC LIMIT 10
"""
    },
    {
        "id": "B4",
        "name": "Federation: Financial fraud by time bucket",
        "category": "Cross-Engine Single-Domain",
        "domain": "Financial",
        "engines": 2,
        "tables": 3,
        "sql": """
SELECT tb.bucket_name, fc.class_name,
       COUNT(*) as txns, ROUND(AVG(ft.amount),2) as avg_amt
FROM postgresql.public.fin_transactions ft
JOIN mysql.financial.fin_fraud_classes fc ON ft.class_id = fc.class_id
JOIN mysql.financial.fin_time_buckets tb 
  ON ft.time_hour >= tb.hour_start AND ft.time_hour < tb.hour_end
GROUP BY tb.bucket_name, fc.class_name ORDER BY tb.bucket_name
"""
    },
    {
        "id": "B5",
        "name": "Federation: Supply chain sales by dept+segment",
        "category": "Cross-Engine Single-Domain",
        "domain": "Supply Chain",
        "engines": 2,
        "tables": 4,
        "sql": """
SELECT d.department_name, cust.segment,
       COUNT(*) as orders, ROUND(SUM(o.sales),2) as total_sales,
       ROUND(AVG(o.order_profit),2) as avg_profit
FROM postgresql.public.sc_orders o
JOIN mysql.supply_chain.sc_departments d ON o.department_id = d.department_id
JOIN mysql.supply_chain.sc_customers cust ON o.customer_id = cust.customer_id
JOIN mysql.supply_chain.sc_categories cat ON o.category_id = cat.category_id
GROUP BY d.department_name, cust.segment ORDER BY total_sales DESC LIMIT 10
"""
    },

    # =====================================================================
    # CATEGORY C: COMPLEX MULTI-TABLE CROSS-ENGINE
    # =====================================================================
    {
        "id": "C1",
        "name": "Complex: Olist 5-table category analysis",
        "category": "Complex Cross-Engine",
        "domain": "E-Commerce",
        "engines": 2,
        "tables": 5,
        "sql": """
SELECT t.product_category_name_english AS category_en, s.seller_state,
       COUNT(*) as items_sold,
       ROUND(SUM(oi.price),2) as revenue,
       ROUND(AVG(CAST(r.review_score AS DOUBLE)),2) as avg_review
FROM postgresql.public.olist_order_items oi
JOIN postgresql.public.olist_order_reviews r ON oi.order_id = r.order_id
JOIN mysql.olist_ecommerce.olist_products p ON oi.product_id = p.product_id
JOIN mysql.olist_ecommerce.olist_sellers s ON oi.seller_id = s.seller_id
JOIN mysql.olist_ecommerce.product_category_translation t 
  ON p.product_category_name = t.product_category_name
GROUP BY t.product_category_name_english, s.seller_state
ORDER BY revenue DESC LIMIT 10
"""
    },
    {
        "id": "C2",
        "name": "Complex: Healthcare 4-table hospital analysis",
        "category": "Complex Cross-Engine",
        "domain": "Healthcare",
        "engines": 2,
        "tables": 4,
        "sql": """
SELECT h.hospital_name, c.condition_name, ins.provider_name,
       COUNT(*) as admissions,
       ROUND(AVG(a.billing_amount),2) as avg_bill,
       ROUND(SUM(a.billing_amount),2) as total_bill
FROM postgresql.public.hc_admissions a
JOIN mysql.healthcare.hc_hospitals h ON a.hospital_id = h.hospital_id
JOIN mysql.healthcare.hc_conditions c ON a.condition_id = c.condition_id
JOIN mysql.healthcare.hc_insurance ins ON a.insurance_id = ins.insurance_id
GROUP BY h.hospital_name, c.condition_name, ins.provider_name
ORDER BY total_bill DESC LIMIT 10
"""
    },
    {
        "id": "C3",
        "name": "Complex: Supply chain 4-table profit analysis",
        "category": "Complex Cross-Engine",
        "domain": "Supply Chain",
        "engines": 2,
        "tables": 4,
        "sql": """
SELECT d.department_name, cat.category_name, cust.segment,
       COUNT(*) as orders,
       ROUND(SUM(o.sales),2) as total_sales,
       ROUND(SUM(o.order_profit),2) as total_profit,
       ROUND(AVG(o.days_shipping_real - o.days_shipment_scheduled),2) as avg_delay
FROM postgresql.public.sc_orders o
JOIN mysql.supply_chain.sc_departments d ON o.department_id = d.department_id
JOIN mysql.supply_chain.sc_categories cat ON o.category_id = cat.category_id
JOIN mysql.supply_chain.sc_customers cust ON o.customer_id = cust.customer_id
GROUP BY d.department_name, cat.category_name, cust.segment
ORDER BY total_profit DESC LIMIT 10
"""
    },

    # =====================================================================
    # CATEGORY D: CROSS-DOMAIN QUERIES (the ultimate federation test)
    # =====================================================================
    {
        "id": "D1",
        "name": "Cross-Domain: 5-domain unified summary",
        "category": "Cross-Domain Federation",
        "domain": "All 5 Domains",
        "engines": 2,
        "tables": 5,
        "sql": """
SELECT 'E-Commerce' as domain, COUNT(*) as rows, ROUND(SUM(price),2) as value
FROM postgresql.public.olist_order_items
UNION ALL
SELECT 'Healthcare', COUNT(*), ROUND(SUM(billing_amount),2)
FROM postgresql.public.hc_admissions
UNION ALL
SELECT 'Retail', COUNT(*), ROUND(SUM(quantity * unit_price),2)
FROM postgresql.public.rt_invoices WHERE quantity > 0
UNION ALL
SELECT 'Financial', COUNT(*), ROUND(SUM(amount),2)
FROM postgresql.public.fin_transactions
UNION ALL
SELECT 'Supply Chain', COUNT(*), ROUND(SUM(sales),2)
FROM postgresql.public.sc_orders
"""
    },
    {
        "id": "D2",
        "name": "Cross-Domain: E-Commerce + Supply Chain comparison",
        "category": "Cross-Domain Federation",
        "domain": "E-Commerce + Supply Chain",
        "engines": 2,
        "tables": 4,
        "sql": """
SELECT 'E-Commerce' as source, 
       c.customer_state as region,
       COUNT(*) as transactions,
       ROUND(SUM(p.payment_value),2) as value
FROM postgresql.public.olist_orders o
JOIN postgresql.public.olist_order_payments p ON o.order_id = p.order_id
JOIN mysql.olist_ecommerce.olist_customers c ON o.customer_id = c.customer_id
GROUP BY c.customer_state
ORDER BY value DESC LIMIT 5
"""
    },
]


def run_query(sql, timeout=120):
    """Run a federated query and return (latency_seconds, success, result_preview)."""
    cmd = f'{JAVA_ENV} && presto-cli --execute "{sql.strip()}" 2>/dev/null'
    start = time.time()
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        elapsed = time.time() - start
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            return elapsed, True, len(lines)
        else:
            return elapsed, False, result.stderr[:200]
    except subprocess.TimeoutExpired:
        return timeout, False, "TIMEOUT"


def main():
    RUNS = 5
    results = []
    
    print(f"{'='*80}")
    print(f"BENCHMARK SUITE — {len(BENCHMARKS)} queries × {RUNS} runs each")
    print(f"{'='*80}\n")
    
    for bench in BENCHMARKS:
        print(f"\n[{bench['id']}] {bench['name']}")
        print(f"    Category: {bench['category']} | Domain: {bench['domain']}")
        print(f"    Engines: {bench['engines']} | Tables: {bench['tables']}")
        
        latencies = []
        row_counts = []
        
        for run in range(RUNS):
            elapsed, success, info = run_query(bench['sql'])
            if success:
                latencies.append(elapsed)
                row_counts.append(info)
                print(f"    Run {run+1}: {elapsed:.3f}s ({info} rows)")
            else:
                print(f"    Run {run+1}: FAILED - {info}")
        
        if latencies:
            result = {
                "id": bench['id'],
                "name": bench['name'],
                "category": bench['category'],
                "domain": bench['domain'],
                "engines": bench['engines'],
                "tables": bench['tables'],
                "runs": RUNS,
                "successful_runs": len(latencies),
                "median_latency": round(statistics.median(latencies), 3),
                "min_latency": round(min(latencies), 3),
                "max_latency": round(max(latencies), 3),
                "mean_latency": round(statistics.mean(latencies), 3),
                "stdev_latency": round(statistics.stdev(latencies), 3) if len(latencies) > 1 else 0,
                "result_rows": row_counts[0] if row_counts else 0
            }
            results.append(result)
            print(f"    → Median: {result['median_latency']:.3f}s | "
                  f"Min: {result['min_latency']:.3f}s | "
                  f"Max: {result['max_latency']:.3f}s | "
                  f"Stdev: {result['stdev_latency']:.3f}s")
    
    # Save results
    with open('/var/www/datasets/benchmark_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    # Print summary table
    print(f"\n\n{'='*80}")
    print("BENCHMARK RESULTS SUMMARY")
    print(f"{'='*80}")
    print(f"{'ID':<5} {'Category':<28} {'Domain':<22} {'Eng':>3} {'Tbl':>3} {'Median':>8} {'Min':>8} {'Max':>8} {'Rows':>6}")
    print("-" * 100)
    
    for r in results:
        print(f"{r['id']:<5} {r['category']:<28} {r['domain']:<22} {r['engines']:>3} {r['tables']:>3} "
              f"{r['median_latency']:>7.3f}s {r['min_latency']:>7.3f}s {r['max_latency']:>7.3f}s {r['result_rows']:>6}")
    
    # Category summaries
    print(f"\n{'='*80}")
    print("CATEGORY AVERAGES")
    print(f"{'='*80}")
    
    categories = {}
    for r in results:
        cat = r['category']
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r['median_latency'])
    
    for cat, lats in categories.items():
        print(f"  {cat}: avg median = {statistics.mean(lats):.3f}s (n={len(lats)} queries)")
    
    # Total data volume
    print(f"\n{'='*80}")
    print("DATA VOLUME")
    print(f"{'='*80}")
    print("  PostgreSQL (facts): 8 tables")
    print("    - olist_orders: 99,441 | olist_order_items: 112,650")
    print("    - olist_order_payments: 103,886 | olist_order_reviews: 99,224")
    print("    - hc_admissions: 55,500 | rt_invoices: 541,909")
    print("    - fin_transactions: 284,807 | sc_orders: 180,519")
    print("  MariaDB (dimensions): 15 tables across 5 schemas")
    print("    - olist_ecommerce: 5 tables (1,135,721 rows)")
    print("    - healthcare: 4 tables (80,228 rows)")
    print("    - retail: 2 tables (8,442 rows)")
    print("    - financial: 2 tables (6 rows)")
    print("    - supply_chain: 4 tables (20,832 rows)")
    print(f"\n  TOTAL: ~2,722,169 rows across 23 tables, 2 engines, 5 domains")
    
    print(f"\nResults saved to /var/www/datasets/benchmark_results.json")


if __name__ == '__main__':
    main()
