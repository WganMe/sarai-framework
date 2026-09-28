#!/usr/bin/env python3
"""
Create dashboard charts (Slices) and dashboards for all 5 business domains.
Uses the dashboard platform's internal Python API via Flask app context.

Run from within the platform's virtualenv. Set DASHBOARD_CONFIG_PATH to the
platform's config module; the fallback is a conventional install location.
"""
import sys, os, json, logging
os.environ.setdefault('DASHBOARD_CONFIG_PATH', '/opt/dashboard/config/dashboard_config.py')

from superset.app import create_app
app = create_app()

with app.app_context():
    from superset.models.core import Database
    from superset.connectors.sqla.models import SqlaTable
    from superset.extensions import db as sa_db
    from superset.models.slice import Slice
    from superset.models.dashboard import Dashboard
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger(__name__)

    presto_db = sa_db.session.query(Database).filter_by(database_name='Federation Engine').first()
    if not presto_db:
        log.error("Federation engine database not found!")
        sys.exit(1)
    log.info(f"Federation engine ID={presto_db.id}")

    datasets = {}
    for ds in sa_db.session.query(SqlaTable).filter_by(database_id=presto_db.id).all():
        datasets[ds.table_name] = ds
        log.info(f"  Dataset: '{ds.table_name}' ID={ds.id}")

    CHARTS = [
        {"name": "E-Commerce: Revenue by State", "dataset": "Olist: Revenue by State", "viz_type": "dist_bar",
         "params": {"viz_type": "dist_bar", "metrics": ["revenue"], "groupby": ["state"], "columns": [],
                    "row_limit": 30, "order_desc": True, "color_scheme": "defaultColors",
                    "show_legend": True, "show_bar_value": True, "y_axis_format": "$,.0f",
                    "bottom_margin": "auto", "x_ticks_layout": "45\u00b0"},
         "description": "Revenue per state via federation engine"},
        {"name": "E-Commerce: Category Revenue", "dataset": "Olist: Category Performance", "viz_type": "dist_bar",
         "params": {"viz_type": "dist_bar", "metrics": ["revenue"], "groupby": ["category"], "columns": [],
                    "row_limit": 20, "order_desc": True, "color_scheme": "defaultColors",
                    "y_axis_format": "$,.0f", "x_ticks_layout": "45\u00b0"},
         "description": "Product category revenue"},
        {"name": "E-Commerce: Category Ratings", "dataset": "Olist: Category Performance", "viz_type": "dist_bar",
         "params": {"viz_type": "dist_bar", "metrics": ["avg_review"], "groupby": ["category"], "columns": [],
                    "row_limit": 20, "order_desc": True, "color_scheme": "bnbColors",
                    "y_axis_format": ".2f", "x_ticks_layout": "45\u00b0"},
         "description": "Average review score by category"},
        {"name": "Healthcare: Billing by Condition", "dataset": "Healthcare: Billing by Condition", "viz_type": "pie",
         "params": {"viz_type": "pie", "metrics": ["total_billing"], "groupby": ["condition_name"],
                    "row_limit": 10, "color_scheme": "defaultColors", "show_labels": True,
                    "show_legend": True, "number_format": "$,.0f", "label_type": "key_percent"},
         "description": "Billing distribution by medical condition"},
        {"name": "Healthcare: Insurance Coverage", "dataset": "Healthcare: Billing by Condition", "viz_type": "dist_bar",
         "params": {"viz_type": "dist_bar", "metrics": ["admissions"], "groupby": ["insurance"],
                    "columns": ["condition_name"], "row_limit": 50, "color_scheme": "defaultColors",
                    "show_legend": True, "stacked_style": "stack", "y_axis_format": ",d"},
         "description": "Admissions by insurance provider"},
        {"name": "Healthcare: Hospital Table", "dataset": "Healthcare: Hospital Analysis", "viz_type": "table",
         "params": {"viz_type": "table", "groupby": ["hospital_name", "admission_type"],
                    "metrics": ["admissions", "avg_billing", "total_billing"],
                    "row_limit": 100, "page_length": 25, "include_search": True, "order_desc": True},
         "description": "Hospital analysis table"},
        {"name": "Retail: Revenue by Country", "dataset": "Retail: Revenue by Country", "viz_type": "dist_bar",
         "params": {"viz_type": "dist_bar", "metrics": ["revenue"], "groupby": ["country"], "columns": [],
                    "row_limit": 20, "order_desc": True, "color_scheme": "defaultColors",
                    "y_axis_format": "$,.0f", "x_ticks_layout": "45\u00b0"},
         "description": "Online retail revenue by country"},
        {"name": "Retail: Top Products Table", "dataset": "Retail: Top Products", "viz_type": "table",
         "params": {"viz_type": "table", "groupby": ["product", "country"],
                    "metrics": ["total_qty", "revenue"], "row_limit": 100,
                    "page_length": 25, "include_search": True, "order_desc": True},
         "description": "Top selling products"},
        {"name": "Financial: Fraud by Time Period", "dataset": "Financial: Fraud by Time Bucket", "viz_type": "dist_bar",
         "params": {"viz_type": "dist_bar", "metrics": ["transactions"], "groupby": ["time_period"],
                    "columns": ["transaction_type"], "row_limit": 50, "color_scheme": "defaultColors",
                    "show_legend": True, "stacked_style": "stack", "y_axis_format": ",d"},
         "description": "Transactions by time period and fraud type"},
        {"name": "Financial: Transaction Summary", "dataset": "Financial: Amount Distribution", "viz_type": "table",
         "params": {"viz_type": "table", "groupby": ["transaction_type"],
                    "metrics": ["count", "avg_amount", "min_amount", "max_amount", "total_amount"],
                    "row_limit": 10, "order_desc": True},
         "description": "Transaction amount statistics"},
        {"name": "Supply Chain: Dept Sales (Donut)", "dataset": "Supply Chain: Sales by Department", "viz_type": "pie",
         "params": {"viz_type": "pie", "metrics": ["total_sales"], "groupby": ["department_name"],
                    "row_limit": 20, "color_scheme": "defaultColors", "show_labels": True,
                    "show_legend": True, "donut": True, "number_format": "$,.0f", "label_type": "key_percent"},
         "description": "Sales by department"},
        {"name": "Supply Chain: Delivery Performance", "dataset": "Supply Chain: Delivery Performance", "viz_type": "dist_bar",
         "params": {"viz_type": "dist_bar", "metrics": ["orders"], "groupby": ["delivery_status"],
                    "columns": ["shipping_mode"], "row_limit": 50, "color_scheme": "defaultColors",
                    "show_legend": True, "stacked_style": "stack", "y_axis_format": ",d"},
         "description": "Delivery status by shipping mode"},
        {"name": "Supply Chain: Segment Profitability", "dataset": "Supply Chain: Sales by Department", "viz_type": "dist_bar",
         "params": {"viz_type": "dist_bar", "metrics": ["avg_profit"], "groupby": ["segment"],
                    "columns": ["department_name"], "row_limit": 50, "color_scheme": "bnbColors",
                    "show_legend": True, "stacked_style": "stack", "y_axis_format": "$,.0f"},
         "description": "Average profit by customer segment"},
        {"name": "Cross-Domain: 5-Domain Summary", "dataset": "Cross-Domain: 5-Domain Summary", "viz_type": "table",
         "params": {"viz_type": "table", "groupby": ["domain"],
                    "metrics": ["fact_rows", "total_value"], "row_limit": 10, "order_desc": True},
         "description": "Federated summary across all 5 domains"},
        {"name": "Cross-Domain: Data Volume", "dataset": "Cross-Domain: 5-Domain Summary", "viz_type": "pie",
         "params": {"viz_type": "pie", "metrics": ["fact_rows"], "groupby": ["domain"],
                    "row_limit": 10, "color_scheme": "defaultColors", "show_labels": True,
                    "show_legend": True, "donut": True, "number_format": ",d", "label_type": "key_percent"},
         "description": "Data volume by domain"},
    ]

    DASHBOARDS = [
        {"title": "E-Commerce Analytics (Olist)", "slug": "ecommerce",
         "charts": ["E-Commerce: Revenue by State", "E-Commerce: Category Revenue", "E-Commerce: Category Ratings"]},
        {"title": "Healthcare Analytics", "slug": "healthcare",
         "charts": ["Healthcare: Billing by Condition", "Healthcare: Insurance Coverage", "Healthcare: Hospital Table"]},
        {"title": "Retail Analytics", "slug": "retail",
         "charts": ["Retail: Revenue by Country", "Retail: Top Products Table"]},
        {"title": "Financial Fraud Analytics", "slug": "financial",
         "charts": ["Financial: Fraud by Time Period", "Financial: Transaction Summary"]},
        {"title": "Supply Chain Analytics", "slug": "supply-chain",
         "charts": ["Supply Chain: Dept Sales (Donut)", "Supply Chain: Delivery Performance", "Supply Chain: Segment Profitability"]},
        {"title": "Cross-Domain Federation Overview", "slug": "overview",
         "charts": ["Cross-Domain: 5-Domain Summary", "Cross-Domain: Data Volume",
                    "E-Commerce: Revenue by State", "Healthcare: Billing by Condition",
                    "Retail: Revenue by Country", "Financial: Fraud by Time Period",
                    "Supply Chain: Dept Sales (Donut)"]},
    ]

    # Create Charts
    print("\n" + "=" * 60)
    print("CREATING CHARTS")
    print("=" * 60)
    chart_objects = {}
    created_c = skipped_c = 0

    for cd in CHARTS:
        name = cd["name"]
        existing = sa_db.session.query(Slice).filter_by(slice_name=name).first()
        if existing:
            chart_objects[name] = existing
            skipped_c += 1
            log.info(f"  SKIP: {name} (ID={existing.id})")
            continue
        ds = datasets.get(cd["dataset"])
        if not ds:
            log.error(f"  MISSING DATASET: {cd['dataset']}")
            continue
        params = cd["params"].copy()
        params["datasource"] = f"{ds.id}__table"
        slc = Slice(slice_name=name, viz_type=cd["viz_type"], datasource_type="table",
                     datasource_id=ds.id, params=json.dumps(params), description=cd.get("description", ""))
        sa_db.session.add(slc)
        sa_db.session.flush()
        chart_objects[name] = slc
        created_c += 1
        log.info(f"  CREATED: {name} (ID={slc.id})")

    sa_db.session.commit()
    print(f"\nCharts: {created_c} created, {skipped_c} skipped")

    # Create Dashboards
    print("\n" + "=" * 60)
    print("CREATING DASHBOARDS")
    print("=" * 60)
    created_d = skipped_d = 0

    for dd in DASHBOARDS:
        title, slug = dd["title"], dd["slug"]
        existing = sa_db.session.query(Dashboard).filter_by(slug=slug).first()
        if existing:
            skipped_d += 1
            log.info(f"  SKIP: {title}")
            continue
        slices = [chart_objects[cn] for cn in dd["charts"] if cn in chart_objects]
        positions = {
            "DASHBOARD_VERSION_KEY": "v2",
            "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
            "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
            "HEADER_ID": {"type": "HEADER", "id": "HEADER_ID", "meta": {"text": title}},
        }
        for i, slc in enumerate(slices):
            rid, cid = f"ROW-{i}", f"CHART-{slc.id}"
            positions[rid] = {"type": "ROW", "id": rid, "children": [cid],
                              "parents": ["ROOT_ID", "GRID_ID"], "meta": {"background": "BACKGROUND_TRANSPARENT"}}
            positions[cid] = {"type": "CHART", "id": cid, "children": [],
                              "parents": ["ROOT_ID", "GRID_ID", rid],
                              "meta": {"width": 12, "height": 50, "chartId": slc.id, "sliceName": slc.slice_name}}
            positions["GRID_ID"]["children"].append(rid)
        dash = Dashboard(dashboard_title=title, slug=slug,
                         position_json=json.dumps(positions), published=True)
        dash.slices = slices
        sa_db.session.add(dash)
        sa_db.session.flush()
        created_d += 1
        log.info(f"  CREATED: {title} (ID={dash.id}, {len(slices)} charts)")

    sa_db.session.commit()

    print("\n" + "=" * 60)
    print("DASHBOARD SETUP COMPLETE")
    print("=" * 60)
    print(f"  Charts:     {created_c} created, {skipped_c} skipped")
    print(f"  Dashboards: {created_d} created, {skipped_d} skipped")
    print(f"\n  Dashboards:")
    for dd in DASHBOARDS:
        print(f"    https://server.example.edu/dashboard/{dd['slug']}/")
