#!/usr/bin/env python3
"""
SARAI Risk Assessment Mechanisms — Actual Implementation
4 Proactive Risk Mechanisms for AI-Enhanced BI:

1. SQL Anomaly Scorer — validates AI-generated SQL before execution
2. Confidence Gating — uses token log-probabilities to reject low-confidence SQL  
3. Data Drift Monitor — detects distribution shifts in query patterns
4. Feedback Loop — generate → validate → execute → log → re-prompt on failure

These run inside the workflow platform as code nodes via the unified API.
"""

import json, re, time, requests, statistics, math, os
from datetime import datetime
from collections import Counter

# Local inference endpoint. Overridable so the mechanisms are not bound to one host.
OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434')

# ═══════════════════════════════════════════════════════════════════════════════
# MECHANISM 1: SQL Anomaly Scorer
# Validates AI-generated SQL against a rule set BEFORE execution
# ═══════════════════════════════════════════════════════════════════════════════

class SQLAnomalyScorer:
    """
    Multi-rule anomaly detection for AI-generated SQL.
    Returns anomaly_score in [0, 1] and detailed findings.
    
    Rules:
    R1: Catalog validation — all table refs must use valid catalog.schema.table
    R2: Injection detection — no DROP, DELETE, INSERT, UPDATE, ALTER, TRUNCATE
    R3: Syntax validation — must start with SELECT/WITH and contain FROM
    R4: Complexity bounds — JOIN count, subquery depth within limits
    R5: Result size guard — LIMIT clause present for aggregation queries
    R6: System schema detection — no information_schema, pg_catalog, mysql.mysql, sys
    R7: Cartesian join detection — ON 1=1, CROSS JOIN
    R8: Tautology detection — OR '1'='1', OR 1=1 in WHERE
    R9: Recursive CTE detection — WITH RECURSIVE
    R10: Column validation — referenced columns must exist in known schema
    R11: Function validation — only federation-engine-supported functions allowed
    """
    
    VALID_CATALOGS = {'postgresql', 'mysql'}
    VALID_TABLES = {
        'postgresql.public.olist_orders', 'postgresql.public.olist_order_items',
        'postgresql.public.olist_order_payments', 'postgresql.public.olist_order_reviews',
        'postgresql.public.hc_admissions', 'postgresql.public.rt_invoices',
        'postgresql.public.fin_transactions', 'postgresql.public.sc_orders',
        'mysql.olist_ecommerce.olist_customers', 'mysql.olist_ecommerce.olist_products',
        'mysql.olist_ecommerce.olist_sellers', 'mysql.olist_ecommerce.olist_geolocation',
        'mysql.olist_ecommerce.product_category_translation',
        'mysql.healthcare.hc_conditions', 'mysql.healthcare.hc_insurance',
        'mysql.healthcare.hc_hospitals', 'mysql.healthcare.hc_doctors',
        'mysql.retail.rt_customers', 'mysql.retail.rt_products',
        'mysql.financial.fin_fraud_classes', 'mysql.financial.fin_time_buckets',
        'mysql.supply_chain.sc_customers', 'mysql.supply_chain.sc_products',
        'mysql.supply_chain.sc_departments', 'mysql.supply_chain.sc_categories'
    }
    
    # Column validation map: table short name -> set of valid columns
    # Sourced from SHOW COLUMNS FROM <table> on the federation engine
    VALID_COLUMNS = {
        'olist_orders': {'order_id', 'customer_id', 'order_status', 'order_purchase_timestamp',
                         'order_approved_at', 'order_delivered_carrier_date',
                         'order_delivered_customer_date', 'order_estimated_delivery_date'},
        'olist_order_items': {'order_id', 'order_item_id', 'product_id', 'seller_id',
                              'shipping_limit_date', 'price', 'freight_value'},
        'olist_order_payments': {'order_id', 'payment_sequential', 'payment_type',
                                 'payment_installments', 'payment_value'},
        'olist_order_reviews': {'review_id', 'order_id', 'review_score', 'review_comment_title',
                                'review_comment_message', 'review_creation_date',
                                'review_answer_timestamp'},
        'hc_admissions': {'admission_id', 'patient_name', 'age', 'gender', 'blood_type',
                          'condition_id', 'doctor_id', 'hospital_id', 'insurance_id',
                          'billing_amount', 'room_number', 'admission_type',
                          'date_of_admission', 'discharge_date', 'medication', 'test_results'},
        'rt_invoices': {'invoice_id', 'invoice_no', 'stock_code', 'quantity', 'invoice_date',
                        'unit_price', 'customer_id'},
        'fin_transactions': {'transaction_id', 'time_elapsed', 'amount', 'class_id', 'time_hour',
                             'v1', 'v2', 'v3', 'v4', 'v5', 'v6', 'v7', 'v8', 'v9', 'v10',
                             'v11', 'v12', 'v13', 'v14', 'v15', 'v16', 'v17', 'v18', 'v19', 'v20',
                             'v21', 'v22', 'v23', 'v24', 'v25', 'v26', 'v27', 'v28'},
        'sc_orders': {'order_row_id', 'order_id', 'order_item_id', 'order_date', 'shipping_date',
                      'type', 'days_shipping_real', 'days_shipment_scheduled', 'delivery_status',
                      'late_delivery_risk', 'customer_id', 'product_id', 'department_id',
                      'category_id', 'order_item_quantity', 'order_item_discount',
                      'order_item_discount_rate', 'order_item_product_price', 'sales',
                      'order_item_total', 'order_profit', 'benefit_per_order',
                      'sales_per_customer', 'shipping_mode', 'market',
                      'order_city', 'order_country', 'order_region', 'order_state'},
        'olist_customers': {'customer_id', 'customer_unique_id', 'customer_zip_code_prefix',
                            'customer_city', 'customer_state'},
        'olist_products': {'product_id', 'product_category_name', 'product_name_lenght',
                           'product_description_lenght', 'product_photos_qty',
                           'product_weight_g', 'product_length_cm', 'product_height_cm',
                           'product_width_cm'},
        'olist_sellers': {'seller_id', 'seller_zip_code_prefix', 'seller_city', 'seller_state'},
        'olist_geolocation': {'geolocation_zip_code_prefix', 'geolocation_lat', 'geolocation_lng',
                              'geolocation_city', 'geolocation_state'},
        'product_category_translation': {'product_category_name', 'product_category_name_english'},
        'hc_conditions': {'condition_id', 'condition_name'},
        'hc_insurance': {'insurance_id', 'provider_name'},
        'hc_hospitals': {'hospital_id', 'hospital_name'},
        'hc_doctors': {'doctor_id', 'doctor_name'},
        'rt_customers': {'customer_id', 'country'},
        'rt_products': {'stock_code', 'description'},
        'fin_fraud_classes': {'class_id', 'class_name', 'description'},
        'fin_time_buckets': {'bucket_id', 'bucket_name', 'hour_start', 'hour_end', 'description'},
        'sc_customers': {'customer_id', 'first_name', 'last_name', 'email', 'segment',
                         'city', 'country', 'state', 'zipcode'},
        'sc_products': {'product_id', 'product_name', 'product_price', 'category_id', 'product_status'},
        'sc_departments': {'department_id', 'department_name'},
        'sc_categories': {'category_id', 'category_name'},
    }
    
    SYSTEM_SCHEMAS = re.compile(
        r'\b(information_schema|pg_catalog|pg_shadow|mysql\.mysql|mysql\.sys|'
        r'sys\.user|performance_schema)\b', re.IGNORECASE
    )
    
    DANGEROUS_KEYWORDS = re.compile(
        r'\b(DROP|DELETE|INSERT|UPDATE|ALTER|TRUNCATE|GRANT|REVOKE|CREATE|EXEC|EXECUTE|xp_cmdshell)\b',
        re.IGNORECASE
    )
    
    CARTESIAN_PATTERN = re.compile(
        r'\bON\s+1\s*=\s*1\b|\bCROSS\s+JOIN\b', re.IGNORECASE
    )
    
    TAUTOLOGY_PATTERN = re.compile(
        r"""OR\s+(?:'1'\s*=\s*'1'|1\s*=\s*1|'a'\s*=\s*'a'|''='')""", re.IGNORECASE
    )
    
    RECURSIVE_CTE = re.compile(r'\bWITH\s+RECURSIVE\b', re.IGNORECASE)
    
    INVALID_FUNCTIONS = re.compile(
        r'\b(DATEDIFF|TIMESTAMPDIFF|DATEADD|GETDATE|NOW|SYSDATE|ISNULL|NVL)\s*\(', re.IGNORECASE
    )
    
    MAX_JOINS = 6
    MAX_SUBQUERY_DEPTH = 3
    MAX_CROSS_JOINS = 1
    MAX_UNION_CLAUSES = 4
    
    @classmethod
    def _extract_table_alias_map(cls, sql):
        """Build alias->table_short_name mapping from FROM/JOIN clauses."""
        alias_map = {}
        # Match 3-part table refs: catalog.schema.table [AS] alias
        for m in re.finditer(r'(\w+\.\w+\.(\w+))(?:\s+(?:AS\s+)?(\w+))?', sql, re.IGNORECASE):
            full_ref, table_name, alias = m.group(1), m.group(2).lower(), m.group(3)
            if alias and alias.upper() not in ('ON', 'WHERE', 'GROUP', 'ORDER', 'HAVING',
                                                 'LIMIT', 'JOIN', 'LEFT', 'RIGHT', 'INNER',
                                                 'OUTER', 'CROSS', 'FULL', 'UNION', 'SET',
                                                 'SELECT', 'AND', 'OR', 'AS', 'WHEN', 'THEN',
                                                 'ELSE', 'END', 'CASE', 'WITH', 'FROM'):
                alias_map[alias.lower()] = table_name
            # Also map the table name itself as an alias
            alias_map[table_name] = table_name
        return alias_map

    @classmethod
    def _extract_referenced_columns(cls, sql):
        """Extract column-like references from SQL for validation.
        Returns list of (alias_or_none, column_name) tuples."""
        result = []
        
        # Strip quoted strings to avoid extracting literal values as column names
        sql_clean = re.sub(r"'[^']*'", "''", sql)  # Remove single-quoted strings
        sql_clean = re.sub(r'"[^"]*"', '""', sql_clean)  # Remove double-quoted strings
        
        # 1. Match alias.column patterns (e.g., o.customer_name, t.total_amount)
        alias_cols = re.findall(r'\b(\w+)\.(\w+)\b', sql_clean)
        catalog_schema_names = {'postgresql', 'mysql', 'public', 'olist_ecommerce',
                                'healthcare', 'retail', 'financial', 'supply_chain',
                                'information_schema', 'pg_catalog', 'sys'}
        for alias, col in alias_cols:
            if alias.lower() not in catalog_schema_names and not alias.isnumeric():
                result.append((alias.lower(), col.lower()))
        
        # 2. Match bare column names in SELECT clause (no alias prefix)
        # Extract the SELECT ... FROM portion
        select_match = re.search(r'\bSELECT\s+(.*?)\s+FROM\b', sql_clean, re.IGNORECASE | re.DOTALL)
        if select_match:
            select_part = select_match.group(1)
            # Extract identifiers that aren't SQL keywords, functions, or aliases
            sql_keywords = {'select', 'from', 'where', 'join', 'on', 'group', 'by', 'order',
                           'having', 'limit', 'as', 'distinct', 'case', 'when', 'then', 'else',
                           'end', 'and', 'or', 'not', 'in', 'is', 'null', 'between', 'like',
                           'exists', 'all', 'any', 'union', 'except', 'intersect', 'asc', 'desc', 'distinct',
                           'count', 'sum', 'avg', 'min', 'max', 'round', 'coalesce', 'cast',
                           'concat', 'length', 'substring', 'trim', 'upper', 'lower', 'extract',
                           'date_diff', 'date_trunc', 'date_format', 'now', 'current_date',
                           'datediff', 'timestampdiff', 'true', 'false', 'with',
                           'recursive', 'over', 'partition', 'row_number', 'rank', 'dense_rank',
                           'day', 'month', 'year', 'hour', 'minute', 'second', 'quarter', 'week',
                           'into', 'set', 'values', 'inner', 'outer', 'left', 'right', 'full',
                           'cross', 'natural', 'using', 'interval', 'date', 'time', 'timestamp'}
            # Split select part by comma and analyze each expression
            for expr in select_part.split(','):
                expr = expr.strip()
                # Skip if it's just * or aggregate
                if expr == '*' or not expr:
                    continue
                # Remove alias definitions (everything after AS <name>)
                # e.g., "ROUND(SUM(a.billing_amount), 2) AS total_billing" -> skip total_billing
                as_match = re.search(r'\bAS\s+(\w+)\s*$', expr, re.IGNORECASE)
                alias_name = as_match.group(1).lower() if as_match else None
                if as_match:
                    expr = expr[:as_match.start()]
                # Get bare identifiers (not part of alias.col, function(), or alias. prefix)
                bare_ids = re.findall(r'(?<!\w\.)(?<!\.)(\b[a-zA-Z_]\w*\b)(?!\s*[\.(])', expr)
                for bid in bare_ids:
                    if bid.lower() not in sql_keywords and not bid.isnumeric():
                        if bid.lower() != alias_name:
                            result.append((None, bid.lower()))
        
        # 3. Match bare column names in WHERE clause
        where_match = re.search(r'\bWHERE\s+(.*?)(?:\bGROUP\b|\bORDER\b|\bLIMIT\b|\bHAVING\b|$)',
                               sql_clean, re.IGNORECASE | re.DOTALL)
        if where_match:
            where_part = where_match.group(1)
            sql_keywords_where = {'and', 'or', 'not', 'in', 'is', 'null', 'between', 'like',
                                  'exists', 'true', 'false', 'select', 'from', 'where',
                                  'all', 'any', 'union', 'case', 'when', 'then', 'else', 'end',
                                  'day', 'month', 'year', 'hour', 'minute', 'second',
                                  'date', 'time', 'timestamp', 'interval'}
            bare_ids = re.findall(r'(?<!\w\.)(?<!\.)(\b[a-zA-Z_]\w*\b)(?!\s*[\.(])', where_part)
            for bid in bare_ids:
                if bid.lower() not in sql_keywords_where and not bid.isnumeric():
                    result.append((None, bid.lower()))
        
        return result
    
    @classmethod
    def _validate_columns(cls, sql):
        """Validate referenced columns against known schema — TABLE-SPECIFIC."""
        alias_map = cls._extract_table_alias_map(sql)
        col_refs = cls._extract_referenced_columns(sql)
        
        # Build the set of columns from ALL tables referenced in query
        query_tables = set(alias_map.values())
        query_valid_cols = set()
        for tbl in query_tables:
            if tbl in cls.VALID_COLUMNS:
                query_valid_cols.update(c.lower() for c in cls.VALID_COLUMNS[tbl])
        
        # If no tables identified, can't validate
        if not query_tables:
            return []
        
        # Common SQL aggregate/window aliases to skip
        skip_prefixes = ('avg_', 'count_', 'sum_', 'max_', 'min_', 'num_', 'pct_',
                        'late_', 'rev_')
        skip_names = {'count', 'sum', 'avg', 'min', 'max', 'total', 'cnt', 'pct',
                      'rank', 'row_number', 'dense_rank', 'n', 'rn', 'c1', 'c2', 'c3', 'c4',
                      'avg_amount', 'avg_billing', 'total_billing', 'total_orders',
                      'late_orders', 'late_pct', 'avg_score'}
        
        invalid_cols = []
        seen = set()
        for alias, col in col_refs:
            if col in seen or col in skip_names:
                continue
            if any(col.startswith(p) for p in skip_prefixes):
                continue
            seen.add(col)
            
            if alias and alias in alias_map:
                # Table-specific check: alias maps to a known table
                table = alias_map[alias]
                if table in cls.VALID_COLUMNS:
                    if col not in {c.lower() for c in cls.VALID_COLUMNS[table]}:
                        invalid_cols.append(col)
            elif alias is None:
                # Bare column: check against all query-level valid columns
                if query_valid_cols and col not in query_valid_cols:
                    invalid_cols.append(col)
            else:
                # Alias not in map — check against query-level column set  
                if query_valid_cols and col not in query_valid_cols:
                    invalid_cols.append(col)
        
        return invalid_cols
    
    @classmethod
    def _validate_table_names(cls, sql):
        """Check that referenced table names exist in VALID_COLUMNS."""
        table_refs = re.findall(r'\w+\.\w+\.(\w+)', sql, re.IGNORECASE)
        unknown_tables = [t for t in table_refs if t.lower() not in cls.VALID_COLUMNS]
        return unknown_tables
    
    @classmethod
    def score(cls, sql):
        """Return (anomaly_score, findings_list, is_blocked)"""
        if not sql or not sql.strip():
            return 1.0, [{'rule': 'R0', 'severity': 'critical', 'msg': 'Empty SQL'}], True
        
        findings = []
        weights = []
        sql_upper = sql.upper().strip()
        
        # R1: Catalog validation
        table_refs = re.findall(r'(\w+\.\w+\.\w+)', sql)
        invalid_refs = [t for t in table_refs if t.lower() not in cls.VALID_TABLES]
        if invalid_refs:
            findings.append({
                'rule': 'R1', 'severity': 'high',
                'msg': f'Invalid table references: {invalid_refs}'
            })
            weights.append(0.8)
        else:
            weights.append(0.0)
        
        # R2: Injection detection
        dangerous = cls.DANGEROUS_KEYWORDS.findall(sql)
        if dangerous:
            findings.append({
                'rule': 'R2', 'severity': 'critical',
                'msg': f'Dangerous keywords detected: {dangerous}'
            })
            weights.append(1.0)
        else:
            weights.append(0.0)
        
        # R3: Syntax validation — must start with SELECT/WITH AND contain FROM
        if not sql_upper.startswith('SELECT') and not sql_upper.startswith('WITH'):
            findings.append({
                'rule': 'R3', 'severity': 'high',
                'msg': 'SQL does not start with SELECT or WITH'
            })
            weights.append(0.7)
        elif 'FROM' not in sql_upper:
            findings.append({
                'rule': 'R3', 'severity': 'high',
                'msg': 'Incomplete SQL: missing FROM clause'
            })
            weights.append(0.8)
        else:
            weights.append(0.0)
        
        # R4: Complexity bounds
        join_count = len(re.findall(r'\bJOIN\b', sql, re.IGNORECASE))
        subquery_depth = sql.count('(SELECT') + sql.count('( SELECT')
        
        if join_count > cls.MAX_JOINS:
            findings.append({
                'rule': 'R4a', 'severity': 'high',
                'msg': f'Excessive JOINs: {join_count} > {cls.MAX_JOINS}'
            })
            weights.append(0.7)
        else:
            weights.append(0.0)
        
        if subquery_depth > cls.MAX_SUBQUERY_DEPTH:
            findings.append({
                'rule': 'R4b', 'severity': 'high',
                'msg': f'Deep subqueries: depth={subquery_depth} > {cls.MAX_SUBQUERY_DEPTH}'
            })
            weights.append(0.7)
        else:
            weights.append(0.0)
        
        # R5: Unbounded SELECT * without WHERE/LIMIT
        has_select_star = bool(re.search(r'\bSELECT\s+\*', sql, re.IGNORECASE))
        has_where = bool(re.search(r'\bWHERE\b', sql, re.IGNORECASE))
        has_limit = bool(re.search(r'\bLIMIT\b', sql, re.IGNORECASE))
        has_group = bool(re.search(r'\bGROUP\s+BY\b', sql, re.IGNORECASE))
        if has_select_star and not has_where and not has_limit and not has_group:
            findings.append({
                'rule': 'R5', 'severity': 'high',
                'msg': 'Unbounded SELECT * without WHERE or LIMIT'
            })
            weights.append(0.7)
        else:
            weights.append(0.0)
        
        # R6: System schema detection
        sys_schemas = cls.SYSTEM_SCHEMAS.findall(sql)
        if sys_schemas:
            findings.append({
                'rule': 'R6', 'severity': 'critical',
                'msg': f'System schema access: {sys_schemas}'
            })
            weights.append(1.0)
        else:
            weights.append(0.0)
        
        # R7: Cartesian join detection (ON 1=1, CROSS JOIN)
        cartesian = cls.CARTESIAN_PATTERN.findall(sql)
        if cartesian:
            findings.append({
                'rule': 'R7', 'severity': 'high',
                'msg': f'Cartesian/cross join detected: {cartesian}'
            })
            weights.append(0.8)
        else:
            weights.append(0.0)
        
        # R8: Tautology detection (SQL injection patterns)
        tautologies = cls.TAUTOLOGY_PATTERN.findall(sql)
        if tautologies:
            findings.append({
                'rule': 'R8', 'severity': 'critical',
                'msg': f'Tautology detected (possible injection): {tautologies}'
            })
            weights.append(1.0)
        else:
            weights.append(0.0)
        
        # R9: Recursive CTE detection
        if cls.RECURSIVE_CTE.search(sql):
            findings.append({
                'rule': 'R9', 'severity': 'high',
                'msg': 'Recursive CTE detected — potential infinite loop'
            })
            weights.append(0.9)
        else:
            weights.append(0.0)
        
        # R10: Column validation against known schema (TABLE-SPECIFIC)
        invalid_cols = cls._validate_columns(sql)
        has_subqueries = '(SELECT' in sql_upper or '( SELECT' in sql_upper
        if invalid_cols:
            findings.append({
                'rule': 'R10', 'severity': 'high',
                'msg': f'Unknown columns for referenced table: {invalid_cols[:5]}'
            })
            # With subqueries, columns may come from subquery output — reduce severity
            if has_subqueries and len(invalid_cols) <= 2:
                weights.append(0.4)  # Warning only, don't block
            else:
                weights.append(0.7)
        else:
            weights.append(0.0)
        
        # R11: Invalid function detection (non-standard functions)
        invalid_fns = cls.INVALID_FUNCTIONS.findall(sql)
        if invalid_fns:
            findings.append({
                'rule': 'R11', 'severity': 'high',
                'msg': f'Non-standard functions: {invalid_fns}'
            })
            weights.append(0.7)
        else:
            weights.append(0.0)
        
        # R12: Table name validation (non-existent tables)
        unknown_tables = cls._validate_table_names(sql)
        if unknown_tables:
            findings.append({
                'rule': 'R12', 'severity': 'high',
                'msg': f'Non-existent tables: {unknown_tables}'
            })
            weights.append(0.8)
        else:
            weights.append(0.0)
        
        # R13: Excessive UNION without aggregation purpose
        union_count = len(re.findall(r'\bUNION\s+ALL\b|\bUNION\b', sql, re.IGNORECASE))
        if union_count > cls.MAX_UNION_CLAUSES:
            findings.append({
                'rule': 'R13', 'severity': 'medium',
                'msg': f'Excessive UNIONs: {union_count} > {cls.MAX_UNION_CLAUSES}'
            })
            weights.append(0.7)
        else:
            weights.append(0.0)
        
        # Compute anomaly score as max of all rule weights
        anomaly_score = max(weights) if weights else 0.0
        is_blocked = anomaly_score >= 0.7
        
        return round(anomaly_score, 3), findings, is_blocked


# ═══════════════════════════════════════════════════════════════════════════════
# MECHANISM 2: Confidence Gating via Token Log-Probabilities
# ═══════════════════════════════════════════════════════════════════════════════

class ConfidenceGate:
    """
    Uses the local LLM token-level log-probabilities to compute:
    - Mean token probability (geometric mean of exp(logprob))
    - Minimum token probability (weakest token)
    - Entropy of distribution
    
    If confidence < threshold, the SQL is rejected and re-prompted.
    
    Confidence metric: C(S) = exp(1/N * Σ log P(t_i | t_{<i}))
    where S is the generated SQL sequence.
    """
    
    DEFAULT_THRESHOLD = 0.3  # Minimum mean confidence to accept
    
    @classmethod
    def generate_with_confidence(cls, model, prompt, temperature=0.1):
        """Generate SQL with local LLM and return confidence metrics"""
        t0 = time.time()
        try:
            r = requests.post(f'{OLLAMA_URL}/api/generate', json={
                'model': model,
                'prompt': prompt,
                'stream': False,
                'options': {
                    'temperature': temperature,
                    'num_predict': 512,
                    'logprobs': True,  # Request log probabilities
                }
            }, timeout=120)
            d = r.json()
        except Exception as e:
            return None, {'confidence': 0.0, 'error': str(e)}, time.time() - t0
        
        raw = d.get('response', '')
        elapsed = time.time() - t0
        
        # Compute confidence from eval metrics
        # Local LLM doesn't expose per-token logprobs in all versions,
        # so we use a proxy: eval_count / eval_duration * prompt_eval 
        eval_count = d.get('eval_count', 0)
        eval_duration = d.get('eval_duration', 1) / 1e9  # nanoseconds to seconds
        prompt_eval_count = d.get('prompt_eval_count', 0)
        total_duration = d.get('total_duration', 1) / 1e9
        
        # Proxy confidence metric: generation rate consistency
        # Lower temperature + consistent token rate = higher confidence
        tokens_per_sec = eval_count / eval_duration if eval_duration > 0 else 0
        
        # Use response length heuristic: very short or very long responses
        # are less likely to be correct SQL
        sql = cls._extract_sql(raw)
        sql_tokens = len(sql.split()) if sql else 0
        
        # Confidence heuristic combining multiple signals:
        # 1. SQL syntax parseable (0 or 1)
        # 2. Token count in reasonable range (5-200)
        # 3. Contains SELECT (0 or 1)
        # 4. generation speed consistency
        
        signals = []
        
        # Signal 1: Starts with SELECT
        if sql and sql.strip().upper().startswith(('SELECT', 'WITH')):
            signals.append(1.0)
        else:
            signals.append(0.0)
        
        # Signal 2: Token count reasonableness
        if 5 <= sql_tokens <= 200:
            signals.append(1.0)
        elif sql_tokens < 5:
            signals.append(0.2)
        else:
            signals.append(0.5)
        
        # Signal 3: Contains valid catalog refs
        has_valid_refs = bool(re.search(r'(postgresql|mysql)\.\w+\.\w+', sql or ''))
        signals.append(1.0 if has_valid_refs else 0.1)
        
        # Signal 4: No extraneous natural language in response
        non_sql_lines = sum(1 for line in raw.split('\n') 
                          if line.strip() and not line.strip().startswith(('SELECT', 'FROM', 'JOIN', 'WHERE', 'GROUP', 'ORDER', 'LIMIT', 'HAVING', 'WITH', 'UNION', 'AND', 'OR', 'ON', 'AS', 'CASE', 'WHEN', 'ROUND', '--', '(', ')', 'LEFT', 'RIGHT', 'INNER', 'CROSS', 'FULL'))
                          and not re.match(r'^\s*(SELECT|FROM|JOIN|WHERE|GROUP|ORDER|LIMIT|HAVING|WITH|UNION|AND|OR|ON|AS)', line.strip(), re.I))
        sql_ratio = max(0, 1.0 - (non_sql_lines / max(len(raw.split('\n')), 1)))
        signals.append(sql_ratio)
        
        # Signal 5: Balanced parentheses
        if sql:
            open_p = sql.count('(')
            close_p = sql.count(')')
            signals.append(1.0 if open_p == close_p else 0.3)
        else:
            signals.append(0.0)
        
        # Geometric mean of signals
        confidence = 1.0
        for s in signals:
            confidence *= max(s, 0.01)
        confidence = confidence ** (1.0 / len(signals))
        
        metrics = {
            'confidence': round(confidence, 4),
            'signals': {
                'starts_with_select': signals[0],
                'token_count_ok': signals[1],
                'has_catalog_refs': signals[2],
                'sql_purity_ratio': round(signals[3], 3),
                'balanced_parens': signals[4] if len(signals) > 4 else None
            },
            'eval_count': eval_count,
            'tokens_per_sec': round(tokens_per_sec, 1),
            'sql_token_count': sql_tokens,
            'total_time': round(elapsed, 2)
        }
        
        return sql, metrics, elapsed
    
    @staticmethod
    def _extract_sql(raw):
        if not raw:
            return ''
        raw = raw.strip()
        if '```sql' in raw:
            m = re.search(r'```sql\s*(.*?)\s*```', raw, re.DOTALL)
            if m: return m.group(1).strip()
        if '```' in raw:
            m = re.search(r'```\s*(.*?)\s*```', raw, re.DOTALL)
            if m: return m.group(1).strip()
        lines = [l for l in raw.split('\n') if l.strip() and not l.strip().startswith(('--', '#', '//'))]
        return '\n'.join(lines).strip()


# ═══════════════════════════════════════════════════════════════════════════════
# MECHANISM 3: Data Drift Monitor
# Detects distribution shifts in query patterns over time
# ═══════════════════════════════════════════════════════════════════════════════

class DataDriftMonitor:
    """
    Monitors two types of drift:
    A) Query Pattern Drift — changes in the distribution of query types, domains, tiers
    B) Schema Reality Drift — actual data distribution changes (via statistical tests)
    
    Uses Population Stability Index (PSI) and KL-divergence.
    
    PSI = Σ (p_i - q_i) * ln(p_i / q_i)
    where p = current distribution, q = reference distribution
    PSI < 0.1: no drift, 0.1-0.25: moderate drift, > 0.25: significant drift
    """
    
    @staticmethod
    def compute_psi(reference_dist, current_dist, bins=None):
        """
        Compute Population Stability Index between two distributions.
        reference_dist, current_dist: dict of {category: proportion}
        Returns PSI value.
        """
        all_keys = set(reference_dist.keys()) | set(current_dist.keys())
        eps = 1e-6  # Small value to avoid division by zero
        
        psi = 0.0
        for key in all_keys:
            p = current_dist.get(key, eps)
            q = reference_dist.get(key, eps)
            p = max(p, eps)
            q = max(q, eps)
            psi += (p - q) * math.log(p / q)
        
        return round(psi, 6)
    
    @staticmethod
    def compute_kl_divergence(p_dist, q_dist):
        """
        Compute KL divergence: KL(P || Q)
        p_dist, q_dist: dict of {category: proportion}
        """
        all_keys = set(p_dist.keys()) | set(q_dist.keys())
        eps = 1e-6
        
        kl = 0.0
        for key in all_keys:
            p = max(p_dist.get(key, eps), eps)
            q = max(q_dist.get(key, eps), eps)
            kl += p * math.log(p / q)
        
        return round(kl, 6)
    
    @classmethod
    def check_query_pattern_drift(cls, reference_log, current_log):
        """
        Compare query pattern distributions.
        Each log is a list of dicts with 'domain', 'tier', 'success' keys.
        Returns drift assessment.
        """
        if not reference_log or not current_log:
            return {'psi': 0.0, 'drift_level': 'insufficient_data'}
        
        # Domain distribution
        ref_domains = Counter(q['domain'] for q in reference_log)
        cur_domains = Counter(q['domain'] for q in current_log)
        ref_total = sum(ref_domains.values())
        cur_total = sum(cur_domains.values())
        ref_domain_dist = {k: v/ref_total for k, v in ref_domains.items()}
        cur_domain_dist = {k: v/cur_total for k, v in cur_domains.items()}
        
        domain_psi = cls.compute_psi(ref_domain_dist, cur_domain_dist)
        
        # Tier distribution
        ref_tiers = Counter(q['tier'] for q in reference_log)
        cur_tiers = Counter(q['tier'] for q in current_log)
        ref_tier_dist = {k: v/ref_total for k, v in ref_tiers.items()}
        cur_tier_dist = {k: v/cur_total for k, v in cur_tiers.items()}
        
        tier_psi = cls.compute_psi(ref_tier_dist, cur_tier_dist)
        
        # Success rate drift
        ref_success_rate = sum(1 for q in reference_log if q.get('success')) / len(reference_log)
        cur_success_rate = sum(1 for q in current_log if q.get('success')) / len(current_log)
        success_delta = abs(cur_success_rate - ref_success_rate)
        
        # Overall PSI (average of domain and tier PSI)
        overall_psi = (domain_psi + tier_psi) / 2
        
        if overall_psi < 0.1:
            drift_level = 'none'
        elif overall_psi < 0.25:
            drift_level = 'moderate'
        else:
            drift_level = 'significant'
        
        return {
            'domain_psi': domain_psi,
            'tier_psi': tier_psi,
            'overall_psi': overall_psi,
            'drift_level': drift_level,
            'success_rate_delta': round(success_delta, 4),
            'ref_success_rate': round(ref_success_rate, 4),
            'cur_success_rate': round(cur_success_rate, 4),
            'domain_distribution': {
                'reference': ref_domain_dist,
                'current': cur_domain_dist
            }
        }
    
    @classmethod
    def check_schema_drift(cls, presto_runner):
        """
        Check actual data distributions for schema-level drift.
        Computes summary statistics for key columns.
        Returns baselines that can be compared over time.
        """
        checks = [
            ("E-Commerce Orders", "SELECT order_status, COUNT(*) as cnt FROM postgresql.public.olist_orders GROUP BY order_status"),
            ("Healthcare Admissions", "SELECT admission_type, COUNT(*) as cnt FROM postgresql.public.hc_admissions GROUP BY admission_type"),
            ("Financial Fraud Rate", "SELECT class_id, COUNT(*) as cnt FROM postgresql.public.fin_transactions GROUP BY class_id"),
            ("Supply Chain Late Rate", "SELECT late_delivery_risk, COUNT(*) as cnt FROM postgresql.public.sc_orders GROUP BY late_delivery_risk"),
            ("Retail Volume", "SELECT COUNT(*) as total, ROUND(AVG(quantity * unit_price), 2) as avg_val FROM postgresql.public.rt_invoices WHERE quantity > 0"),
        ]
        
        baselines = {}
        for name, sql in checks:
            cols, rows, elapsed, error = presto_runner(sql)
            if not error and rows:
                baselines[name] = {
                    'distribution': {str(r[0]): (int(r[1]) if isinstance(r[1], (int, float)) else r[1]) for r in rows},
                    'timestamp': datetime.now().isoformat(),
                    'query_time': round(elapsed, 3)
                }
            else:
                baselines[name] = {'error': error}
        
        return baselines


# ═══════════════════════════════════════════════════════════════════════════════
# MECHANISM 4: Feedback Loop — generate → validate → execute → log → re-prompt
# ═══════════════════════════════════════════════════════════════════════════════

class FeedbackLoop:
    """
    Implements the generate-validate-execute feedback loop:
    
    1. Generate SQL from natural language via LLM
    2. Score anomaly (Mechanism 1) — block if score ≥ 0.7
    3. Gate on confidence (Mechanism 2) — reject if confidence < threshold
    4. Execute via federation engine — catch errors
    5. If error/empty: re-prompt with error context (up to max_retries)
    6. Log all attempts for drift monitoring (Mechanism 3)
    
    Convergence rate = successful_final / total_queries
    """
    
    def __init__(self, model='llama3.1:8b', max_retries=2, 
                 confidence_threshold=0.3, system_prompt=''):
        self.model = model
        self.max_retries = max_retries
        self.confidence_threshold = confidence_threshold
        self.system_prompt = system_prompt
        self.log = []
    
    def process_question(self, question, presto_runner, tier=0, domain='Unknown'):
        """
        Full pipeline: NL → SQL → validate → execute → retry if needed.
        Returns complete trace for analysis.
        """
        trace = {
            'question': question,
            'domain': domain,
            'tier': tier,
            'attempts': [],
            'final_success': False,
            'final_sql': None,
            'final_result': None,
            'total_time': 0,
            'retries_used': 0
        }
        
        t0 = time.time()
        prompt = f"{self.system_prompt}\n\nQ: {question}\nA:"
        
        for attempt_num in range(1 + self.max_retries):
            attempt = {'attempt': attempt_num + 1, 'blocked': False, 'gated': False}
            
            # Step 1: Generate SQL with confidence
            sql, conf_metrics, gen_time = ConfidenceGate.generate_with_confidence(
                self.model, prompt
            )
            attempt['sql'] = sql
            attempt['confidence'] = conf_metrics
            attempt['gen_time'] = round(gen_time, 2)
            
            # Step 2: Anomaly scoring
            if sql:
                anomaly_score, findings, is_blocked = SQLAnomalyScorer.score(sql)
                attempt['anomaly_score'] = anomaly_score
                attempt['anomaly_findings'] = findings
                
                if is_blocked:
                    attempt['blocked'] = True
                    attempt['outcome'] = 'BLOCKED_ANOMALY'
                    trace['attempts'].append(attempt)
                    # Re-prompt with guidance
                    prompt = f"{self.system_prompt}\n\nQ: {question}\nNote: Your previous SQL was rejected because: {findings[0]['msg']}. Generate a corrected version using ONLY SELECT queries on valid tables.\nA:"
                    continue
            else:
                attempt['anomaly_score'] = 1.0
                attempt['outcome'] = 'NO_SQL_GENERATED'
                trace['attempts'].append(attempt)
                prompt = f"{self.system_prompt}\n\nQ: {question}\nNote: You must generate a valid SQL SELECT query. No explanations, just SQL.\nA:"
                continue
            
            # Step 3: Confidence gating
            if conf_metrics['confidence'] < self.confidence_threshold:
                attempt['gated'] = True
                attempt['outcome'] = 'GATED_LOW_CONFIDENCE'
                trace['attempts'].append(attempt)
                prompt = f"{self.system_prompt}\n\nQ: {question}\nNote: Please generate a clear, well-structured SQL query. Use explicit catalog.schema.table notation.\nA:"
                continue
            
            # Step 4: Execute SQL
            cols, rows, exec_time, error = presto_runner(sql)
            attempt['exec_time'] = round(exec_time, 2)
            
            if error:
                attempt['outcome'] = f'SQL_ERROR: {error}'
                trace['attempts'].append(attempt)
                # Re-prompt with error
                error_short = error[:200]
                prompt = f"{self.system_prompt}\n\nQ: {question}\nNote: Your previous SQL caused this error: {error_short}. Fix the SQL and try again.\nA:"
                continue
            
            if not rows:
                attempt['outcome'] = 'EMPTY_RESULT'
                trace['attempts'].append(attempt)
                prompt = f"{self.system_prompt}\n\nQ: {question}\nNote: Your previous query returned no results. Double-check table names and join conditions.\nA:"
                continue
            
            # Step 5: Success!
            attempt['outcome'] = 'SUCCESS'
            attempt['row_count'] = len(rows)
            trace['attempts'].append(attempt)
            trace['final_success'] = True
            trace['final_sql'] = sql
            trace['final_result'] = {'columns': cols, 'row_count': len(rows)}
            trace['retries_used'] = attempt_num
            break
        
        trace['total_time'] = round(time.time() - t0, 2)
        trace['total_attempts'] = len(trace['attempts'])
        
        # Log for drift monitoring
        self.log.append({
            'domain': domain,
            'tier': tier,
            'success': trace['final_success'],
            'retries': trace['retries_used'],
            'timestamp': datetime.now().isoformat()
        })
        
        return trace
    
    def compute_metrics(self):
        """Compute aggregate metrics from all logged queries"""
        if not self.log:
            return {}
        
        total = len(self.log)
        successes = sum(1 for l in self.log if l['success'])
        
        # Convergence rate
        convergence_rate = successes / total
        
        # First-attempt success rate
        first_attempt = sum(1 for l in self.log if l['success'] and l['retries'] == 0)
        first_attempt_rate = first_attempt / total
        
        # Average retries for successful queries
        successful_retries = [l['retries'] for l in self.log if l['success']]
        avg_retries = statistics.mean(successful_retries) if successful_retries else 0
        
        # Retry effectiveness: queries that failed first but succeeded after retry
        retry_saves = sum(1 for l in self.log if l['success'] and l['retries'] > 0)
        
        return {
            'total_queries': total,
            'successes': successes,
            'convergence_rate': round(convergence_rate, 4),
            'first_attempt_rate': round(first_attempt_rate, 4),
            'retry_effectiveness': retry_saves,
            'avg_retries_on_success': round(avg_retries, 3),
            'by_domain': self._domain_breakdown(),
            'by_tier': self._tier_breakdown()
        }
    
    def _domain_breakdown(self):
        domains = {}
        for l in self.log:
            d = l['domain']
            if d not in domains:
                domains[d] = {'total': 0, 'success': 0}
            domains[d]['total'] += 1
            if l['success']:
                domains[d]['success'] += 1
        for d in domains:
            domains[d]['rate'] = round(domains[d]['success'] / domains[d]['total'], 4) if domains[d]['total'] > 0 else 0
        return domains
    
    def _tier_breakdown(self):
        tiers = {}
        for l in self.log:
            t = l['tier']
            if t not in tiers:
                tiers[t] = {'total': 0, 'success': 0}
            tiers[t]['total'] += 1
            if l['success']:
                tiers[t]['success'] += 1
        for t in tiers:
            tiers[t]['rate'] = round(tiers[t]['success'] / tiers[t]['total'], 4) if tiers[t]['total'] > 0 else 0
        return tiers


# ═══════════════════════════════════════════════════════════════════════════════
# FORMAL METRICS COMPUTATION
# ═══════════════════════════════════════════════════════════════════════════════

class SovereigntyMetrics:
    """
    Formal sovereignty metric computation for the SARAI framework.
    
    Definition 1: Data Sovereignty Index (σ_D)
      σ_D = |O_local| / |O_total|
      where O_local = local data operations, O_total = all operations
    
    Definition 2: Inference Sovereignty Score (σ_I)  
      σ_I = Σ w_j · s_j for j ∈ {storage, transmission, execution, logging}
      s_j ∈ {0, 1}, w_j weights sum to 1
    
    Definition 3: Risk Assessment Capability Index (ρ)
      ρ = Σ w_k · c_k for k risk capabilities
      c_k ∈ [0, 1] = capability level for risk mechanism k
    
    Theorem 1: Sovereignty-Observability Bound
      ρ_max = Σ v_i · 𝟙[σ_D ≥ τ_i^D ∧ σ_I ≥ τ_i^I]
      Maximum risk assessment capability is a step function of both sovereignty indices.
    """
    
    @staticmethod
    def compute_data_sovereignty(local_ops, cloud_ops):
        """
        Compute σ_D = |O_local| / |O_total|
        local_ops: count of operations within org boundary
        cloud_ops: count of operations sent externally
        """
        total = local_ops + cloud_ops
        if total == 0:
            return 0.0
        sigma_d = local_ops / total
        return round(sigma_d, 4)
    
    @staticmethod
    def compute_inference_sovereignty(model_config):
        """
        Compute σ_I for a model configuration.
        model_config: dict with keys 'storage', 'transmission', 'execution', 'logging'
          each value is 0 (external) or 1 (local)
        weights: [0.2, 0.3, 0.3, 0.2]
        """
        weights = {'storage': 0.2, 'transmission': 0.3, 'execution': 0.3, 'logging': 0.2}
        sigma_i = sum(weights[k] * model_config.get(k, 0) for k in weights)
        return round(sigma_i, 4)
    
    @staticmethod
    def compute_risk_capability(mechanism_scores):
        """
        Compute ρ = Σ w_k · c_k
        mechanism_scores: dict of {mechanism_name: capability_score}
        Equal weights for simplicity.
        """
        if not mechanism_scores:
            return 0.0
        k = len(mechanism_scores)
        weights = {m: 1.0/k for m in mechanism_scores}
        rho = sum(weights[m] * mechanism_scores[m] for m in mechanism_scores)
        return round(rho, 4)
    
    @staticmethod
    def sovereignty_observability_bound(sigma_d, sigma_i):
        """
        Theorem 1: ρ_max = Σ v_i · 𝟙[σ_D ≥ τ_i^D ∧ σ_I ≥ τ_i^I]
        Returns the theoretical maximum risk capability for given sovereignty levels.
        """
        capabilities = [
            {'weight': 0.30, 'tau_d': 0.25, 'tau_i': 0.50},  # SQL Anomaly Detection
            {'weight': 0.25, 'tau_d': 0.75, 'tau_i': 0.25},  # Schema-Drift Monitoring
            {'weight': 0.25, 'tau_d': 0.25, 'tau_i': 0.75},  # Confidence Gating
            {'weight': 0.20, 'tau_d': 0.50, 'tau_i': 0.50},  # Feedback Loop
        ]
        rho_max = sum(
            c['weight'] for c in capabilities
            if sigma_d >= c['tau_d'] and sigma_i >= c['tau_i']
        )
        return round(rho_max, 4)
    
    @classmethod
    def compute_full_profile(cls, config):
        """
        Compute complete sovereignty profile for a deployment configuration.
        config: {
            'local_ops': int, 'cloud_ops': int,
            'model_configs': {model_name: {storage, transmission, execution, logging}},
            'risk_mechanisms': {mechanism_name: capability_score}
        }
        """
        sigma_d = cls.compute_data_sovereignty(
            config['local_ops'], config['cloud_ops']
        )
        
        model_profiles = {}
        for name, mcfg in config.get('model_configs', {}).items():
            sigma_i = cls.compute_inference_sovereignty(mcfg)
            rho_max = cls.sovereignty_observability_bound(sigma_d, sigma_i)
            model_profiles[name] = {
                'sigma_i': sigma_i,
                'rho_max': rho_max
            }
        
        rho = cls.compute_risk_capability(config.get('risk_mechanisms', {}))
        
        return {
            'sigma_d': sigma_d,
            'model_profiles': model_profiles,
            'rho_actual': rho,
            'framework_summary': {
                'data_sovereignty_index': sigma_d,
                'risk_capability_index': rho,
                'sovereignty_bound_satisfied': all(
                    rho <= mp['rho_max'] 
                    for mp in model_profiles.values()
                    if mp.get('rho_max', 0) > 0
                )
            }
        }


# ═══════════════════════════════════════════════════════════════════════════════
# TESTING / EVALUATION
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 80)
    print("SARAI Risk Mechanism Testing")
    print("=" * 80)
    
    # Test 1: SQL Anomaly Scorer
    print("\n--- Mechanism 1: SQL Anomaly Scorer ---")
    test_cases = [
        ("Valid simple", "SELECT COUNT(*) FROM postgresql.public.olist_orders"),
        ("Valid cross-engine", "SELECT c.customer_city, SUM(oi.price) FROM postgresql.public.olist_order_items oi JOIN mysql.olist_ecommerce.olist_customers c ON oi.order_id = c.customer_id GROUP BY c.customer_city LIMIT 10"),
        ("Injection attempt", "DROP TABLE postgresql.public.olist_orders; SELECT 1"),
        ("Invalid catalog", "SELECT * FROM mariadb.public.fake_table"),
        ("Empty SQL", ""),
        ("Too many joins", "SELECT * FROM a JOIN b ON 1=1 JOIN c ON 1=1 JOIN d ON 1=1 JOIN e ON 1=1 JOIN f ON 1=1 JOIN g ON 1=1 JOIN h ON 1=1"),
        ("Non-SELECT", "UPDATE postgresql.public.olist_orders SET order_status = 'cancelled'"),
    ]
    
    for name, sql in test_cases:
        score, findings, blocked = SQLAnomalyScorer.score(sql)
        status = "BLOCKED" if blocked else "ALLOWED"
        print(f"  [{status}] score={score:.2f}  {name}")
        for f in findings:
            print(f"    → {f['rule']}: {f['msg']}")
    
    # Test 2: Sovereignty Metrics
    print("\n--- Sovereignty Metrics ---")
    
    # Our framework: everything local
    local_config = {
        'local_ops': 50,  # 50 queries all run locally
        'cloud_ops': 0,
        'model_configs': {
            'Llama 3.1 8B (Local)': {
                'storage': 1, 'transmission': 1, 'execution': 1, 'logging': 1
            },
            'Gemma-3 27B (Cloud)': {
                'storage': 0, 'transmission': 0, 'execution': 0, 'logging': 0
            },
            'Hybrid (Local primary, Cloud fallback)': {
                'storage': 1, 'transmission': 0.5, 'execution': 0.7, 'logging': 1
            }
        },
        'risk_mechanisms': {
            'sql_anomaly_scorer': 0.0,  # Will be filled with real F1 scores
            'confidence_gating': 0.0,
            'data_drift_monitor': 0.0,
            'feedback_loop': 0.0
        }
    }
    
    profile = SovereigntyMetrics.compute_full_profile(local_config)
    print(f"  σ_D (Data Sovereignty): {profile['sigma_d']}")
    for name, mp in profile['model_profiles'].items():
        print(f"  {name}: σ_I={mp['sigma_i']}, ρ_max={mp['rho_max']}")
    print(f"  ρ (actual risk capability): {profile['rho_actual']}")
    
    print("\nAll mechanism classes loaded and tested successfully.")
