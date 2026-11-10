import base64
from types import SimpleNamespace

import pytest
from httpx import AsyncClient


async def admin_session(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "mamari", "password": "passer123m"},
    )
    assert response.status_code == 200
    return response.json()["memberships"][0]["organization_id"]


@pytest.mark.asyncio
async def test_public_store_checkout_creates_order_and_reserves_stock(
    client: AsyncClient,
) -> None:
    organization_id = await admin_session(client)
    headers = {"X-Organization-ID": organization_id}
    product = await client.post(
        "/api/v1/sales/products",
        headers=headers,
        data={
            "name": "Miel de saison",
            "description": "Miel récolté localement.",
            "category": "Épicerie",
            "unit": "pot",
            "price_fcfa": "3500",
            "stock_quantity": "8",
            "is_published": "true",
        },
    )
    assert product.status_code == 201
    product_id = product.json()["id"]

    client.cookies.clear()
    catalog = await client.get("/api/v1/store/products")
    assert catalog.status_code == 200
    assert catalog.json()["organization_name"] == "Mamari"
    assert [item["id"] for item in catalog.json()["items"]] == [product_id]
    for protected_path in (
        "/api/v1/store/my-profile",
        "/api/v1/store/my-orders/summary",
        "/api/v1/store/my-notifications",
    ):
        assert (await client.get(protected_path)).status_code == 401

    registration = await client.post(
        "/api/v1/auth/customer/register",
        json={
            "full_name": "Aminata Diallo",
            "phone": "+221 77 123 45 67",
            "email": "aminata@example.com",
            "password": "secret123",
        },
    )
    assert registration.status_code == 201
    assert registration.json()["customer_account"] is True

    free_quote = await client.post(
        "/api/v1/store/delivery-quote",
        json={"latitude": 12.1348, "longitude": 15.0557},
    )
    assert free_quote.status_code == 200
    assert free_quote.json() == {
        "distance_km": 0.0,
        "fee_fcfa": 0,
        "zone_label": "À 5 km : gratuit",
        "quote_required": False,
    }
    standard_quote = await client.post(
        "/api/v1/store/delivery-quote",
        json={"latitude": 12.2248, "longitude": 15.0557},
    )
    assert standard_quote.status_code == 200
    assert standard_quote.json()["fee_fcfa"] == 1000
    extended_quote = await client.post(
        "/api/v1/store/delivery-quote",
        json={"latitude": 12.3148, "longitude": 15.0557},
    )
    assert extended_quote.status_code == 200
    assert extended_quote.json()["fee_fcfa"] == 2000
    outside_quote = await client.post(
        "/api/v1/store/delivery-quote",
        json={"latitude": 13.1348, "longitude": 15.0557},
    )
    assert outside_quote.status_code == 200
    assert outside_quote.json()["fee_fcfa"] is None
    assert outside_quote.json()["quote_required"] is True

    checkout = await client.post(
        "/api/v1/store/orders",
        json={
            "delivery_address": "Avenue Charles de Gaulle, N'Djamena, Tchad",
            "delivery_latitude": 12.1348,
            "delivery_longitude": 15.0557,
            "items": [
                {"product_id": product_id, "quantity": 2},
                {"product_id": product_id, "quantity": 1},
            ],
        },
    )
    assert checkout.status_code == 201
    order = checkout.json()
    assert order["customer_id"]
    assert order["customer_name"] == "Aminata Diallo"
    assert order["customer_phone"] == "+221 77 123 45 67"
    assert order["customer_email"] == "aminata@example.com"
    assert order["delivery_address"] == "Avenue Charles de Gaulle, N'Djamena, Tchad"
    assert order["delivery_distance_km"] == 0
    assert order["delivery_fee_fcfa"] == 0
    assert order["delivery_quote_required"] is False
    assert order["amount_fcfa"] == 10_500
    assert order["status"] == "pending"
    assert [event["status"] for event in order["status_history"]] == ["pending"]
    assert order["items"] == [
        {
            "product_id": product_id,
            "product_name": "Miel de saison",
            "unit": "pot",
            "quantity": 3,
            "unit_price_fcfa": 3500,
        }
    ]

    await admin_session(client)
    customer_page = await client.get("/api/v1/sales/customers", headers=headers)
    assert customer_page.status_code == 200
    assert customer_page.json()["total"] == 1
    assert customer_page.json()["items"][0]["id"] == order["customer_id"]
    customer_purchases = await client.get(
        f"/api/v1/sales/customers/{order['customer_id']}/orders",
        headers=headers,
    )
    assert customer_purchases.status_code == 200
    assert [item["id"] for item in customer_purchases.json()["items"]] == [order["id"]]
    customer_transactions = await client.get(
        f"/api/v1/sales/customers/{order['customer_id']}/transactions",
        headers=headers,
    )
    assert customer_transactions.status_code == 200
    assert customer_transactions.json() == []
    assert customer_page.json()["items"][0]["has_account"] is True
    sales_orders = await client.get("/api/v1/sales/orders", headers=headers)
    assert sales_orders.status_code == 200
    assert sales_orders.json()["items"][0]["id"] == order["id"]
    dashboard = await client.get("/api/v1/dashboard/overview", headers=headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["pending_order_count"] == 1
    assert dashboard.json()["revenue_fcfa"] == 0

    customer_login = await client.post(
        "/api/v1/auth/login",
        json={"username": "AMINATA@example.com", "password": "secret123"},
    )
    assert customer_login.status_code == 200
    customer_orders = await client.get("/api/v1/store/my-orders")
    assert customer_orders.status_code == 200
    assert [item["id"] for item in customer_orders.json()["items"]] == [order["id"]]
    second_checkout = await client.post(
        "/api/v1/store/orders",
        json={
            "delivery_address": "Avenue Charles de Gaulle, N'Djamena, Tchad",
            "delivery_latitude": 12.1348,
            "delivery_longitude": 15.0557,
            "items": [{"product_id": product_id, "quantity": 1}],
        },
    )
    assert second_checkout.status_code == 201
    first_order_page = await client.get("/api/v1/store/my-orders?page=1&page_size=1")
    second_order_page = await client.get("/api/v1/store/my-orders?page=2&page_size=1")
    assert first_order_page.status_code == second_order_page.status_code == 200
    assert first_order_page.json()["total"] == 2
    assert first_order_page.json()["items"][0]["id"] != second_order_page.json()["items"][0]["id"]
    searched_orders = await client.get(
        f"/api/v1/store/my-orders?search={order['reference']}"
    )
    assert searched_orders.status_code == 200
    assert searched_orders.json()["total"] == 1
    assert searched_orders.json()["items"][0]["id"] == order["id"]
    confirmed_orders = await client.get("/api/v1/store/my-orders?status=confirmed")
    assert confirmed_orders.status_code == 200
    assert confirmed_orders.json()["items"] == []
    summary = await client.get("/api/v1/store/my-orders/summary")
    assert summary.status_code == 200
    assert summary.json() == {
        "in_progress_count": 2,
        "delivered_count": 0,
        "total_spent_fcfa": 0,
    }
    customer_profile = await client.get("/api/v1/store/my-profile")
    assert customer_profile.status_code == 200
    assert customer_profile.json() == {
        "full_name": "Aminata Diallo",
        "email": "aminata@example.com",
        "phone": "+221 77 123 45 67",
        "address": "Avenue Charles de Gaulle, N'Djamena, Tchad",
    }
    updated_profile = await client.put(
        "/api/v1/store/my-profile",
        json={
            "full_name": "Aminata Cissé",
            "phone": "+221 76 555 12 34",
            "address": "Thiès, Sénégal",
        },
    )
    assert updated_profile.status_code == 200
    assert updated_profile.json()["full_name"] == "Aminata Cissé"
    assert updated_profile.json()["phone"] == "+221 76 555 12 34"
    assert updated_profile.json()["address"] == "Thiès, Sénégal"
    assert (await client.get("/api/v1/auth/me")).json()["full_name"] == "Aminata Cissé"
    initial_notifications = await client.get("/api/v1/store/my-notifications")
    assert initial_notifications.status_code == 200
    assert {item["status"] for item in initial_notifications.json()} == {"pending"}

    second_order_id = first_order_page.json()["items"][0]["id"]
    cancelled_by_customer = await client.post(
        f"/api/v1/store/my-orders/{second_order_id}/cancel"
    )
    assert cancelled_by_customer.status_code == 200
    assert cancelled_by_customer.json()["status"] == "cancelled"
    assert [event["status"] for event in cancelled_by_customer.json()["status_history"]] == [
        "pending",
        "cancelled",
    ]
    already_cancelled_order = await client.post(
        f"/api/v1/store/my-orders/{second_order_id}/cancel"
    )
    assert already_cancelled_order.status_code == 409

    other_registration = await client.post(
        "/api/v1/auth/customer/register",
        json={
            "full_name": "Autre client",
            "phone": "771111111",
            "email": "autre@example.com",
            "password": "secret123",
        },
    )
    assert other_registration.status_code == 201
    other_orders = await client.get("/api/v1/store/my-orders")
    assert other_orders.status_code == 200
    assert other_orders.json()["items"] == []
    assert (await client.get("/api/v1/store/my-profile")).status_code == 200
    other_customer_cannot_cancel_order = await client.post(
        f"/api/v1/store/my-orders/{order['id']}/cancel"
    )
    assert other_customer_cannot_cancel_order.status_code == 404

    await admin_session(client)
    for next_status in ("confirmed", "preparing", "delivered"):
        progressed_order = await client.patch(
            f"/api/v1/sales/orders/{order['id']}/status",
            headers=headers,
            json={"status": next_status},
        )
        assert progressed_order.status_code == 200
    await client.post(
        "/api/v1/auth/login",
        json={"username": "aminata@example.com", "password": "secret123"},
    )
    delivered_summary = await client.get("/api/v1/store/my-orders/summary")
    assert delivered_summary.status_code == 200
    assert delivered_summary.json() == {
        "in_progress_count": 0,
        "delivered_count": 1,
        "total_spent_fcfa": 10_500,
    }
    delivered_history = await client.get("/api/v1/store/my-orders?status=delivered")
    assert delivered_history.status_code == 200
    assert [
        event["status"]
        for event in delivered_history.json()["items"][0]["status_history"]
    ] == ["pending", "confirmed", "preparing", "delivered"]
    await admin_session(client)
    cancelled = await client.patch(
        f"/api/v1/sales/orders/{order['id']}/status",
        headers=headers,
        json={"status": "cancelled"},
    )
    assert cancelled.status_code == 200
    await client.post(
        "/api/v1/auth/login",
        json={"username": "aminata@example.com", "password": "secret123"},
    )
    updated_customer_orders = await client.get("/api/v1/store/my-orders?status=cancelled")
    assert updated_customer_orders.status_code == 200
    first_order_after_cancellation = next(
        item for item in updated_customer_orders.json()["items"] if item["id"] == order["id"]
    )
    assert first_order_after_cancellation["status"] == "cancelled"
    assert [
        event["status"]
        for event in first_order_after_cancellation["status_history"]
    ] == ["pending", "confirmed", "preparing", "delivered", "cancelled"]
    notifications_after_update = await client.get("/api/v1/store/my-notifications")
    assert notifications_after_update.status_code == 200
    assert any(item["status"] == "cancelled" for item in notifications_after_update.json())

    await admin_session(client)
    products = await client.get("/api/v1/sales/products", headers=headers)
    assert products.status_code == 200
    assert products.json()[0]["stock_quantity"] == 8
    reactivated = await client.patch(
        f"/api/v1/sales/orders/{order['id']}/status",
        headers=headers,
        json={"status": "confirmed"},
    )
    assert reactivated.status_code == 409


@pytest.mark.asyncio
async def test_public_store_rejects_unavailable_products_and_exposes_only_published(
    client: AsyncClient,
) -> None:
    organization_id = await admin_session(client)
    headers = {"X-Organization-ID": organization_id}
    product = await client.post(
        "/api/v1/sales/products",
        headers=headers,
        data={
            "name": "Produit privé",
            "price_fcfa": "1000",
            "stock_quantity": "2",
            "is_published": "false",
        },
    )
    assert product.status_code == 201
    product_id = product.json()["id"]

    client.cookies.clear()
    catalog = await client.get("/api/v1/store/products")
    assert catalog.status_code == 200
    assert catalog.json()["items"] == []
    unauthenticated_order = await client.post(
        "/api/v1/store/orders",
        json={
            "delivery_address": "N'Djamena, Tchad",
            "delivery_latitude": 12.1348,
            "delivery_longitude": 15.0557,
            "items": [{"product_id": product_id, "quantity": 1}],
        },
    )
    assert unauthenticated_order.status_code == 401
    registration = await client.post(
        "/api/v1/auth/customer/register",
        json={
            "full_name": "Client Mamari",
            "phone": "771234567",
            "email": "client-mamari@example.com",
            "password": "secret123",
        },
    )
    assert registration.status_code == 201
    unavailable_order = await client.post(
        "/api/v1/store/orders",
        json={
            "delivery_address": "N'Djamena, Tchad",
            "delivery_latitude": 12.1348,
            "delivery_longitude": 15.0557,
            "items": [{"product_id": product_id, "quantity": 1}],
        },
    )
    assert unavailable_order.status_code == 409


@pytest.mark.asyncio
async def test_product_photos_are_available_to_the_store_and_authorized_admins(
    client: AsyncClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mamari_api.modules.sales import router as sales_router

    monkeypatch.setattr(
        sales_router,
        "get_settings",
        lambda: SimpleNamespace(upload_directory=tmp_path, public_store_slug="mamari"),
    )
    organization_id = await admin_session(client)
    headers = {"X-Organization-ID": organization_id}
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/"
        "l7sAAAAASUVORK5CYII="
    )
    created = await client.post(
        "/api/v1/sales/products",
        headers=headers,
        data={
            "name": "Produit illustré",
            "price_fcfa": "1500",
            "stock_quantity": "5",
            "is_published": "true",
        },
        files={"photo": ("produit.png", png, "image/png")},
    )
    assert created.status_code == 201
    private_photo_url = created.json()["photo_url"]
    private_photo = await client.get(
        f"/api/v1{private_photo_url}",
        headers=headers,
    )
    assert private_photo.status_code == 200
    assert private_photo.content == png

    client.cookies.clear()
    public_catalog = await client.get("/api/v1/store/products")
    assert public_catalog.status_code == 200
    public_photo_url = public_catalog.json()["items"][0]["photo_url"]
    public_photo = await client.get(f"/api/v1{public_photo_url}")
    assert public_photo.status_code == 200
    assert public_photo.content == png

    unauthorized_private_photo = await client.get(f"/api/v1{private_photo_url}")
    assert unauthorized_private_photo.status_code == 401
