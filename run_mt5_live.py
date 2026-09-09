"""
MT5 Live Trader - Manual Start
===============================
Runs RegimeFilteredOB strategy on MT5 (Exness trial account).
Ctrl+C to stop, closes all open positions.
"""

import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from trading_bot.config.settings import MT5Config
from trading_bot.execution.mt5_executor import MT5Executor
from trading_bot.data.mt5_provider import MT5DataProvider
from trading_bot.execution.mt5_live_trader import MT5LiveTrader
from pine_ob_strategy import RegimeFilteredOB


def main():
    # Load strategy config
    config_path = Path('configs/base_config.json')
    if config_path.exists():
        with open(config_path) as f:
            cfg = json.load(f)
    else:
        cfg = {
            "filters": {
                "use_ofi_filter": True,
                "ofi_window": 6,
                "ofi_threshold": 150,
                "use_vol_filter": True,
                "min_atr_pct": 0.8,
                "max_atr_pct": 2.5,
            },
            "risk": {
                "sl_atr_mult": 2.0,
                "tp_rr_mult": 1.5,
            },
            "trading": {
                "position_size": 0.01,
                "max_open_trades": 1,
            }
        }

    # Initialize components
    executor = MT5Executor(
        symbol="BTCUSDm",
        login=MT5Config.LOGIN,
        password=MT5Config.PASSWORD,
        server=MT5Config.SERVER,
        magic=MT5Config.MAGIC_NUMBER,
        comment=MT5Config.COMMENT,
    )

    provider = MT5DataProvider(
        symbol="BTCUSDm",
        login=MT5Config.LOGIN,
        password=MT5Config.PASSWORD,
        server=MT5Config.SERVER,
    )

    # Initialize strategy
    filters = cfg.get('filters', {})
    risk = cfg.get('risk', {})

    strategy = RegimeFilteredOB(
        input_range=5,
        use_ofi_filter=filters.get('use_ofi_filter', True),
        ofi_window=filters.get('ofi_window', 6),
        ofi_threshold=filters.get('ofi_threshold', 150),
        use_vol_filter=filters.get('use_vol_filter', True),
        min_atr_pct=filters.get('min_atr_pct', 0.8),
        max_atr_pct=filters.get('max_atr_pct', 2.5),
        sl_atr_mult=risk.get('sl_atr_mult', 2.0),
        tp_rr_mult=risk.get('tp_rr_mult', 1.5),
        position_size=cfg.get('trading', {}).get('position_size', 0.01),
    )

    # Load telegram config
    tg_path = Path('trading_bot/config/telegram_config.json')
    tg_cfg = {}
    if tg_path.exists():
        with open(tg_path) as f:
            tg_cfg = json.load(f)

    trader_cfg = {
        'telegram_token': tg_cfg.get('bot_token', ''),
        'telegram_chat_id': tg_cfg.get('chat_id', ''),
        'send_telegram': tg_cfg.get('enabled', True),
        'check_interval': 900,
    }

    trader = MT5LiveTrader(
        executor=executor,
        provider=provider,
        strategy=strategy,
        config=trader_cfg,
    )

    trader.run()


if __name__ == '__main__':
    main()
