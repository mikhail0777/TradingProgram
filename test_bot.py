import asyncio
from bot import TradingBot

async def main():
    print("Initializing TradingBot...")
    bot = TradingBot()
    print(f"Loaded symbols: {bot.symbols}")
    
    for symbol in bot.symbols[:3]: # Test a few symbols
        print(f"\n--- Running tick for {symbol} ---")
        try:
            await bot.tick(symbol)
            print(f"Success ticking {symbol}")
        except Exception as e:
            print(f"Error ticking {symbol}: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
