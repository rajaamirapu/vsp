"""
╔══════════════════════════════════════════════════════════════╗
║         VENDOR SPEND ANALYSIS — AGENTIC AI DASHBOARD        ║
║         Powered by Claude AI  |  Built with Streamlit        ║
╚══════════════════════════════════════════════════════════════╝
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os
import re
from datetime import datetime, timedelta
import anthropic
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Vendor Spend Analysis",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Main background */
    .main { background-color: #0f1117; }

    /* Metric cards */
    .metric-card {
        background: linear-gradient(135deg, #1e2130, #252a3d);
        border-radius: 12px;
        padding: 20px;
        border-left: 4px solid #4f8ef7;
        margin-bottom: 10px;
    }
    .metric-card h2 { color: #4f8ef7; font-size: 2rem; margin: 0; }
    .metric-card p  { color: #a0aec0; font-size: 0.85rem; margin: 4px 0 0; }

    /* AI result box */
    .ai-result {
        background: linear-gradient(135deg, #1a1f35, #1e2642);
        border-radius: 12px;
        padding: 24px;
        border: 1px solid #3d4f7c;
        margin-top: 16px;
        color: #e2e8f0;
        line-height: 1.7;
    }

    /* Section headers */
    .section-header {
        color: #4f8ef7;
        font-size: 1.4rem;
        font-weight: 700;
        border-bottom: 2px solid #4f8ef7;
        padding-bottom: 8px;
        margin-bottom: 20px;
    }

    /* Prompt chip */
    .prompt-badge {
        display: inline-block;
        background: #2d3748;
        color: #90cdf4;
        border-radius: 20px;
        padding: 4px 12px;
        font-size: 0.8rem;
        margin-bottom: 8px;
    }

    /* Warning banner */
    .warning-banner {
        background: linear-gradient(135deg, #2d2012, #3d2c1a);
        border-left: 4px solid #f6ad55;
        border-radius: 8px;
        padding: 16px;
        color: #fbd38d;
        margin: 10px 0;
    }

    /* Risk pill */
    .risk-high   { color: #fc8181; font-weight: bold; }
    .risk-medium { color: #f6ad55; font-weight: bold; }
    .risk-low    { color: #68d391; font-weight: bold; }

    /* Sidebar label */
    .sidebar-label { color: #718096; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; margin-top: 16px; }

    /* Hide default Streamlit branding */
    #MainMenu, footer { visibility: hidden; }

    /* Scrollable AI output */
    .ai-scroll {
        max-height: 500px;
        overflow-y: auto;
        padding-right: 8px;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# PROMPT LIBRARY  (all 13 prompts from vendor_spend_prompts.txt)
# ─────────────────────────────────────────────────────────────────────────────
PROMPTS = {
    # ── Category 1: Spend Overview ──────────────────────────────────────────
    "executive_summary": {
        "label": "1 · Executive Spend Summary",
        "category": "Spend Overview",
        "icon": "📊",
        "template": """You are a procurement analyst. Analyze the following vendor spend data and produce an executive summary including:
1. Total spend and period covered
2. Top 5 spend categories (with % of total)
3. Top 10 vendors by spend
4. Month-over-month or quarter-on-quarter trend
5. Notable observations or red flags

Format with clear sections and a brief narrative. Be concise and data-driven.

SPEND DATA:
{data}""",
    },
    "spend_by_bu": {
        "label": "2 · Spend by Business Unit",
        "category": "Spend Overview",
        "icon": "🏢",
        "template": """You are a finance analyst. Given the spend data below, break down total expenditure by business unit or cost center:
- Total spend per unit
- % of overall spend
- Top 3 vendors per unit
- Any units exceeding budget (if budget info is provided)

Present as a structured table followed by 3–5 key insights.

SPEND DATA:
{data}""",
    },

    # ── Category 2: Vendor Analysis ─────────────────────────────────────────
    "concentration_risk": {
        "label": "3 · Vendor Concentration Risk",
        "category": "Vendor Analysis",
        "icon": "⚠️",
        "template": """Analyze the following vendor spend data for concentration risk:
- Calculate what % of total spend goes to the top 1, 3, and 5 vendors
- Flag any single vendor representing more than 20% of total spend
- Identify categories with only one active vendor (single-source risk)
- Recommend diversification actions where risk is high

Be specific with vendor names and amounts.

SPEND DATA:
{data}""",
    },
    "vendor_scorecard": {
        "label": "4 · Vendor Performance Scorecard",
        "category": "Vendor Analysis",
        "icon": "🏆",
        "template": """Create a vendor performance scorecard from the spend data below. For each vendor include:
- Total spend (period)
- Transaction count
- Average transaction value
- Spend trend (growing / stable / declining)
- Category they serve

Rank vendors by total spend. Highlight any vendor with unusual transaction patterns (very high or low avg ticket).

SPEND DATA:
{data}""",
    },
    "duplicate_vendors": {
        "label": "5 · Duplicate Vendor Detection",
        "category": "Vendor Analysis",
        "icon": "🔍",
        "template": """Review the vendor list in the spend data below and identify potential duplicate vendors — the same supplier appearing under slightly different names (e.g. "Microsoft Corp" vs "Microsoft Corporation" vs "MSFT").

For each suspected duplicate:
- List all name variants found
- Show combined total spend if merged
- Recommend canonical vendor name

Also flag vendors with suspiciously similar names that may indicate data entry errors.

SPEND DATA:
{data}""",
    },

    # ── Category 3: Anomaly Detection ───────────────────────────────────────
    "unusual_transactions": {
        "label": "6 · Unusual Transaction Detector",
        "category": "Anomaly Detection",
        "icon": "🚨",
        "template": """You are a spend controls analyst. Scan the following transactions for anomalies:
- Transactions significantly above or below the vendor's average
- Purchases on weekends or holidays
- Round-number transactions (potential estimates, not actuals)
- Multiple transactions to same vendor on same day (possible split invoicing)
- Transactions just below approval thresholds (e.g. $9,999 when threshold is $10,000)

For each anomaly found, list: date, vendor, amount, anomaly type, and recommended action.

TRANSACTION DATA:
{data}""",
    },
    "spend_spikes": {
        "label": "7 · Spend Spike Analysis",
        "category": "Anomaly Detection",
        "icon": "📈",
        "template": """Compare the spend data across two periods and identify significant spikes:
- Any category or vendor with spend increase >30% vs prior period
- New vendors appearing in the current period not in prior
- Vendors with dramatic spend drops (possible contract end or offboarding)

For each spike or anomaly explain likely cause if discernible from context, and flag those requiring follow-up.

SPEND DATA (H1 vs H2 split automatically):
{data}""",
    },

    # ── Category 4: Savings Opportunities ───────────────────────────────────
    "consolidation": {
        "label": "8 · Consolidation Opportunities",
        "category": "Savings Opportunities",
        "icon": "💡",
        "template": """Analyze the spend data for vendor consolidation opportunities:
- Identify categories with 5+ active vendors where spend is fragmented
- Estimate potential savings from consolidating to 1–2 preferred vendors (assume 10–15% volume discount)
- Prioritize opportunities by potential savings size
- Flag categories where consolidation may not be advisable (e.g. professional services, specialized tech)

Output as a ranked opportunity list with estimated savings range.

SPEND DATA:
{data}""",
    },
    "tail_spend": {
        "label": "9 · Tail Spend Analysis",
        "category": "Savings Opportunities",
        "icon": "📉",
        "template": """Identify tail spend in the vendor data below. Tail spend = vendors with individually low total spend but collectively significant cost and high management overhead.

Define tail as: vendors making up the bottom 80% of suppliers by count but representing <20% of total spend.

For the tail vendors:
- Total count and combined spend
- Average spend per vendor
- Top categories represented
- Recommended approach: consolidate to marketplace, p-card, or preferred supplier

SPEND DATA:
{data}""",
    },
    "contract_compliance": {
        "label": "10 · Contract Compliance Gaps",
        "category": "Savings Opportunities",
        "icon": "📋",
        "template": """Review the spend data for contract compliance gaps. Since we don't have contracted rates here, analyze based on:
- Identify transactions that may indicate off-contract buying (unusual amounts, non-standard vendors)
- Flag spend with vendors not likely on an approved vendor list based on spend patterns
- Identify transactions just below approval thresholds (possible threshold circumvention)
- Estimate potential risk exposure from compliance gaps

Present findings sorted by risk level (High/Medium/Low), largest exposure first.

SPEND DATA:
{data}""",
    },

    # ── Category 5: Category Mapping ────────────────────────────────────────
    "auto_classify": {
        "label": "11 · Auto-Classify Spend Categories",
        "category": "Category Mapping",
        "icon": "🏷️",
        "template": """Classify each vendor/transaction in the spend data below into a standard spend category. Use these categories:
IT & Software | Professional Services | Marketing & Advertising | Travel & Expenses | Facilities & Real Estate | HR & Recruitment | Logistics & Freight | Raw Materials | Office Supplies | Utilities | Other

Review the existing category assignments and:
1. Validate if current categories are correct
2. Flag any misclassified transactions
3. For each correction output: Vendor | Current Category | Suggested Category | Confidence (High/Medium/Low) | Notes

SPEND DATA:
{data}""",
    },
    "remap_taxonomy": {
        "label": "12 · Remap to Standard Taxonomy",
        "category": "Category Mapping",
        "icon": "🗂️",
        "template": """Remap the existing spend categories in the data below to a UNSPSC-aligned taxonomy. For each existing category:
- Identify the best matching UNSPSC level-2 segment
- Suggest standardized category names
- Flag any categories needing to be split
- Provide confidence level for each mapping

Then summarize: total spend by remapped category, and % of spend that maps cleanly vs. requires review.

SPEND DATA:
{data}""",
    },

    # ── Category 6: Policy Compliance ───────────────────────────────────────
    "policy_violations": {
        "label": "13 · Policy Violation Scan",
        "category": "Policy Compliance",
        "icon": "🚫",
        "template": """Review the following transactions against standard spend policy and flag violations:

Policy rules applied:
- Single-source purchases above $10,000 require 3 quotes
- Hospitality/T&E spend above $500 per person requires VP approval
- Software purchases must go through IT procurement (flag if approved_by is not IT/VP)
- Any transaction marked "Pending" payment status requires review
- Round-number transactions above $5,000 are flagged (potential estimates)
- Transactions just below thresholds ($9,999 when limit is $10,000) are flagged

For each violation: Date | Vendor | Amount | Policy rule breached | Severity (High/Medium/Low) | Recommended action

TRANSACTION DATA:
{data}""",
    },
}

# Group by category
CATEGORIES = {}
for key, p in PROMPTS.items():
    cat = p["category"]
    if cat not in CATEGORIES:
        CATEGORIES[cat] = []
    CATEGORIES[cat].append(key)

# Category icons
CAT_ICONS = {
    "Spend Overview":        "📊",
    "Vendor Analysis":       "🏢",
    "Anomaly Detection":     "🚨",
    "Savings Opportunities": "💰",
    "Category Mapping":      "🏷️",
    "Policy Compliance":     "⚖️",
}

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
if "ai_results"  not in st.session_state: st.session_state.ai_results  = {}
if "df"          not in st.session_state: st.session_state.df          = None
if "api_key"     not in st.session_state: st.session_state.api_key     = ""

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data
def load_sample_data():
    base = os.path.dirname(os.path.abspath(__file__))
    sample = os.path.join(base, "vendor_spend_data.csv")
    if os.path.exists(sample):
        return pd.read_csv(sample, parse_dates=["date"])
    return None


def df_to_summary_csv(df: pd.DataFrame, max_rows: int = 300) -> str:
    """Convert dataframe to CSV string for prompt injection (capped for token budget)."""
    sample = df.head(max_rows) if len(df) > max_rows else df
    return sample.to_csv(index=False)


def call_claude(prompt_key: str, df: pd.DataFrame, api_key: str) -> str:
    """Call Claude API with the selected prompt and data."""
    template = PROMPTS[prompt_key]["template"]
    data_csv  = df_to_summary_csv(df)
    full_prompt = template.format(data=data_csv)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=2048,
            messages=[{"role": "user", "content": full_prompt}],
        )
        return message.content[0].text
    except anthropic.AuthenticationError:
        return "❌ **Authentication Error:** Invalid API key. Please check your Anthropic API key in the sidebar."
    except anthropic.RateLimitError:
        return "❌ **Rate Limit:** Too many requests. Please wait a moment and try again."
    except Exception as e:
        return f"❌ **Error:** {str(e)}"


def fmt_currency(value: float) -> str:
    if value >= 1_000_000:
        return f"${value/1_000_000:.1f}M"
    elif value >= 1_000:
        return f"${value/1_000:.0f}K"
    return f"${value:,.0f}"


def color_bar(pct: float) -> str:
    if pct >= 40: return "#fc8181"
    if pct >= 20: return "#f6ad55"
    return "#68d391"


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/color/96/money-bag.png", width=60)
    st.markdown("## 💰 Vendor Spend AI")
    st.markdown("*Agentic analysis powered by Claude*")
    st.divider()

    # API Key
    st.markdown('<p class="sidebar-label">🔑 Claude API Key</p>', unsafe_allow_html=True)
    api_input = st.text_input(
        "API Key",
        value=st.session_state.api_key,
        type="password",
        label_visibility="collapsed",
        placeholder="sk-ant-api03-...",
    )
    if api_input != st.session_state.api_key:
        st.session_state.api_key = api_input

    if st.session_state.api_key:
        st.success("✅ API key set")
    else:
        st.warning("⚠️ Enter key for AI analysis")

    st.divider()

    # Data Source
    st.markdown('<p class="sidebar-label">📂 Data Source</p>', unsafe_allow_html=True)
    data_source = st.radio(
        "data",
        ["📊 Use Sample Data", "📁 Upload My CSV"],
        label_visibility="collapsed",
    )

    uploaded_file = None
    if data_source == "📁 Upload My CSV":
        uploaded_file = st.file_uploader(
            "Upload CSV", type=["csv", "xlsx"],
            label_visibility="collapsed",
        )

    st.divider()
    st.markdown('<p class="sidebar-label">📐 Navigation</p>', unsafe_allow_html=True)
    page = st.radio(
        "nav",
        ["🏠 Dashboard", "📊 Spend Overview", "🏢 Vendor Analysis",
         "🚨 Anomaly Detection", "💰 Savings Opportunities",
         "🏷️ Category Mapping", "⚖️ Policy Compliance"],
        label_visibility="collapsed",
    )

    st.divider()
    st.caption("Built with Streamlit + Claude AI\n\nPrompts: 13 | Categories: 6")


# ─────────────────────────────────────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────────────────────────────────────
df = None
if data_source == "📊 Use Sample Data":
    df = load_sample_data()
    if df is None:
        st.error("Sample data file not found. Please place `vendor_spend_data.csv` in the same folder.")
elif uploaded_file is not None:
    try:
        if uploaded_file.name.endswith(".xlsx"):
            df = pd.read_excel(uploaded_file)
        else:
            df = pd.read_csv(uploaded_file)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
    except Exception as e:
        st.error(f"Error reading file: {e}")

st.session_state.df = df

# ─────────────────────────────────────────────────────────────────────────────
# GUARD: No data yet
# ─────────────────────────────────────────────────────────────────────────────
if df is None:
    st.markdown("""
    # 💰 Vendor Spend Analysis
    ### Agentic AI Dashboard

    **Getting Started:**
    1. Use the **sample data** or upload your own CSV in the sidebar
    2. Enter your **Claude API key** to enable AI analysis
    3. Navigate to any analysis category

    **CSV format expected:**
    | invoice_id | date | vendor | category | business_unit | amount | description | approved_by | payment_status |
    |---|---|---|---|---|---|---|---|---|
    """)
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# PRE-COMPUTE AGGREGATES
# ─────────────────────────────────────────────────────────────────────────────
total_spend    = df["amount"].sum()
total_vendors  = df["vendor"].nunique()
total_txns     = len(df)
avg_txn        = df["amount"].mean()
top_category   = df.groupby("category")["amount"].sum().idxmax() if "category" in df.columns else "N/A"

spend_by_cat   = df.groupby("category")["amount"].sum().sort_values(ascending=False).reset_index()
spend_by_cat["pct"] = (spend_by_cat["amount"] / total_spend * 100).round(1)

spend_by_vendor = df.groupby("vendor")["amount"].sum().sort_values(ascending=False).reset_index()
spend_by_vendor["pct"] = (spend_by_vendor["amount"] / total_spend * 100).round(1)

if "business_unit" in df.columns:
    spend_by_bu = df.groupby("business_unit")["amount"].sum().sort_values(ascending=False).reset_index()
else:
    spend_by_bu = pd.DataFrame()

# Monthly trend
if "date" in df.columns:
    df["month"] = df["date"].dt.to_period("M").astype(str)
    monthly = df.groupby("month")["amount"].sum().reset_index().sort_values("month")
else:
    monthly = pd.DataFrame()

# ─────────────────────────────────────────────────────────────────────────────
# REUSABLE AI ANALYSIS WIDGET
# ─────────────────────────────────────────────────────────────────────────────
def ai_analysis_section(prompt_key: str):
    """Render a single AI analysis block."""
    info     = PROMPTS[prompt_key]
    result_k = f"result_{prompt_key}"
    cached   = st.session_state.ai_results.get(prompt_key)

    st.markdown(f'<div class="prompt-badge">{info["icon"]} Prompt #{list(PROMPTS.keys()).index(prompt_key)+1} — {info["category"]}</div>', unsafe_allow_html=True)

    col_btn, col_clear = st.columns([3, 1])
    with col_btn:
        run_btn = st.button(
            f"🤖 Run AI Analysis: {info['label']}",
            key=f"run_{prompt_key}",
            use_container_width=True,
            type="primary" if not cached else "secondary",
        )
    with col_clear:
        if cached:
            if st.button("🗑️ Clear", key=f"clear_{prompt_key}", use_container_width=True):
                st.session_state.ai_results.pop(prompt_key, None)
                st.rerun()

    if run_btn:
        if not st.session_state.api_key:
            st.error("Please enter your Claude API key in the sidebar first.")
        else:
            with st.spinner(f"🧠 Claude is analyzing your data using prompt: {info['label']}..."):
                result = call_claude(prompt_key, df, st.session_state.api_key)
                st.session_state.ai_results[prompt_key] = result
                st.rerun()

    if cached:
        st.markdown(f'<div class="ai-result"><div class="ai-scroll">{cached}</div></div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# ═══════════════════════════ PAGE: DASHBOARD ════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────
if "Dashboard" in page:
    st.markdown("# 💰 Vendor Spend Analysis Dashboard")
    st.markdown(f"*Data loaded: **{total_txns:,}** transactions | {total_vendors} vendors | Period: {df['date'].min().date() if 'date' in df.columns else 'N/A'} → {df['date'].max().date() if 'date' in df.columns else 'N/A'}*")
    st.divider()

    # ── KPI Metrics ──────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    metrics = [
        (c1, "Total Spend",     fmt_currency(total_spend),  "All vendors combined"),
        (c2, "Vendors",         f"{total_vendors}",          "Unique suppliers"),
        (c3, "Transactions",    f"{total_txns:,}",           "Invoice count"),
        (c4, "Avg Transaction", fmt_currency(avg_txn),       "Per invoice"),
        (c5, "Top Category",    top_category.split(" ")[0],  "By total spend"),
    ]
    for col, title, value, sub in metrics:
        with col:
            st.markdown(f"""
            <div class="metric-card">
                <p>{title}</p>
                <h2>{value}</h2>
                <p>{sub}</p>
            </div>""", unsafe_allow_html=True)

    st.divider()

    # ── Row 1: Category Donut + Monthly Trend ────────────────────────────────
    col_l, col_r = st.columns([1, 1])

    with col_l:
        st.markdown("#### 📊 Spend by Category")
        fig_donut = px.pie(
            spend_by_cat, values="amount", names="category",
            hole=0.55,
            color_discrete_sequence=px.colors.sequential.Plasma_r,
        )
        fig_donut.update_traces(textposition="inside", textinfo="percent+label")
        fig_donut.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font_color="#e2e8f0", showlegend=False,
            margin=dict(t=10, b=10, l=10, r=10), height=360,
        )
        st.plotly_chart(fig_donut, use_container_width=True)

    with col_r:
        if not monthly.empty:
            st.markdown("#### 📈 Monthly Spend Trend")
            fig_trend = px.area(
                monthly, x="month", y="amount",
                color_discrete_sequence=["#4f8ef7"],
                labels={"amount": "Spend ($)", "month": ""},
            )
            fig_trend.update_traces(fill="tozeroy", fillcolor="rgba(79,142,247,0.15)")
            fig_trend.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="#e2e8f0",
                xaxis=dict(showgrid=False, tickangle=-45),
                yaxis=dict(showgrid=True, gridcolor="#2d3748"),
                margin=dict(t=10, b=10), height=360,
            )
            st.plotly_chart(fig_trend, use_container_width=True)

    # ── Row 2: Top Vendors + BU Breakdown ───────────────────────────────────
    col_l2, col_r2 = st.columns([1, 1])

    with col_l2:
        st.markdown("#### 🏆 Top 10 Vendors by Spend")
        top10 = spend_by_vendor.head(10).copy()
        top10["color"] = top10["pct"].apply(color_bar)
        fig_bar = px.bar(
            top10[::-1], x="amount", y="vendor",
            orientation="h", text="pct",
            color="pct",
            color_continuous_scale=["#68d391", "#f6ad55", "#fc8181"],
        )
        fig_bar.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig_bar.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font_color="#e2e8f0", coloraxis_showscale=False,
            xaxis=dict(showgrid=True, gridcolor="#2d3748"),
            yaxis=dict(showgrid=False),
            margin=dict(t=10, b=10), height=380,
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_r2:
        if not spend_by_bu.empty:
            st.markdown("#### 🏢 Spend by Business Unit")
            fig_bu = px.bar(
                spend_by_bu, x="business_unit", y="amount",
                color="amount",
                color_continuous_scale=px.colors.sequential.Blues_r,
                labels={"amount": "Spend ($)", "business_unit": ""},
            )
            fig_bu.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="#e2e8f0", coloraxis_showscale=False,
                xaxis=dict(showgrid=False, tickangle=-30),
                yaxis=dict(showgrid=True, gridcolor="#2d3748"),
                margin=dict(t=10, b=10), height=380,
            )
            st.plotly_chart(fig_bu, use_container_width=True)

    # ── Row 3: Concentration Risk Gauge ─────────────────────────────────────
    st.markdown("#### ⚠️ Vendor Concentration Heat Map")
    top5_pct   = spend_by_vendor.head(5)["pct"].sum()
    top3_pct   = spend_by_vendor.head(3)["pct"].sum()
    top1_pct   = spend_by_vendor.head(1)["pct"].sum()

    c_a, c_b, c_c = st.columns(3)
    for col, label, pct in [(c_a, "Top Vendor", top1_pct), (c_b, "Top 3 Vendors", top3_pct), (c_c, "Top 5 Vendors", top5_pct)]:
        with col:
            risk = "HIGH" if pct > 50 else ("MEDIUM" if pct > 30 else "LOW")
            risk_color = "#fc8181" if risk == "HIGH" else ("#f6ad55" if risk == "MEDIUM" else "#68d391")
            fig_g = go.Figure(go.Indicator(
                mode="gauge+number",
                value=round(pct, 1),
                number={"suffix": "%", "font": {"color": "#e2e8f0", "size": 32}},
                title={"text": f"{label}<br><span style='color:{risk_color};font-size:14px'>Risk: {risk}</span>",
                       "font": {"color": "#a0aec0"}},
                gauge={
                    "axis": {"range": [0, 100], "tickcolor": "#718096"},
                    "bar": {"color": risk_color},
                    "bgcolor": "#1e2130",
                    "bordercolor": "#2d3748",
                    "steps": [
                        {"range": [0,  30], "color": "#1a3a2a"},
                        {"range": [30, 50], "color": "#3a2e14"},
                        {"range": [50, 100],"color": "#3a1a1a"},
                    ],
                },
            ))
            fig_g.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#e2e8f0",
                height=220, margin=dict(t=30, b=0, l=20, r=20),
            )
            st.plotly_chart(fig_g, use_container_width=True)

    # ── Quick AI Summary ─────────────────────────────────────────────────────
    st.divider()
    st.markdown("### 🤖 Quick AI Executive Summary")
    ai_analysis_section("executive_summary")

    # ── Data Table Preview ───────────────────────────────────────────────────
    with st.expander("📋 Raw Data Preview (first 100 rows)", expanded=False):
        st.dataframe(df.head(100), use_container_width=True, height=300)


# ─────────────────────────────────────────────────────────────────────────────
# ═══════════════════════════ PAGE: SPEND OVERVIEW ═══════════════════════════
# ─────────────────────────────────────────────────────────────────────────────
elif "Spend Overview" in page:
    st.markdown("## 📊 Spend Overview")
    st.caption("Prompts 1–2: Executive summary and business unit breakdown")
    st.divider()

    # Category stacked bar by month
    if "date" in df.columns and "category" in df.columns:
        st.markdown("#### Category Spend Trend by Month")
        df_mc = df.copy()
        df_mc["month"] = df_mc["date"].dt.to_period("M").astype(str)
        pivot = df_mc.groupby(["month", "category"])["amount"].sum().reset_index()
        fig_stack = px.bar(
            pivot, x="month", y="amount", color="category",
            barmode="stack",
            color_discrete_sequence=px.colors.qualitative.Bold,
            labels={"amount": "Spend ($)", "month": ""},
        )
        fig_stack.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font_color="#e2e8f0",
            xaxis=dict(showgrid=False, tickangle=-45),
            yaxis=dict(showgrid=True, gridcolor="#2d3748"),
            legend=dict(orientation="h", y=-0.25),
            margin=dict(t=10, b=60), height=400,
        )
        st.plotly_chart(fig_stack, use_container_width=True)

    # Category table
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Category Breakdown")
        display = spend_by_cat.copy()
        display["amount"] = display["amount"].apply(fmt_currency)
        display.columns = ["Category", "Spend", "% of Total"]
        st.dataframe(display, use_container_width=True, hide_index=True)

    with col2:
        if not spend_by_bu.empty:
            st.markdown("#### Business Unit Breakdown")
            bu_display = spend_by_bu.copy()
            bu_display["pct"] = (bu_display["amount"] / total_spend * 100).round(1)
            bu_display["amount"] = bu_display["amount"].apply(fmt_currency)
            bu_display.columns = ["Business Unit", "Spend", "% of Total"]
            st.dataframe(bu_display, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("### 🤖 AI Analysis — Spend Overview")
    tabs = st.tabs([PROMPTS[k]["label"] for k in CATEGORIES["Spend Overview"]])
    for tab, key in zip(tabs, CATEGORIES["Spend Overview"]):
        with tab:
            ai_analysis_section(key)


# ─────────────────────────────────────────────────────────────────────────────
# ═══════════════════════════ PAGE: VENDOR ANALYSIS ══════════════════════════
# ─────────────────────────────────────────────────────────────────────────────
elif "Vendor Analysis" in page:
    st.markdown("## 🏢 Vendor Analysis")
    st.caption("Prompts 3–5: Concentration risk, performance scorecard, duplicate detection")
    st.divider()

    # Treemap of vendor spend
    st.markdown("#### Vendor Spend Treemap")
    fig_tree = px.treemap(
        spend_by_vendor.head(20), path=["vendor"], values="amount",
        color="pct",
        color_continuous_scale=["#1a3a2a", "#f6ad55", "#fc8181"],
        color_continuous_midpoint=20,
    )
    fig_tree.update_traces(textinfo="label+value+percent root")
    fig_tree.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", font_color="#e2e8f0",
        coloraxis_colorbar=dict(title="% Spend"),
        margin=dict(t=10, b=10), height=400,
    )
    st.plotly_chart(fig_tree, use_container_width=True)

    # Vendor stats table
    st.markdown("#### Vendor Statistics")
    vendor_stats = df.groupby("vendor").agg(
        total_spend=("amount", "sum"),
        tx_count=("amount", "count"),
        avg_tx=("amount", "mean"),
        min_tx=("amount", "min"),
        max_tx=("amount", "max"),
    ).sort_values("total_spend", ascending=False).reset_index()
    vendor_stats["% of Total"] = (vendor_stats["total_spend"] / total_spend * 100).round(1)
    vendor_stats["Cum %"]      = vendor_stats["% of Total"].cumsum().round(1)

    display_stats = vendor_stats.copy()
    for col in ["total_spend", "avg_tx", "min_tx", "max_tx"]:
        display_stats[col] = display_stats[col].apply(fmt_currency)
    display_stats.columns = ["Vendor", "Total Spend", "# Txns", "Avg Txn", "Min Txn", "Max Txn", "% Share", "Cum %"]
    st.dataframe(display_stats.head(25), use_container_width=True, hide_index=True, height=350)

    # Pareto chart
    st.markdown("#### Pareto Chart — Vendor Concentration")
    pareto = vendor_stats.head(20).copy()
    pareto["cum_pct"] = (pareto["total_spend"].cumsum() / total_spend * 100).round(1)
    fig_pareto = make_subplots(specs=[[{"secondary_y": True}]])
    fig_pareto.add_trace(go.Bar(x=pareto["vendor"], y=pareto["total_spend"],
                                 name="Spend", marker_color="#4f8ef7"), secondary_y=False)
    fig_pareto.add_trace(go.Scatter(x=pareto["vendor"], y=pareto["cum_pct"],
                                     name="Cum %", mode="lines+markers",
                                     marker_color="#f6ad55", line_width=2), secondary_y=True)
    fig_pareto.add_hline(y=80, line_dash="dash", line_color="#fc8181",
                          annotation_text="80% threshold", secondary_y=True)
    fig_pareto.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e2e8f0",
        xaxis=dict(tickangle=-45, showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#2d3748"),
        legend=dict(orientation="h", y=1.1),
        margin=dict(t=20, b=80), height=420,
    )
    st.plotly_chart(fig_pareto, use_container_width=True)

    st.divider()
    st.markdown("### 🤖 AI Analysis — Vendor Analysis")
    tabs = st.tabs([PROMPTS[k]["label"] for k in CATEGORIES["Vendor Analysis"]])
    for tab, key in zip(tabs, CATEGORIES["Vendor Analysis"]):
        with tab:
            ai_analysis_section(key)


# ─────────────────────────────────────────────────────────────────────────────
# ═══════════════════════ PAGE: ANOMALY DETECTION ════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────
elif "Anomaly Detection" in page:
    st.markdown("## 🚨 Anomaly Detection")
    st.caption("Prompts 6–7: Unusual transactions and spend spikes")
    st.divider()

    # Local anomaly detection (rules-based for visualization)
    anomalies = []
    thresholds = [5000, 10000, 25000, 50000]

    for _, row in df.iterrows():
        reasons = []
        if row["amount"] in [round(t - 1, 0) for t in thresholds] or \
           any(abs(row["amount"] - (t - 1)) < 2 for t in thresholds):
            reasons.append("Below-threshold amount")
        if row["amount"] == round(row["amount"], -3) and row["amount"] >= 5000:
            reasons.append("Round-number transaction")
        if "date" in df.columns:
            weekday = pd.to_datetime(row["date"]).weekday()
            if weekday >= 5:
                reasons.append("Weekend transaction")
        if reasons:
            anomalies.append({**row.to_dict(), "flags": ", ".join(reasons)})

    if anomalies:
        anom_df = pd.DataFrame(anomalies)
        st.markdown(f"#### ⚠️ Rule-Based Anomaly Flags ({len(anom_df)} detected)")

        col_flags = st.columns(3)
        flag_types = ["Below-threshold amount", "Round-number transaction", "Weekend transaction"]
        flag_icons = ["🎯", "🔢", "📅"]
        for i, (col, ft, fi) in enumerate(zip(col_flags, flag_types, flag_icons)):
            count = anom_df["flags"].str.contains(ft).sum()
            with col:
                st.markdown(f"""
                <div class="metric-card">
                    <p>{fi} {ft}</p>
                    <h2 style="color:#f6ad55">{count}</h2>
                    <p>transactions flagged</p>
                </div>""", unsafe_allow_html=True)

        # Scatter plot of transactions, highlight anomalies
        df_plot = df.copy()
        df_plot["is_anomaly"] = df_plot.index.isin(anom_df.index)
        df_plot["color"] = df_plot["is_anomaly"].map({True: "Anomaly 🚨", False: "Normal ✅"})

        fig_scatter = px.scatter(
            df_plot, x="date" if "date" in df_plot.columns else df_plot.index,
            y="amount", color="color",
            hover_data=["vendor", "category"] if "category" in df_plot.columns else ["vendor"],
            color_discrete_map={"Anomaly 🚨": "#fc8181", "Normal ✅": "#4f8ef7"},
            opacity=0.7,
        )
        fig_scatter.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font_color="#e2e8f0", height=380,
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="#2d3748"),
            margin=dict(t=10, b=10),
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

        with st.expander("📋 Anomaly Details Table", expanded=False):
            st.dataframe(
                anom_df[["date", "vendor", "amount", "flags"]].sort_values("amount", ascending=False),
                use_container_width=True, hide_index=True,
            )
    else:
        st.info("No rule-based anomalies detected in the current dataset.")

    # Spike analysis: H1 vs H2
    if "date" in df.columns:
        st.markdown("#### 📈 Period-over-Period Spend Comparison")
        df_h = df.copy()
        midpoint = df_h["date"].min() + (df_h["date"].max() - df_h["date"].min()) / 2
        df_h["period"] = df_h["date"].apply(lambda d: "H2 (Recent)" if d >= midpoint else "H1 (Prior)")
        period_cat = df_h.groupby(["period", "category"])["amount"].sum().reset_index()

        fig_compare = px.bar(
            period_cat, x="category", y="amount", color="period",
            barmode="group",
            color_discrete_map={"H1 (Prior)": "#4f8ef7", "H2 (Recent)": "#f6ad55"},
            labels={"amount": "Spend ($)", "category": ""},
        )
        fig_compare.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font_color="#e2e8f0", height=380,
            xaxis=dict(tickangle=-30, showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="#2d3748"),
            legend=dict(orientation="h", y=1.1),
            margin=dict(t=20, b=70),
        )
        st.plotly_chart(fig_compare, use_container_width=True)

    st.divider()
    st.markdown("### 🤖 AI Analysis — Anomaly Detection")
    tabs = st.tabs([PROMPTS[k]["label"] for k in CATEGORIES["Anomaly Detection"]])
    for tab, key in zip(tabs, CATEGORIES["Anomaly Detection"]):
        with tab:
            ai_analysis_section(key)


# ─────────────────────────────────────────────────────────────────────────────
# ════════════════════════ PAGE: SAVINGS OPPORTUNITIES ═══════════════════════
# ─────────────────────────────────────────────────────────────────────────────
elif "Savings Opportunities" in page:
    st.markdown("## 💰 Savings Opportunities")
    st.caption("Prompts 8–10: Consolidation, tail spend, contract compliance")
    st.divider()

    # Vendors per category
    if "category" in df.columns:
        vendors_per_cat = df.groupby("category")["vendor"].nunique().sort_values(ascending=False).reset_index()
        vendors_per_cat.columns = ["category", "vendor_count"]
        spend_per_cat_total = df.groupby("category")["amount"].sum().reset_index()
        vendors_per_cat = vendors_per_cat.merge(spend_per_cat_total, on="category")
        vendors_per_cat["est_savings_10pct"] = (vendors_per_cat["amount"] * 0.10).round(0)
        vendors_per_cat["consolidation_opp"] = vendors_per_cat["vendor_count"].apply(
            lambda x: "High 🔴" if x >= 5 else ("Medium 🟡" if x >= 3 else "Low 🟢")
        )

        st.markdown("#### 🎯 Consolidation Opportunity Matrix")
        col_l, col_r = st.columns([1, 1])

        with col_l:
            fig_bubble = px.scatter(
                vendors_per_cat,
                x="vendor_count", y="amount",
                size="est_savings_10pct",
                color="vendor_count",
                hover_name="category",
                hover_data={"est_savings_10pct": ":,.0f"},
                color_continuous_scale=["#68d391", "#f6ad55", "#fc8181"],
                labels={"vendor_count": "# Vendors", "amount": "Total Spend ($)"},
            )
            fig_bubble.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="#e2e8f0", coloraxis_showscale=False,
                xaxis=dict(showgrid=True, gridcolor="#2d3748"),
                yaxis=dict(showgrid=True, gridcolor="#2d3748"),
                margin=dict(t=10, b=10), height=380,
            )
            st.plotly_chart(fig_bubble, use_container_width=True)

        with col_r:
            st.markdown("#### Consolidation Opportunity Table")
            display_cons = vendors_per_cat.copy()
            display_cons["amount"] = display_cons["amount"].apply(fmt_currency)
            display_cons["est_savings_10pct"] = display_cons["est_savings_10pct"].apply(lambda x: fmt_currency(float(x)))
            display_cons.columns = ["Category", "# Vendors", "Total Spend", "Est. Savings (10%)", "Opportunity"]
            st.dataframe(display_cons, use_container_width=True, hide_index=True)

            total_est_savings = vendors_per_cat[vendors_per_cat["vendor_count"] >= 3]["est_savings_10pct"].sum()
            st.markdown(f"""
            <div class="metric-card">
                <p>💡 Total Estimated Savings (10% consolidation discount)</p>
                <h2>{fmt_currency(total_est_savings)}</h2>
                <p>from categories with 3+ vendors</p>
            </div>""", unsafe_allow_html=True)

    # Tail spend analysis
    st.markdown("#### 📉 Tail Spend Analysis")
    vendor_totals = df.groupby("vendor")["amount"].sum().sort_values(ascending=False).reset_index()
    vendor_totals["cum_pct"] = (vendor_totals["amount"].cumsum() / total_spend * 100)
    tail_vendors = vendor_totals[vendor_totals["cum_pct"] > 80]
    head_vendors = vendor_totals[vendor_totals["cum_pct"] <= 80]

    col_t1, col_t2, col_t3 = st.columns(3)
    with col_t1:
        st.markdown(f"""<div class="metric-card">
            <p>🏠 Strategic Vendors (80% spend)</p>
            <h2>{len(head_vendors)}</h2>
            <p>{fmt_currency(head_vendors['amount'].sum())} spend</p>
        </div>""", unsafe_allow_html=True)
    with col_t2:
        st.markdown(f"""<div class="metric-card">
            <p>📉 Tail Vendors</p>
            <h2 style="color:#f6ad55">{len(tail_vendors)}</h2>
            <p>{fmt_currency(tail_vendors['amount'].sum())} combined spend</p>
        </div>""", unsafe_allow_html=True)
    with col_t3:
        avg_tail = tail_vendors["amount"].mean() if len(tail_vendors) > 0 else 0
        st.markdown(f"""<div class="metric-card">
            <p>📊 Avg Tail Vendor Spend</p>
            <h2>{fmt_currency(avg_tail)}</h2>
            <p>per vendor annually</p>
        </div>""", unsafe_allow_html=True)

    st.divider()
    st.markdown("### 🤖 AI Analysis — Savings Opportunities")
    tabs = st.tabs([PROMPTS[k]["label"] for k in CATEGORIES["Savings Opportunities"]])
    for tab, key in zip(tabs, CATEGORIES["Savings Opportunities"]):
        with tab:
            ai_analysis_section(key)


# ─────────────────────────────────────────────────────────────────────────────
# ════════════════════════ PAGE: CATEGORY MAPPING ════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────
elif "Category Mapping" in page:
    st.markdown("## 🏷️ Category Mapping & Taxonomy")
    st.caption("Prompts 11–12: Auto-classify transactions and remap to standard taxonomy")
    st.divider()

    if "category" in df.columns:
        col_l, col_r = st.columns([1, 1])

        with col_l:
            st.markdown("#### Current Category Distribution")
            fig_cat_bar = px.bar(
                spend_by_cat, x="pct", y="category",
                orientation="h",
                color="pct",
                color_continuous_scale=px.colors.sequential.Blues,
                text="pct",
                labels={"pct": "% of Spend", "category": ""},
            )
            fig_cat_bar.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig_cat_bar.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="#e2e8f0", coloraxis_showscale=False,
                xaxis=dict(showgrid=True, gridcolor="#2d3748"),
                yaxis=dict(showgrid=False),
                margin=dict(t=10, b=10), height=400,
            )
            st.plotly_chart(fig_cat_bar, use_container_width=True)

        with col_r:
            st.markdown("#### Vendor ↔ Category Matrix (Top 15)")
            top_vendors_list = spend_by_vendor.head(15)["vendor"].tolist()
            heat_df = df[df["vendor"].isin(top_vendors_list)].groupby(["vendor", "category"])["amount"].sum().reset_index()
            heat_pivot = heat_df.pivot(index="vendor", columns="category", values="amount").fillna(0)

            fig_heat = px.imshow(
                heat_pivot,
                color_continuous_scale="Blues",
                aspect="auto",
                labels=dict(color="Spend ($)"),
            )
            fig_heat.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="#e2e8f0", coloraxis_showscale=True,
                xaxis=dict(tickangle=-45),
                margin=dict(t=10, b=80, l=10), height=400,
            )
            st.plotly_chart(fig_heat, use_container_width=True)

    # UNSPSC mapping reference table
    st.markdown("#### 📚 UNSPSC Standard Category Mapping Reference")
    unspsc_map = {
        "IT & Software":             "43000000 — Information Technology",
        "Professional Services":     "80000000 — Management & Business",
        "Marketing & Advertising":   "82000000 — Editorial & Design",
        "Travel & Expenses":         "90000000 — Travel & Food Services",
        "Facilities & Real Estate":  "72000000 — Building & Construction",
        "HR & Recruitment":          "93000000 — Politics & Civic Affairs",
        "Logistics & Freight":       "78000000 — Transportation & Storage",
        "Raw Materials":             "11000000 — Mineral & Textile",
        "Office Supplies":           "44000000 — Office Equipment",
        "Utilities":                 "83000000 — Public Utilities",
    }
    map_df = pd.DataFrame([(k, v) for k, v in unspsc_map.items()], columns=["Current Category", "UNSPSC Segment"])
    st.dataframe(map_df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("### 🤖 AI Analysis — Category Mapping")
    tabs = st.tabs([PROMPTS[k]["label"] for k in CATEGORIES["Category Mapping"]])
    for tab, key in zip(tabs, CATEGORIES["Category Mapping"]):
        with tab:
            ai_analysis_section(key)


# ─────────────────────────────────────────────────────────────────────────────
# ════════════════════════ PAGE: POLICY COMPLIANCE ════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────
elif "Policy Compliance" in page:
    st.markdown("## ⚖️ Policy Compliance")
    st.caption("Prompt 13: Policy violation scan against spend controls")
    st.divider()

    # Rule-based compliance flags
    violations = []
    policy_rules = {
        "Single-source >$10K (3 quotes required)": lambda r: r["amount"] > 10000,
        "T&E >$500 requires VP approval":           lambda r: r.get("category","") == "Travel & Expenses" and r["amount"] > 500 and r.get("approved_by","") not in ["VP","Director"],
        "Round number >$5K (estimate risk)":        lambda r: r["amount"] >= 5000 and r["amount"] == round(r["amount"],-3),
        "Below threshold flag ($9,999)":            lambda r: any(abs(r["amount"] - (t - 1)) < 5 for t in [5000, 10000, 25000, 50000]),
        "Pending payment >$10K":                    lambda r: r.get("payment_status","") == "Pending" and r["amount"] > 10000,
    }

    for _, row in df.iterrows():
        row_dict = row.to_dict()
        for rule_name, rule_fn in policy_rules.items():
            try:
                if rule_fn(row_dict):
                    severity = "High" if "VP" in rule_name or "single-source" in rule_name.lower() else "Medium"
                    violations.append({
                        "date": row_dict.get("date", ""),
                        "vendor": row_dict.get("vendor", ""),
                        "amount": row_dict.get("amount", 0),
                        "rule": rule_name,
                        "severity": severity,
                        "approved_by": row_dict.get("approved_by", ""),
                    })
            except:
                pass

    if violations:
        viol_df = pd.DataFrame(violations)
        total_viol_spend = viol_df["amount"].sum()

        col_v1, col_v2, col_v3 = st.columns(3)
        with col_v1:
            st.markdown(f"""<div class="metric-card">
                <p>🚫 Total Violations</p>
                <h2 style="color:#fc8181">{len(viol_df)}</h2>
                <p>across {viol_df['rule'].nunique()} policy rules</p>
            </div>""", unsafe_allow_html=True)
        with col_v2:
            high_sev = (viol_df["severity"] == "High").sum()
            st.markdown(f"""<div class="metric-card">
                <p>🔴 High Severity</p>
                <h2 style="color:#fc8181">{high_sev}</h2>
                <p>require immediate review</p>
            </div>""", unsafe_allow_html=True)
        with col_v3:
            st.markdown(f"""<div class="metric-card">
                <p>💸 Spend at Risk</p>
                <h2 style="color:#f6ad55">{fmt_currency(total_viol_spend)}</h2>
                <p>non-compliant transactions</p>
            </div>""", unsafe_allow_html=True)

        # Violations by rule
        st.markdown("#### Violations by Policy Rule")
        rule_counts = viol_df.groupby("rule").agg(
            count=("amount", "count"),
            total_spend=("amount", "sum"),
        ).reset_index().sort_values("total_spend", ascending=False)

        fig_viol = px.bar(
            rule_counts, x="total_spend", y="rule",
            orientation="h",
            color="count",
            color_continuous_scale=["#f6ad55", "#fc8181"],
            text="count",
            labels={"total_spend": "Spend at Risk ($)", "rule": "", "count": "# Violations"},
        )
        fig_viol.update_traces(texttemplate="%{text} violations", textposition="outside")
        fig_viol.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font_color="#e2e8f0", coloraxis_showscale=False,
            xaxis=dict(showgrid=True, gridcolor="#2d3748"),
            yaxis=dict(showgrid=False),
            margin=dict(t=10, b=10), height=360,
        )
        st.plotly_chart(fig_viol, use_container_width=True)

        # Detail table
        with st.expander("📋 Violation Detail Table", expanded=True):
            display_v = viol_df.copy()
            display_v["amount"] = display_v["amount"].apply(fmt_currency)
            display_v["severity"] = display_v["severity"].apply(
                lambda s: f"🔴 {s}" if s == "High" else f"🟡 {s}"
            )
            st.dataframe(
                display_v.sort_values("severity", ascending=False),
                use_container_width=True, hide_index=True, height=300,
            )
    else:
        st.success("✅ No rule-based policy violations detected.")

    st.divider()
    st.markdown("### 🤖 AI Analysis — Policy Compliance (Prompt 13)")
    ai_analysis_section("policy_violations")


# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
st.divider()
st.markdown(
    "<center><small>💰 Vendor Spend Analysis · Powered by Claude AI · Built with Streamlit</small></center>",
    unsafe_allow_html=True,
)
