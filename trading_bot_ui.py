"""
Streamlit-based dashboard for the Autonomous Paper Trading Bot.

This UI surfaces key functionality exposed by the bot without
requiring users to drop into a terminal.  It lets you inspect recent
trades, run a quick analysis on the latest market data for any
configured symbol, visualise candles with detected fair value gaps
and breaks of structure, and examine risk sizing along with AI
review decisions.  The code assumes it lives alongside the
TradingProgram package and reuses its existing modules for data
fetching, technical analysis, risk management and database access.

To run the dashboard install the required dependencies (see
requirements.txt in the TradingProgram repo) and execute:

    streamlit run trading_bot_ui.py

"""

import asyncio
from datetime import datetime
from typing import Optional, List

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

try:
    # Import local modules from the TradingProgram.  These imports will
    # succeed when this file is placed in the same directory as the
    # existing bot code.  If you move the UI elsewhere, adjust the
    # import paths accordingly.
    from config import settings
    from data_feed import MarketDataFeed
    from analyzer import MarketAnalyzer
    from models import TradeSetupPayload, AIReviewResult
    from risk_engine import evaluate_risk
    from ai_review import run_ai_review
    from db import get_db, DBTrade
except Exception as exc:
    raise RuntimeError(
        "Failed to import TradingProgram modules. Place this file in the same "
        "directory as the bot code or adjust the import paths.") from exc



def fetch_and_analyze(symbol: str) -> pd.DataFrame:
    """Fetches recent market data for a symbol and runs the full analysis.

    Returns a DataFrame with aggregated 5‑minute candles and columns
    describing swings, ATR, FVGs and BOS signals.
    """
    feed = MarketDataFeed(symbol=symbol)
    # Fetch up to 5 days of 1m candles (internal logic inside fetch)
    df_1m = feed.fetch_latest_candles(limit=200)
    if df_1m.empty:
        return pd.DataFrame()
    # Aggregate to 5m candles and compute ATR
    df_5m = feed.get_aggregated_candles(df_1m, timeframe_rule='5min')
    df_5m = feed.compute_atr(df_5m)
    analyzer = MarketAnalyzer(atr_mult_threshold=settings.displacement_atr_threshold)
    return analyzer.analyze(df_5m)



def generate_trade_candidates(df_analyzed: pd.DataFrame) -> List[dict]:
    """Scans analysed candles for valid BOS + FVG pairings and returns
    trade candidate dictionaries.  This logic mirrors the pairing logic
    from TradingBot.evaluate_new_setup but simplified for interactive use.

    Each candidate dict contains a payload (TradeSetupPayload), a risk
    evaluation, and optional AI review result.
    """
    candidates: List[dict] = []
    # Look at the last 15 fully closed candles only
    recent_df = df_analyzed.iloc[:-1].tail(15)
    n = len(recent_df)
    if n == 0:
        return candidates
    # Track FVGs that haven’t been consumed
    used_fvg_indices: set[int] = set()
    for i in range(n):
        row = recent_df.iloc[i]
        if not row.get('fvg_active', False):
            continue
        # Skip stale or already used
        if row.get('fvg_stale', False) or i in used_fvg_indices:
            continue
        direction = 'LONG' if row['fvg_type'] == 'BULLISH' else 'SHORT'
        # search up to ±3 candles around i for a BOS in same direction
        start_j = max(0, i - 3)
        end_j = min(n - 1, i + 3)
        bos_idx: Optional[int] = None
        for j in range(start_j, end_j + 1):
            bos_row = recent_df.iloc[j]
            bos_dir = bos_row.get('bos_direction', 'NONE')
            if (direction == 'LONG' and bos_dir == 'BULLISH') or (
                direction == 'SHORT' and bos_dir == 'BEARISH'):
                bos_idx = j
                break
        if bos_idx is None:
            continue
        # Mark FVG as used
        used_fvg_indices.add(i)
        fvg_row = row
        bos_row = recent_df.iloc[bos_idx]
        # Merge necessary information into one record
        merged = fvg_row.copy()
        merged['bos_direction'] = bos_row['bos_direction']
        # Use the latest swing levels for stops
        if bos_idx > i:
            merged['last_swing_low_price'] = bos_row['last_swing_low_price']
            merged['last_swing_high_price'] = bos_row['last_swing_high_price']
        # Build payload
        entry_mode = settings.entry_mode
        if direction == 'LONG':
            stop = merged['last_swing_low_price'] - settings.stop_buffer_atr * merged.get('ATR', 0)
            if entry_mode == 'FVG_TOP':
                entry_price = merged['fvg_top']
            elif entry_mode == 'FULL_ZONE_TOUCH':
                entry_price = merged['fvg_bottom']
            else:
                # midpoint
                entry_price = merged['fvg_bottom'] + (merged['fvg_top'] - merged['fvg_bottom']) * 0.5
            risk = entry_price - stop
            tp1 = entry_price + risk * settings.min_rr
            tp2 = entry_price + risk * settings.tp2_rr
        else:  # SHORT
            stop = merged['last_swing_high_price'] + settings.stop_buffer_atr * merged.get('ATR', 0)
            if entry_mode == 'FVG_TOP':
                entry_price = merged['fvg_bottom']  # technically top for bearish
            elif entry_mode == 'FULL_ZONE_TOUCH':
                entry_price = merged['fvg_top']
            else:
                entry_price = merged['fvg_bottom'] + (merged['fvg_top'] - merged['fvg_bottom']) * 0.5
            risk = stop - entry_price
            tp1 = entry_price - risk * settings.min_rr
            tp2 = entry_price - risk * settings.tp2_rr
        # Build TradeSetupPayload
        try:
            payload = TradeSetupPayload(
                symbol=merged['symbol'] if 'symbol' in merged else 'N/A',
                timeframe='5m',
                direction=direction,
                entry=round(entry_price, 2),
                stop=round(stop, 2),
                tp1=round(tp1, 2),
                tp2=round(tp2, 2),
                bos_direction=merged['bos_direction'],
                fvg_top=merged['fvg_top'],
                fvg_bottom=merged['fvg_bottom'],
                fvg_atr_mult=merged['fvg_atr_mult'],
                displacement_atr_mult=merged['displacement_atr_mult'],
                active_session='INTERACTIVE',
                htf_trend='NEUTRAL',
                liquidity_sweep=False,
                entry_zone=entry_mode,
                be_enabled=settings.break_even_after_tp1,
                trail_enabled=settings.trailing_after_tp1,
                volume_ratio=merged.get('volume_ratio', 1.0),
                chop_flag=bool(merged.get('chop_flag', False)),
                stop_buffer=settings.stop_buffer_atr,
                tp2_rr=settings.tp2_rr,
                expiry_bars=settings.max_bars_to_retrace,
                fvg_stale=bool(merged.get('fvg_stale', False))
            )
        except Exception:
            continue
        # Evaluate risk
        daily_losses = 0  # interactive analysis has no prior losses
        valid, reason, risk_details = evaluate_risk(payload, daily_losses)
        # Optionally run AI review
        ai_result: Optional[AIReviewResult] = None
        if valid and settings.use_mock_ai:
            ai_result = run_ai_review(payload)
        candidates.append({
            'payload': payload,
            'valid': valid,
            'reason': reason,
            'risk': risk_details,
            'ai': ai_result
        })
    return candidates



def plot_candles_with_fvg(df: pd.DataFrame) -> go.Figure:
    """Produces a candlestick chart with shaded FVG zones.

    FVG regions are highlighted as semi-transparent rectangles.  BOS
    signals are annotated with arrows.  Only fully formed FVGs
    (fvg_active==True) are drawn.
    """
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df['timestamp'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        name='5m OHLC'
    ))
    # Add FVG rectangles
    for idx, row in df.iterrows():
        if row.get('fvg_active', False):
            color = 'rgba(0, 255, 0, 0.2)' if row['fvg_type'] == 'BULLISH' else 'rgba(255, 0, 0, 0.2)'
            fig.add_shape(
                type='rect',
                x0=row['timestamp'], x1=row['timestamp'],
                y0=row['fvg_bottom'], y1=row['fvg_top'],
                fillcolor=color, line=dict(width=0),
                xref='x', yref='y'
            )
    # Add BOS markers
    for idx, row in df.iterrows():
        bos_dir = row.get('bos_direction', 'NONE')
        if bos_dir in ('BULLISH', 'BEARISH'):
            y = row['high'] if bos_dir == 'BULLISH' else row['low']
            color = 'green' if bos_dir == 'BULLISH' else 'red'
            fig.add_annotation(
                x=row['timestamp'], y=y,
                text='📈' if bos_dir == 'BULLISH' else '📉',
                showarrow=False,
                font=dict(size=12, color=color)
            )
    fig.update_layout(
        height=500,
        xaxis_title='Time',
        yaxis_title='Price',
        margin=dict(l=10, r=10, t=30, b=40),
        showlegend=False
    )
    return fig



def load_recent_trades(limit: int = 50) -> pd.DataFrame:
    """Loads recent trades from the SQLite database.

    Returns a DataFrame sorted by descending timestamp.  If the DB is
    empty, returns an empty DataFrame.
    """
    with next(get_db()) as db:
        results = db.query(DBTrade).order_by(DBTrade.timestamp.desc()).limit(limit).all()
    if not results:
        return pd.DataFrame()
    rows = []
    for trade in results:
        rows.append({
            'id': trade.id,
            'timestamp': trade.timestamp,
            'symbol': trade.symbol,
            'direction': trade.direction,
            'entry': trade.entry,
            'stop': trade.stop,
            'tp1': trade.tp1,
            'tp2': trade.tp2,
            'rr_tp1': trade.rr_to_tp1,
            'rr_tp2': trade.rr_to_tp2,
            'status': trade.status,
            'reason': trade.reason,
            'ai_action': trade.ai_action,
            'ai_grade': trade.ai_grade
        })
    return pd.DataFrame(rows)



def main() -> None:
    st.set_page_config(page_title="Trading Bot Dashboard", layout="wide")
    st.title("🧠📈 BOS + FVG Trading Bot Dashboard")
    st.markdown(
        "This dashboard helps you interact with the autonomous paper trading system.\n"
        "Select a symbol to run a quick strategy scan, inspect detected setups,\n"
        "and review recent trades logged in the SQLite database."
    )
    # Sidebar for symbol selection and analysis
    with st.sidebar:
        st.header("Analysis Controls")
        symbol = st.selectbox("Select Symbol", options=settings.symbols)
        if st.button("Run Analysis Now"):
            with st.spinner(f"Fetching and analysing data for {symbol}…"):
                df_analyzed = fetch_and_analyze(symbol)
            if df_analyzed.empty:
                st.error("No data returned for this symbol. Check your internet connection and symbol validity.")
            else:
                st.session_state['analysis_df'] = df_analyzed
                st.session_state['candidates'] = generate_trade_candidates(df_analyzed)
    # Display analysis output if available
    if 'analysis_df' in st.session_state:
        df_analyzed: pd.DataFrame = st.session_state['analysis_df']
        candidates: List[dict] = st.session_state.get('candidates', [])
        st.subheader(f"Technical Analysis for {symbol}")
        # Chart
        fig = plot_candles_with_fvg(df_analyzed)
        st.plotly_chart(fig, use_container_width=True)
        # Candidate setups
        if candidates:
            st.markdown("### Detected Setup Candidates")
            for i, cand in enumerate(candidates, start=1):
                payload: TradeSetupPayload = cand['payload']
                risk = cand['risk']
                ai = cand['ai']
                valid = cand['valid']
                reason = cand['reason']
                container = st.container()
                with container:
                    col1, col2, col3 = st.columns([2, 2, 3])
                    with col1:
                        st.write(f"**{payload.direction} {payload.symbol}**")
                        st.write(f"Entry: {payload.entry}")
                        st.write(f"Stop: {payload.stop}")
                        st.write(f"TP1: {payload.tp1}")
                        st.write(f"TP2: {payload.tp2}")
                    with col2:
                        st.write(f"RR TP1: {payload.rr_to_tp1}")
                        st.write(f"RR TP2: {payload.rr_to_tp2}")
                        st.write(f"Displacement: {payload.displacement_atr_mult:.2f}x ATR")
                        st.write(f"FVG Mult: {payload.fvg_atr_mult:.2f}x ATR")
                    with col3:
                        if valid:
                            st.success("Passed risk checks")
                            st.write(f"Position size: ${risk['position_size_usd']}")
                            st.write(f"Units: {risk['units_to_buy']}")
                        else:
                            st.error(reason)
                        if ai:
                            # Show AI review summary
                            st.write(f"AI Decision: **{ai.action}** (Grade {ai.grade}, Conf {ai.confidence}%)")
                            st.write("Reasons:")
                            for r in ai.reasons:
                                st.write(f"- {r}")
                        else:
                            st.write("AI review not available.")
        else:
            st.info("No valid BOS + FVG pairings found in the last few candles.")
    else:
        st.info("Use the sidebar to run an analysis on a symbol.")
    # Show recent trades table
    st.subheader("📜 Recent Trades Log")
    trades_df = load_recent_trades(limit=50)
    if trades_df.empty:
        st.write("No trades have been logged yet.")
    else:
        st.dataframe(trades_df, use_container_width=True)


if __name__ == '__main__':
    # Run inside asyncio event loop if necessary.  Streamlit will manage
    # its own loop, but including an event loop runner here keeps type
    # checkers happy and allows for future async expansion.
    try:
        asyncio.run(main())
    except RuntimeError:
        # If an event loop is already running (as Streamlit does), just call main directly.
        main()
