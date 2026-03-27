"""FastAPI REST endpoint tests using FastAPI TestClient with dependency overrides."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from bot.engine.market_maker import BotState, MarketMaker
from server import dependencies
from server.main import create_app
from server.routers import chart, fills, health, orders, pnl, portfolio, report, status


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_bot_state(**overrides: Any) -> BotState:
    """Build a default BotState with optional field overrides."""
    state = BotState(
        state="RUNNING",
        feeds_enabled=True,
        wagyu_enabled=True,
        quoting_enabled=True,
        inv_limit_enabled=True,
        cycle_count=42,
        last_cycle_ms=85.3,
        fills_count=10,
        fair_price=155.50,
        regime="CALM",
        inventory_pct=20.0,
        realized_pnl=12.34,
        unrealized_pnl=5.67,
        portfolio_value=2000.0,
        open_orders_count=6,
        halt_reason=None,
        feed_health=[
            {
                "source": "hyperliquid",
                "healthy": True,
                "price": 155.50,
                "latency_ms": 12.0,
                "last_updated": 1700000000.0,
            },
            {
                "source": "kraken",
                "healthy": True,
                "price": 155.45,
                "latency_ms": 25.0,
                "last_updated": 1700000001.0,
            },
        ],
        alerts=[],
    )
    for key, val in overrides.items():
        setattr(state, key, val)
    return state


def _make_mock_mm(state: BotState | None = None) -> MagicMock:
    """Create a MagicMock MarketMaker with sensible defaults."""
    # Use MagicMock without spec so instance attributes (_client, _order_manager)
    # defined in __init__ are accessible on the mock.
    mm = MagicMock()
    mm.get_state.return_value = state or _make_bot_state()
    mm.toggle_feeds.return_value = False
    mm.toggle_wagyu.return_value = False
    mm.toggle_quoting.return_value = False
    mm.toggle_inv_limit.return_value = False

    # Mock the internal client for portfolio endpoint
    user_state = MagicMock()
    user_state.usdc_balance = 1000.0
    user_state.xmr_balance = 6.5
    mm._client.get_user_state.return_value = user_state

    # Mock open orders
    order = MagicMock()
    order.oid = "oid-001"
    order.side = "buy"
    order.price = 154.0
    order.size = 0.5
    order.status = "open"
    order.created_at = datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc)
    mm._order_manager.get_open_orders.return_value = [order]

    return mm


@pytest.fixture()
def mock_mm() -> MagicMock:
    return _make_mock_mm()


@pytest.fixture()
def client(mock_mm: MagicMock) -> TestClient:
    """Return a TestClient with dependency overrides, bypassing lifespan."""
    app = create_app()
    mm = mock_mm
    # Override get_bot and each router's _get_mm to bypass isinstance check
    app.dependency_overrides[dependencies.get_bot] = lambda: mm
    app.dependency_overrides[status._get_mm] = lambda: mm
    app.dependency_overrides[portfolio._get_mm] = lambda: mm
    app.dependency_overrides[orders._get_mm] = lambda: mm
    app.dependency_overrides[pnl._get_mm] = lambda: mm
    app.dependency_overrides[health._get_mm] = lambda: mm
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Helper: patch repository functions used by endpoints that hit the DB
# ---------------------------------------------------------------------------


def _empty_fills_patch() -> Any:
    return patch(
        "bot.persistence.repository.get_fills",
        new=AsyncMock(return_value=([], 0)),
    )


def _empty_pnl_patch() -> Any:
    return patch(
        "bot.persistence.repository.get_pnl_history",
        new=AsyncMock(return_value=[]),
    )


def _empty_price_patch() -> Any:
    return patch(
        "bot.persistence.repository.get_price_history",
        new=AsyncMock(return_value=[]),
    )


def _empty_hodl_patch() -> Any:
    return patch(
        "bot.persistence.repository.get_hodl_benchmark",
        new=AsyncMock(return_value=None),
    )


def _empty_daily_pnl_patch() -> Any:
    return patch(
        "bot.persistence.repository.get_daily_pnl_summary",
        new=AsyncMock(return_value=[]),
    )


# ---------------------------------------------------------------------------
# /api/status
# ---------------------------------------------------------------------------


class TestStatusEndpoint:
    def test_get_status_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/status")
        assert response.status_code == 200

    def test_get_status_state_field(self, client: TestClient) -> None:
        response = client.get("/api/status")
        data: dict[str, Any] = response.json()
        assert data["state"] == "RUNNING"

    def test_get_status_toggles_structure(self, client: TestClient) -> None:
        response = client.get("/api/status")
        toggles = response.json()["toggles"]
        assert "feeds" in toggles
        assert "wagyu" in toggles
        assert "quoting" in toggles
        assert "inv_limit" in toggles

    def test_get_status_feed_health_list(self, client: TestClient) -> None:
        response = client.get("/api/status")
        data = response.json()
        assert isinstance(data["feed_health"], list)
        assert len(data["feed_health"]) == 2
        assert data["feed_health"][0]["source"] == "hyperliquid"

    def test_get_status_numeric_fields(self, client: TestClient) -> None:
        response = client.get("/api/status")
        data = response.json()
        assert data["fair_price"] == pytest.approx(155.50)
        assert data["realized_pnl"] == pytest.approx(12.34)
        assert data["portfolio_value"] == pytest.approx(2000.0)

    def test_get_status_halt_reason_none(self, client: TestClient) -> None:
        response = client.get("/api/status")
        assert response.json()["halt_reason"] is None

    def test_get_status_halted_state(self, mock_mm: MagicMock) -> None:
        halted_state = _make_bot_state(state="HALTED", halt_reason="Daily loss limit breached")
        mock_mm.get_state.return_value = halted_state
        mm = mock_mm
        app = create_app()
        app.dependency_overrides[dependencies.get_bot] = lambda: mm
        app.dependency_overrides[status._get_mm] = lambda: mm
        c = TestClient(app, raise_server_exceptions=True)
        response = c.get("/api/status")
        data = response.json()
        assert data["state"] == "HALTED"
        assert "Daily loss limit" in data["halt_reason"]


# ---------------------------------------------------------------------------
# POST /api/toggle/{target}
# ---------------------------------------------------------------------------


class TestToggleEndpoint:
    def test_toggle_feeds_returns_200(self, client: TestClient, mock_mm: MagicMock) -> None:
        mock_mm.toggle_feeds.return_value = False
        response = client.post("/api/toggle/feeds")
        assert response.status_code == 200

    def test_toggle_returns_target_and_enabled(
        self, client: TestClient, mock_mm: MagicMock
    ) -> None:
        mock_mm.toggle_wagyu.return_value = True
        response = client.post("/api/toggle/wagyu")
        data = response.json()
        assert data["target"] == "wagyu"
        assert data["enabled"] is True

    def test_toggle_quoting(self, client: TestClient, mock_mm: MagicMock) -> None:
        mock_mm.toggle_quoting.return_value = False
        response = client.post("/api/toggle/quoting")
        assert response.status_code == 200
        assert response.json()["target"] == "quoting"

    def test_toggle_inv_limit(self, client: TestClient, mock_mm: MagicMock) -> None:
        mock_mm.toggle_inv_limit.return_value = True
        response = client.post("/api/toggle/inv_limit")
        assert response.status_code == 200

    def test_toggle_invalid_target_returns_400(self, client: TestClient) -> None:
        response = client.post("/api/toggle/invalid_target")
        assert response.status_code == 400

    def test_toggle_calls_correct_method(
        self, client: TestClient, mock_mm: MagicMock
    ) -> None:
        mock_mm.toggle_feeds.return_value = True
        client.post("/api/toggle/feeds")
        mock_mm.toggle_feeds.assert_called_once()


# ---------------------------------------------------------------------------
# GET /api/portfolio
# ---------------------------------------------------------------------------


class TestPortfolioEndpoint:
    def test_get_portfolio_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/portfolio")
        assert response.status_code == 200

    def test_get_portfolio_fields(self, client: TestClient) -> None:
        response = client.get("/api/portfolio")
        data = response.json()
        assert "usdc_balance" in data
        assert "xmr_balance" in data
        assert "total_value_usdc" in data
        assert "xmr_price" in data

    def test_get_portfolio_values(self, client: TestClient) -> None:
        response = client.get("/api/portfolio")
        data = response.json()
        assert data["usdc_balance"] == pytest.approx(1000.0)
        assert data["xmr_balance"] == pytest.approx(6.5)
        # total = 1000 + 6.5 * 155.50
        assert data["total_value_usdc"] == pytest.approx(1000.0 + 6.5 * 155.50)


# ---------------------------------------------------------------------------
# GET /api/fills
# ---------------------------------------------------------------------------


class TestFillsEndpoint:
    def test_get_fills_empty_returns_200(self, client: TestClient) -> None:
        with _empty_fills_patch():
            response = client.get("/api/fills")
        assert response.status_code == 200

    def test_get_fills_empty_structure(self, client: TestClient) -> None:
        with _empty_fills_patch():
            response = client.get("/api/fills")
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    def test_get_fills_pagination_defaults(self, client: TestClient) -> None:
        with _empty_fills_patch():
            response = client.get("/api/fills")
        data = response.json()
        assert data["limit"] == 50

    def test_get_fills_custom_page(self, client: TestClient) -> None:
        with _empty_fills_patch():
            response = client.get("/api/fills?page=2&limit=10")
        data = response.json()
        assert data["page"] == 2
        assert data["limit"] == 10

    def test_get_fills_with_data(self, client: TestClient) -> None:
        fill_rows = [
            {
                "id": 1,
                "timestamp": "2026-03-22T10:00:00+00:00",
                "oid": "oid-xyz",
                "side": "buy",
                "price": 155.50,
                "size": 0.32,
                "fee": 0.005,
                "is_maker": True,
                "mid_price_at_fill": 155.48,
            }
        ]
        with patch(
            "bot.persistence.repository.get_fills",
            new=AsyncMock(return_value=(fill_rows, 1)),
        ):
            response = client.get("/api/fills")
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["side"] == "buy"
        assert data["items"][0]["is_maker"] is True


# ---------------------------------------------------------------------------
# GET /api/orders
# ---------------------------------------------------------------------------


class TestOrdersEndpoint:
    def test_get_orders_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/orders")
        assert response.status_code == 200

    def test_get_orders_items_structure(self, client: TestClient) -> None:
        response = client.get("/api/orders")
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_get_orders_item_fields(self, client: TestClient) -> None:
        response = client.get("/api/orders")
        items = response.json()["items"]
        assert len(items) == 1
        item = items[0]
        assert item["oid"] == "oid-001"
        assert item["side"] == "buy"
        assert "age_seconds" in item


# ---------------------------------------------------------------------------
# GET /api/pnl/summary
# ---------------------------------------------------------------------------


class TestPnLSummaryEndpoint:
    def test_get_pnl_summary_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/pnl/summary")
        assert response.status_code == 200

    def test_get_pnl_summary_fields(self, client: TestClient) -> None:
        response = client.get("/api/pnl/summary")
        data = response.json()
        assert "realized" in data
        assert "unrealized" in data
        assert "total" in data
        assert "daily" in data

    def test_get_pnl_summary_values(self, client: TestClient) -> None:
        response = client.get("/api/pnl/summary")
        data = response.json()
        assert data["realized"] == pytest.approx(12.34)
        assert data["unrealized"] == pytest.approx(5.67)
        assert data["total"] == pytest.approx(12.34 + 5.67)


# ---------------------------------------------------------------------------
# GET /api/pnl/history
# ---------------------------------------------------------------------------


class TestPnLHistoryEndpoint:
    def test_get_pnl_history_returns_200(self, client: TestClient) -> None:
        with _empty_pnl_patch():
            response = client.get("/api/pnl/history")
        assert response.status_code == 200

    def test_get_pnl_history_empty(self, client: TestClient) -> None:
        with _empty_pnl_patch():
            response = client.get("/api/pnl/history")
        data = response.json()
        assert data["points"] == []

    def test_get_pnl_history_timeframe_param(self, client: TestClient) -> None:
        with _empty_pnl_patch():
            response = client.get("/api/pnl/history?timeframe=7d")
        assert response.status_code == 200

    def test_get_pnl_history_with_data(self, client: TestClient) -> None:
        pnl_rows = [
            {
                "timestamp": "2026-03-22T10:00:00+00:00",
                "total_pnl": 18.01,
                "realized_pnl": 12.34,
            }
        ]
        with patch(
            "bot.persistence.repository.get_pnl_history",
            new=AsyncMock(return_value=pnl_rows),
        ):
            response = client.get("/api/pnl/history")
        data = response.json()
        assert len(data["points"]) == 1
        assert data["points"][0]["total"] == pytest.approx(18.01)


# ---------------------------------------------------------------------------
# GET /api/health
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_get_health_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_get_health_feeds_list(self, client: TestClient) -> None:
        response = client.get("/api/health")
        data = response.json()
        assert "feeds" in data
        assert "errors" in data
        assert len(data["feeds"]) == 2

    def test_get_health_feed_healthy_flag(self, client: TestClient) -> None:
        response = client.get("/api/health")
        feeds = response.json()["feeds"]
        assert all(f["healthy"] is True for f in feeds)


# ---------------------------------------------------------------------------
# GET /api/chart/price
# ---------------------------------------------------------------------------


class TestChartPriceEndpoint:
    def test_get_chart_price_returns_200(self, client: TestClient) -> None:
        with _empty_price_patch():
            response = client.get("/api/chart/price")
        assert response.status_code == 200

    def test_get_chart_price_empty_points(self, client: TestClient) -> None:
        with _empty_price_patch():
            response = client.get("/api/chart/price")
        data = response.json()
        assert data["points"] == []

    def test_get_chart_price_timeframe(self, client: TestClient) -> None:
        with _empty_price_patch():
            response = client.get("/api/chart/price?timeframe=12h")
        assert response.status_code == 200

    def test_get_chart_price_with_data(self, client: TestClient) -> None:
        price_rows = [
            {
                "timestamp": "2026-03-22T10:00:00+00:00",
                "fair_price": 155.50,
                "bid_prices": [155.42, 155.38],
                "ask_prices": [155.58, 155.62],
            }
        ]
        with patch(
            "bot.persistence.repository.get_price_history",
            new=AsyncMock(return_value=price_rows),
        ):
            response = client.get("/api/chart/price")
        data = response.json()
        assert len(data["points"]) == 1
        assert data["points"][0]["fair"] == pytest.approx(155.50)
        assert data["points"][0]["bid1"] == pytest.approx(155.42)
        assert data["points"][0]["ask1"] == pytest.approx(155.58)


# ---------------------------------------------------------------------------
# GET /api/chart/pnl
# ---------------------------------------------------------------------------


class TestChartPnLEndpoint:
    def test_get_chart_pnl_returns_200(self, client: TestClient) -> None:
        with _empty_pnl_patch():
            response = client.get("/api/chart/pnl")
        assert response.status_code == 200

    def test_get_chart_pnl_timeframe_30d(self, client: TestClient) -> None:
        with _empty_pnl_patch():
            response = client.get("/api/chart/pnl?timeframe=30d")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/chart/bot_vs_hodl
# ---------------------------------------------------------------------------


class TestChartBotVsHodlEndpoint:
    def test_get_bot_vs_hodl_returns_200(self, client: TestClient) -> None:
        with _empty_pnl_patch(), _empty_hodl_patch():
            response = client.get("/api/chart/bot_vs_hodl")
        assert response.status_code == 200

    def test_get_bot_vs_hodl_empty_when_no_benchmark(self, client: TestClient) -> None:
        with _empty_pnl_patch(), _empty_hodl_patch():
            response = client.get("/api/chart/bot_vs_hodl")
        data = response.json()
        assert data["points"] == []

    def test_get_bot_vs_hodl_timeframe(self, client: TestClient) -> None:
        with _empty_pnl_patch(), _empty_hodl_patch():
            response = client.get("/api/chart/bot_vs_hodl?timeframe=7d")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/report/daily
# ---------------------------------------------------------------------------


class TestReportDailyEndpoint:
    def test_get_daily_report_returns_200(self, client: TestClient) -> None:
        with _empty_daily_pnl_patch():
            response = client.get("/api/report/daily")
        assert response.status_code == 200

    def test_get_daily_report_empty_rows(self, client: TestClient) -> None:
        with _empty_daily_pnl_patch():
            response = client.get("/api/report/daily")
        data = response.json()
        assert data["rows"] == []
        assert "summary" in data

    def test_get_daily_report_summary_fields(self, client: TestClient) -> None:
        with _empty_daily_pnl_patch():
            response = client.get("/api/report/daily")
        summary = response.json()["summary"]
        assert "cumulative" in summary
        assert "avg_per_day" in summary
        assert "win_rate" in summary
        assert "sharpe_annualized" in summary
        assert "total_days" in summary

    def test_get_daily_report_days_param(self, client: TestClient) -> None:
        with _empty_daily_pnl_patch():
            response = client.get("/api/report/daily?days=7")
        assert response.status_code == 200

    def test_get_daily_report_with_rows(self, client: TestClient) -> None:
        rows_data = [
            {
                "day": 1,
                "date": "2026-03-21",
                "fills": 487,
                "realized_pnl": 207.0,
                "fee_rebates": 11.0,
                "net_pnl": 218.0,
            },
            {
                "day": 2,
                "date": "2026-03-22",
                "fills": 612,
                "realized_pnl": 287.0,
                "fee_rebates": 14.0,
                "net_pnl": 301.0,
            },
        ]
        with patch(
            "bot.persistence.repository.get_daily_pnl_summary",
            new=AsyncMock(return_value=rows_data),
        ):
            response = client.get("/api/report/daily?days=2")
        data = response.json()
        assert len(data["rows"]) == 2
        summary = data["summary"]
        assert summary["cumulative"] == pytest.approx(218.0 + 301.0)
        assert summary["total_days"] == 2
        assert summary["win_rate"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# GET /api/report/daily/export
# ---------------------------------------------------------------------------


class TestReportDailyExportEndpoint:
    def test_export_returns_200(self, client: TestClient) -> None:
        with _empty_daily_pnl_patch():
            response = client.get("/api/report/daily/export")
        assert response.status_code == 200

    def test_export_content_type_is_text(self, client: TestClient) -> None:
        with _empty_daily_pnl_patch():
            response = client.get("/api/report/daily/export")
        assert "text/plain" in response.headers["content-type"]

    def test_export_contains_header_text(self, client: TestClient) -> None:
        with _empty_daily_pnl_patch():
            response = client.get("/api/report/daily/export")
        assert "Wagyu.xyz MM Bot" in response.text
        assert "XMR1/USDC" in response.text

    def test_export_days_param(self, client: TestClient) -> None:
        with _empty_daily_pnl_patch():
            response = client.get("/api/report/daily/export?days=7")
        assert response.status_code == 200
        assert "Content-Disposition" in response.headers

    def test_export_with_rows_shows_table(self, client: TestClient) -> None:
        rows_data = [
            {
                "day": 1,
                "date": "2026-03-22",
                "fills": 100,
                "realized_pnl": 50.0,
                "fee_rebates": 5.0,
                "net_pnl": 55.0,
            }
        ]
        with patch(
            "bot.persistence.repository.get_daily_pnl_summary",
            new=AsyncMock(return_value=rows_data),
        ):
            response = client.get("/api/report/daily/export?days=1")
        assert "2026-03-22" in response.text
        assert "CUMULATIVE" in response.text
