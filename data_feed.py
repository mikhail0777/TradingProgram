import yfinance as yf
import pandas as pd
import pandas_ta as ta
import logging

logger = logging.getLogger(__name__)

class MarketDataFeed:
    def __init__(self, symbol='SPY', timeframe='1m'):
        """
        Initializes the data feed using Yahoo Finance.
        Defaults to SPY and 1m candles.
        """
        self.symbol = symbol
        self.timeframe = timeframe
        self.df = pd.DataFrame()

    def fetch_latest_candles(self, limit=200) -> pd.DataFrame:
        """Fetches the latest OHLCV data using yfinance."""
        try:
            ticker = yf.Ticker(self.symbol)
            # yfinance mapping: 1m data is limited to last 7 days. limit parameter determines days.
            df = ticker.history(period="5d", interval=self.timeframe)
            if df.empty:
                return pd.DataFrame()
            
            # yfinance returns timezone-aware datetime index.
            df.reset_index(inplace=True)
            # Rename columns to lowercase to match our existing system
            df.rename(columns={'Datetime': 'timestamp', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
            
            # Ensure timestamp is standard pandas datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
            
            # Drop unnecessary cols like 'Dividends', 'Stock Splits'
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            
            self.df = df
            return df
        except Exception as e:
            logger.error(f"Error fetching yfinance data for {self.symbol}: {e}")
            return pd.DataFrame()

    def get_aggregated_candles(self, df: pd.DataFrame = None, timeframe_rule='5min') -> pd.DataFrame:
        """Aggregates the base candles to a higher timeframe."""
        if df is None:
            df = self.df
            
        if df.empty:
            return pd.DataFrame()
        
        # Set timestamp as index for resampling
        df_indexed = df.set_index('timestamp')
        
        # Resample logic
        agg_dict = {
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }
        resampled_df = df_indexed.resample(timeframe_rule).agg(agg_dict).dropna()
        resampled_df.reset_index(inplace=True)
        return resampled_df

    def compute_atr(self, df: pd.DataFrame, length=14) -> pd.DataFrame:
        """Computes the Average True Range (ATR) and appends it to the DataFrame."""
        if df.empty or len(df) <= length:
            df['ATR'] = 0.0
            return df
        
        df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=length)
        df['ATR'] = df['ATR'].fillna(0.0)
        return df
