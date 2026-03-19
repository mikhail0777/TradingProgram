import logging
from config import settings
import alpaca_trade_api as tradeapi

logger = logging.getLogger(__name__)

class Executor:
    def __init__(self):
        self.mode = settings.execution_mode
        
        if self.mode == "LIVE":
            if not settings.alpaca_api_key or not settings.alpaca_api_secret:
                logger.warning("LIVE mode requested but Alpaca API keys are missing. Falling back to PAPER mode.")
                self.mode = "PAPER"
            else:
                self.api = tradeapi.REST(
                    key_id=settings.alpaca_api_key,
                    secret_key=settings.alpaca_api_secret,
                    base_url=settings.alpaca_base_url
                )
                try:
                    # Test connection
                    account = self.api.get_account()
                    logger.info(f"Successfully connected to Alpaca in LIVE mode. Account Status: {account.status}")
                except Exception as e:
                    logger.error(f"Failed to connect to Alpaca broker: {e}")
                    raise
        
        if self.mode == "PAPER":
            logger.info("Executor initialized in PAPER format - no real orders will be sent to the broker.")

    def place_order(self, symbol: str, direction: str, quantity: float, entry_price: float, stop_loss_price: float, take_profit_price: float) -> dict | None:
        if self.mode == "PAPER":
            logger.info(f"[PAPER TRADE] Placed {direction} {quantity} shares of {symbol} @ {entry_price} [SL: {stop_loss_price}, TP: {take_profit_price}]")
            return {"status": "paper_success", "id": "paper_test_001"}
            
        try:
            order_side = 'buy' if direction == 'LONG' else 'sell'
            
            logger.info(f"[LIVE TRADE] Placing Bracket Order for {quantity} shares of {symbol}")
            
            # Alpaca supports full bracket orders natively (Entry -> Stop Loss + Take Profit)
            order = self.api.submit_order(
                symbol=symbol,
                qty=quantity,
                side=order_side,
                type='market',
                time_in_force='gtc',
                order_class='bracket',
                take_profit=dict(
                    limit_price=round(take_profit_price, 2),
                ),
                stop_loss=dict(
                    stop_price=round(stop_loss_price, 2),
                )
            )
            
            logger.info(f"Bracket order placed: {order.id}.")
            return {"status": "success", "id": order.id, "order": order}
        except Exception as e:
            logger.error(f"Error placing live Alpaca order: {e}")
            return None
