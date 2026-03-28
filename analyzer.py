import pandas as pd

class MarketAnalyzer:
    def __init__(self, atr_mult_threshold=1.0, fvg_min_atr_mult=0.5, body_range_ratio_min=0.5, min_break_distance_atr=0.1, volume_ma_length=20):
        self.atr_mult_threshold = atr_mult_threshold
        self.fvg_min_atr_mult = fvg_min_atr_mult
        self.body_range_ratio_min = body_range_ratio_min
        self.min_break_distance_atr = min_break_distance_atr
        self.volume_ma_length = volume_ma_length

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
        df['raw_bos_direction'] = 'NONE'
        df['displacement_atr_mult'] = 0.0
        df['body_ratio'] = 0.0
        df['break_distance_atr'] = 0.0

        for i in range(1, len(df)):
            close = df['close'].iloc[i]
            open_p = df['open'].iloc[i]
            body_size = abs(close - open_p)
            candle_range = df['high'].iloc[i] - df['low'].iloc[i]
            atr = df['ATR'].iloc[i]
            
            last_swing_high = df['last_swing_high_price'].iloc[i-1]
            last_swing_low = df['last_swing_low_price'].iloc[i-1]
            
            # Displacement rule: large body relative to ATR
            displacement_mult = body_size / atr if atr > 0 else 0
            df.at[df.index[i], 'displacement_atr_mult'] = displacement_mult

            # Body to range ratio: avoid massive wicks
            body_ratio = body_size / candle_range if candle_range > 0 else 0
            df.at[df.index[i], 'body_ratio'] = body_ratio

            if pd.isna(last_swing_high) or pd.isna(last_swing_low):
                continue
                
            # Bullish BOS
            if close > last_swing_high:
                df.at[df.index[i], 'raw_bos_direction'] = 'BULLISH'
                break_dist = (close - last_swing_high) / atr if atr > 0 else 0
                df.at[df.index[i], 'break_distance_atr'] = break_dist
                if displacement_mult >= self.atr_mult_threshold and body_ratio >= self.body_range_ratio_min and break_dist >= self.min_break_distance_atr:
                    df.at[df.index[i], 'bos_direction'] = 'BULLISH'
            # Bearish BOS
            elif close < last_swing_low:
                df.at[df.index[i], 'raw_bos_direction'] = 'BEARISH'
                break_dist = (last_swing_low - close) / atr if atr > 0 else 0
                df.at[df.index[i], 'break_distance_atr'] = break_dist
                if displacement_mult >= self.atr_mult_threshold and body_ratio >= self.body_range_ratio_min and break_dist >= self.min_break_distance_atr:
                    df.at[df.index[i], 'bos_direction'] = 'BEARISH'
                
        return df

    def detect_fvg(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detects Fair Value Gaps (Bullish & Bearish)."""
        df['fvg_active'] = False
        df['raw_fvg_active'] = False
        df['fvg_type'] = 'NONE'
        df['fvg_top'] = 0.0
        df['fvg_bottom'] = 0.0
        df['fvg_atr_mult'] = 0.0
        df['fvg_time'] = None
        df['fvg_stale'] = False
        
        # FVG requires 3 candles: i-2, i-1, i
        for i in range(2, len(df)):
            low_i = df['low'].iloc[i]
            high_i_minus_2 = df['high'].iloc[i-2]
            
            high_i = df['high'].iloc[i]
            low_i_minus_2 = df['low'].iloc[i-2]
            
            atr = df['ATR'].iloc[i]
            
            # Bullish FVG: Low of candle 3 is higher than High of candle 1
            if low_i > high_i_minus_2:
                df.at[df.index[i-1], 'raw_fvg_active'] = True
                gap_size = low_i - high_i_minus_2
                gap_mult = gap_size / atr if atr > 0 else 0
                if gap_mult >= self.fvg_min_atr_mult:
                    df.at[df.index[i-1], 'fvg_active'] = True # FVG belongs to the displacement candle (i-1)
                    df.at[df.index[i-1], 'fvg_type'] = 'BULLISH'
                    df.at[df.index[i-1], 'fvg_top'] = low_i
                    df.at[df.index[i-1], 'fvg_bottom'] = high_i_minus_2
                    df.at[df.index[i-1], 'fvg_atr_mult'] = gap_mult
                    df.at[df.index[i-1], 'fvg_time'] = str(df['timestamp'].iloc[i-1])
                    
            # Bearish FVG: High of candle 3 is lower than Low of candle 1
            elif high_i < low_i_minus_2:
                df.at[df.index[i-1], 'raw_fvg_active'] = True
                gap_size = low_i_minus_2 - high_i
                gap_mult = gap_size / atr if atr > 0 else 0
                if gap_mult >= self.fvg_min_atr_mult:
                    df.at[df.index[i-1], 'fvg_active'] = True
                    df.at[df.index[i-1], 'fvg_type'] = 'BEARISH'
                    df.at[df.index[i-1], 'fvg_top'] = low_i_minus_2
                    df.at[df.index[i-1], 'fvg_bottom'] = high_i
                    df.at[df.index[i-1], 'fvg_atr_mult'] = gap_mult
                    df.at[df.index[i-1], 'fvg_time'] = str(df['timestamp'].iloc[i-1])

        # Track staleness post-formation
        active_bullish_fvg_bottom = None
        active_bearish_fvg_top = None
        
        for i in range(len(df)):
            if df['fvg_active'].iloc[i]:
                if df['fvg_type'].iloc[i] == 'BULLISH':
                    active_bullish_fvg_bottom = df['fvg_bottom'].iloc[i]
                elif df['fvg_type'].iloc[i] == 'BEARISH':
                    active_bearish_fvg_top = df['fvg_top'].iloc[i]
            
            close = df['close'].iloc[i]
            # If price closes below bullish FVG or above bearish FVG, it invalidates it
            if active_bullish_fvg_bottom is not None and close < active_bullish_fvg_bottom:
                df.at[df.index[i], 'fvg_stale'] = True
                active_bullish_fvg_bottom = None
            if active_bearish_fvg_top is not None and close > active_bearish_fvg_top:
                df.at[df.index[i], 'fvg_stale'] = True
                active_bearish_fvg_top = None

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
        elif close > sma_50:
            return "BULLISH" # Fallback if 200 is flat but 50 is cleanly broken
        elif close < sma_50:
            return "BEARISH"
        return "NEUTRAL"
        
    def detect_chop_and_volume(self, df: pd.DataFrame) -> pd.DataFrame:
        df['chop_flag'] = False
        df['volume_ratio'] = 1.0
        
        if len(df) < self.volume_ma_length:
            return df
            
        df['vol_sma'] = df['volume'].rolling(window=self.volume_ma_length).mean()
        # Prevent division by zero
        df['volume_ratio'] = df['volume'] / df['vol_sma'].replace(0, 1)
        
        # Chop logic: ATR compression
        df['atr_sma'] = df['ATR'].rolling(window=self.volume_ma_length).mean()
        # If current ATR is < 80% of average ATR, it represents extreme compression/chop
        df['chop_flag'] = df['ATR'] < (df['atr_sma'] * 0.8)
        
        return df
        
    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Runs the full analysis pipeline."""
        df = self.identify_swings(df)
        df = self.detect_bos(df)
        df = self.detect_fvg(df)
        df = self.detect_chop_and_volume(df)
        return df
