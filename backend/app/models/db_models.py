"""Database models using SQLAlchemy / SQLAlchemy 데이터베이스 모델."""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Boolean,
    Index,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class User(Base):
    """User accounts / 사용자 계정."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    exchange_credentials = relationship("ExchangeCredential", back_populates="user")
    orders = relationship("Order", back_populates="user")
    balances = relationship("BalanceSnapshot", back_populates="user")


class ExchangeCredential(Base):
    """Encrypted exchange API keys / 암호화된 거래소 API 키."""

    __tablename__ = "exchange_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    exchange = Column(String(50), nullable=False)  # binance, okx, upbit, etc.
    api_key_encrypted = Column(Text, nullable=False)
    api_secret_encrypted = Column(Text, nullable=False)
    api_passphrase_encrypted = Column(Text, nullable=True)  # For OKX, etc.
    is_testnet = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="exchange_credentials")

    __table_args__ = (Index("idx_user_exchange", "user_id", "exchange"),)


class OrderStatus(str, enum.Enum):
    """Order status enum / 주문 상태 열거형."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


class Order(Base):
    """Order records / 주문 기록."""

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    opportunity_id = Column(String(50), nullable=True)  # UUID from opportunity
    exchange = Column(String(50), nullable=False)
    exchange_order_id = Column(String(255), nullable=True)  # Exchange's order ID
    symbol = Column(String(50), nullable=False)
    side = Column(String(10), nullable=False)  # buy, sell
    order_type = Column(String(20), nullable=False)  # market, limit, etc.
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=True)  # Limit price (null for market orders)
    filled_quantity = Column(Float, default=0.0)
    average_fill_price = Column(Float, nullable=True)
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING, nullable=False)
    fee = Column(Float, default=0.0)
    fee_currency = Column(String(10), nullable=True)
    order_metadata = Column(JSON, nullable=True)  # Additional data (renamed from metadata)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    submitted_at = Column(DateTime, nullable=True)
    filled_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="orders")
    fills = relationship("Fill", back_populates="order")

    __table_args__ = (
        Index("idx_user_status", "user_id", "status"),
        Index("idx_opportunity", "opportunity_id"),
    )


class Fill(Base):
    """Order fill records / 주문 체결 기록."""

    __tablename__ = "fills"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    exchange_fill_id = Column(String(255), nullable=True)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    fee = Column(Float, default=0.0)
    fee_currency = Column(String(10), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    fill_metadata = Column(JSON, nullable=True)  # Additional data (renamed from metadata)

    # Relationships
    order = relationship("Order", back_populates="fills")


class BalanceSnapshot(Base):
    """Balance snapshots per exchange / 거래소별 잔고 스냅샷."""

    __tablename__ = "balance_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    exchange = Column(String(50), nullable=False)
    asset = Column(String(20), nullable=False)
    free = Column(Float, nullable=False)  # Available balance
    locked = Column(Float, default=0.0)  # Locked in orders
    total = Column(Float, nullable=False)
    usd_value = Column(Float, nullable=True)  # Estimated USD value
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="balances")

    __table_args__ = (
        Index("idx_user_exchange_asset", "user_id", "exchange", "asset"),
        Index("idx_timestamp", "timestamp"),
    )


class OpportunityHistory(Base):
    """Historical opportunity records / 기회 히스토리 기록."""

    __tablename__ = "opportunity_history"

    id = Column(Integer, primary_key=True, index=True)
    opportunity_id = Column(String(50), unique=True, nullable=False)  # UUID
    type = Column(String(50), nullable=False)  # spot_cross, kimchi_premium, etc.
    symbol = Column(String(50), nullable=False)
    spread_bps = Column(Float, nullable=False)
    expected_pnl_pct = Column(Float, nullable=False)
    notional = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    legs = Column(JSON, nullable=False)  # Serialized legs
    opportunity_metadata = Column(JSON, nullable=True)  # Additional data (renamed from metadata)
    was_executed = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_type_timestamp", "type", "timestamp"),
        Index("idx_symbol", "symbol"),
    )


class RiskLimit(Base):
    """User risk limits / 사용자 리스크 한도."""

    __tablename__ = "risk_limits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    max_position_size_usd = Column(Float, default=10000.0)
    max_leverage = Column(Float, default=1.0)
    max_daily_loss_usd = Column(Float, default=1000.0)
    max_open_orders = Column(Integer, default=10)
    stop_loss_pct = Column(Float, default=5.0)
    take_profit_pct = Column(Float, default=10.0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ExecutionLog(Base):
    """Execution attempt logs / 실행 시도 로그."""

    __tablename__ = "execution_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    opportunity_id = Column(String(50), nullable=True)
    action = Column(String(50), nullable=False)  # execute, cancel, risk_check, etc.
    status = Column(String(20), nullable=False)  # success, failure
    details = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (Index("idx_user_timestamp", "user_id", "timestamp"),)
