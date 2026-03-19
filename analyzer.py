import pandas as pd

class MarketAnalyzer:
    def __init__(self, atr_mult_threshold=1.0, fvg_min_atr_mult=0.5):
        self.atr_mult_threshold = atr_mult_threshold
        self.fvg_min_atr_mult = fvg_min_atr_mult

    def identify_swings(self, df: pd.DataFrame, lookback=5) -> pd.DataFrame:
        """Identifies Swing Highs and Swing Lows."""
        df['swing_high'] = False
        df['swing_low'] = False
        
        for i in range(lookback, len(df) - lookback):
            # Check for swing high
            if df['high'].iloc[i] == max(df['high'].iloc[i-lookback:i+lookback+1]):
                df.at[df.index[i], 'swing_high'] = True
            # Check for swing low
            if df['low'].iloc[i] == min(df['low'].iloc[i-lookback:i+lookback+1]):
                df.at[df.index[i], 'swing_low'] = True
                
        # Forward fill the last swing high/low prices
        df['last_swing_high_price'] = df['high'].where(df['swing_high']).ffill()
        df['last_swing_low_price'] = df['low'].where(df['swing_low']).ffill()
        return df

    def detect_bos(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detects Break of Structure based on candle close exceeding swing levels."""
        df['bos_direction'] = 'NONE'
        df['displacement_atr_mult'] = 0.0

        for i in range(1, len(df)):
            close = df['close'].iloc[i]
            open_p = df['open'].iloc[i]
            body_size = abs(close - open_p)
            atr = df['ATR'].iloc[i]
            
            last_swing_high = df['last_swing_high_price'].iloc[i-1]
            last_swing_low = df['last_swing_low_price'].iloc[i-1]
            
            # Displacement rule: large body relative to ATR
            displacement_mult = body_size / atr if atr > 0 else 0
            df.at[df.index[i], 'displacement_atr_mult'] = displacement_mult

            if pd.isna(last_swing_high) or pd.isna(last_swing_low):
                continue
                
            # Bullish BOS
            if close > last_swing_high and displacement_mult >= self.atr_mult_threshold:
                df.at[df.index[i], 'bos_direction'] = 'BULLISH'
            # Bearish BOS
            elif close < last_swing_low and displacement_mult >= self.atr_mult_threshold:
                df.at[df.index[i], 'bos_direction'] = 'BEARISH'
                
        return df

    def detect_fvg(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detects Fair Value Gaps (Bullish & Bearish)."""
        df['fvg_active'] = False
        df['fvg_type'] = 'NONE'
        df['fvg_top'] = 0.0
        df['fvg_bottom'] = 0.0
        df['fvg_atr_mult'] = 0.0
        
        # FVG requires 3 candles: i-2, i-1, i
        for i in range(2, len(df)):
            low_i = df['low'].iloc[i]
            high_i_minus_2 = df['high'].iloc[i-2]
            
            high_i = df['high'].iloc[i]
            low_i_minus_2 = df['low'].iloc[i-2]
            
            atr = df['ATR'].iloc[i]
            
            # Bullish FVG: Low of candle 3 is higher than High of candle 1
            if low_i > high_i_minus_2:
                gap_size = low_i - high_i_minus_2
                gap_mult = gap_size / atr if atr > 0 else 0
                if gap_mult >= self.fvg_min_atr_mult:
                    df.at[df.index[i-1], 'fvg_active'] = True # FVG belongs to the displacement candle (i-1)
                    df.at[df.index[i-1], 'fvg_type'] = 'BULLISH'
                    df.at[df.index[i-1], 'fvg_top'] = low_i
                    df.at[df.index[i-1], 'fvg_bottom'] = high_i_minus_2
                    df.at[df.index[i-1], 'fvg_atr_mult'] = gap_mult
                    
            # Bearish FVG: High of candle 3 is lower than Low of candle 1
            elif high_i < low_i_minus_2:
                gap_size = low_i_minus_2 - high_i
                gap_mult = gap_size / atr if atr > 0 else 0
                if gap_mult >= self.fvg_min_atr_mult:
                    df.at[df.index[i-1], 'fvg_active'] = True
                    df.at[df.index[i-1], 'fvg_type'] = 'BEARISH'
                    df.at[df.index[i-1], 'fvg_top'] = low_i_minus_2
                    df.at[df.index[i-1], 'fvg_bottom'] = high_i
                    df.at[df.index[i-1], 'fvg_atr_mult'] = gap_mult
                    
        return df

    def get_htf_trend(self, df: pd.DataFrame) -> str:
        """Simple HTF bias using moving averages on the provided dataframe."""
        if len(df) < 200:
            return "NEUTRAL"
        
        close = df['close'].iloc[-1]
        sma_50 = df['close'].rolling(window=50).mean().iloc[-1]
        sma_200 = df['close'].rolling(window=200).mean().iloc[-1]
        
        if close > sma_50 and sma_50 > sma_200:
            return "BULLISH"
        elif close < sma_50 and sma_50 < sma_200:
            return "BEARISH"
        return "NEUTRAL"
        
    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Runs the full analysis pipeline."""
        df = self.identify_swings(df)
        df = self.detect_bos(df)
        df = self.detect_fvg(df)
        return df
