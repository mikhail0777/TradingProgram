import logging
from config import settings
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

logger = logging.getLogger(__name__)

class Executor:
    def __init__(self):
        self.mode = settings.execution_mode
        
        if self.mode == "LIVE":
            if not settings.alpaca_api_key or not settings.alpaca_api_secret:
                logger.warning("LIVE mode requested but Alpaca API keys are missing. Falling back to PAPER mode.")
                self.mode = "PAPER"
            else:
                self.api = TradingClient(
                    api_key=settings.alpaca_api_key,
                    secret_key=settings.alpaca_api_secret,
                    paper=(self.mode == "PAPER" or "paper" in settings.alpaca_base_url.lower())
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
            order_side = OrderSide.BUY if direction == 'LONG' else OrderSide.SELL
            
            logger.info(f"[LIVE TRADE] Placing Bracket Order for {quantity} shares of {symbol}")
            
            req = MarketOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=order_side,
                time_in_force=TimeInForce.GTC,
                order_class=OrderClass.BRACKET,
                take_profit=TakeProfitRequest(limit_price=round(take_profit_price, 2)),
                stop_loss=StopLossRequest(stop_price=round(stop_loss_price, 2))
            )
            order = self.api.submit_order(req)
            
            logger.info(f"Bracket order placed: {order.id}.")
            return {"status": "success", "id": str(order.id), "order": order}
        except Exception as e:
            logger.error(f"Error placing live Alpaca order: {e}")
            return None

    def close_position(self, symbol: str, direction: str, quantity: float, reason: str) -> dict | None:
        """Executes a market order to close all or part of an open position."""
        if self.mode == "PAPER":
            logger.info(f"[PAPER EXIT] Closed {quantity:.4f} units of {symbol} ({direction}) due to: {reason}")
            return {"status": "paper_success"}
            
        try:
            logger.info(f"[LIVE EXIT] Closing {quantity:.4f} units of {symbol} due to: {reason}")
            order_side = OrderSide.SELL if direction == 'LONG' else OrderSide.BUY
            
            req = MarketOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=order_side,
                time_in_force=TimeInForce.GTC
            )
            order = self.api.submit_order(req)
            
            logger.info(f"Close/Partial order placed securely: {order.id}.")
            return {"status": "success", "id": str(order.id), "order": order}
        except Exception as e:
            logger.error(f"Error executing live close Alpaca order: {e}")
            return None
