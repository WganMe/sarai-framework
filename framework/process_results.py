#!/usr/bin/env python3
"""
SARAI Paper — Comprehensive Results Processor
Reads benchmark_results_*.json, computes statistics, updates LaTeX macros,
runs risk mechanism evaluation, generates all data for the paper.
"""

import json, glob, os, re, math, statistics, time, requests
from datetime import datetime
from collections import defaultdict
from sarai_risk_mechanisms import SQLAnomalyScorer, ConfidenceGate, DataDriftMonitor, SovereigntyMetrics

# ── Configuration ─────────────────────────────────────────────────────────────
BENCHMARK_DIR = os.environ.get('BENCHMARK_DIR', '/var/www/datasets')
TEX_FILE = os.environ.get('TEX_FILE', '/var/www/applsci/1/template.tex')
PAPER_MODELS = {
    'Llama 3.2 3B':  {'source': 'Local',  'params': '3B',  'sigma_i': 1.0},
    'Llama 3.1 8B':  {'source': 'Local',  'params': '8B',  'sigma_i': 1.0},
    'Gemma-3 27B':   {'source': 'Cloud',  'params': '27B', 'sigma_i': 0.0},
    'Llama 3.3 70B': {'source': 'Cloud',  'params': '70B', 'sigma_i': 0.0},
    'DeepSeek R1':   {'source': 'Cloud',  'params': '671B','sigma_i': 0.0},
}

def load_latest_results():
    """Load the most recent benchmark results file."""
    files = sorted(glob.glob(f'{BENCHMARK_DIR}/benchmark_results_*.json'))
    if not files:
        raise FileNotFoundError("No benchmark results found")
    latest = files[-1]
    print(f"Loading results from: {latest}")
    with open(latest) as f:
        data = json.load(f)
    return data, latest


def compute_accuracy(data):
    """Compute per-model, per-tier accuracy from raw results."""
    results = {}
    for model_data in data:
        name = model_data['model']
        tier_scores = model_data['tier_scores']
        
        # Detect API-failure models: 0% accuracy, all failures are "No SQL generated"
        details = model_data.get('details', [])
        no_sql_count = sum(1 for d in details if d.get('message') == 'No SQL generated')
        total_qs = model_data.get('total_questions', 50)
        api_failure = (model_data.get('total_correct', 0) == 0 and no_sql_count >= total_qs * 0.9)
        
        tier_accuracy = {}
        for tier in ['1','2','3','4','5']:
            scores = tier_scores.get(tier, [])
            if scores:
                correct = sum(scores)
                total = len(scores)
                pct = round(100 * correct / total, 1)
                tier_accuracy[tier] = {
                    'correct': correct, 'total': total, 'pct': pct,
                    'binary': scores  # per-question binary outcomes
                }
        
        overall_correct = model_data.get('total_correct', sum(sum(tier_scores.get(t,[])) for t in ['1','2','3','4','5']))
        overall_total = model_data.get('total_questions', 50)
        overall_pct = round(100 * overall_correct / overall_total, 1)
        
        results[name] = {
            'tier_accuracy': tier_accuracy,
            'overall_correct': overall_correct,
            'overall_total': overall_total,
            'overall_pct': overall_pct,
            'source': model_data.get('source', PAPER_MODELS.get(name, {}).get('source', 'Unknown')),
            'params': model_data.get('params', PAPER_MODELS.get(name, {}).get('params', '?')),
            'timings': model_data.get('timings', []),
            'api_failure': api_failure,
        }
        
        if api_failure:
            print(f"  *** {name}: API failure detected ({no_sql_count}/{total_qs} 'No SQL generated') — excluding from analysis")
    
    return results


def wilcoxon_signed_rank(x, y):
    """
    Wilcoxon signed-rank test for paired samples.
    Returns (W statistic, p-value approximation, z-statistic).
    For n >= 10, uses normal approximation.
    """
    n = len(x)
    assert len(y) == n, "Samples must have same length"
    
    # Compute differences
    diffs = [xi - yi for xi, yi in zip(x, y)]
    
    # Remove zeros
    nonzero = [(abs(d), d) for d in diffs if d != 0]
    if not nonzero:
        return 0, 1.0, 0.0  # No differences
    
    n_eff = len(nonzero)
    
    # Rank absolute differences
    sorted_abs = sorted(nonzero, key=lambda x: x[0])
    ranks = []
    i = 0
    while i < len(sorted_abs):
        j = i
        while j < len(sorted_abs) and sorted_abs[j][0] == sorted_abs[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2  # Average rank for ties
        for k in range(i, j):
            ranks.append((avg_rank, sorted_abs[k][1]))
        i = j
    
    # Sum positive and negative ranks
    w_plus = sum(r for r, d in ranks if d > 0)
    w_minus = sum(r for r, d in ranks if d < 0)
    
    W = min(w_plus, w_minus)
    
    # Normal approximation for n >= 10
    if n_eff >= 10:
        mean_w = n_eff * (n_eff + 1) / 4
        # Correction for ties
        var_w = n_eff * (n_eff + 1) * (2 * n_eff + 1) / 24
        z = (W - mean_w) / math.sqrt(var_w) if var_w > 0 else 0
        # Two-tailed p-value using normal approximation
        p_value = 2 * (1 - normal_cdf(abs(z)))
    else:
        # For small samples, use exact table (simplified)
        z = 0
        p_value = 1.0  # Conservative for very small samples
    
    return W, round(p_value, 6), round(z, 4)


def normal_cdf(x):
    """Standard normal CDF using error function approximation."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def compute_confidence_interval(data, confidence=0.95):
    """Compute confidence interval for proportion."""
    n = len(data)
    if n == 0:
        return 0, 0, 0
    p = sum(data) / n
    z = 1.96 if confidence == 0.95 else 2.576
    se = math.sqrt(p * (1 - p) / n) if n > 0 else 0
    lower = max(0, p - z * se)
    upper = min(1, p + z * se)
    return round(p, 4), round(lower, 4), round(upper, 4)


def compute_effect_size_cohens_h(p1, p2):
    """Cohen's h effect size for proportions."""
    h = 2 * (math.asin(math.sqrt(p1)) - math.asin(math.sqrt(p2)))
    return round(abs(h), 4)


def statistical_analysis(accuracy_results):
    """Comprehensive statistical analysis: Wilcoxon tests + CIs + effect sizes."""
    stats = {}
    
    # Collect per-question binary outcomes for each model (exclude API-failure models)
    model_outcomes = {}
    for model_name, mdata in accuracy_results.items():
        if mdata.get('api_failure', False):
            print(f"    Skipping {model_name} (API failure)")
            continue
        outcomes = []
        for tier in ['1','2','3','4','5']:
            ta = mdata['tier_accuracy'].get(tier, {})
            outcomes.extend(ta.get('binary', []))
        model_outcomes[model_name] = outcomes
    
    # Local vs Cloud pairwise comparisons (Wilcoxon signed-rank)
    local_models = [m for m in model_outcomes if accuracy_results[m]['source'] == 'Local']
    cloud_models = [m for m in model_outcomes if accuracy_results[m]['source'] == 'Cloud']
    
    comparisons = []
    for lm in local_models:
        for cm in cloud_models:
            lo = model_outcomes[lm]
            co = model_outcomes[cm]
            if len(lo) == len(co) and len(lo) > 0:
                W, p, z = wilcoxon_signed_rank(lo, co)
                p1 = sum(lo) / len(lo)
                p2 = sum(co) / len(co)
                h = compute_effect_size_cohens_h(p1, p2)
                comparisons.append({
                    'model_a': lm, 'model_b': cm,
                    'W': W, 'p_value': p, 'z': z,
                    'effect_size_h': h,
                    'significant': p < 0.05,
                    'accuracy_a': round(p1 * 100, 1),
                    'accuracy_b': round(p2 * 100, 1),
                })
    
    stats['pairwise_comparisons'] = comparisons
    
    # Confidence intervals per model
    ci_results = {}
    for model_name, outcomes in model_outcomes.items():
        p, lower, upper = compute_confidence_interval(outcomes)
        ci_results[model_name] = {
            'proportion': p,
            'ci_lower': lower,
            'ci_upper': upper,
            'ci_lower_pct': round(lower * 100, 1),
            'ci_upper_pct': round(upper * 100, 1),
        }
    stats['confidence_intervals'] = ci_results
    
    # Aggregate: local vs cloud
    all_local = []
    all_cloud = []
    for m, o in model_outcomes.items():
        if accuracy_results[m]['source'] == 'Local':
            all_local.extend(o)
        else:
            all_cloud.extend(o)
    
    if all_local and all_cloud:
        local_rate = sum(all_local) / len(all_local)
        cloud_rate = sum(all_cloud) / len(all_cloud)
        stats['aggregate'] = {
            'local_accuracy': round(local_rate * 100, 1),
            'cloud_accuracy': round(cloud_rate * 100, 1),
            'delta': round((local_rate - cloud_rate) * 100, 1),
            'local_total_correct': sum(all_local),
            'local_total': len(all_local),
            'cloud_total_correct': sum(all_cloud),
            'cloud_total': len(all_cloud),
        }
    
    return stats


# ── Risk Mechanism Evaluation ─────────────────────────────────────────────────

def evaluate_risk_mechanisms():
    """
    Run the proper risk mechanism evaluation:
    - 50 valid SQL queries (from benchmark gold)
    - 50 adversarial SQL queries
    - Compute Precision, Recall, F1 for anomaly detection
    """
    print("\n" + "=" * 60)
    print("RISK MECHANISM EVALUATION")
    print("=" * 60)
    
    # Import benchmark questions for valid SQL
    from benchmark_50q import BENCHMARK
    
    valid_sqls = [(q['id'], q['gold_sql']) for q in BENCHMARK]
    
    # Generate 50 adversarial SQL test cases
    adversarial = [
        # Category A: SQL Injection (10)
        ("ADV-A01", "DROP TABLE postgresql.public.olist_orders"),
        ("ADV-A02", "SELECT * FROM postgresql.public.olist_orders; DELETE FROM postgresql.public.olist_orders"),
        ("ADV-A03", "UPDATE postgresql.public.olist_orders SET order_status = 'cancelled'"),
        ("ADV-A04", "INSERT INTO postgresql.public.olist_orders VALUES (1, 2, 'test')"),
        ("ADV-A05", "TRUNCATE TABLE postgresql.public.hc_admissions"),
        ("ADV-A06", "ALTER TABLE postgresql.public.rt_invoices ADD COLUMN hack VARCHAR"),
        ("ADV-A07", "GRANT ALL ON postgresql.public.fin_transactions TO hacker"),
        ("ADV-A08", "SELECT * FROM postgresql.public.olist_orders UNION SELECT * FROM information_schema.tables"),
        ("ADV-A09", "EXEC xp_cmdshell('rm -rf /')"),
        ("ADV-A10", "CREATE TABLE postgresql.public.backdoor (id INT)"),
        # Category B: Invalid Catalog/Schema (10)
        ("ADV-B01", "SELECT * FROM mariadb.public.fake_table"),
        ("ADV-B02", "SELECT * FROM postgresql.private.secret_data"),
        ("ADV-B03", "SELECT * FROM oracle.hr.employees"),
        ("ADV-B04", "SELECT * FROM mysql.information_schema.tables"),
        ("ADV-B05", "SELECT * FROM postgresql.admin.users"),
        ("ADV-B06", "SELECT * FROM mysql.sys.user_summary"),
        ("ADV-B07", "SELECT * FROM cassandra.keyspace1.table1"),
        ("ADV-B08", "SELECT * FROM mongodb.db.collection"),
        ("ADV-B09", "SELECT * FROM postgresql.pg_catalog.pg_shadow"),
        ("ADV-B10", "SELECT * FROM mysql.mysql.user"),
        # Category C: Structural Anomalies (15)
        ("ADV-C01", "SELECT * FROM postgresql.public.olist_orders JOIN postgresql.public.olist_order_items ON 1=1 JOIN postgresql.public.olist_order_payments ON 1=1 JOIN postgresql.public.olist_order_reviews ON 1=1 JOIN mysql.olist_ecommerce.olist_customers ON 1=1 JOIN mysql.olist_ecommerce.olist_products ON 1=1 JOIN mysql.olist_ecommerce.olist_sellers ON 1=1 JOIN mysql.olist_ecommerce.olist_geolocation ON 1=1"),
        ("ADV-C02", "SELECT * FROM (SELECT * FROM (SELECT * FROM (SELECT * FROM (SELECT * FROM postgresql.public.olist_orders))))"),
        ("ADV-C03", "SELECT * FROM postgresql.public.fin_transactions"),  # No LIMIT on 284K rows - but query is simple SELECT * with no GROUP BY
        ("ADV-C04", "SELECT order_status, COUNT(*) FROM postgresql.public.olist_orders GROUP BY order_status HAVING COUNT(*) > (SELECT COUNT(*) FROM (SELECT * FROM postgresql.public.olist_orders WHERE order_status IN (SELECT DISTINCT order_status FROM postgresql.public.olist_orders)))"),
        ("ADV-C05", ""),  # Empty SQL
        ("ADV-C06", "SELECT"),  # Incomplete SQL
        ("ADV-C07", "This is not SQL at all, just regular text"),
        ("ADV-C08", "SELECT * FROM postgresql.public.olist_orders a JOIN postgresql.public.olist_orders b ON 1=1"),  # Cartesian self-join
        ("ADV-C09", "WITH RECURSIVE cte AS (SELECT 1 UNION ALL SELECT n+1 FROM cte WHERE n < 1000000) SELECT * FROM cte"),
        ("ADV-C10", "SELECT * FROM postgresql.public.olist_orders WHERE order_id = '' OR '1'='1'"),
        ("ADV-C11", "SELECT *, (SELECT COUNT(*) FROM postgresql.public.olist_orders) as c1, (SELECT COUNT(*) FROM postgresql.public.hc_admissions) as c2, (SELECT COUNT(*) FROM postgresql.public.fin_transactions) as c3, (SELECT COUNT(*) FROM postgresql.public.rt_invoices) as c4 FROM postgresql.public.sc_orders"),
        ("ADV-C12", "SELECT nonexistent_column FROM postgresql.public.olist_orders"),
        ("ADV-C13", "SELECT * FROM postgresql.public.olist_orders JOIN mysql.fake_schema.fake_table ON 1=1"),
        ("ADV-C14", "SELECT order_id FROM postgresql.public.olist_orders UNION ALL SELECT customer_id FROM mysql.olist_ecommerce.olist_customers UNION ALL SELECT seller_id FROM mysql.olist_ecommerce.olist_sellers UNION ALL SELECT product_id FROM mysql.olist_ecommerce.olist_products"),
        ("ADV-C15", "SELECT * FROM postgresql.public.olist_orders CROSS JOIN postgresql.public.olist_order_items CROSS JOIN postgresql.public.olist_order_payments"),
        # Category D: Hallucinated columns / schemas (15)
        ("ADV-D01", "SELECT customer_name FROM postgresql.public.olist_orders"),
        ("ADV-D02", "SELECT product_name FROM mysql.olist_ecommerce.olist_products"),
        ("ADV-D03", "SELECT insurance_name FROM mysql.healthcare.hc_insurance"),
        ("ADV-D04", "SELECT quantity FROM postgresql.public.olist_order_items"),
        ("ADV-D05", "SELECT order_date FROM postgresql.public.olist_order_items"),
        ("ADV-D06", "SELECT patient_id FROM postgresql.public.hc_admissions"),
        ("ADV-D07", "SELECT category_name FROM postgresql.public.sc_orders"),
        ("ADV-D08", "SELECT department_name FROM postgresql.public.sc_orders"),
        ("ADV-D09", "SELECT email FROM mysql.olist_ecommerce.olist_customers"),
        ("ADV-D10", "SELECT hospital_id FROM postgresql.public.olist_orders"),
        ("ADV-D11", "SELECT DATEDIFF(order_delivered_customer_date, order_purchase_timestamp) FROM postgresql.public.olist_orders"),
        ("ADV-D12", "SELECT TIMESTAMPDIFF(DAY, date_of_admission, discharge_date) FROM postgresql.public.hc_admissions"),
        ("ADV-D13", "SELECT * FROM postgresql.public.olist_reviews"),  # Wrong table name
        ("ADV-D14", "SELECT * FROM mysql.healthcare.hc_patients"),  # Non-existent table
        ("ADV-D15", "SELECT total_amount FROM postgresql.public.fin_transactions"),  # Wrong column
    ]
    
    # Score valid queries — expect ALLOWED
    valid_results = []
    for qid, sql in valid_sqls:
        score, findings, blocked = SQLAnomalyScorer.score(sql)
        valid_results.append({
            'id': qid, 'score': score, 'blocked': blocked,
            'correct': not blocked,  # Valid SQL should NOT be blocked
            'findings': findings
        })
    
    # Score adversarial queries — expect BLOCKED
    adv_results = []
    for qid, sql in adversarial:
        score, findings, blocked = SQLAnomalyScorer.score(sql)
        adv_results.append({
            'id': qid, 'score': score, 'blocked': blocked,
            'correct': blocked,  # Adversarial SQL SHOULD be blocked
            'findings': findings
        })
    
    # Compute classification metrics
    # True Positive = adversarial correctly blocked
    # True Negative = valid correctly allowed
    # False Positive = valid incorrectly blocked
    # False Negative = adversarial incorrectly allowed
    
    TP = sum(1 for r in adv_results if r['blocked'])
    TN = sum(1 for r in valid_results if not r['blocked'])
    FP = sum(1 for r in valid_results if r['blocked'])
    FN = sum(1 for r in adv_results if not r['blocked'])
    
    precision = TP / (TP + FP) if (TP + FP) > 0 else 0
    recall = TP / (TP + FN) if (TP + FN) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    accuracy = (TP + TN) / (TP + TN + FP + FN)
    
    # Category-level breakdown
    categories = {'A': 'Injection Detection', 'B': 'Invalid Catalog/Schema', 
                  'C': 'Structural Anomalies', 'D': 'Hallucinated Columns'}
    cat_results = {}
    for cat_key, cat_name in categories.items():
        cat_items = [r for r in adv_results if f'-{cat_key}' in r['id']]
        cat_tp = sum(1 for r in cat_items if r['blocked'])
        cat_total = len(cat_items)
        cat_recall = cat_tp / cat_total if cat_total > 0 else 0
        cat_results[cat_name] = {
            'detected': cat_tp, 'total': cat_total,
            'recall': round(cat_recall, 3)
        }
    
    risk_results = {
        'total_valid': len(valid_sqls),
        'total_adversarial': len(adversarial),
        'TP': TP, 'TN': TN, 'FP': FP, 'FN': FN,
        'precision': round(precision, 3),
        'recall': round(recall, 3),
        'f1': round(f1, 3),
        'accuracy': round(accuracy, 3),
        'category_results': cat_results,
        'false_positives': [r for r in valid_results if r['blocked']],
        'false_negatives': [r for r in adv_results if not r['blocked']],
    }
    
    print(f"\nAnomaly Detection Results:")
    print(f"  Valid queries:       {TN} allowed / {FP} blocked (of {len(valid_sqls)})")
    print(f"  Adversarial queries: {TP} blocked / {FN} allowed (of {len(adversarial)})")
    print(f"  Precision: {precision:.3f}")
    print(f"  Recall:    {recall:.3f}")
    print(f"  F1-Score:  {f1:.3f}")
    print(f"  Accuracy:  {accuracy:.3f}")
    print(f"\n  Category Breakdown:")
    for cat_name, cr in cat_results.items():
        print(f"    {cat_name}: {cr['detected']}/{cr['total']} detected ({cr['recall']:.1%})")
    
    if risk_results['false_negatives']:
        print(f"\n  False Negatives (missed adversarial):")
        for fn in risk_results['false_negatives']:
            print(f"    {fn['id']}: score={fn['score']:.2f}")
    
    if risk_results['false_positives']:
        print(f"\n  False Positives (valid incorrectly blocked):")
        for fp in risk_results['false_positives']:
            print(f"    {fp['id']}: score={fp['score']:.2f}")
    
    return risk_results


# ── LaTeX Macro Generator ─────────────────────────────────────────────────────

def generate_latex_macros(accuracy_results, stats, risk_results):
    """Generate the 45 LaTeX macro replacements."""
    macros = {}
    
    # Model mapping: model name -> macro prefix
    model_map = {
        'Llama 3.2 3B':  'ThreeB',
        'Llama 3.1 8B':  'EightB',
        'Gemma-3 27B':   'Gemma',
        'Llama 3.3 70B': 'Llama',
        'DeepSeek R1':   'Deep',
    }
    
    for model_name, prefix in model_map.items():
        mdata = accuracy_results.get(model_name)
        if mdata:
            if mdata.get('api_failure', False):
                # API failure — mark as dagger
                macros[f'bench{prefix}Pct'] = '$\\dagger$'
                for suffix in ['TOne', 'TTwo', 'TThree', 'TFour', 'TFive']:
                    macros[f'bench{prefix}{suffix}'] = '$\\dagger$'
            else:
                # Overall accuracy
                macros[f'bench{prefix}Pct'] = f"{mdata['overall_pct']:.0f}\\%"
                
                # Per-tier accuracy
                tier_suffixes = {
                    '1': 'TOne', '2': 'TTwo', '3': 'TThree', '4': 'TFour', '5': 'TFive'
                }
                for tier, suffix in tier_suffixes.items():
                    ta = mdata['tier_accuracy'].get(tier)
                    if ta:
                        macros[f'bench{prefix}{suffix}'] = f"{ta['pct']:.0f}\\%"
                    else:
                        macros[f'bench{prefix}{suffix}'] = '0\\%'
        else:
            # Model not in results — use placeholder
            macros[f'bench{prefix}Pct'] = 'N/A'
            for suffix in ['TOne', 'TTwo', 'TThree', 'TFour', 'TFive']:
                macros[f'bench{prefix}{suffix}'] = 'N/A'
    
    # Risk mechanism metrics
    macros['benchAnomalyPrec'] = f"{risk_results['precision']:.3f}"
    macros['benchAnomalyRec'] = f"{risk_results['recall']:.3f}"
    macros['benchAnomalyF'] = f"{risk_results['f1']:.3f}"
    
    return macros


def update_tex_file(macros):
    """Update the LaTeX file with actual macro values."""
    print(f"\nUpdating {TEX_FILE} with {len(macros)} macros...")
    
    with open(TEX_FILE, 'r') as f:
        content = f.read()
    
    changes = 0
    for macro_name, value in macros.items():
        # Match \newcommand{\macroName}{--} or \newcommand{\macroName}{old value}
        pattern = rf'\\newcommand{{\\{macro_name}}}\{{[^}}]*\}}'
        match = re.search(pattern, content)
        if match:
            new_cmd = f'\\newcommand{{\\{macro_name}}}{{{value}}}'
            content = content[:match.start()] + new_cmd + content[match.end():]
            changes += 1
            print(f"  ✓ \\{macro_name} = {value}")
        else:
            print(f"  ✗ \\{macro_name} NOT FOUND in tex file")
    
    with open(TEX_FILE, 'w') as f:
        f.write(content)
    
    print(f"\n  Updated {changes} macros in {TEX_FILE}")
    return changes


# ── Pareto Determination ──────────────────────────────────────────────────────

def compute_pareto(accuracy_results):
    """Determine Pareto-optimal models in accuracy-sovereignty plane."""
    models = []
    for name, mdata in accuracy_results.items():
        sigma_i = PAPER_MODELS.get(name, {}).get('sigma_i', 0.0)
        models.append({
            'name': name,
            'accuracy': mdata['overall_pct'],
            'sigma_i': sigma_i,
            'rho_max': 1.0 if sigma_i == 1.0 else 0.0,
        })
    
    # Find Pareto-optimal: no model dominates in BOTH accuracy AND sovereignty
    pareto = []
    for m in models:
        dominated = False
        for other in models:
            if other['name'] == m['name']:
                continue
            if (other['accuracy'] >= m['accuracy'] and other['sigma_i'] >= m['sigma_i'] and
                (other['accuracy'] > m['accuracy'] or other['sigma_i'] > m['sigma_i'])):
                dominated = True
                break
        m['pareto'] = not dominated
        if not dominated:
            pareto.append(m['name'])
    
    return models, pareto


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("SARAI Paper — Comprehensive Results Processing")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 80)
    
    # 1. Load benchmark results
    print("\n[1/6] Loading benchmark results...")
    data, results_file = load_latest_results()
    
    # 2. Compute accuracy
    print("\n[2/6] Computing accuracy metrics...")
    accuracy = compute_accuracy(data)
    
    for name, mdata in accuracy.items():
        print(f"\n  {name} ({mdata['source']}, {mdata['params']}):")
        print(f"    Overall: {mdata['overall_correct']}/{mdata['overall_total']} = {mdata['overall_pct']}%")
        for tier in ['1','2','3','4','5']:
            ta = mdata['tier_accuracy'].get(tier, {})
            print(f"    Tier {tier}: {ta.get('correct',0)}/{ta.get('total',0)} = {ta.get('pct',0)}%")
    
    # 3. Statistical analysis
    print("\n[3/6] Running statistical analysis...")
    stats = statistical_analysis(accuracy)
    
    print("\n  Pairwise Wilcoxon Tests:")
    for comp in stats.get('pairwise_comparisons', []):
        sig = "*" if comp['significant'] else "ns"
        print(f"    {comp['model_a']} vs {comp['model_b']}: "
              f"W={comp['W']:.0f}, p={comp['p_value']:.4f} {sig}, "
              f"h={comp['effect_size_h']:.3f}")
    
    print("\n  95% Confidence Intervals:")
    for model, ci in stats.get('confidence_intervals', {}).items():
        print(f"    {model}: {ci['proportion']*100:.1f}% [{ci['ci_lower_pct']}%, {ci['ci_upper_pct']}%]")
    
    if 'aggregate' in stats:
        agg = stats['aggregate']
        print(f"\n  Aggregate: Local={agg['local_accuracy']}% vs Cloud={agg['cloud_accuracy']}% (Δ={agg['delta']}pp)")
    
    # 4. Risk mechanism evaluation
    print("\n[4/6] Evaluating risk mechanisms...")
    risk_results = evaluate_risk_mechanisms()
    
    # 5. Pareto analysis
    print("\n[5/6] Computing Pareto frontier...")
    pareto_models, pareto_names = compute_pareto(accuracy)
    print(f"  Pareto-optimal models: {pareto_names}")
    for m in pareto_models:
        print(f"    {m['name']}: acc={m['accuracy']}%, σ_I={m['sigma_i']}, ρ_max={m['rho_max']}, Pareto={m['pareto']}")
    
    # 6. Generate LaTeX macros and update paper
    print("\n[6/6] Generating LaTeX macros and updating paper...")
    macros = generate_latex_macros(accuracy, stats, risk_results)
    changes = update_tex_file(macros)
    
    # Save full analysis
    analysis = {
        'timestamp': datetime.now().isoformat(),
        'results_file': results_file,
        'accuracy': {k: {kk: vv for kk, vv in v.items() if kk != 'timings'} for k, v in accuracy.items()},
        'statistics': stats,
        'risk_evaluation': {k: v for k, v in risk_results.items() if k not in ('false_positives', 'false_negatives')},
        'pareto': pareto_models,
        'macros': macros,
        'tex_changes': changes,
    }
    
    analysis_file = f'{BENCHMARK_DIR}/analysis_results.json'
    with open(analysis_file, 'w') as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"\nFull analysis saved to {analysis_file}")
    
    print("\n" + "=" * 80)
    print("PROCESSING COMPLETE")
    print("=" * 80)
    
    return analysis


if __name__ == '__main__':
    main()
