# 👻 GhostLedger for Umbrel

**Local-First Bitcoin Tax Calculator for Canadian Taxpayers**

## Installation on Umbrel

### Option 1: Community App Store (Recommended)

1. Add the GhostLedger Community App Store to your Umbrel:
   - Go to **Umbrel > App Store > ⚙️ > Community App Stores**
   - Add: `https://github.com/ghostledger/umbrel-app-store`

2. Find GhostLedger in your App Store and click **Install**

### Option 2: Manual Installation

1. SSH into your Umbrel:
   ```bash
   ssh umbrel@umbrel.local
   ```

2. Navigate to the apps directory:
   ```bash
   cd ~/umbrel/app-data
   ```

3. Clone or copy the ghostledger directory:
   ```bash
   git clone https://github.com/ghostledger/ghostledger.git
   ```

4. Restart Umbrel or install via CLI:
   ```bash
   ~/umbrel/scripts/app install ghostledger
   ```

### Option 3: Build from Source

If you want to build the Docker image yourself:

```bash
# Clone the repo
git clone https://github.com/ghostledger/ghostledger.git
cd ghostledger

# Build multi-arch image (requires docker buildx)
docker buildx build --platform linux/arm64,linux/amd64 \
  --tag ghostledger/ghostledger:v1.0.0 \
  --output "type=registry" .
```

## Usage

1. **Prepare Price Data**
   - Download BTC/CAD historical prices from [Yahoo Finance](https://finance.yahoo.com/quote/BTC-CAD/history)
   - Save as CSV with Date and Close columns

2. **Export from Sparrow Wallet**
   - In Sparrow: `File > Export > Transaction History`
   - Label your transactions (e.g., "DCA Buy", "Sell profit") for automatic type detection

3. **Upload to GhostLedger**
   - Access via your Umbrel dashboard
   - Upload price CSV first (Step 1)
   - Upload Sparrow CSV (Step 2)
   - Review your capital gains summary

4. **Export for Tax Filing**
   - Download CRA Schedule 3 formatted CSV
   - Review superficial loss warnings
   - Consult your tax professional

## Privacy Architecture

GhostLedger is designed with privacy as the primary concern:

- **Zero Network Calls**: No APIs, no telemetry, no data leaves your Umbrel
- **Stateless Design**: Nothing persists between sessions
- **Read-Only Container**: Cannot write to the filesystem
- **Non-Root Execution**: Minimal privilege principle
- **Local Processing Only**: All calculations happen on your hardware

## Tax Calculation Method

GhostLedger implements the **Adjusted Cost Base (ACB)** method required by CRA:

```
ACB per BTC = Total Cost of All BTC Held / Total BTC Held
Capital Gain = Proceeds - (Amount Sold × ACB per BTC)
```

This is a **weighted average** approach, not FIFO or LIFO.

## Superficial Loss Rule

CRA disallows capital losses if you repurchase identical property within 30 days before or after the sale. GhostLedger flags these transactions for review.

## File Structure

```
ghostledger/
├── umbrel-app.yml      # Umbrel app manifest
├── docker-compose.yml  # Umbrel Docker configuration
├── exports.sh          # Environment variable exports
├── Dockerfile          # Multi-arch Docker build
├── app.py              # Streamlit UI
├── acb_engine.py       # ACB calculation engine
├── parsers.py          # CSV parsing
├── requirements.txt    # Python dependencies
└── README.md           # This file
```

## Troubleshooting

### App won't start
Check Umbrel logs:
```bash
docker logs ghostledger_web_1
```

### Memory issues on Raspberry Pi
GhostLedger is limited to 512MB RAM. For large transaction histories (1000+), consider processing in batches.

### Price data not loading
Ensure your CSV has columns named `date` (or `Date`) and `close` (or `Close`, `price`, `Price`).

## Disclaimer

**This is not tax advice.** GhostLedger is a calculation tool to assist with tax preparation. Always consult a qualified tax professional. The developers are not responsible for any errors in tax filings.

## License

MIT License

---

Built with 🍁 for Canadian Bitcoiners who run their own nodes.
