import os
import pandas as pd
from datetime import datetime
from db import get_db, DBTrade, init_db

def compute_trade_r(row) -> float:
    # 1R risk profile.
    if row['status'] == 'STOPPED' or row['status'] == 'LOSS':
        return -1.0
    elif row['status'] == 'BREAKEVEN_EXIT':
        return 0.5 * row['rr_to_tp1']
    elif row['status'] in ['TP2_HIT', 'WIN']:
        # Assuming old WIN mapped to TP1 or TP2. We'll use Phase 4 strict targets.
        r1 = 0.5 * row['rr_to_tp1'] if pd.notna(row['rr_to_tp1']) else 0.0
        r2 = 0.5 * row['rr_to_tp2'] if pd.notna(row['rr_to_tp2']) else 0.0
        return r1 + r2
    return 0.0

def generate_stats_dict(db) -> dict:
    trades = db.query(DBTrade).all()
    if not trades:
        return {"error": "No trades found"}
        
    df = pd.DataFrame([{
        "id": t.id,
        "symbol": t.symbol,
        "direction": t.direction,
        "status": t.status,
        "rr_to_tp1": t.rr_to_tp1,
        "rr_to_tp2": t.rr_to_tp2,
        "timeframe": t.timeframe,
        "session": getattr(t, 'active_session', 'N/A'),
        "ai_grade": t.ai_grade,
        "entered_at": t.entered_at,
        "closed_at": t.closed_at
    } for t in trades])
    
    total_signals = len(df)
    rejected = len(df[df['status'] == 'REJECTED'])
    entered = df[df['status'].isin(['ENTERED', 'PARTIAL_TP1', 'BREAKEVEN_EXIT', 'TP2_HIT', 'STOPPED', 'WIN', 'LOSS'])]
    completed = entered[entered['status'].isin(['BREAKEVEN_EXIT', 'TP2_HIT', 'STOPPED', 'WIN', 'LOSS'])]
    
    if completed.empty:
        return {
            "total_signals": total_signals,
            "rejected_signals": rejected,
            "entered_trades": len(entered),
            "completed_trades": 0
        }
    
    # Calculate R-multiples
    completed = completed.copy()
    completed['R'] = completed.apply(compute_trade_r, axis=1)
    
    # Calculate hold times
    valid_times = completed.dropna(subset=['entered_at', 'closed_at']).copy()
    if not valid_times.empty:
        valid_times['hold_minutes'] = (pd.to_datetime(valid_times['closed_at']) - pd.to_datetime(valid_times['entered_at'])).dt.total_seconds() / 60
        avg_hold_time = f"{valid_times['hold_minutes'].mean():.1f}m"
    else:
        avg_hold_time = "N/A"
        
    win_rate = len(completed[completed['status'].isin(['TP2_HIT', 'WIN'])]) / len(completed)
    be_rate = len(completed[completed['status'] == 'BREAKEVEN_EXIT']) / len(completed)
    stop_rate = len(completed[completed['status'].isin(['STOPPED', 'LOSS'])]) / len(completed)
    
    avg_r = completed['R'].mean()
    expectancy = avg_r # Average R per completed trade is the mathematical expectancy given 1R risk baseline.
    
    best_symbol = completed.groupby('symbol')['R'].sum().idxmax() if not completed.empty else "N/A"
    best_session = completed.groupby('session')['R'].sum().idxmax() if 'session' in completed.columns and not completed.empty else "N/A"
    
    ai_metrics = completed.groupby('ai_grade')['R'].mean().to_dict()
    
    return {
        "total_signals": total_signals,
        "rejected_signals": rejected,
        "entered_trades": len(entered),
        "completed_trades": len(completed),
        "win_rate_pct": round(float(win_rate * 100), 2),
        "stop_rate_pct": round(float(stop_rate * 100), 2),
        "breakeven_rate_pct": round(float(be_rate * 100), 2),
        "avg_r_multiple": round(float(avg_r), 2),
        "expectancy_r": round(float(expectancy), 2),
        "best_symbol": best_symbol,
        "best_session": best_session,
        "avg_hold_time": avg_hold_time,
        "ai_grade_performance": ai_metrics
    }

def print_stats():
    init_db()
    db = next(get_db())
    stats = generate_stats_dict(db)
    
    if "error" in stats:
        print(stats["error"])
        return
        
    print("\n" + "="*50)
    print("      PROFESSIONAL TRADING PROGRAM ANALYTICS      ")
    print("="*50)
    print(f"Total Signals:       {stats.get('total_signals')}")
    print(f"Rejected Signals:    {stats.get('rejected_signals')}")
    print(f"Entered Trades:      {stats.get('entered_trades')}")
    print(f"Completed Trades:    {stats.get('completed_trades')}")
    print("-" * 50)
    if stats.get('completed_trades', 0) > 0:
        print(f"Win Rate (TP2 Hit):  {stats.get('win_rate_pct')}%")
        print(f"Break-Even Rate:     {stats.get('breakeven_rate_pct')}%")
        print(f"Stop Loss Rate:      {stats.get('stop_rate_pct')}%")
        print("-" * 50)
        print(f"Avg R-Multiple:      {stats.get('avg_r_multiple')} R")
        print(f"System Expectancy:   {stats.get('expectancy_r')} R per trade")
        print(f"Avg Hold Time:       {stats.get('avg_hold_time')}")
        print(f"Best Symbol:         {stats.get('best_symbol')}")
        print(f"Best Session:        {stats.get('best_session')}")
        print("-" * 50)
        print("AI Grade Performance (Avg R):")
        for k, v in stats.get('ai_grade_performance', {}).items():
            print(f"  Grade {k}: {v:.2f} R")
            
    # Export full history to CSV
    os.makedirs('reports', exist_ok=True)
    trades = db.query(DBTrade).all()
    df = pd.DataFrame([t.__dict__ for t in trades])
    if '_sa_instance_state' in df.columns:
        df.drop('_sa_instance_state', axis=1, inplace=True)
    df.to_csv('reports/trade_history.csv', index=False)
    print(f"\n[Export] Full trade history saved to reports/trade_history.csv")
    print("="*50 + "\n")

if __name__ == "__main__":
    print_stats()
