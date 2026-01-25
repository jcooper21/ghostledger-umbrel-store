"""
GhostLedger - Local-First Bitcoin Tax Calculator
================================================

A privacy-focused Bitcoin tax calculator for Canadian taxpayers.
All processing happens locally - your transaction data never leaves your device.

Running:
    streamlit run app.py

Features:
- Import from Sparrow Wallet CSV
- Adjusted Cost Base (ACB) calculation per CRA rules
- Capital gains/loss tracking
- Superficial loss detection
- Schedule 3 export
"""

import streamlit as st
import pandas as pd
from decimal import Decimal
from datetime import datetime
from io import StringIO, BytesIO
from typing import Optional

# Local imports
from acb_engine import ACBCalculator, Transaction, LedgerEntry
from parsers import (
    parse_sparrow_csv, 
    HistoricalPriceProvider,
    add_prices_to_transactions,
    generate_sample_price_csv
)


# Page configuration
st.set_page_config(
    page_title="GhostLedger - Bitcoin Tax Calculator",
    page_icon="👻",
    layout="wide",
    initial_sidebar_state="expanded"
)


def init_session_state():
    """Initialize session state variables."""
    if 'transactions' not in st.session_state:
        st.session_state.transactions = []
    if 'ledger' not in st.session_state:
        st.session_state.ledger = []
    if 'summary' not in st.session_state:
        st.session_state.summary = None
    if 'price_provider' not in st.session_state:
        st.session_state.price_provider = HistoricalPriceProvider()
    if 'price_fetch_attempted' not in st.session_state:
        st.session_state.price_fetch_attempted = False
    
    # Auto-fetch on startup if not yet attempted
    if not st.session_state.prices_loaded and not st.session_state.price_fetch_attempted:
        fetch_prices()


    if 'selected_year' not in st.session_state:
        st.session_state.selected_year = datetime.now().year


def fetch_prices():
    """Attempt to fetch prices with retry logic."""
    import time
    
    st.session_state.price_fetch_attempted = True
    
    with st.spinner("👻 GhostLedger is fetching latest Bitcoin prices..."):
        # Simple retry logic
        max_retries = 3
        for i in range(max_retries):
            success, msg = st.session_state.price_provider.fetch_from_coingecko()
            if success:
                st.session_state.prices_loaded = True
                st.toast(f"✅ {msg}")
                return
            
            # If failed, wait briefly before retry (unless it's the last attempt)
            if i < max_retries - 1:
                time.sleep(2)
        
        # If we get here, all retries failed
        st.toast(f"⚠️ Could not auto-fetch prices: {msg}")


def render_sidebar():
    """Render the sidebar with file uploaders and settings."""
    with st.sidebar:
        st.title("👻 GhostLedger")
        st.caption("Local-First Bitcoin Tax Calculator")
        
        st.divider()
        
        # Privacy notice
        st.info(
            "🔒 **100% Local Processing**\n\n"
            "Your transaction data never leaves this device. "
            "All calculations happen in your browser/container."
        )
        
        st.divider()
        
        # Step 1: Price Data
        st.subheader("1️⃣ Historical Prices")
        st.caption(
            "Prices are fetched automatically from CoinGecko. "
            "You can also upload your own CSV below."
        )
        
        if st.session_state.prices_loaded:
             st.success("✅ Price history loaded")
        else:
            col1, col2 = st.columns([2, 1])
            with col1:
                st.warning("⚠️ No prices loaded")
            with col2:
                if st.button("Retry"):
                    fetch_prices()
                    st.rerun()

        
        with st.expander("Upload Manual CSV"):
            price_file = st.file_uploader(
                "Upload Price CSV",
                type=['csv'],
                key='price_uploader',
                help="Download daily BTC-CAD.csv from Yahoo Finance"
            )
            
            if price_file:
                success, message = st.session_state.price_provider.load_price_csv(price_file)
                if success:
                    st.success(f"✅ {message}")
                    st.session_state.prices_loaded = True
                else:
                    st.error(f"❌ {message}")
        
        # Show sample download
        with st.expander("📥 Need sample price data?"):
            sample_csv = generate_sample_price_csv()
            st.download_button(
                "Download Sample Prices (2024)",
                data=sample_csv,
                file_name="btc_cad_2024_sample.csv",
                mime="text/csv"
            )
            st.caption(
                "⚠️ Sample data is synthetic. For accurate tax filing, "
                "download real prices from Yahoo Finance or CoinGecko."
            )
        
        st.divider()
        
        # Step 2: Transaction Data
        st.subheader("2️⃣ Transactions")
        st.caption("Upload your Sparrow Wallet CSV export.")
        
        tx_file = st.file_uploader(
            "Upload Sparrow CSV",
            type=['csv'],
            key='tx_uploader',
            help="Export from Sparrow: File > Export > Transaction History"
        )
        
        if tx_file:
            process_transactions(tx_file)
        
        # Show sample transaction download
        with st.expander("📥 Need sample transaction data?"):
            sample_tx = """Date,Label,Value,Balance,Txid
2024-01-15 10:30:00,DCA Buy,50000000,50000000,abc123
2024-02-20 14:15:00,Buy exchange,25000000,75000000,def456
2024-03-10 09:00:00,Sell profit,-30000000,45000000,ghi789
2024-04-05 16:45:00,DCA Buy,10000000,55000000,jkl012
2024-04-20 11:30:00,Sell position,-20000000,35000000,mno345
2024-06-15 14:00:00,DCA Buy,15000000,50000000,pqr678
2024-09-01 09:30:00,Sell partial,-10000000,40000000,stu901
2024-11-20 16:00:00,Buy dip,30000000,70000000,vwx234
"""
            st.download_button(
                "Download Sample Transactions",
                data=sample_tx,
                file_name="sample_sparrow_export.csv",
                mime="text/csv"
            )
        
        st.divider()
        
        # Year selector
        st.subheader("3️⃣ Tax Year")
        years = list(range(2020, datetime.now().year + 2))
        st.session_state.selected_year = st.selectbox(
            "Select Tax Year",
            years,
            index=years.index(datetime.now().year)
        )
        
        st.divider()
        
        # Footer
        st.caption(
            "GhostLedger v0.1 MVP\n\n"
            "Built for Canadian taxpayers following CRA ACB rules.\n\n"
            "⚠️ Not tax advice. Consult a professional."
        )


def process_transactions(tx_file):
    """Process uploaded transaction file."""
    # Parse transactions
    transactions, parse_warnings = parse_sparrow_csv(tx_file)
    
    if parse_warnings:
        for warning in parse_warnings:
            if warning.startswith('ERROR'):
                st.sidebar.error(warning)
            else:
                st.sidebar.warning(warning)
    
    if not transactions:
        st.sidebar.error("No valid transactions found")
        return
    
    # Add prices
    transactions, price_warnings = add_prices_to_transactions(
        transactions, 
        st.session_state.price_provider
    )
    
    if price_warnings:
        with st.sidebar.expander(f"⚠️ {len(price_warnings)} price warnings"):
            for w in price_warnings:
                st.caption(w)
    
    # Process with ACB calculator
    calculator = ACBCalculator()
    ledger = calculator.process_transactions(transactions)
    summary = calculator.get_summary(st.session_state.selected_year)
    
    # Store in session state
    st.session_state.transactions = transactions
    st.session_state.ledger = ledger
    st.session_state.summary = summary
    st.session_state.calculator = calculator
    
    st.sidebar.success(f"✅ Processed {len(transactions)} transactions")


def render_metrics():
    """Render the top metric cards."""
    summary = st.session_state.summary
    
    if not summary:
        st.info("👈 Upload transaction data to see your tax summary")
        return
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Net Capital Gain/Loss",
            f"${float(summary['net_capital_gain']):,.2f}",
            delta=f"{summary['selected_year'] if 'selected_year' in summary else 'YTD'}"
        )
    
    with col2:
        st.metric(
            "Taxable Amount (50%)",
            f"${float(summary['taxable_capital_gain']):,.2f}",
            help="Capital gains inclusion rate is 50% (first $250k)"
        )
    
    with col3:
        st.metric(
            "Current Holdings",
            f"{float(summary['current_holdings_btc']):.8f} BTC",
            help="Total BTC still held"
        )
    
    with col4:
        st.metric(
            "Current ACB",
            f"${float(summary['current_acb_per_btc']):,.2f}/BTC",
            help="Your weighted average cost basis per Bitcoin"
        )
    
    # Superficial loss warning
    if summary['superficial_loss_count'] > 0:
        st.warning(
            f"⚠️ **{summary['superficial_loss_count']} potential superficial loss(es) detected!**\n\n"
            "Review flagged transactions - these losses may be denied by CRA if you repurchased "
            "within 30 days before or after the sale."
        )


def render_ledger_table():
    """Render the detailed transaction ledger."""
    ledger = st.session_state.ledger
    
    if not ledger:
        return
    
    st.subheader("📊 Transaction Ledger")
    
    # Filter options
    col1, col2, col3 = st.columns(3)
    
    with col1:
        show_all = st.checkbox("Show all years", value=False)
    
    with col2:
        show_only_dispositions = st.checkbox("Show only taxable events", value=False)
    
    with col3:
        show_superficial = st.checkbox("Highlight superficial losses", value=True)
    
    # Filter ledger
    filtered_ledger = ledger
    
    if not show_all:
        filtered_ledger = [
            e for e in filtered_ledger 
            if e.date.year == st.session_state.selected_year
        ]
    
    if show_only_dispositions:
        filtered_ledger = [
            e for e in filtered_ledger 
            if e.capital_gain is not None
        ]
    
    if not filtered_ledger:
        st.info("No transactions found for selected filters")
        return
    
    # Build display dataframe
    rows = []
    for entry in filtered_ledger:
        row = {
            'Date': entry.date.strftime('%Y-%m-%d'),
            'Type': entry.tx_type.upper(),
            'Amount (BTC)': f"{float(entry.amount_btc):.8f}",
            'Price (CAD)': f"${float(entry.price_cad):,.2f}",
            'ACB/BTC': f"${float(entry.acb_per_btc):,.2f}",
            'Holdings': f"{float(entry.total_btc_after):.8f}",
        }
        
        if entry.capital_gain is not None:
            row['Proceeds'] = f"${float(entry.proceeds):,.2f}"
            row['Cost Basis'] = f"${float(entry.cost_basis):,.2f}"
            
            gain = float(entry.capital_gain)
            if gain >= 0:
                row['Gain/Loss'] = f"🟢 ${gain:,.2f}"
            else:
                if entry.superficial_loss_flag:
                    row['Gain/Loss'] = f"🔴⚠️ ${gain:,.2f}"
                else:
                    row['Gain/Loss'] = f"🔴 ${gain:,.2f}"
        else:
            row['Proceeds'] = '-'
            row['Cost Basis'] = '-'
            row['Gain/Loss'] = '-'
        
        row['Label'] = entry.label or ''
        
        if entry.superficial_loss_flag and show_superficial:
            row['⚠️'] = 'SUPERFICIAL'
        else:
            row['⚠️'] = ''
        
        rows.append(row)
    
    df = pd.DataFrame(rows)
    
    # Display table
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            'Date': st.column_config.TextColumn('Date', width='small'),
            'Type': st.column_config.TextColumn('Type', width='small'),
            'Amount (BTC)': st.column_config.TextColumn('Amount', width='medium'),
            'Price (CAD)': st.column_config.TextColumn('Price', width='small'),
            'ACB/BTC': st.column_config.TextColumn('ACB/BTC', width='small'),
            'Holdings': st.column_config.TextColumn('Holdings', width='medium'),
            'Proceeds': st.column_config.TextColumn('Proceeds', width='small'),
            'Cost Basis': st.column_config.TextColumn('Cost Basis', width='small'),
            'Gain/Loss': st.column_config.TextColumn('Gain/Loss', width='medium'),
            'Label': st.column_config.TextColumn('Label', width='medium'),
            '⚠️': st.column_config.TextColumn('⚠️', width='small'),
        }
    )


def render_export_section():
    """Render the export options."""
    if not st.session_state.ledger:
        return
    
    st.subheader("📤 Export for Tax Filing")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Schedule 3 export
        st.markdown("**CRA Schedule 3 Format**")
        st.caption("Formatted for Canadian tax return Schedule 3")
        
        if 'calculator' in st.session_state:
            schedule_df = st.session_state.calculator.export_for_schedule_3(
                st.session_state.selected_year
            )
            
            if not schedule_df.empty:
                csv_buffer = BytesIO()
                schedule_df.to_csv(csv_buffer, index=False)
                csv_buffer.seek(0)
                
                st.download_button(
                    "📥 Download Schedule 3 CSV",
                    data=csv_buffer.getvalue(),
                    file_name=f"ghostledger_schedule3_{st.session_state.selected_year}.csv",
                    mime="text/csv"
                )
            else:
                st.info("No dispositions in selected year")
    
    with col2:
        # Full ledger export
        st.markdown("**Full Transaction Ledger**")
        st.caption("Complete ledger with all ACB calculations")
        
        ledger_rows = []
        for entry in st.session_state.ledger:
            ledger_rows.append({
                'Date': entry.date.strftime('%Y-%m-%d %H:%M:%S'),
                'Type': entry.tx_type,
                'Amount_BTC': float(entry.amount_btc),
                'Price_CAD': float(entry.price_cad),
                'Fee_CAD': float(entry.fee_cad),
                'Total_Cost_After': float(entry.total_cost_after),
                'Total_BTC_After': float(entry.total_btc_after),
                'ACB_Per_BTC': float(entry.acb_per_btc),
                'Proceeds': float(entry.proceeds) if entry.proceeds else '',
                'Cost_Basis': float(entry.cost_basis) if entry.cost_basis else '',
                'Capital_Gain': float(entry.capital_gain) if entry.capital_gain else '',
                'Superficial_Loss': entry.superficial_loss_flag,
                'Superficial_Note': entry.superficial_loss_note,
                'Label': entry.label
            })
        
        ledger_df = pd.DataFrame(ledger_rows)
        csv_buffer = BytesIO()
        ledger_df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)
        
        st.download_button(
            "📥 Download Full Ledger CSV",
            data=csv_buffer.getvalue(),
            file_name=f"ghostledger_full_ledger_{st.session_state.selected_year}.csv",
            mime="text/csv"
        )
    
    with col3:
        # Summary export
        st.markdown("**Tax Summary**")
        st.caption("Quick summary for your records")
        
        if st.session_state.summary:
            summary = st.session_state.summary
            summary_text = f"""GhostLedger Tax Summary
=======================
Tax Year: {st.session_state.selected_year}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

CAPITAL GAINS SUMMARY
---------------------
Total Gains: ${float(summary['total_gains']):,.2f}
Total Losses: ${float(summary['total_losses']):,.2f}
Net Capital Gain/Loss: ${float(summary['net_capital_gain']):,.2f}
Taxable Amount (50%): ${float(summary['taxable_capital_gain']):,.2f}

CURRENT HOLDINGS
----------------
Total BTC Held: {float(summary['current_holdings_btc']):.8f} BTC
Total ACB: ${float(summary['current_acb_total']):,.2f}
ACB per BTC: ${float(summary['current_acb_per_btc']):,.2f}

WARNINGS
--------
Potential Superficial Losses: {summary['superficial_loss_count']}

DISCLAIMER
----------
This summary is for informational purposes only.
Consult a qualified tax professional for tax advice.
GhostLedger is not responsible for any errors in tax filings.
"""
            st.download_button(
                "📥 Download Summary TXT",
                data=summary_text,
                file_name=f"ghostledger_summary_{st.session_state.selected_year}.txt",
                mime="text/plain"
            )


def render_acb_explainer():
    """Render an expandable explainer about ACB calculations."""
    with st.expander("📚 Understanding ACB (Adjusted Cost Base)"):
        st.markdown("""
        ### What is ACB?
        
        The **Adjusted Cost Base (ACB)** is the weighted average cost of your Bitcoin holdings.
        Unlike FIFO (First-In-First-Out), ACB treats all your BTC as a single pool with an average cost.
        
        ### How it's calculated
        
        **When you BUY Bitcoin:**
        ```
        New Total Cost = Previous Total Cost + (Amount × Price + Fees)
        New Total BTC = Previous Total BTC + Amount
        ACB per BTC = Total Cost ÷ Total BTC
        ```
        
        **When you SELL Bitcoin:**
        ```
        Proceeds = Amount Sold × Sale Price - Fees
        Cost Basis = Amount Sold × Current ACB per BTC
        Capital Gain/Loss = Proceeds - Cost Basis
        ```
        
        ### Example
        
        | Event | Amount | Price | Total Cost | Total BTC | ACB/BTC |
        |-------|--------|-------|------------|-----------|---------|
        | Buy | 0.5 BTC | $60,000 | $30,000 | 0.5 | $60,000 |
        | Buy | 0.25 BTC | $80,000 | $50,000 | 0.75 | $66,667 |
        | Sell | 0.3 BTC | $90,000 | $30,000 | 0.45 | $66,667 |
        
        **Sell Calculation:**
        - Proceeds: 0.3 × $90,000 = $27,000
        - Cost Basis: 0.3 × $66,667 = $20,000
        - Capital Gain: $27,000 - $20,000 = **$7,000**
        
        ### Superficial Loss Rule
        
        CRA disallows capital losses if you repurchase "identical property" within 30 days 
        before or after the sale. GhostLedger flags potential superficial losses for your review.
        
        ---
        *This is educational information, not tax advice. Consult a professional.*
        """)


def render_main_content():
    """Render the main content area."""
    st.title("👻 GhostLedger")
    st.caption(f"Bitcoin Tax Calculator for Canada | Tax Year: {st.session_state.selected_year}")
    
    render_metrics()
    
    st.divider()
    
    # Tabs for different views
    tab1, tab2, tab3 = st.tabs(["📊 Ledger", "📤 Export", "📚 Learn"])
    
    with tab1:
        render_ledger_table()
    
    with tab2:
        render_export_section()
    
    with tab3:
        render_acb_explainer()


def main():
    """Main application entry point."""
    init_session_state()
    render_sidebar()
    render_main_content()


if __name__ == '__main__':
    main()
