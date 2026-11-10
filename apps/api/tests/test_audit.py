from datetime import date, timedelta

import pytest
from httpx import AsyncClient


async def login(client: AsyncClient, username: str = "mamari") -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "passer123m"},
    )
    assert response.status_code == 200
    return response.json()["memberships"][0]["organization_id"]


@pytest.mark.asyncio
async def test_operator_stock_adjustment_requires_and_records_approval(
    client: AsyncClient,
) -> None:
    organization_id = await login(client)
    headers = {"X-Organization-ID": organization_id}
    stock = await client.post(
        "/api/v1/stocks/items",
        headers=headers,
        json={
            "source": "other",
            "name": "Riz",
            "unit": "kg",
            "opening_quantity": 10,
            "minimum_quantity": 3,
        },
    )
    assert stock.status_code == 201, stock.text
    assert float(stock.json()["minimum_quantity"]) == 3

    operator = await client.post(
        "/api/v1/organizations/users",
        headers=headers,
        json={
            "username": "approval-operator",
            "full_name": "Awa Diop",
            "password": "passer123m",
            "role": "operator",
        },
    )
    assert operator.status_code == 201, operator.text
    client.cookies.clear()
    assert (await login(client, "approval-operator")) == organization_id

    direct_adjustment = await client.post(
        f"/api/v1/stocks/items/{stock.json()['id']}/movements",
        headers=headers,
        json={
            "movement_type": "adjustment",
            "direction": "out",
            "quantity": 2,
            "movement_date": "2026-01-15",
            "note": "Test d’autorisation.",
        },
    )
    assert direct_adjustment.status_code == 403

    requested = await client.post(
        "/api/v1/audit/requests",
        headers=headers,
        json={
            "action": "stock_adjustment",
            "resource_id": stock.json()["id"],
            "reason": "Correction après inventaire.",
            "quantity": 2,
            "direction": "out",
            "movement_date": "2026-01-15",
        },
    )
    assert requested.status_code == 201, requested.text
    assert requested.json()["status"] == "pending"

    client.cookies.clear()
    await login(client)
    approved = await client.patch(
        f"/api/v1/audit/requests/{requested.json()['id']}",
        headers=headers,
        json={"decision": "approved"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    movements = await client.get(
        f"/api/v1/stocks/movements?item_id={stock.json()['id']}",
        headers=headers,
    )
    assert movements.status_code == 200
    assert movements.json()["total"] == 2
    events = await client.get("/api/v1/audit/events?module=stocks", headers=headers)
    assert events.status_code == 200
    assert any(event["action"] == "approval_approved" for event in events.json()["items"])


@pytest.mark.asyncio
async def test_reports_compare_equal_periods_and_hide_financials_for_operator(
    client: AsyncClient,
) -> None:
    organization_id = await login(client)
    headers = {"X-Organization-ID": organization_id}
    item = await client.post(
        "/api/v1/stocks/items",
        headers=headers,
        json={
            "source": "other",
            "name": "Maïs",
            "unit": "kg",
            "opening_quantity": 5,
            "minimum_quantity": 2,
        },
    )
    assert item.status_code == 201

    operator = await client.post(
        "/api/v1/organizations/users",
        headers=headers,
        json={
            "username": "report-operator",
            "full_name": "Moussa Ba",
            "password": "passer123m",
            "role": "operator",
        },
    )
    assert operator.status_code == 201, operator.text
    client.cookies.clear()
    await login(client, "report-operator")
    today = date.today()
    report = await client.get(
        "/api/v1/dashboard/reports/summary"
        f"?start_date={today.isoformat()}&end_date={today.isoformat()}",
        headers=headers,
    )
    assert report.status_code == 200, report.text
    result = report.json()
    assert result["financial_access"] is False
    assert result["current"]["stock_movement_count"] == 1
    assert result["current"]["stock_quantities"] == [
        {"unit": "kg", "quantity_in": 5.0, "quantity_out": 0.0}
    ]
    assert result["current"]["revenue_fcfa"] is None
    previous_day = (today - timedelta(days=1)).isoformat()
    assert result["previous"]["start_date"] == previous_day
    assert result["previous"]["end_date"] == previous_day


@pytest.mark.asyncio
async def test_pending_order_cancellation_is_executed_when_approved(
    client: AsyncClient,
) -> None:
    organization_id = await login(client)
    headers = {"X-Organization-ID": organization_id}
    product = await client.post(
        "/api/v1/sales/products",
        headers=headers,
        data={
            "name": "Huile locale",
            "unit": "bouteille",
            "price_fcfa": "2500",
            "stock_quantity": "3",
            "is_published": "true",
        },
    )
    assert product.status_code == 201, product.text
    operator = await client.post(
        "/api/v1/organizations/users",
        headers=headers,
        json={
            "username": "cancel-operator",
            "full_name": "Aminata Fall",
            "password": "passer123m",
            "role": "operator",
        },
    )
    assert operator.status_code == 201, operator.text

    client.cookies.clear()
    customer = await client.post(
        "/api/v1/auth/customer/register",
        json={
            "full_name": "Fatou Ndiaye",
            "phone": "+221 77 111 22 33",
            "email": "fatou@example.com",
            "password": "customer123",
        },
    )
    assert customer.status_code == 201, customer.text
    order = await client.post(
        "/api/v1/store/orders",
        json={
            "delivery_address": "N'Djamena, Tchad",
            "delivery_latitude": 12.1348,
            "delivery_longitude": 15.0557,
            "items": [{"product_id": product.json()["id"], "quantity": 1}],
        },
    )
    assert order.status_code == 201, order.text
    assert order.json()["status"] == "pending"

    client.cookies.clear()
    assert (await login(client, "cancel-operator")) == organization_id
    request = await client.post(
        "/api/v1/audit/requests",
        headers=headers,
        json={
            "action": "order_cancellation",
            "resource_id": order.json()["id"],
            "reason": "Le client a demandé l’annulation.",
        },
    )
    assert request.status_code == 201, request.text

    client.cookies.clear()
    await login(client)
    reviewed = await client.patch(
        f"/api/v1/audit/requests/{request.json()['id']}",
        headers=headers,
        json={"decision": "approved"},
    )
    assert reviewed.status_code == 200, reviewed.text
    orders = await client.get("/api/v1/sales/orders?status=cancelled", headers=headers)
    assert orders.status_code == 200
    assert orders.json()["items"][0]["id"] == order.json()["id"]
    stock_items = await client.get("/api/v1/stocks/items", headers=headers)
    product_stock = next(
        item for item in stock_items.json() if item["product_id"] == product.json()["id"]
    )
    assert float(product_stock["balance"]) == 3
