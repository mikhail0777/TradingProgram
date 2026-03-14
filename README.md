# Paper Trading Alert Application

A production-style webhook server for paper trading a BOS + FVG strategy. It receives JSON alerts from TradingView, applies strict strategy filters, evaluates risk management rules, optionally acts as an AI reviewer, logs all setups in SQLite, and sends out Discord/Telegram notifications.

## Features
- **FastAPI Webhook Server**: Receives POST requests securely.
- **Strict Strategy Filters**: Rejects setups lacking structure breaks, displacement, or session alignment.
- **Risk Engine**: Checks max daily losses, minimum RR, and calculates an exact position size off a 1% risk threshold.
- **AI Review**: Extensible module to query OpenAI to critique a setup before logging/notifying. Defaults to mock/sandbox mode.
- **Robust Storage**: Uses SQLite and SQLAlchemy to log `PENDING`, `REJECTED`, `WIN`, and `LOSS` trades.
- **Result Updating Endpoint**: Provides a clean `/update_result` path to mark your paper trades post hoc and calculate win rates.

## Setup Instructions

### 1. Install Dependencies
Ensure Python 3.10+ is installed.
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
Rename `.env.example` to `.env` and fill in the values:
```bash
cp .env.example .env
```
Make sure to adjust the `WEBHOOK_SECRET` to whatever you paste into TradingView!
If you have Discord/Telegram, configure URLs/tokens. Adjust the `ACCOUNT_BALANCE` and constraints as needed.

### 3. Run the Server
The simplest way to start the FastAPI server locally:
```bash
uvicorn app:app --reload --port 8000
```

### 4. TradingView Alert Setup
1. Paste the `pine/bos_fvg_alerts.pine` script into your Pine Editor and save it.
2. Add it to your chart.
3. Configure the settings (HTF bias, Session times) in the indicator inputs.
4. Create an Alert condition using this indicator.
5. Set the Action to **Webhook URL**. Use something like `http://<your-ip-or-ngrok>/webhook`.
6. Enable sending custom headers: add `x-algo-secret: your_super_secret_webhook_token_here`.

## Tracking Results
The backend is configured to use a SQLite database. Trades are inserted exactly as they happen.

To update the final conclusion of an entry (since this is a pure alert system without broker integration), issue a POST command from Postman, curl, or a script:
```bash
curl -X POST http://localhost:8000/update_result \
     -H "Content-Type: application/json" \
     -d '{"trade_id": 1, "outcome": "WIN"}'
```

Afterward, you can query your local `paper_trades.db` utilizing any SQLite viewer (like DBeaver or SQLite Studio) to figure out true win rates filtered by symbol, AI grade, or timeframe!
