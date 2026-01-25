"""
GhostLedger ACB Engine
======================
Implements the Adjusted Cost Base (ACB) method for Canadian tax calculations.

WHY ACB (not FIFO/LIFO)?
------------------------
CRA requires the "Adjusted Cost Base" method for capital property, which is a 
weighted average cost approach. This differs fundamentally from FIFO (First-In-First-Out)
or LIFO (Last-In-First-Out) used in other jurisdictions.

The principle: When you acquire property multiple times at different prices, your
cost basis becomes the AVERAGE cost across all holdings, not the cost of specific units.

Mathematical Foundation:
- Total Cost = Sum of all acquisition costs (including fees)
- Total Units = Sum of all units acquired
- ACB per Unit = Total Cost / Total Units

When you dispose (sell/spend):
- Cost Basis of Disposed Portion = Units Disposed × Current ACB per Unit
- Capital Gain/Loss = Proceeds - Cost Basis of Disposed Portion

After disposal, ACB per unit remains unchanged (only total cost and units decrease proportionally).
"""

import pandas as pd
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP


@dataclass
class Transaction:
    """Represents a single cryptocurrency transaction."""
    date: datetime
    tx_type: str  # 'buy', 'sell', 'spend', 'receive', 'send'
    amount_btc: Decimal  # Amount in BTC (positive for all types)
    price_cad: Decimal  # Price per BTC in CAD at time of transaction
    fee_cad: Decimal = Decimal('0')  # Transaction fees in CAD
    label: str = ''  # User label from Sparrow
    
    @property
    def total_cad(self) -> Decimal:
        """Total CAD value including fees."""
        return (self.amount_btc * self.price_cad) + self.fee_cad


@dataclass
class LedgerEntry:
    """
    A processed ledger entry with ACB calculations.
    
    This is what gets displayed in the UI and exported for CRA Schedule 3.
    """
    date: datetime
    tx_type: str
    amount_btc: Decimal
    price_cad: Decimal
    fee_cad: Decimal
    
    # ACB tracking (updated after each transaction)
    total_cost_after: Decimal  # Total ACB of all holdings after this tx
    total_btc_after: Decimal   # Total BTC held after this tx
    acb_per_btc: Decimal       # ACB per unit after this tx
    
    # Capital gains (only populated for dispositions)
    proceeds: Optional[Decimal] = None
    cost_basis: Optional[Decimal] = None
    capital_gain: Optional[Decimal] = None
    
    # Superficial loss flag
    superficial_loss_flag: bool = False
    superficial_loss_note: str = ''
    
    label: str = ''


class ACBCalculator:
    """
    Calculates Adjusted Cost Base for Bitcoin transactions per CRA rules.
    
    Key CRA Concepts Implemented:
    1. Weighted Average Cost: All acquisitions pool together
    2. Superficial Loss Rule: Losses denied if repurchased within 30 days
    3. Identical Property: All BTC is treated as one fungible pool
    """
    
    def __init__(self):
        # Running totals - the core state
        self.total_cost: Decimal = Decimal('0')  # Total ACB of all BTC held
        self.total_btc: Decimal = Decimal('0')   # Total BTC units held
        
        # Processed results
        self.ledger: List[LedgerEntry] = []
        
        # For superficial loss detection
        self._recent_transactions: List[Transaction] = []
    
    @property
    def acb_per_btc(self) -> Decimal:
        """
        Current ACB per Bitcoin.
        
        WHY this formula?
        -----------------
        ACB per unit = Total Cost / Total Units
        
        This gives us the average price paid for all BTC we currently hold.
        When we sell, we use this to determine our cost basis for that sale.
        """
        if self.total_btc <= 0:
            return Decimal('0')
        return (self.total_cost / self.total_btc).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
    
    def process_transactions(self, transactions: List[Transaction]) -> List[LedgerEntry]:
        """
        Process a list of transactions and compute ACB for each.
        
        Transactions must be sorted by date (oldest first) for correct calculation.
        
        Returns: List of LedgerEntry objects with full ACB calculations.
        """
        # Sort by date to ensure chronological processing
        sorted_txs = sorted(transactions, key=lambda x: x.date)
        
        self.ledger = []
        self.total_cost = Decimal('0')
        self.total_btc = Decimal('0')
        self._recent_transactions = []
        
        for tx in sorted_txs:
            if tx.tx_type in ('buy', 'receive'):
                entry = self._process_acquisition(tx)
            elif tx.tx_type in ('sell', 'spend', 'send'):
                entry = self._process_disposition(tx)
            else:
                # Unknown type - log but skip
                continue
            
            self.ledger.append(entry)
            self._recent_transactions.append(tx)
        
        return self.ledger
    
    def _process_acquisition(self, tx: Transaction) -> LedgerEntry:
        """
        Process a BTC acquisition (buy or receive).
        
        ACB Formula for Acquisitions:
        -----------------------------
        New Total Cost = Previous Total Cost + (Amount × Price + Fees)
        New Total BTC = Previous Total BTC + Amount
        
        WHY include fees?
        -----------------
        CRA allows you to add acquisition costs (including fees) to your ACB.
        This increases your cost basis, reducing capital gains when you sell.
        """
        # Calculate cost of this acquisition
        acquisition_cost = (tx.amount_btc * tx.price_cad) + tx.fee_cad
        
        # Update running totals
        self.total_cost += acquisition_cost
        self.total_btc += tx.amount_btc
        
        # Create ledger entry
        entry = LedgerEntry(
            date=tx.date,
            tx_type=tx.tx_type,
            amount_btc=tx.amount_btc,
            price_cad=tx.price_cad,
            fee_cad=tx.fee_cad,
            total_cost_after=self.total_cost,
            total_btc_after=self.total_btc,
            acb_per_btc=self.acb_per_btc,
            label=tx.label
        )
        
        return entry
    
    def _process_disposition(self, tx: Transaction) -> LedgerEntry:
        """
        Process a BTC disposition (sell, spend, or send).
        
        Capital Gain Formula:
        ---------------------
        Proceeds = Amount Sold × Price at Sale
        Cost Basis = Amount Sold × Current ACB per Unit
        Capital Gain/Loss = Proceeds - Cost Basis
        
        WHY use ACB per unit (not purchase price)?
        ------------------------------------------
        In the ACB method, you don't track which specific coins you're selling.
        Instead, you sell from a pool with an average cost. The cost basis
        is always: Amount × Average Cost (ACB per unit).
        
        After Disposition:
        ------------------
        New Total Cost = Previous Total Cost - (Amount Sold × ACB per Unit)
        New Total BTC = Previous Total BTC - Amount Sold
        ACB per Unit remains UNCHANGED (this is mathematically consistent)
        """
        # Calculate proceeds from this sale
        proceeds = tx.amount_btc * tx.price_cad
        
        # Deduct fees from proceeds (reduces your gain / increases your loss)
        # WHY? Selling fees are deductible as they reduce your net proceeds
        proceeds -= tx.fee_cad
        
        # Cost basis using current ACB
        cost_basis = tx.amount_btc * self.acb_per_btc
        
        # Capital gain or loss
        capital_gain = proceeds - cost_basis
        
        # Check for superficial loss
        superficial_flag = False
        superficial_note = ''
        
        if capital_gain < 0:
            flag, note = self._check_superficial_loss(tx)
            superficial_flag = flag
            superficial_note = note
        
        # Reduce total cost proportionally
        # WHY proportional? We're removing assets at their average cost
        cost_removed = tx.amount_btc * self.acb_per_btc
        self.total_cost -= cost_removed
        self.total_btc -= tx.amount_btc
        
        # Prevent negative values from floating point issues
        if self.total_btc < Decimal('0.00000001'):
            self.total_btc = Decimal('0')
            self.total_cost = Decimal('0')
        
        entry = LedgerEntry(
            date=tx.date,
            tx_type=tx.tx_type,
            amount_btc=tx.amount_btc,
            price_cad=tx.price_cad,
            fee_cad=tx.fee_cad,
            total_cost_after=self.total_cost,
            total_btc_after=self.total_btc,
            acb_per_btc=self.acb_per_btc,
            proceeds=proceeds,
            cost_basis=cost_basis,
            capital_gain=capital_gain,
            superficial_loss_flag=superficial_flag,
            superficial_loss_note=superficial_note,
            label=tx.label
        )
        
        return entry
    
    def _check_superficial_loss(self, tx: Transaction) -> Tuple[bool, str]:
        """
        Check if a loss triggers the Superficial Loss Rule.
        
        CRA Superficial Loss Rule:
        --------------------------
        A capital loss is DENIED if you (or an affiliated person):
        1. Acquired identical property during the period starting 30 days 
           BEFORE the sale and ending 30 days AFTER the sale, AND
        2. Still own that property at the end of the period
        
        The denied loss gets added to the ACB of the replacement property.
        
        MVP Implementation:
        -------------------
        For the MVP, we check if there was a BUY within 30 days BEFORE the sale.
        We can't check 30 days AFTER without future data, so we flag potential
        issues and note they need manual review.
        
        WHY this matters?
        -----------------
        People might try to "harvest" losses by selling then immediately rebuying.
        CRA disallows this - you can't crystallize a loss if you just repurchase.
        """
        loss_date = tx.date
        window_start = loss_date - timedelta(days=30)
        
        # Check for acquisitions in the 30 days before this loss
        for recent_tx in self._recent_transactions:
            if recent_tx.tx_type in ('buy', 'receive'):
                if window_start <= recent_tx.date < loss_date:
                    return (
                        True,
                        f"POTENTIAL SUPERFICIAL LOSS: BTC acquired on "
                        f"{recent_tx.date.strftime('%Y-%m-%d')} "
                        f"(within 30 days before this sale). "
                        f"Review if still held 30 days after sale."
                    )
        
        # Note: We can't check future purchases in this pass
        # The user should re-run at year-end to check all transactions
        return (
            False,
            "Note: Check for purchases within 30 days AFTER this sale for superficial loss."
        )
    
    def get_summary(self, tax_year: Optional[int] = None) -> dict:
        """
        Generate a summary of capital gains/losses.
        
        Args:
            tax_year: Optional year to filter. None returns all-time totals.
        
        Returns:
            Dictionary with total gains, losses, net, and superficial loss warnings.
        """
        entries = self.ledger
        
        if tax_year:
            entries = [e for e in entries if e.date.year == tax_year]
        
        total_gains = Decimal('0')
        total_losses = Decimal('0')
        superficial_count = 0
        
        for entry in entries:
            if entry.capital_gain is not None:
                if entry.capital_gain >= 0:
                    total_gains += entry.capital_gain
                else:
                    if entry.superficial_loss_flag:
                        superficial_count += 1
                        # Superficial losses are denied - don't add to loss total
                        # In reality, they add to ACB of replacement property
                    else:
                        total_losses += abs(entry.capital_gain)
        
        net_gain = total_gains - total_losses
        
        # CRA inclusion rate is 50% for capital gains (as of 2024)
        # Note: This changed to 66.67% for gains over $250k starting June 25, 2024
        # For MVP, we use the standard 50% rate
        inclusion_rate = Decimal('0.50')
        taxable_gain = max(Decimal('0'), net_gain * inclusion_rate)
        
        return {
            'total_gains': total_gains,
            'total_losses': total_losses,
            'net_capital_gain': net_gain,
            'taxable_capital_gain': taxable_gain,
            'inclusion_rate': inclusion_rate,
            'superficial_loss_count': superficial_count,
            'current_holdings_btc': self.total_btc,
            'current_acb_total': self.total_cost,
            'current_acb_per_btc': self.acb_per_btc
        }
    
    def export_for_schedule_3(self, tax_year: int) -> pd.DataFrame:
        """
        Export disposition data formatted for CRA Schedule 3.
        
        Schedule 3 requires:
        - Description of property (Bitcoin/BTC)
        - Proceeds of disposition
        - Adjusted cost base
        - Outlays and expenses (fees)
        - Gain (or loss)
        
        Returns:
            DataFrame ready for export with Schedule 3 columns.
        """
        dispositions = [
            e for e in self.ledger 
            if e.capital_gain is not None and e.date.year == tax_year
        ]
        
        if not dispositions:
            return pd.DataFrame()
        
        data = []
        for entry in dispositions:
            data.append({
                'Date of Disposition': entry.date.strftime('%Y-%m-%d'),
                'Description': f'Bitcoin (BTC) - {entry.tx_type}',
                'Number of Units': float(entry.amount_btc),
                'Proceeds of Disposition (CAD)': float(entry.proceeds + entry.fee_cad),  # Gross proceeds
                'Adjusted Cost Base (CAD)': float(entry.cost_basis),
                'Outlays and Expenses (CAD)': float(entry.fee_cad),
                'Gain (or Loss) (CAD)': float(entry.capital_gain),
                'Superficial Loss': 'YES - REVIEW' if entry.superficial_loss_flag else 'No',
                'Notes': entry.superficial_loss_note if entry.superficial_loss_flag else entry.label
            })
        
        return pd.DataFrame(data)


# Utility function for testing
def create_test_transactions() -> List[Transaction]:
    """Create sample transactions for testing the ACB calculator."""
    return [
        Transaction(
            date=datetime(2024, 1, 15),
            tx_type='buy',
            amount_btc=Decimal('0.5'),
            price_cad=Decimal('60000'),
            fee_cad=Decimal('50'),
            label='DCA Purchase'
        ),
        Transaction(
            date=datetime(2024, 2, 20),
            tx_type='buy',
            amount_btc=Decimal('0.25'),
            price_cad=Decimal('65000'),
            fee_cad=Decimal('30'),
            label='DCA Purchase'
        ),
        Transaction(
            date=datetime(2024, 3, 10),
            tx_type='sell',
            amount_btc=Decimal('0.3'),
            price_cad=Decimal('70000'),
            fee_cad=Decimal('25'),
            label='Taking profit'
        ),
        Transaction(
            date=datetime(2024, 4, 5),
            tx_type='buy',
            amount_btc=Decimal('0.1'),
            price_cad=Decimal('55000'),
            fee_cad=Decimal('15'),
            label='Buying dip'
        ),
        Transaction(
            date=datetime(2024, 4, 20),
            tx_type='sell',
            amount_btc=Decimal('0.2'),
            price_cad=Decimal('50000'),
            fee_cad=Decimal('20'),
            label='Loss sale - check superficial'
        ),
    ]


if __name__ == '__main__':
    # Test the calculator
    calc = ACBCalculator()
    test_txs = create_test_transactions()
    ledger = calc.process_transactions(test_txs)
    
    print("=" * 80)
    print("GhostLedger ACB Test Run")
    print("=" * 80)
    
    for entry in ledger:
        print(f"\n{entry.date.strftime('%Y-%m-%d')} | {entry.tx_type.upper()}")
        print(f"  Amount: {entry.amount_btc} BTC @ ${entry.price_cad:,.2f}")
        print(f"  ACB after: ${entry.acb_per_btc:,.2f}/BTC | Holdings: {entry.total_btc_after} BTC")
        if entry.capital_gain is not None:
            status = "GAIN" if entry.capital_gain >= 0 else "LOSS"
            print(f"  Capital {status}: ${entry.capital_gain:,.2f}")
            if entry.superficial_loss_flag:
                print(f"  ⚠️  {entry.superficial_loss_note}")
    
    print("\n" + "=" * 80)
    summary = calc.get_summary(2024)
    print("2024 Summary:")
    print(f"  Total Gains: ${summary['total_gains']:,.2f}")
    print(f"  Total Losses: ${summary['total_losses']:,.2f}")
    print(f"  Net Capital Gain: ${summary['net_capital_gain']:,.2f}")
    print(f"  Taxable (50%): ${summary['taxable_capital_gain']:,.2f}")
    print(f"  Current Holdings: {summary['current_holdings_btc']} BTC")
    print(f"  Current ACB: ${summary['current_acb_per_btc']:,.2f}/BTC")
