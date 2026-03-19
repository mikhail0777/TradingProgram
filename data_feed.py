import ccxt
import pandas as pd
import pandas_ta as ta
import logging

logger = logging.getLogger(__name__)

class MarketDataFeed:
    def __init__(self, exchange_id='gemini', symbol='BTC/USD', timeframe='1m'):
        """
        Initializes the data feed using CCXT.
        Defaults to Gemini and BTC/USD 1m candles.
        """
        self.exchange_class = getattr(ccxt, exchange_id)
        # Using rateLimit=True to avoid hitting API rate limits automatically
        self.exchange = self.exchange_class({'enableRateLimit': True})
        self.symbol = symbol
        self.timeframe = timeframe
        self.df = pd.DataFrame()

    def fetch_latest_candles(self, limit=200) -> pd.DataFrame:
        """Fetches the latest OHLCV data and returns a pandas DataFrame."""
        try:
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Remove incomplete active candle if needed, but for real-time analysis 
            # we sometimes need the current volatile price. We'll leave it in.
            self.df = df
            return df
        except Exception as e:
            logger.error(f"Error fetching data from {self.exchange.id}: {e}")
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
        
        # Using pandas_ta for ATR
        df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=length)
        # Fill NaNs from early lookback period with 0.0
        df['ATR'] = df['ATR'].fillna(0.0)
        return df
