"""
Multi-instrument configuration for RegimeFilteredOB strategy.

Auto-detects instrument from symbol and returns optimized parameters.
Strategy file (pine_ob_strategy.py) is NOT modified.
"""

# Symbol → instrument name mapping
SYMBOL_MAP = {
    # Gold
    'XAU': 'gold', 'XAUT': 'gold', 'GC=F': 'gold', 'XAUUSD': 'gold',
    'XAUUSDT': 'gold', 'XAUEUR': 'gold',
    # US100 (Nasdaq)
    'US100': 'nasdaq', 'NDAQ': 'nasdaq', 'QQQ': 'nasdaq', 'NDX': 'nasdaq',
    'US100USD': 'nasdaq', 'NQ=F': 'nasdaq',
    # US500 (S&P 500)
    'US500': 'sp500', 'SPX': 'sp500', 'SPY': 'sp500', 'ES=F': 'sp500',
    'US500USD': 'sp500', 'SPX500': 'sp500',
    # BTC (reference)
    'BTC': 'btc', 'BTCUSDT': 'btc', 'BTCUSD': 'btc',
    # ETH
    'ETH': 'eth', 'ETHUSDT': 'eth', 'ETHUSD': 'eth',
}

# Default config (BTC 1h — fallback)
DEFAULT_CONFIG = {
    'input_range': 25,
    'min_risk_reward': 1.5,
    'sl_atr_mult': 2.0,
    'tp_rr_mult': 2.0,
    'max_age_bars': 1000,
    'position_size': 0.5,
    'mitigated_size_mult': 0.5,
    'use_vol_filter': True,
    'min_atr_pct': 0.8,
    'max_atr_pct': 2.5,
    'use_adx_filter': False,
    'use_ofi_filter': True,
    'ofi_window': 6,
    'ofi_threshold': 150,
    'use_trailing_stop': True,
    'trail_activate_atr': 3.0,
    'trail_distance_atr': 0.5,
}

# Instrument-specific configs (tuned)
INSTRUMENT_CONFIGS = {
    'btc': {
        '1h': {
            'min_atr_pct': 0.8,
            'max_atr_pct': 2.5,
            'ofi_window': 6,
            'ofi_threshold': 150,
            'trail_activate_atr': 3.0,
            'trail_distance_atr': 0.5,
            'sl_atr_mult': 2.0,
            'tp_rr_mult': 2.0,
        }
    },
    'gold': {
        '1h': {
            'min_atr_pct': 0.8,
            'max_atr_pct': 2.5,
            'ofi_window': 6,
            'ofi_threshold': 150,
            'trail_activate_atr': 3.0,
            'trail_distance_atr': 0.5,
            'sl_atr_mult': 2.0,
            'tp_rr_mult': 2.0,
            '_note': 'No edge found. Best result -0.80%. Strategy is BTC-specific.',
        }
    },
    'nasdaq': {
        '1h': {
            'min_atr_pct': 0.25,
            'max_atr_pct': 0.55,
            'ofi_window': 6,
            'ofi_threshold': 150,
            'trail_activate_atr': 3.0,
            'trail_distance_atr': 0.5,
            'sl_atr_mult': 2.0,
            'tp_rr_mult': 2.0,
            '_note': 'No edge found. Best result -1.97%. Strategy is BTC-specific.',
        }
    },
    'sp500': {
        '1h': {
            'min_atr_pct': 0.8,
            'max_atr_pct': 2.5,
            'ofi_window': 6,
            'ofi_threshold': 150,
            'trail_activate_atr': 3.0,
            'trail_distance_atr': 0.5,
            'sl_atr_mult': 2.0,
            'tp_rr_mult': 2.0,
            '_note': 'No edge found. Best result -5.46%. Strategy is BTC-specific.',
        }
    },
    'eth': {
        '1h': {
            'min_atr_pct': 0.5,
            'max_atr_pct': 1.5,
            'ofi_window': 4,
            'ofi_threshold': 50,
            'trail_activate_atr': 2.5,
            'trail_distance_atr': 0.5,
            'sl_atr_mult': 2.0,
            'tp_rr_mult': 2.0,
        }
    },
}


def get_config(symbol, timeframe='1h'):
    """
    Auto-detect instrument from symbol, return optimized config.

    Usage:
        from instrument_configs import get_config
        from pine_ob_strategy import RegimeFilteredOB

        strategy = RegimeFilteredOB(**get_config('XAUUSD'))
        strategy = RegimeFilteredOB(**get_config('QQQ'))
    """
    symbol_clean = symbol.upper().replace('/', '').replace('-', '').replace(' ', '')
    instrument = SYMBOL_MAP.get(symbol_clean)

    if instrument is None:
        for key, val in SYMBOL_MAP.items():
            if key in symbol_clean or symbol_clean in key:
                instrument = val
                break

    if instrument and instrument in INSTRUMENT_CONFIGS:
        tf_config = INSTRUMENT_CONFIGS[instrument].get(timeframe, {})
        if tf_config:
            merged = {**DEFAULT_CONFIG, **tf_config}
            return merged

    return DEFAULT_CONFIG.copy()


def list_instruments():
    """Return list of available instrument names."""
    return list(INSTRUMENT_CONFIGS.keys())


def list_timeframes(instrument):
    """Return list of available timeframes for an instrument."""
    return list(INSTRUMENT_CONFIGS.get(instrument, {}).keys())
