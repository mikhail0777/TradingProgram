from db import get_db, DBTrade
import pandas as pd

def print_stats():
    db = next(get_db())
    trades = db.query(DBTrade).all()
    if not trades:
        print("No trades found in database.")
        return
        
    df = pd.DataFrame([{
        "id": t.id,
        "symbol": t.symbol,
        "direction": t.direction,
        "status": t.status,
        "rr": t.rr,
        "timestamp": t.timestamp
    } for t in trades])
    
    total = len(df)
    completed = df[df['status'].isin(['WIN', 'LOSS'])]
    wins = completed[completed['status'] == 'WIN']
    losses = completed[completed['status'] == 'LOSS']
    
    print("\n" + "="*40)
    print("      TRADING PROGRAM ANALYTICS      ")
    print("="*40)
    print(f"Total Trades Logged: {total}")
    print(f"Completed Trades: {len(completed)}")
    print(f"Pending/Open Trades: {total - len(completed)}")
    
    if len(completed) > 0:
        win_rate = len(wins) / len(completed) * 100
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Wins: {len(wins)}, Losses: {len(losses)}")
        
        # Calculate expectancy if applicable
        avg_rr = completed[completed['status'] == 'WIN']['rr'].mean() if not wins.empty else 0
        loss_rr = 1.0 # 1R loss by definition
        
        expectancy = ((win_rate/100) * avg_rr) - ((1 - win_rate/100) * loss_rr)
        print(f"Average Winning R:R: {avg_rr:.2f}")
        print(f"System Expectancy (per 1R risked): {expectancy:.2f}R")
    print("="*40 + "\n")
        
if __name__ == "__main__":
    print_stats()
