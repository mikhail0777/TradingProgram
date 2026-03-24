# Autonomous Paper Trading Bot

An autonomous paper trading system for a BOS + FVG strategy. It continually polls market data, applies strict technical structure filters, evaluates risk management rules, incorporates a mock/real AI reviewer, logs setups in SQLite, and executes simulated trades using an internal executor.

## Features
- **Autonomous Setup Detection**: Automatically fetches market data and detects fair value gaps (FVGs) and breaks of structure (BOS) without external indicators.
- **Strict Strategy Filters**: Rejects setups lacking correct positioning, strict invalidation, or session alignment.
- **Risk Engine**: Checks max daily losses, positions sizes based on 1% risk threshold, and enforces global risk rules.
- **AI Review**: Built-in module to query OpenAI for a secondary review of setups before entry.
- **Trade Execution & Management**: Internal trade logic handles entry, partial take profits, breakeven trailing, and stop losses.
- **Robust Storage**: Uses SQLite and SQLAlchemy to log the entire lifecycle of trades (`WAITING_FOR_RETRACE`, `ENTERED`, `STOPPED`, `TP2_HIT`).

## Setup Instructions

### 1. Install Dependencies
Ensure Python 3.10+ is installed.
```bash
python -m pip install -r requirements.txt
```

### 2. Configure Environment
Rename `.env.example` to `.env` and fill in the corresponding values (e.g., OpenAI Key, Discord Webhook).
```bash
copy .env.example .env
```

### 3. Run the Bot
To start the autonomous market scanner and trader:
```bash
python bot.py
```

## Tracking Results
The bot logs everything natively into the `paper_trades.db` SQLite database. You can query your local database utilizing any SQLite viewer (like DBeaver or SQLite Studio) to figure out true win rates filtered by symbol, AI grade, or timeframe!
