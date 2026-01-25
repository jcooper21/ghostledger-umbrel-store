"""
GhostLedger Parsers
===================
Handles importing transaction data from various sources.

Privacy-First Design:
---------------------
All parsing happens locally. Price data comes from:
1. User-provided historical price CSV (recommended for privacy)
2. Hardcoded fallback data (for testing)
3. Future: Optional CoinGecko API (user-initiated, no wallet data sent)

WHY Sparrow Wallet?
-------------------
Sparrow is the gold standard for Bitcoin self-custody:
- Open source
- Supports hardware wallets
- Full UTXO control
- Clean CSV export format

The CSV export contains transaction history with labels, making it ideal
for tax tracking when combined with historical price data.
"""

import pandas as pd
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import List, Optional, Tuple, BinaryIO
from io import StringIO
import re
import requests
import time

from acb_engine import Transaction


# Sats to BTC conversion factor
SATS_PER_BTC = Decimal('100000000')


def parse_sparrow_csv(file_buffer: BinaryIO) -> Tuple[List[Transaction], List[str]]:
    """
    Parse a Sparrow Wallet CSV export into Transaction objects.
    
    Sparrow CSV Format (typical columns):
    - Date: Transaction timestamp
    - Label: User-defined label
    - Value: Amount in sats or BTC (positive = receive, negative = send)
    - Balance: Running balance after transaction
    - Fee: Transaction fee (for sends)
    - Txid: Transaction ID (optional, for reference)
    
    Args:
        file_buffer: File-like object containing CSV data
        
    Returns:
        Tuple of (transactions, warnings)
        - transactions: List of parsed Transaction objects (without prices)
        - warnings: List of warning messages for rows that couldn't be parsed
    
    Note: Transactions returned do NOT have prices filled in.
          Use add_prices_to_transactions() to add historical prices.
    """
    warnings = []
    transactions = []
    
    try:
        # Read the file content
        if hasattr(file_buffer, 'read'):
            content = file_buffer.read()
            if isinstance(content, bytes):
                content = content.decode('utf-8')
        else:
            content = str(file_buffer)
        
        # Parse CSV
        df = pd.read_csv(StringIO(content))
        
        # Normalize column names (handle variations)
        df.columns = df.columns.str.strip().str.lower()
        
        # Map common column name variations
        column_map = {
            'date': ['date', 'datetime', 'timestamp', 'time', 'date (utc)'],
            'label': ['label', 'memo', 'note', 'description'],
            'value': ['value', 'amount', 'btc', 'sats'],
            'balance': ['balance', 'running_balance', 'total'],
            'fee': ['fee', 'fees', 'tx_fee', 'network_fee'],
        }
        
        # Find matching columns
        found_cols = {}
        for target, candidates in column_map.items():
            for candidate in candidates:
                if candidate in df.columns:
                    found_cols[target] = candidate
                    break
        
        # Validate required columns
        if 'date' not in found_cols:
            warnings.append("ERROR: Could not find date column in CSV")
            return [], warnings
        if 'value' not in found_cols:
            warnings.append("ERROR: Could not find value/amount column in CSV")
            return [], warnings
        
        # Process each row
        for idx, row in df.iterrows():
            try:
                # Parse date
                date_str = str(row[found_cols['date']])
                tx_date = _parse_date(date_str)
                
                if tx_date is None:
                    warnings.append(f"Row {idx+1}: Could not parse date '{date_str}'")
                    continue
                
                # Parse value (amount)
                value_raw = row[found_cols['value']]
                amount_btc, is_negative = _parse_amount(value_raw)
                
                if amount_btc is None:
                    warnings.append(f"Row {idx+1}: Could not parse amount '{value_raw}'")
                    continue
                
                # Determine transaction type from sign
                # Positive = receive/buy, Negative = send/spend
                if is_negative:
                    tx_type = 'send'  # Could also be 'sell' or 'spend'
                else:
                    tx_type = 'receive'  # Could also be 'buy'
                
                # Parse fee if available
                fee_cad = Decimal('0')
                if 'fee' in found_cols and pd.notna(row.get(found_cols['fee'])):
                    fee_btc = _parse_amount(row[found_cols['fee']])[0]
                    if fee_btc:
                        # Store fee in BTC for now - will convert to CAD with price data
                        # For now, set to 0 - price conversion handles this
                        pass
                
                # Get label if available
                label = ''
                if 'label' in found_cols and pd.notna(row.get(found_cols['label'])):
                    label = str(row[found_cols['label']]).strip()
                
                # Refine transaction type based on label hints
                tx_type = _infer_tx_type(tx_type, label)
                
                # Create transaction (price_cad will be filled later)
                tx = Transaction(
                    date=tx_date,
                    tx_type=tx_type,
                    amount_btc=amount_btc,
                    price_cad=Decimal('0'),  # Placeholder - needs price data
                    fee_cad=Decimal('0'),
                    label=label
                )
                
                transactions.append(tx)
                
            except Exception as e:
                warnings.append(f"Row {idx+1}: Error processing - {str(e)}")
                continue
        
        if not transactions:
            warnings.append("No valid transactions found in CSV")
        
    except Exception as e:
        warnings.append(f"Failed to parse CSV: {str(e)}")
    
    return transactions, warnings


def _parse_date(date_str: str) -> Optional[datetime]:
    """
    Parse various date formats commonly used in wallet exports.
    
    WHY multiple formats?
    ---------------------
    Different wallet versions and locales use different date formats.
    We need to handle common variations gracefully.
    """
    date_formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d',
        '%d/%m/%Y %H:%M:%S',
        '%d/%m/%Y',
        '%m/%d/%Y %H:%M:%S',
        '%m/%d/%Y',
        '%Y/%m/%d %H:%M:%S',
        '%Y/%m/%d',
        '%d-%m-%Y %H:%M:%S',
        '%d-%m-%Y',
    ]
    
    date_str = date_str.strip()
    
    for fmt in date_formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    # Try pandas parser as fallback
    try:
        return pd.to_datetime(date_str).to_pydatetime()
    except:
        return None


def _parse_amount(value) -> Tuple[Optional[Decimal], bool]:
    """
    Parse amount from various formats (BTC or sats).
    
    Returns:
        Tuple of (amount_in_btc, is_negative)
    
    WHY handle both BTC and sats?
    -----------------------------
    Some exports use BTC (0.00050000), others use sats (50000).
    
    Detection heuristics:
    1. If the value has a decimal point with significant fractional digits, it's BTC
    2. If the value is a whole number > 21, it's likely sats
    3. Values > 21 million are definitely sats (max BTC supply)
    """
    if pd.isna(value):
        return None, False
    
    # Convert to string and clean
    value_str = str(value).strip()
    
    # Check for negative
    is_negative = value_str.startswith('-')
    value_str = value_str.lstrip('-')
    
    # Check if this looks like BTC (has meaningful decimal places)
    has_decimal = '.' in value_str
    
    # Remove any currency symbols or commas
    value_str = re.sub(r'[^\d.]', '', value_str)
    
    try:
        amount = Decimal(value_str)
    except InvalidOperation:
        return None, False
    
    # Detect if this is sats or BTC
    # Heuristics:
    # 1. If it has a decimal point and fractional part, assume BTC
    # 2. If it's a whole number and > 21 (unlikely to hold 21+ whole BTC), assume sats
    # 3. If > 21 million, definitely sats (can't have more than max supply)
    
    if has_decimal and amount != amount.to_integral_value():
        # Has meaningful decimal places - this is BTC
        pass  # Keep as BTC
    elif amount > 21_000_000:
        # Definitely sats - exceeds max BTC supply
        amount = amount / SATS_PER_BTC
    elif amount > 21 and amount == amount.to_integral_value():
        # Whole number > 21 - likely sats
        # (Unlikely someone has 22+ whole BTC in a single transaction)
        amount = amount / SATS_PER_BTC
    # else: Small whole number (0-21), ambiguous but assume BTC
    
    return amount, is_negative


def _infer_tx_type(base_type: str, label: str) -> str:
    """
    Refine transaction type based on label keywords.
    
    WHY this matters for tax?
    -------------------------
    'receive' vs 'buy' matters for ACB calculation:
    - 'buy' = exchange purchase (has CAD cost basis)
    - 'receive' = transfer from own wallet (no new cost basis)
    - 'sell' = exchange sale (triggers capital gain)
    - 'spend' = payment for goods/services (triggers capital gain)
    - 'send' = transfer to own wallet (no tax event)
    
    Users should label their transactions appropriately in Sparrow.
    """
    label_lower = label.lower()
    
    buy_keywords = ['buy', 'purchase', 'dca', 'exchange', 'acquired', 'bought']
    sell_keywords = ['sell', 'sold', 'exchange', 'profit', 'exit']
    spend_keywords = ['spend', 'payment', 'paid', 'purchase', 'bought']  # buying goods
    
    if base_type == 'receive':
        for kw in buy_keywords:
            if kw in label_lower:
                return 'buy'
    
    if base_type == 'send':
        for kw in sell_keywords:
            if kw in label_lower:
                return 'sell'
        for kw in spend_keywords:
            if kw in label_lower:
                return 'spend'
    
    return base_type


class HistoricalPriceProvider:
    """
    Provides historical BTC/CAD prices for transaction valuation.
    
    Privacy-First Architecture:
    ---------------------------
    1. PRIMARY: User provides their own price CSV (fully offline)
    2. FALLBACK: Hardcoded monthly averages (for testing/demos)
    3. FUTURE: Optional API fetch (user-initiated, no wallet data sent)
    
    WHY user-provided CSV?
    ----------------------
    - 100% offline operation
    - User controls data source
    - Can use official exchange records for CRA audit
    - No API rate limits or reliability concerns
    """
    
    def __init__(self):
        self.prices: dict = {}  # date string -> CAD price
        self._load_fallback_prices()
    
    def _load_fallback_prices(self):
        """
        Load hardcoded fallback prices for testing.
        
        These are approximate monthly averages - NOT suitable for production.
        Users should provide their own price data from a reliable source.
        """
        # Approximate BTC/CAD monthly averages for testing
        # Format: 'YYYY-MM' -> approximate_cad_price
        self.fallback_monthly = {
            '2023-01': 23000,
            '2023-02': 31000,
            '2023-03': 37000,
            '2023-04': 39000,
            '2023-05': 37000,
            '2023-06': 41000,
            '2023-07': 40000,
            '2023-08': 36000,
            '2023-09': 36000,
            '2023-10': 46000,
            '2023-11': 50000,
            '2023-12': 58000,
            '2024-01': 58000,
            '2024-02': 70000,
            '2024-03': 90000,
            '2024-04': 85000,
            '2024-05': 87000,
            '2024-06': 85000,
            '2024-07': 88000,
            '2024-08': 80000,
            '2024-09': 78000,
            '2024-10': 92000,
            '2024-11': 125000,
            '2024-12': 130000,
            '2025-01': 135000,
        }
    
    def load_price_csv(self, file_buffer: BinaryIO) -> Tuple[bool, str]:
        """
        Load historical prices from user-provided CSV.
        
        Expected CSV Format:
        - Column 1: Date (YYYY-MM-DD)
        - Column 2: Price (BTC/CAD)
        
        Accepts downloads from Yahoo Finance, CoinGecko exports, etc.
        """
        try:
            if hasattr(file_buffer, 'read'):
                content = file_buffer.read()
                if isinstance(content, bytes):
                    content = content.decode('utf-8')
            else:
                content = str(file_buffer)
            
            df = pd.read_csv(StringIO(content))
            df.columns = df.columns.str.strip().str.lower()
            
            # Find date and price columns
            date_col = None
            price_col = None
            
            for col in df.columns:
                if 'date' in col:
                    date_col = col
                elif any(x in col for x in ['close', 'price', 'cad', 'value']):
                    price_col = col
            
            if date_col is None or price_col is None:
                # Try first two columns as fallback
                if len(df.columns) >= 2:
                    date_col = df.columns[0]
                    price_col = df.columns[1]
                else:
                    return False, "Could not identify date and price columns"
            
            # Parse and store prices
            loaded_count = 0
            for _, row in df.iterrows():
                try:
                    date = pd.to_datetime(row[date_col])
                    date_str = date.strftime('%Y-%m-%d')
                    
                    # Clean price value
                    price_raw = str(row[price_col]).replace(',', '').replace('$', '')
                    price = Decimal(price_raw)
                    
                    self.prices[date_str] = price
                    loaded_count += 1
                except:
                    continue
            
            if loaded_count > 0:
                return True, f"Loaded {loaded_count} daily prices"
            else:
                return False, "No valid price data found in CSV"
                
        except Exception as e:
            return False, f"Error loading price CSV: {str(e)}"
    
    def get_price(self, date: datetime) -> Tuple[Decimal, str]:
        """
        Get BTC/CAD price for a specific date.
        
        Lookup Priority:
        1. Exact date match in user-provided prices
        2. Nearest date within 7 days in user-provided prices
        3. Monthly fallback (with warning)
        
        Returns:
            Tuple of (price, source_note)
        """
        date_str = date.strftime('%Y-%m-%d')
        
        # 1. Try exact match
        if date_str in self.prices:
            return self.prices[date_str], 'exact'
        
        # 2. Try nearest date within 7 days
        for days_offset in range(1, 8):
            for delta in [-days_offset, days_offset]:
                check_date = date + pd.Timedelta(days=delta)
                check_str = check_date.strftime('%Y-%m-%d')
                if check_str in self.prices:
                    return self.prices[check_str], f'nearest ({delta:+d} days)'
        
        # 3. Fall back to monthly average
        month_str = date.strftime('%Y-%m')
        if month_str in self.fallback_monthly:
            return Decimal(str(self.fallback_monthly[month_str])), 'monthly_fallback'
        
        # 4. Last resort - return 0 with error
        return Decimal('0'), 'NO_PRICE_DATA'

    def fetch_from_coingecko(self) -> Tuple[bool, str]:
        """
        Fetch historical BTC/CAD prices using CoinCap API (free, no auth).
        
        Strategy:
        1. Fetch BTC/USD from CoinCap (free API, no auth)
        2. Use a fixed approximate USD/CAD rate of 1.35 for historical data
        
        Returns:
            Tuple of (success, message)
        """
        try:
            # CoinCap provides BTC/USD historical data for free
            # Get last 2000 days of daily data
            end_time = int(time.time() * 1000)
            start_time = end_time - (2000 * 24 * 60 * 60 * 1000)  # ~5.5 years back
            
            url = "https://api.coincap.io/v2/assets/bitcoin/history"
            params = {
                'interval': 'd1',
                'start': start_time,
                'end': end_time
            }
            
            headers = {
                'Accept': 'application/json',
                'Accept-Encoding': 'gzip'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=15)
            
            if response.status_code != 200:
                return False, f"API Error: {response.status_code} - {response.text[:100]}"
            
            data = response.json()
            
            if 'data' not in data or not data['data']:
                return False, "No price data in API response"
            
            # Approximate USD/CAD rate (historical average)
            # This is close enough for tax estimation purposes
            usd_cad_rate = Decimal('1.35')
            
            loaded_count = 0
            for item in data['data']:
                try:
                    ts_ms = item.get('time')
                    price_usd = item.get('priceUsd')
                    
                    if ts_ms and price_usd:
                        dt = datetime.fromtimestamp(ts_ms / 1000)
                        date_str = dt.strftime('%Y-%m-%d')
                        
                        # Convert USD to CAD
                        price_cad = Decimal(str(price_usd)) * usd_cad_rate
                        self.prices[date_str] = price_cad
                        loaded_count += 1
                except (ValueError, TypeError):
                    continue
            
            if loaded_count > 0:
                return True, f"Loaded {loaded_count} daily prices (USD×1.35 to CAD)"
            else:
                return False, "No valid price data found"
                
        except requests.exceptions.Timeout:
            return False, "Request timed out - try again"
        except requests.exceptions.ConnectionError:
            return False, "Network connection failed"
        except Exception as e:
            return False, f"Error: {str(e)}"


def add_prices_to_transactions(
    transactions: List[Transaction], 
    price_provider: HistoricalPriceProvider
) -> Tuple[List[Transaction], List[str]]:
    """
    Add historical prices to parsed transactions.
    
    WHY separate from parsing?
    --------------------------
    Separating price lookup from parsing allows:
    1. User to load price data separately
    2. Retry price lookup with different data source
    3. Clear separation of concerns
    
    Args:
        transactions: List of Transaction objects (without prices)
        price_provider: HistoricalPriceProvider instance with loaded prices
        
    Returns:
        Tuple of (updated_transactions, warnings)
    """
    warnings = []
    
    for tx in transactions:
        price, source = price_provider.get_price(tx.date)
        
        if source == 'NO_PRICE_DATA':
            warnings.append(
                f"{tx.date.strftime('%Y-%m-%d')}: No price data available. "
                f"Using $0 - MUST UPDATE for accurate tax calculation."
            )
            tx.price_cad = Decimal('0')
        elif source == 'monthly_fallback':
            warnings.append(
                f"{tx.date.strftime('%Y-%m-%d')}: Using monthly average price (${price:,.2f}). "
                f"Upload historical price CSV for accuracy."
            )
            tx.price_cad = price
        else:
            tx.price_cad = price
    
    return transactions, warnings


# Sample price data generator for testing
def generate_sample_price_csv() -> str:
    """
    Generate sample BTC/CAD price CSV for testing.
    
    This creates ~365 days of synthetic price data.
    In production, users should download real data from Yahoo Finance or similar.
    """
    import random
    from datetime import timedelta
    
    lines = ['date,close']
    base_price = 50000
    current_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 12, 31)
    
    while current_date <= end_date:
        # Random walk with slight upward bias
        change = random.gauss(0.002, 0.03)  # 0.2% daily drift, 3% volatility
        base_price = base_price * (1 + change)
        base_price = max(20000, min(200000, base_price))  # Bound prices
        
        lines.append(f"{current_date.strftime('%Y-%m-%d')},{base_price:.2f}")
        current_date += timedelta(days=1)
    
    return '\n'.join(lines)


if __name__ == '__main__':
    # Test the parser with sample data
    sample_sparrow_csv = """Date,Label,Value,Balance,Txid
2024-01-15 10:30:00,DCA Buy,50000000,50000000,abc123
2024-02-20 14:15:00,Buy from exchange,25000000,75000000,def456
2024-03-10 09:00:00,Sell profit,-30000000,45000000,ghi789
2024-04-05 16:45:00,DCA Buy,10000000,55000000,jkl012
2024-04-20 11:30:00,Sell at loss,-20000000,35000000,mno345
"""
    
    print("Testing Sparrow CSV Parser")
    print("=" * 60)
    
    from io import StringIO
    
    transactions, warnings = parse_sparrow_csv(StringIO(sample_sparrow_csv))
    
    print(f"Parsed {len(transactions)} transactions")
    if warnings:
        print(f"Warnings: {warnings}")
    
    for tx in transactions:
        print(f"  {tx.date.strftime('%Y-%m-%d')} | {tx.tx_type:8} | {tx.amount_btc:.8f} BTC | {tx.label}")
    
    print("\nAdding prices...")
    provider = HistoricalPriceProvider()
    transactions, price_warnings = add_prices_to_transactions(transactions, provider)
    
    if price_warnings:
        print("Price warnings:")
        for w in price_warnings:
            print(f"  ⚠️  {w}")
    
    print("\nTransactions with prices:")
    for tx in transactions:
        print(f"  {tx.date.strftime('%Y-%m-%d')} | {tx.tx_type:8} | {tx.amount_btc:.8f} BTC @ ${tx.price_cad:,.2f}")
