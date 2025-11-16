"""Check deposit and withdrawal status for exchanges / 거래소 입출금 상태 확인."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Set

import httpx

logger = logging.getLogger(__name__)


class DepositWithdrawalChecker:
    """Checks deposit/withdrawal status across exchanges / 거래소별 입출금 상태 확인."""

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=5.0)
        self._cache: Dict[str, Set[str]] = {}  # exchange -> set of disabled symbols
        self._cache_time: Dict[str, datetime] = {}
        self._cache_duration = timedelta(minutes=5)  # Cache for 5 minutes

    async def close(self) -> None:
        await self._client.aclose()

    async def is_trading_enabled(self, exchange: str, symbol: str) -> bool:
        """Check if deposit/withdrawal is enabled for a symbol on an exchange.

        Returns True if trading is fully enabled (deposits AND withdrawals both working).
        Returns False if either is disabled.
        """
        # Update cache if needed
        await self._update_cache_if_needed(exchange)

        disabled_symbols = self._cache.get(exchange, set())
        return symbol not in disabled_symbols

    async def get_disabled_symbols(self, exchange: str) -> Set[str]:
        """Get set of symbols with disabled deposits or withdrawals."""
        await self._update_cache_if_needed(exchange)
        return self._cache.get(exchange, set())

    async def _update_cache_if_needed(self, exchange: str) -> None:
        """Update cache if it's stale."""
        now = datetime.utcnow()
        last_update = self._cache_time.get(exchange)

        if last_update is None or (now - last_update) > self._cache_duration:
            await self._update_cache(exchange)
            self._cache_time[exchange] = now

    async def _update_cache(self, exchange: str) -> None:
        """Fetch latest deposit/withdrawal status from exchange."""
        exchange_lower = exchange.lower()

        if exchange_lower == "binance":
            await self._update_binance_cache()
        elif exchange_lower == "okx":
            await self._update_okx_cache()
        elif exchange_lower == "upbit":
            await self._update_upbit_cache()
        elif exchange_lower == "bithumb":
            await self._update_bithumb_cache()
        elif exchange_lower == "bybit":
            await self._update_bybit_cache()
        else:
            logger.warning(f"Unknown exchange for deposit/withdrawal check: {exchange}")
            self._cache[exchange] = set()

    async def _update_binance_cache(self) -> None:
        """Fetch Binance spot deposit/withdrawal status."""
        try:
            response = await self._client.get("https://api.binance.com/sapi/v1/capital/config/getall")
            response.raise_for_status()
            coins = response.json()

            disabled = set()
            for coin in coins:
                symbol = coin.get("coin")
                deposit_enabled = coin.get("depositAllEnable", False)
                withdraw_enabled = coin.get("withdrawAllEnable", False)

                # Mark as disabled if either deposit OR withdrawal is disabled
                if not deposit_enabled or not withdraw_enabled:
                    disabled.add(symbol)

            self._cache["binance"] = disabled
            logger.info(f"Binance: {len(disabled)} symbols with disabled deposits/withdrawals")

        except Exception as exc:
            logger.warning(f"Failed to fetch Binance deposit/withdrawal status: {exc}")
            self._cache["binance"] = set()

    async def _update_okx_cache(self) -> None:
        """Fetch OKX deposit/withdrawal status."""
        try:
            response = await self._client.get("https://www.okx.com/api/v5/asset/currencies")
            response.raise_for_status()
            data = response.json()

            disabled = set()
            for currency in data.get("data", []):
                symbol = currency.get("ccy")
                can_deposit = currency.get("canDep", False)
                can_withdraw = currency.get("canWd", False)

                if not can_deposit or not can_withdraw:
                    disabled.add(symbol)

            self._cache["okx"] = disabled
            logger.info(f"OKX: {len(disabled)} symbols with disabled deposits/withdrawals")

        except Exception as exc:
            logger.warning(f"Failed to fetch OKX deposit/withdrawal status: {exc}")
            self._cache["okx"] = set()

    async def _update_upbit_cache(self) -> None:
        """Fetch Upbit deposit/withdrawal status."""
        try:
            response = await self._client.get("https://api.upbit.com/v1/status/wallet")
            response.raise_for_status()
            wallets = response.json()

            disabled = set()
            for wallet in wallets:
                # Upbit uses market format like "BTC" or "KRW-BTC"
                currency = wallet.get("currency")

                wallet_state = wallet.get("wallet_state", "")
                block_state = wallet.get("block_state", "")

                # Mark as disabled if wallet is not working or blockchain is not normal
                if wallet_state != "working" or block_state != "normal":
                    disabled.add(currency)

            self._cache["upbit"] = disabled
            logger.info(f"Upbit: {len(disabled)} symbols with disabled deposits/withdrawals")

        except Exception as exc:
            logger.warning(f"Failed to fetch Upbit deposit/withdrawal status: {exc}")
            self._cache["upbit"] = set()

    async def _update_bithumb_cache(self) -> None:
        """Fetch Bithumb deposit/withdrawal status."""
        try:
            response = await self._client.get("https://api.bithumb.com/public/assetsstatus/ALL")
            response.raise_for_status()
            data = response.json()

            disabled = set()
            if data.get("status") == "0000":
                assets = data.get("data", {})
                for symbol, status in assets.items():
                    if isinstance(status, dict):
                        deposit_status = status.get("deposit_status", 0)
                        withdrawal_status = status.get("withdrawal_status", 0)

                        # 1 = enabled, 0 = disabled
                        if deposit_status != 1 or withdrawal_status != 1:
                            disabled.add(symbol)

            self._cache["bithumb"] = disabled
            logger.info(f"Bithumb: {len(disabled)} symbols with disabled deposits/withdrawals")

        except Exception as exc:
            logger.warning(f"Failed to fetch Bithumb deposit/withdrawal status: {exc}")
            self._cache["bithumb"] = set()

    async def _update_bybit_cache(self) -> None:
        """Fetch Bybit deposit/withdrawal status."""
        try:
            response = await self._client.get("https://api.bybit.com/v5/asset/coin/query-info")
            response.raise_for_status()
            data = response.json()

            disabled = set()
            if data.get("retCode") == 0:
                rows = data.get("result", {}).get("rows", [])
                for row in rows:
                    symbol = row.get("coin")
                    chains = row.get("chains", [])

                    # Check if ANY chain has both deposit and withdrawal enabled
                    has_enabled_chain = False
                    for chain in chains:
                        deposit_enabled = chain.get("chainDeposit") == "1"
                        withdraw_enabled = chain.get("chainWithdraw") == "1"

                        if deposit_enabled and withdraw_enabled:
                            has_enabled_chain = True
                            break

                    if not has_enabled_chain:
                        disabled.add(symbol)

            self._cache["bybit"] = disabled
            logger.info(f"Bybit: {len(disabled)} symbols with disabled deposits/withdrawals")

        except Exception as exc:
            logger.warning(f"Failed to fetch Bybit deposit/withdrawal status: {exc}")
            self._cache["bybit"] = set()


# Global singleton instance
_checker_instance: DepositWithdrawalChecker | None = None


def get_deposit_checker() -> DepositWithdrawalChecker:
    """Get global deposit/withdrawal checker instance."""
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = DepositWithdrawalChecker()
    return _checker_instance


async def close_deposit_checker() -> None:
    """Close global deposit/withdrawal checker."""
    global _checker_instance
    if _checker_instance is not None:
        await _checker_instance.close()
        _checker_instance = None
