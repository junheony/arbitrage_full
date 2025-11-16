"""Exchange client factory for order execution / 주문 실행용 거래소 클라이언트 팩토리."""
from __future__ import annotations

import logging
from typing import Any

import ccxt
from ccxt.base.exchange import Exchange

from app.auth.encryption import decrypt_api_key
from app.models.db_models import ExchangeCredential

logger = logging.getLogger(__name__)


class ExchangeClientFactory:
    """Factory for creating exchange clients / 거래소 클라이언트 팩토리."""

    @staticmethod
    def create_client(credential: ExchangeCredential) -> Exchange:
        """
        Create a CCXT exchange client from credentials.
        인증정보로 CCXT 거래소 클라이언트 생성.

        Args:
            credential: Exchange credential with encrypted API keys

        Returns:
            CCXT exchange instance

        Raises:
            ValueError: If exchange is not supported
        """
        # Decrypt API keys
        api_key = decrypt_api_key(credential.api_key_encrypted)
        api_secret = decrypt_api_key(credential.api_secret_encrypted)

        # Optional passphrase for exchanges like OKX
        passphrase = None
        if credential.api_passphrase_encrypted:
            passphrase = decrypt_api_key(credential.api_passphrase_encrypted)

        # Map exchange names to CCXT classes
        exchange_map = {
            "binance": ccxt.binance,
            "okx": ccxt.okx,
            "bybit": ccxt.bybit,
            "upbit": ccxt.upbit,
            "bithumb": ccxt.bithumb,
            "hyperliquid": ccxt.hyperliquid,
            "coinbase": ccxt.coinbase,
            "kraken": ccxt.kraken,
            "bitfinex": ccxt.bitfinex,
            "huobi": ccxt.huobi,
        }

        exchange_class = exchange_map.get(credential.exchange.lower())
        if not exchange_class:
            raise ValueError(
                f"Unsupported exchange: {credential.exchange}. "
                f"Supported: {', '.join(exchange_map.keys())}"
            )

        # Build configuration
        config: dict[str, Any] = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,  # Prevent rate limit violations
            "timeout": 30000,  # 30 seconds
        }

        # Add passphrase if needed (OKX, KuCoin)
        if passphrase:
            config["password"] = passphrase

        # Set testnet/sandbox if configured
        if credential.is_testnet:
            config["options"] = {"defaultType": "future"}
            if credential.exchange.lower() == "binance":
                config["options"]["testnet"] = True
            elif credential.exchange.lower() == "bybit":
                config["options"]["testnet"] = True

        # Create exchange instance
        exchange = exchange_class(config)

        logger.info(
            "Created %s exchange client (testnet=%s) / %s 거래소 클라이언트 생성 (테스트넷=%s)",
            credential.exchange,
            credential.is_testnet,
            credential.exchange,
            credential.is_testnet,
        )

        return exchange

    @staticmethod
    async def submit_order(
        exchange: Exchange,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        price: float | None = None,
    ) -> dict[str, Any]:
        """
        Submit an order to the exchange.
        거래소에 주문 제출.

        Args:
            exchange: CCXT exchange instance
            symbol: Trading pair (e.g., "BTC/USDT")
            side: "buy" or "sell"
            quantity: Order quantity
            order_type: "market" or "limit"
            price: Limit price (required for limit orders)

        Returns:
            Order response from exchange

        Raises:
            ccxt.ExchangeError: On exchange errors
        """
        try:
            # Normalize symbol format for CCXT (BTC/USDT)
            normalized_symbol = symbol.replace("_", "/") if "_" in symbol else symbol

            # Submit order based on type
            if order_type == "limit":
                if price is None:
                    raise ValueError("Price required for limit orders")

                order = exchange.create_limit_order(
                    symbol=normalized_symbol,
                    side=side,
                    amount=quantity,
                    price=price,
                )
            else:  # market order
                order = exchange.create_market_order(
                    symbol=normalized_symbol,
                    side=side,
                    amount=quantity,
                )

            logger.info(
                "Order submitted to %s: %s %s %s @ %s (order_id=%s) / "
                "%s에 주문 제출: %s %s %s @ %s (주문ID=%s)",
                exchange.id,
                side,
                quantity,
                normalized_symbol,
                price or "market",
                order.get("id"),
                exchange.id,
                side,
                quantity,
                normalized_symbol,
                price or "시장가",
                order.get("id"),
            )

            return order

        except ccxt.InsufficientFunds as exc:
            logger.error("Insufficient funds on %s: %s", exchange.id, exc)
            raise
        except ccxt.InvalidOrder as exc:
            logger.error("Invalid order on %s: %s", exchange.id, exc)
            raise
        except ccxt.ExchangeError as exc:
            logger.error("Exchange error on %s: %s", exchange.id, exc)
            raise
        except Exception as exc:
            logger.exception("Unexpected error submitting order to %s: %s", exchange.id, exc)
            raise

    @staticmethod
    async def fetch_order_status(
        exchange: Exchange, order_id: str, symbol: str
    ) -> dict[str, Any]:
        """
        Fetch order status from exchange.
        거래소에서 주문 상태 조회.

        Args:
            exchange: CCXT exchange instance
            order_id: Exchange order ID
            symbol: Trading pair

        Returns:
            Order status response
        """
        try:
            normalized_symbol = symbol.replace("_", "/") if "_" in symbol else symbol
            order = exchange.fetch_order(order_id, normalized_symbol)

            logger.debug(
                "Fetched order %s status: %s / 주문 %s 상태 조회: %s",
                order_id,
                order.get("status"),
                order_id,
                order.get("status"),
            )

            return order

        except ccxt.OrderNotFound as exc:
            logger.warning("Order %s not found on %s: %s", order_id, exchange.id, exc)
            raise
        except Exception as exc:
            logger.exception("Error fetching order %s from %s: %s", order_id, exchange.id, exc)
            raise

    @staticmethod
    async def set_leverage(
        exchange: Exchange,
        symbol: str,
        leverage: int,
    ) -> dict[str, Any]:
        """
        Set leverage for perpetual futures trading.
        무기한 선물 거래 레버리지 설정.

        Args:
            exchange: CCXT exchange instance
            symbol: Trading pair (e.g., "BTC/USDT:USDT")
            leverage: Leverage level (1-125 depending on exchange)

        Returns:
            Response from exchange
        """
        try:
            # Normalize symbol for perp contracts
            # Most exchanges use "BTC/USDT:USDT" format for USDT-margined perps
            if ":" not in symbol and "/" in symbol:
                symbol = f"{symbol}:USDT"

            result = exchange.set_leverage(leverage, symbol)

            logger.info(
                "Set leverage for %s on %s to %dx / %s에서 %s 레버리지를 %d배로 설정",
                symbol,
                exchange.id,
                leverage,
                exchange.id,
                symbol,
                leverage,
            )

            return result

        except ccxt.NotSupported:
            logger.warning(
                "Leverage setting not supported on %s / %s에서 레버리지 설정 미지원",
                exchange.id,
                exchange.id,
            )
            return {"status": "not_supported"}
        except Exception as exc:
            logger.error(
                "Error setting leverage on %s: %s / %s 레버리지 설정 오류: %s",
                exchange.id,
                exc,
                exchange.id,
                exc,
            )
            raise

    @staticmethod
    async def submit_perp_order(
        exchange: Exchange,
        symbol: str,
        side: str,
        quantity: float,
        leverage: int = 1,
        order_type: str = "market",
        price: float | None = None,
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        """
        Submit a perpetual futures order.
        무기한 선물 주문 제출.

        Args:
            exchange: CCXT exchange instance
            symbol: Trading pair (e.g., "BTC/USDT" or "BTC/USDT:USDT")
            side: "buy" or "sell"
            quantity: Order quantity (in contracts or base currency)
            leverage: Leverage level
            order_type: "market" or "limit"
            price: Limit price (required for limit orders)
            reduce_only: If True, order only reduces position (doesn't open new)

        Returns:
            Order response from exchange
        """
        try:
            # Normalize symbol for perp contracts
            perp_symbol = symbol
            if ":" not in symbol and "/" in symbol:
                perp_symbol = f"{symbol}:USDT"

            # Set leverage first
            try:
                await ExchangeClientFactory.set_leverage(exchange, perp_symbol, leverage)
            except Exception as exc:
                logger.warning("Could not set leverage, continuing anyway: %s", exc)

            # Prepare order parameters
            params: dict[str, Any] = {}
            if reduce_only:
                params["reduceOnly"] = True

            # Submit order
            if order_type == "limit":
                if price is None:
                    raise ValueError("Price required for limit orders")

                order = exchange.create_limit_order(
                    symbol=perp_symbol,
                    side=side,
                    amount=quantity,
                    price=price,
                    params=params,
                )
            else:  # market order
                order = exchange.create_market_order(
                    symbol=perp_symbol,
                    side=side,
                    amount=quantity,
                    params=params,
                )

            logger.info(
                "Perp order submitted to %s: %s %s %s @ %s (leverage=%dx, order_id=%s) / "
                "%s에 무기한 선물 주문 제출: %s %s %s @ %s (레버리지=%d배, 주문ID=%s)",
                exchange.id,
                side,
                quantity,
                perp_symbol,
                price or "market",
                leverage,
                order.get("id"),
                exchange.id,
                side,
                quantity,
                perp_symbol,
                price or "시장가",
                leverage,
                order.get("id"),
            )

            return order

        except Exception as exc:
            logger.exception(
                "Error submitting perp order to %s: %s / %s 무기한 선물 주문 제출 오류: %s",
                exchange.id,
                exc,
                exchange.id,
                exc,
            )
            raise

    @staticmethod
    def close_client(exchange: Exchange) -> None:
        """Close exchange client connection / 거래소 클라이언트 연결 종료."""
        try:
            exchange.close()
            logger.debug("Closed exchange client for %s", exchange.id)
        except Exception as exc:
            logger.warning("Error closing exchange client: %s", exc)
