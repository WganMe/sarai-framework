#!/usr/bin/env python3
"""Deploy/Update the Context-Aware BI Framework unified workflow to the orchestration platform."""
import json
import urllib.request
import urllib.error

# Read API key from .env
API_KEY = None
with open('/var/www/.env') as f:
    for line in f:
        if line.startswith('WORKFLOW_API_KEY='):
            API_KEY = line.split('=', 1)[1].strip().strip('"')
            break

BASE = 'http://127.0.0.1:5678/api/v1'
WF_ID = 'zpJWWljIklNinXF4'

HANDLER_CODE = r'''
// ============================================================
// Context-Aware BI Framework — Unified API Handler v1.1
// POST /webhook/framework  { action, ...params }
// Actions: ask, health, stats, metrics, chat, compile, dashboards
// ============================================================
const axios = require('axios');

const input = $input.first().json;
const body = input.body || input;
const action = (body.action || 'help').toLowerCase().trim();
const ts = new Date().toISOString();

// ---- Helper: Federation engine query runner with timeout (accumulates all pages) ----
async function runPresto(sql, timeoutMs = 30000) {
  const resp = await axios.post('http://127.0.0.1:8080/v1/statement', sql, {
    headers: { 'X-Presto-User': 'framework', 'X-Presto-Catalog': 'postgresql', 'X-Presto-Schema': 'public', 'Content-Type': 'text/plain' },
    timeout: 10000
  });
  let data = resp.data;
  let allRows = data.data || [];
  let columns = (data.columns || []).map(c => c.name);
  const deadline = Date.now() + timeoutMs;
  while (data.nextUri) {
    if (Date.now() > deadline) throw new Error('Federation engine query timeout');
    await new Promise(r => setTimeout(r, 300));
    const poll = await axios.get(data.nextUri, { timeout: 10000 });
    data = poll.data;
    if (data.data) allRows = allRows.concat(data.data);
    if (!columns.length && data.columns) columns = data.columns.map(c => c.name);
  }
  if (data.error) throw new Error(data.error.message);
  return allRows.map(row => {
    const obj = {}; columns.forEach((c, i) => obj[c] = row[i]); return obj;
  });
}

// ---- Helper: Local LLM call ----
async function callLocalLLM(prompt, opts = {}) {
  const start = Date.now();
  const resp = await axios.post('http://127.0.0.1:11434/api/generate', {
    model: opts.model || 'llama3.1:8b', prompt, stream: false,
    options: { temperature: opts.temp || 0.1, ...(opts.num_predict ? {num_predict: opts.num_predict} : {}) }
  }, { timeout: 120000 });
  return { text: resp.data.response || '', time_ms: Date.now() - start };
}

// ---- Helper: Cloud LLM call ----
const OR_KEYS = [
  process.env.CLOUD_API_KEY_1 || '',
  process.env.CLOUD_API_KEY_3 || '',
  process.env.CLOUD_API_KEY_4 || '',
];
async function callCloudLLM(prompt, opts = {}) {
  const start = Date.now();
  const key = OR_KEYS[Math.floor(Math.random() * OR_KEYS.length)];
  const resp = await axios.post('https://openrouter.ai/api/v1/chat/completions', {
    model: opts.model || 'google/gemma-3-27b-it:free',
    messages: [{ role: 'user', content: prompt }],
    temperature: opts.temp || 0.1
  }, { headers: { 'Authorization': 'Bearer ' + key }, timeout: 60000 });
  return { text: resp.data.choices?.[0]?.message?.content || '', time_ms: Date.now() - start };
}

// ============================================================
// ACTION HANDLERS
// ============================================================

// ---- HELP ----
if (action === 'help') {
  return [{ json: {
    framework: 'Context-Aware BI Framework — Unified API',
    version: '1.1.0', timestamp: ts,
    endpoint: 'POST /webhook/framework',
    actions: {
      ask:        { params: 'question, model(auto|local|cloud)', desc: 'Text-to-SQL with sovereignty-aware dual-model routing' },
      health:     { params: 'none', desc: 'Check all 8 services health status' },
      stats:      { params: 'none', desc: 'Dataset statistics across 5 domains, 29 tables, 2 engines' },
      metrics:    { params: 'none', desc: 'Live framework performance benchmarks and AI accuracy' },
      chat:       { params: 'message, context(general|methodology|literature|thesis), model(local|cloud)', desc: 'AI research assistant for PhD guidance' },
      compile:    { params: 'target(article|thesis|proposal)', desc: 'LaTeX compilation with error reporting' },
      dashboards: { params: 'none', desc: 'Dashboard platform listing and status' }
    },
    examples: [
      '{"action":"ask","question":"Top 5 states by e-commerce revenue?"}',
      '{"action":"health"}',
      '{"action":"chat","message":"Explain DSR methodology phases"}',
      '{"action":"metrics"}',
      '{"action":"compile","target":"article"}'
    ]
  }}];
}

// ---- ASK (Text-to-SQL) ----
if (action === 'ask') {
  const question = body.question || 'What are the top 5 states by e-commerce revenue?';
  const modelPref = (body.model || 'auto').toLowerCase();

  const schema = "You write federated SQL queries. Output ONLY the SQL, nothing else.\n\nTwo catalogs: postgresql and mysql. Always use catalog.schema.table format.\n\nTables:\npostgresql.public.olist_orders(order_id, customer_id, order_status)\npostgresql.public.olist_order_items(order_id, product_id, seller_id, price, freight_value)\npostgresql.public.olist_order_payments(order_id, payment_type, payment_value)\npostgresql.public.olist_order_reviews(review_id, order_id, review_score, review_comment_message)\npostgresql.public.hc_admissions(admission_id, patient_name, age, gender, condition_id, doctor_id, hospital_id, insurance_id, billing_amount)\npostgresql.public.rt_invoices(invoice_id, invoice_no, stock_code, quantity, unit_price, customer_id)\npostgresql.public.fin_transactions(transaction_id, amount, class_id, time_hour)\npostgresql.public.sc_orders(order_row_id, order_id, customer_id, product_id, department_id, category_id, sales, order_profit, delivery_status)\nmysql.olist_ecommerce.olist_customers(customer_id, customer_state, customer_city)\nmysql.olist_ecommerce.olist_products(product_id, product_category_name)\nmysql.olist_ecommerce.olist_sellers(seller_id, seller_city, seller_state)\nmysql.olist_ecommerce.olist_geolocation(geolocation_zip_code_prefix, geolocation_lat, geolocation_lng, geolocation_city, geolocation_state)\nmysql.olist_ecommerce.product_category_translation(product_category_name, product_category_name_english)\nmysql.healthcare.hc_conditions(condition_id, condition_name)\nmysql.healthcare.hc_insurance(insurance_id, provider_name)\nmysql.healthcare.hc_hospitals(hospital_id, hospital_name)\nmysql.healthcare.hc_doctors(doctor_id, doctor_name, specialization)\nmysql.retail.rt_customers(customer_id, country)\nmysql.retail.rt_products(stock_code, description)\nmysql.financial.fin_fraud_classes(class_id, class_name)\nmysql.financial.fin_time_buckets(time_id, time_label)\nmysql.supply_chain.sc_customers(customer_id, segment, country)\nmysql.supply_chain.sc_products(product_id, product_name)\nmysql.supply_chain.sc_departments(department_id, department_name)\nmysql.supply_chain.sc_categories(category_id, category_name)\n\nCross-engine JOINs work in the federation engine. Example:\nQ: Total e-commerce revenue by customer state?\nSQL: SELECT c.customer_state, SUM(oi.price) AS revenue FROM postgresql.public.olist_order_items oi JOIN postgresql.public.olist_orders o ON oi.order_id = o.order_id JOIN mysql.olist_ecommerce.olist_customers c ON o.customer_id = c.customer_id GROUP BY c.customer_state ORDER BY revenue DESC\n\nQ: How many fraud cases?\nSQL: SELECT COUNT(*) FROM postgresql.public.fin_transactions t JOIN mysql.financial.fin_fraud_classes f ON t.class_id = f.class_id WHERE f.class_name = 'Fraudulent'\n\nQ: Total retail revenue by country?\nSQL: SELECT c.country, SUM(i.quantity * i.unit_price) AS revenue FROM postgresql.public.rt_invoices i JOIN mysql.retail.rt_customers c ON i.customer_id = c.customer_id GROUP BY c.country ORDER BY revenue DESC\n\nQ: Total supply chain sales by department?\nSQL: SELECT d.department_name, SUM(o.sales) AS total_sales FROM postgresql.public.sc_orders o JOIN mysql.supply_chain.sc_departments d ON o.department_id = d.department_id GROUP BY d.department_name ORDER BY total_sales DESC";

  const prompt = schema + '\n\nQuestion: ' + question + '\nSQL:';

  let genResult;
  try {
    if (modelPref === 'cloud') {
      const r = await callCloudLLM(prompt);
      genResult = { ...r, model: 'gemma-3-27b-it', source: 'cloud', sovereignty: false };
    } else if (modelPref === 'local') {
      const r = await callLocalLLM(prompt);
      genResult = { ...r, model: 'llama3.1:8b', source: 'local', sovereignty: true };
    } else {
      try {
        const r = await callLocalLLM(prompt);
        genResult = { ...r, model: 'llama3.1:8b', source: 'local', sovereignty: true };
      } catch(e) {
        const r = await callCloudLLM(prompt);
        genResult = { ...r, model: 'gemma-3-27b-it', source: 'cloud', sovereignty: false, fallback: true };
      }
    }
  } catch(e) {
    return [{ json: { action: 'ask', success: false, error: e.message, timestamp: ts } }];
  }

  let sql = genResult.text.replace(/```sql\n?/gi, '').replace(/```\n?/g, '').replace(/^\s*SQL:\s*/i, '').trim();
  if (sql.includes('\n')) { sql = sql.split('\n').filter(l => !l.startsWith('--') && l.trim()).join(' '); }

  try {
    const rows = await runPresto(sql);
    return [{ json: {
      action: 'ask', success: true, question, sql,
      model: genResult.model, source: genResult.source, sovereignty: genResult.sovereignty,
      generation_time_ms: genResult.time_ms, fallback: genResult.fallback || false,
      row_count: rows.length, results: rows.slice(0, 50), timestamp: ts
    }}];
  } catch(e) {
    return [{ json: {
      action: 'ask', success: false, question, sql,
      model: genResult.model, source: genResult.source,
      generation_time_ms: genResult.time_ms, error: 'Federation engine: ' + e.message, timestamp: ts
    }}];
  }
}

// ---- HEALTH ----
if (action === 'health') {
  const checks = [
    { name: 'WorkflowEngine',      url: 'http://127.0.0.1:5678/healthz' },
    { name: 'FederationEngine', url: 'http://127.0.0.1:8080/v1/info' },
    { name: 'DashboardPlatform', url: 'http://127.0.0.1:8088/health' },
    { name: 'LocalLLM',   url: 'http://127.0.0.1:11434/api/tags' },
    { name: 'Nginx',    url: 'http://127.0.0.1:80/' }
  ];
  const results = [];
  for (const svc of checks) {
    const start = Date.now();
    try {
      const resp = await axios.get(svc.url, { timeout: 5000 });
      const latency = Date.now() - start;
      let detail = {};
      if (svc.name === 'FederationEngine') { detail = { version: resp.data.nodeVersion?.version, uptime: resp.data.uptime }; }
      else if (svc.name === 'LocalLLM') { detail = { models: resp.data.models?.map(m => m.name) }; }
      else if (svc.name === 'DashboardPlatform') { detail = { response: typeof resp.data === 'string' ? resp.data.trim() : 'OK' }; }
      results.push({ service: svc.name, status: 'healthy', latency_ms: latency, ...detail });
    } catch(e) {
      results.push({ service: svc.name, status: 'down', error: (e.message || '').slice(0, 100) });
    }
  }

  // DB checks via federation engine
  for (const db of [{name:'PostgreSQL', sql:'SELECT 1'}, {name:'MariaDB', sql:"SELECT 1 FROM mysql.olist_ecommerce.olist_customers LIMIT 1"}]) {
    const start = Date.now();
    try { await runPresto(db.sql, 15000); results.push({service: db.name, status: 'healthy', latency_ms: Date.now()-start}); }
    catch(e) { results.push({service: db.name, status: 'down', latency_ms: Date.now()-start, error: (e.message||'').slice(0,100)}); }
  }

  // Redis
  try {
    const { execSync } = require('child_process');
    const start = Date.now();
    execSync('redis-cli -a "' + (process.env.REDIS_PASSWORD || '') + '" ping 2>/dev/null', {timeout: 3000});
    results.push({service: 'Redis', status: 'healthy', latency_ms: Date.now()-start});
  } catch(e) { results.push({service: 'Redis', status: 'down'}); }

  const healthy = results.filter(r => r.status === 'healthy').length;
  return [{ json: {
    action: 'health', timestamp: ts,
    summary: healthy + '/' + results.length + ' services healthy',
    overall: healthy === results.length ? 'ALL_HEALTHY' : 'DEGRADED',
    services: results
  }}];
}

// ---- STATS (optimized with batch UNION ALL queries) ----
if (action === 'stats') {
  // Use 5 batch queries instead of 25 individual ones
  const batchQueries = [
    { domain: 'E-Commerce (Olist)', sql: "SELECT 'olist_orders' AS tbl, CAST(COUNT(*) AS VARCHAR) AS cnt FROM postgresql.public.olist_orders UNION ALL SELECT 'olist_order_items', CAST(COUNT(*) AS VARCHAR) FROM postgresql.public.olist_order_items UNION ALL SELECT 'olist_order_payments', CAST(COUNT(*) AS VARCHAR) FROM postgresql.public.olist_order_payments UNION ALL SELECT 'olist_order_reviews', CAST(COUNT(*) AS VARCHAR) FROM postgresql.public.olist_order_reviews UNION ALL SELECT 'olist_customers', CAST(COUNT(*) AS VARCHAR) FROM mysql.olist_ecommerce.olist_customers UNION ALL SELECT 'olist_products', CAST(COUNT(*) AS VARCHAR) FROM mysql.olist_ecommerce.olist_products UNION ALL SELECT 'olist_sellers', CAST(COUNT(*) AS VARCHAR) FROM mysql.olist_ecommerce.olist_sellers UNION ALL SELECT 'olist_geolocation', CAST(COUNT(*) AS VARCHAR) FROM mysql.olist_ecommerce.olist_geolocation UNION ALL SELECT 'product_category_translation', CAST(COUNT(*) AS VARCHAR) FROM mysql.olist_ecommerce.product_category_translation" },
    { domain: 'Healthcare', sql: "SELECT 'hc_admissions' AS tbl, CAST(COUNT(*) AS VARCHAR) AS cnt FROM postgresql.public.hc_admissions UNION ALL SELECT 'hc_conditions', CAST(COUNT(*) AS VARCHAR) FROM mysql.healthcare.hc_conditions UNION ALL SELECT 'hc_insurance', CAST(COUNT(*) AS VARCHAR) FROM mysql.healthcare.hc_insurance UNION ALL SELECT 'hc_hospitals', CAST(COUNT(*) AS VARCHAR) FROM mysql.healthcare.hc_hospitals UNION ALL SELECT 'hc_doctors', CAST(COUNT(*) AS VARCHAR) FROM mysql.healthcare.hc_doctors" },
    { domain: 'Retail', sql: "SELECT 'rt_invoices' AS tbl, CAST(COUNT(*) AS VARCHAR) AS cnt FROM postgresql.public.rt_invoices UNION ALL SELECT 'rt_customers', CAST(COUNT(*) AS VARCHAR) FROM mysql.retail.rt_customers UNION ALL SELECT 'rt_products', CAST(COUNT(*) AS VARCHAR) FROM mysql.retail.rt_products" },
    { domain: 'Financial Fraud', sql: "SELECT 'fin_transactions' AS tbl, CAST(COUNT(*) AS VARCHAR) AS cnt FROM postgresql.public.fin_transactions UNION ALL SELECT 'fin_fraud_classes', CAST(COUNT(*) AS VARCHAR) FROM mysql.financial.fin_fraud_classes UNION ALL SELECT 'fin_time_buckets', CAST(COUNT(*) AS VARCHAR) FROM mysql.financial.fin_time_buckets" },
    { domain: 'Supply Chain', sql: "SELECT 'sc_orders' AS tbl, CAST(COUNT(*) AS VARCHAR) AS cnt FROM postgresql.public.sc_orders UNION ALL SELECT 'sc_customers', CAST(COUNT(*) AS VARCHAR) FROM mysql.supply_chain.sc_customers UNION ALL SELECT 'sc_products', CAST(COUNT(*) AS VARCHAR) FROM mysql.supply_chain.sc_products UNION ALL SELECT 'sc_departments', CAST(COUNT(*) AS VARCHAR) FROM mysql.supply_chain.sc_departments UNION ALL SELECT 'sc_categories', CAST(COUNT(*) AS VARCHAR) FROM mysql.supply_chain.sc_categories" }
  ];

  let totalRows = 0;
  let tableCount = 0;
  const domainResults = [];

  for (const batch of batchQueries) {
    try {
      const rows = await runPresto(batch.sql, 45000);
      const tables = rows.map(r => ({ table: r.tbl, rows: parseInt(r.cnt || '0') }));
      const domainTotal = tables.reduce((s, t) => s + t.rows, 0);
      totalRows += domainTotal;
      tableCount += tables.length;
      domainResults.push({ domain: batch.domain, tables, total_rows: domainTotal });
    } catch(e) {
      domainResults.push({ domain: batch.domain, error: (e.message||'').slice(0, 200) });
    }
  }

  return [{ json: {
    action: 'stats', timestamp: ts,
    summary: { total_tables: tableCount, total_rows: totalRows, domains: batchQueries.length, engines: ['PostgreSQL','MariaDB'], federation: 'federation_engine' },
    datasets: domainResults
  }}];
}

// ---- METRICS ----
if (action === 'metrics') {
  const benchmarks = [
    { name: 'Single-Engine (PG)', sql: "SELECT order_status, COUNT(*) AS cnt FROM postgresql.public.olist_orders GROUP BY order_status" },
    { name: 'Single-Engine (MySQL)', sql: "SELECT customer_state, COUNT(*) AS cnt FROM mysql.olist_ecommerce.olist_customers GROUP BY customer_state ORDER BY cnt DESC LIMIT 5" },
    { name: 'Cross-Engine Federation', sql: "SELECT c.customer_state, SUM(oi.price) AS revenue FROM postgresql.public.olist_order_items oi JOIN postgresql.public.olist_orders o ON oi.order_id = o.order_id JOIN mysql.olist_ecommerce.olist_customers c ON o.customer_id = c.customer_id GROUP BY c.customer_state ORDER BY revenue DESC LIMIT 5" },
    { name: 'Cross-Domain Federation', sql: "SELECT 'E-Commerce' AS domain, COUNT(*) AS records FROM postgresql.public.olist_orders UNION ALL SELECT 'Healthcare', COUNT(*) FROM postgresql.public.hc_admissions UNION ALL SELECT 'Retail', COUNT(*) FROM postgresql.public.rt_invoices UNION ALL SELECT 'Financial', COUNT(*) FROM postgresql.public.fin_transactions UNION ALL SELECT 'Supply Chain', COUNT(*) FROM postgresql.public.sc_orders" },
    { name: 'Complex Aggregation', sql: "SELECT p.product_category_name, COUNT(DISTINCT o.order_id) AS orders, SUM(oi.price) AS revenue FROM postgresql.public.olist_order_items oi JOIN postgresql.public.olist_orders o ON oi.order_id = o.order_id JOIN mysql.olist_ecommerce.olist_products p ON oi.product_id = p.product_id GROUP BY p.product_category_name ORDER BY revenue DESC LIMIT 10" }
  ];

  const queryResults = [];
  for (const bq of benchmarks) {
    const start = Date.now();
    try {
      const rows = await runPresto(bq.sql, 30000);
      queryResults.push({ name: bq.name, latency_ms: Date.now() - start, rows: rows.length, status: 'ok' });
    } catch(e) {
      queryResults.push({ name: bq.name, latency_ms: Date.now() - start, status: 'error', error: (e.message||'').slice(0,100) });
    }
  }

  // AI latency
  let aiLatency = 0;
  try {
    const r = await callLocalLLM('SELECT 1', { num_predict: 10 });
    aiLatency = r.time_ms;
  } catch(e) {}

  // Local LLM models
  let models = [];
  try {
    const resp = await axios.get('http://127.0.0.1:11434/api/tags');
    models = (resp.data.models || []).map(m => ({ name: m.name, size_gb: (m.size / 1e9).toFixed(1) }));
  } catch(e) {}

  // Federation engine info
  let prestoInfo = {};
  try { const r = await axios.get('http://127.0.0.1:8080/v1/info'); prestoInfo = r.data; } catch(e) {}

  const avgLatency = queryResults.length ? Math.round(queryResults.reduce((s, r) => s + r.latency_ms, 0) / queryResults.length) : 0;

  return [{ json: {
    action: 'metrics', timestamp: ts,
    framework: { name: 'Context-Aware BI Framework', version: '1.1.0' },
    server: { domain: 'server.example.edu', os: 'Linux', vcpus: 8, ram_gb: 32, storage_gb: 500 },
    presto: { version: prestoInfo.nodeVersion?.version, uptime: prestoInfo.uptime, coordinator: prestoInfo.coordinator },
    ai: {
      engine: 'LocalLLM', models, inference_latency_ms: aiLatency,
      text_to_sql_accuracy: {
        'llama3.1:8b (local)': '90%', 'llama3.2:3b (local)': '60%',
        'gemma-3-27b-it (cloud)': '80%', 'gemma-3-12b-it (cloud)': '60%',
        'nemotron-mini-9b (cloud)': '10%'
      },
      sovereignty_finding: 'Local 8B CPU model (90%) outperforms cloud 27B model (80%) — few-shot prompt engineering > model scale for domain-specific tasks'
    },
    query_benchmarks: { avg_latency_ms: avgLatency, results: queryResults },
    data_coverage: { domains: 5, tables: 29, total_rows: '~2.7M', engines: 2 }
  }}];
}

// ---- CHAT ----
if (action === 'chat') {
  const message = body.message || body.question || '';
  const context = body.context || 'general';
  const modelPref = (body.model || 'local').toLowerCase();

  if (!message) {
    return [{ json: { action: 'chat', success: false, error: 'Provide message. Example: {"action":"chat","message":"Explain DSR methodology"}', timestamp: ts } }];
  }

  const sysPrompt = "You are Dr. AI, an expert PhD research assistant specializing in Information Systems, AI Governance, Business Intelligence, and Design Science Research (DSR).\n\nYou assist a PhD candidate in Information Systems.\n\nDissertation: \"Context-Aware Strategic Decision Support: An AI-Enhanced Business Intelligence Framework for Ubiquitous Computing Environments\"\nSupervisor: [Redacted]\n\nMethodology: Design Science Research (Peffers et al. 2007), 6 phases, 36 months.\n\nFramework Architecture (5 Layers):\n- Layer 1: Multi-Engine Data (PostgreSQL + MariaDB)\n- Layer 2: Orchestration (workflow platform)\n- Layer 3: Federated Query (federation engine)\n- Layer 4: Visualization (dashboard platform)\n- Layer 5: AI/NLP (local inference engine + cloud API gateway)\n\nKey Finding: Local 8B CPU model achieves 90% text-to-SQL accuracy vs cloud 27B at 80%. Few-shot prompt engineering > model scale for domain-specific tasks. Infrastructure sovereignty enables verifiable AI governance.\n\nResearch Questions:\n- Main RQ: How can organizations implement proactive risk assessment for AI in context-aware BI?\n- RQ1: Current risk practices and limitations?\n- RQ2: Design principles for proactive risk assessment frameworks?\n- RQ3: Does systematic risk assessment reduce AI failures?\n\nHypotheses: H1 (40% faster deviation detection), H2 (50% failure reduction), H3 (35% higher reliability)\n\n3 Problem Dimensions: AI Trust Deficit, Context Gap, Integration Chaos\n\nCore Literature: Rivero 2025, Lu & Lo 2024, Batool et al. 2023, Augusto 2022, Peffers et al. 2007\n\nProvide evidence-based, academically rigorous responses. Use formal academic English. Cite specific works when possible.";

  const userMsg = 'Context: ' + context + '\n\nQuestion: ' + message;

  let response, model, source, sovereignty;
  const start = Date.now();

  try {
    if (modelPref === 'cloud') {
      const r = await callCloudLLM(sysPrompt + '\n\n' + userMsg, { temp: 0.3 });
      response = r.text; model = 'gemma-3-27b-it'; source = 'cloud'; sovereignty = false;
    } else {
      const r = await callLocalLLM(sysPrompt + '\n\n' + userMsg, { temp: 0.3 });
      response = r.text; model = 'llama3.1:8b'; source = 'local'; sovereignty = true;
    }
  } catch(e) {
    return [{ json: { action: 'chat', success: false, error: e.message, timestamp: ts } }];
  }

  return [{ json: {
    action: 'chat', success: true, message, context, response,
    model, source, sovereignty, generation_time_ms: Date.now() - start, timestamp: ts
  }}];
}

// ---- COMPILE ----
if (action === 'compile') {
  const target = (body.target || 'article').toLowerCase();
  const { execSync } = require('child_process');

  const configs = {
    article:  { dir: '/var/www/Article_Title', main: 'sn-article', bib: 'sn-bibliography' },
    thesis:   { dir: '/var/www/Thesis/FCIT ThesisTemplate (V7)', main: 'FCIT-Main', bib: 'sample' },
    proposal: { dir: '/var/www/FinalProposal', main: 'FCIT-Main', bib: 'sample' }
  };

  const cfg = configs[target];
  if (!cfg) {
    return [{ json: { action: 'compile', success: false, error: 'Unknown target: ' + target + '. Use: article, thesis, proposal', timestamp: ts } }];
  }

  const TEXBIN = '/usr/local/texlive/2025/bin/x86_64-linux';
  try {
    const opts = { cwd: cfg.dir, timeout: 120000, encoding: 'utf8' };
    execSync(TEXBIN + '/pdflatex -interaction=nonstopmode ' + cfg.main + '.tex 2>&1 > /dev/null', opts);
    try { execSync(TEXBIN + '/bibtex ' + cfg.main + ' 2>&1 > /dev/null', opts); } catch(e) {}
    execSync(TEXBIN + '/pdflatex -interaction=nonstopmode ' + cfg.main + '.tex 2>&1 > /dev/null', opts);
    execSync(TEXBIN + '/pdflatex -interaction=nonstopmode ' + cfg.main + '.tex 2>&1 > /dev/null', opts);

    let errors = 0, pages = 0, warnings = 0;
    try {
      const log = execSync('cat ' + cfg.main + '.log', opts);
      errors = (log.match(/^!/gm) || []).length;
      warnings = (log.match(/Warning/gi) || []).length;
      const pm = log.match(/Output written on .+ \((\d+) page/);
      pages = pm ? parseInt(pm[1]) : 0;
    } catch(e) {}

    return [{ json: {
      action: 'compile', success: errors === 0, target,
      pdf: cfg.dir + '/' + cfg.main + '.pdf',
      pages, errors, warnings, timestamp: ts
    }}];
  } catch(e) {
    return [{ json: { action: 'compile', success: false, target, error: (e.message || '').slice(0, 500), timestamp: ts } }];
  }
}

// ---- DASHBOARDS ----
if (action === 'dashboards') {
  const dashboards = [
    { name: 'E-Commerce Analytics (Olist)', slug: 'ecommerce', charts: 3 },
    { name: 'Healthcare Analytics', slug: 'healthcare', charts: 3 },
    { name: 'Retail Analytics', slug: 'retail', charts: 2 },
    { name: 'Financial Fraud Analytics', slug: 'financial', charts: 2 },
    { name: 'Supply Chain Analytics', slug: 'supply-chain', charts: 3 },
    { name: 'Cross-Domain Overview', slug: 'overview', charts: 7 }
  ];

  let status = 'unknown';
  try {
    const r = await axios.get('http://127.0.0.1:8088/health', { timeout: 3000 });
    const body = typeof r.data === 'string' ? r.data.trim() : 'OK';
    status = body === 'OK' ? 'healthy' : 'degraded';
  } catch(e) { status = 'down'; }

  return [{ json: {
    action: 'dashboards', timestamp: ts,
    dashboard_status: status, base_url: 'https://server.example.edu',
    total_dashboards: dashboards.length,
    total_charts: dashboards.reduce((s, d) => s + d.charts, 0),
    total_datasets: 11,
    dashboards: dashboards.map(d => ({ ...d, url: 'https://server.example.edu/dashboard/' + d.slug + '/' }))
  }}];
}

// ---- UNKNOWN ACTION ----
return [{ json: {
  action, success: false,
  error: "Unknown action: '" + action + "'. Use: ask, health, stats, metrics, chat, compile, dashboards",
  timestamp: ts
}}];
'''

# Build the workflow JSON
workflow = {
    "name": "Context-Aware BI Framework — Unified API",
    "nodes": [
        {
            "parameters": {
                "httpMethod": "POST",
                "path": "framework",
                "responseMode": "lastNode",
                "options": {}
            },
            "id": "wh-framework",
            "name": "Webhook",
            "type": "workflow-nodes-base.webhook",
            "typeVersion": 2,
            "position": [200, 400],
            "webhookId": "framework-unified"
        },
        {
            "parameters": {
                "jsCode": HANDLER_CODE.strip()
            },
            "id": "handler-unified",
            "name": "Framework Handler",
            "type": "workflow-nodes-base.code",
            "typeVersion": 2,
            "position": [440, 400]
        }
    ],
    "connections": {
        "Webhook": {
            "main": [[{"node": "Framework Handler", "type": "main", "index": 0}]]
        }
    },
    "settings": {
        "executionOrder": "v1"
    }
}

def api(method, path, data=None):
    url = BASE + path
    if data is not None:
        req = urllib.request.Request(url, json.dumps(data).encode(), method=method)
        req.add_header('Content-Type', 'application/json')
    else:
        req = urllib.request.Request(url, method=method)
    req.add_header('X-WORKFLOW-API-KEY', API_KEY)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        print(f'  HTTP {e.code}: {e.read().decode()[:200]}')
        return None

# Step 1: Deactivate existing
print(f'1. Deactivating {WF_ID}...')
api('POST', f'/workflows/{WF_ID}/deactivate')

# Step 2: Delete old
print(f'2. Deleting {WF_ID}...')
api('DELETE', f'/workflows/{WF_ID}')

# Step 3: Also clean up inactive dupes
print('3. Cleaning up...')
wfs = api('GET', '/workflows')
if wfs:
    for w in wfs.get('data', []):
        if 'Unified API' in w['name'] and w['id'] != WF_ID:
            print(f'   Deleting dupe: {w["id"]}')
            api('DELETE', f'/workflows/{w["id"]}')

# Step 4: Create new
print('4. Creating workflow...')
result = api('POST', '/workflows', workflow)
if result:
    new_id = result['id']
    print(f'   Created: {new_id}')

    # Step 5: Activate
    print(f'5. Activating {new_id}...')
    act = api('POST', f'/workflows/{new_id}/activate')
    if act:
        print(f'   Active: {act.get("active")}')
        print(f'\nDone! Workflow ID: {new_id}')
        print(f'Endpoint: POST https://server.example.edu/webhook/framework')
    else:
        print('   Activation failed - check logs')
else:
    print('   Creation failed!')
