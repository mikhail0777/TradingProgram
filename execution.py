import ccxt
import logging
from config import settings

logger = logging.getLogger(__name__)

class Executor:
    def __init__(self, exchange_id='gemini'):
        self.mode = settings.execution_mode
        self.exchange_class = getattr(ccxt, exchange_id)
        
        if self.mode == "LIVE":
            if not settings.gemini_api_key or not settings.gemini_api_secret:
                logger.warning("LIVE mode requested but Gemini API keys are missing. Falling back to PAPER mode.")
                self.mode = "PAPER"
            else:
                self.exchange = self.exchange_class({
                    'apiKey': settings.gemini_api_key,
                    'secret': settings.gemini_api_secret,
                    'enableRateLimit': True,
                })
                try:
                    # Test connection
                    self.exchange.fetch_balance()
                    logger.info(f"Successfully connected to {exchange_id} in LIVE mode.")
                except Exception as e:
                    logger.error(f"Failed to connect to broker: {e}")
                    raise
        
        if self.mode == "PAPER":
            logger.info(f"Executor initialized in PAPER mode - no real orders will be placed on {exchange_id}.")

    def place_order(self, symbol: str, direction: str, quantity: float, entry_price: float, stop_loss_price: float, take_profit_price: float) -> dict | None:
        """Places the bracket / SL/TP orders."""
        if self.mode == "PAPER":
            logger.info(f"[PAPER TRADE] Placed {direction} {quantity} of {symbol} @ {entry_price} [SL: {stop_loss_price}, TP: {take_profit_price}]")
            return {"status": "paper_success", "id": "paper_test_001"}
            
        try:
            # We place a basic market order for entry in ccxt. 
            # Note: Managing SL and TP bracket orders on Gemini via CCXT often requires placing stop-limit orders or handling them via an active monitoring loop.
            order_side = 'buy' if direction == 'LONG' else 'sell'
            
            logger.info(f"[LIVE TRADE] Placing {order_side} market order for {quantity} {symbol}")
            entry_order = self.exchange.create_order(symbol, 'market', order_side, quantity)
            
            logger.info(f"Entry order placed: {entry_order.get('id', 'Unknown ID')}.")
            # Production implementations would wait for fill, then actively place conditional SL and TP orders.
            
            return entry_order
        except Exception as e:
            logger.error(f"Error placing live order: {e}")
            return None
