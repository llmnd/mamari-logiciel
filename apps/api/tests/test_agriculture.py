from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient


async def admin_organization(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "mamari", "password": "passer123m"},
    )
    assert response.status_code == 200
    return response.json()["memberships"][0]["organization_id"]


async def setup_farm(client: AsyncClient) -> tuple[str, dict, dict]:
    organization_id = await admin_organization(client)
    farm_response = await client.post(
        "/api/v1/agriculture/farms",
        headers={"X-Organization-ID": organization_id},
        data={"name": "Ferme des Collines", "location": "Thiès"},
    )
    assert farm_response.status_code == 201
    crops_response = await client.get(
        "/api/v1/agriculture/crops",
        headers={"X-Organization-ID": organization_id},
    )
    assert crops_response.status_code == 200
    crop = next((item for item in crops_response.json() if item["name"] == "Maïs"), None)
    if crop is None:
        crop_response = await client.post(
            "/api/v1/agriculture/crops",
            headers={"X-Organization-ID": organization_id},
            json={"name": "Maïs"},
        )
        assert crop_response.status_code == 201
        crop = crop_response.json()
    return organization_id, farm_response.json(), crop


async def create_parcel(
    client: AsyncClient,
    organization_id: str,
    farm_id: str,
    crop_id: str,
    name: str = "Parcelle Nord",
    area: float = 2.5,
) -> dict:
    response = await client.post(
        "/api/v1/agriculture/parcels",
        headers={"X-Organization-ID": organization_id},
        json={
            "farm_id": farm_id,
            "crop_id": crop_id,
            "name": name,
            "area_hectares": area,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_parcels_and_harvests_feed_real_dashboard_metrics(
    client: AsyncClient,
) -> None:
    organization_id, farm, crop = await setup_farm(client)
    headers = {"X-Organization-ID": organization_id}
    parcel = await create_parcel(client, organization_id, farm["id"], crop["id"])
    harvest_response = await client.post(
        "/api/v1/agriculture/harvests",
        headers=headers,
        json={
            "parcel_id": parcel["id"],
            "harvest_date": date.today().isoformat(),
            "quantity_kg": 1250.75,
            "notes": "Récolte principale",
        },
    )

    assert harvest_response.status_code == 201
    harvest = harvest_response.json()
    assert harvest["parcel_name"] == "Parcelle Nord"
    assert float(harvest["quantity_kg"]) == 1250.75

    parcel_list = await client.get("/api/v1/agriculture/parcels", headers=headers)
    harvest_list = await client.get("/api/v1/agriculture/harvests", headers=headers)
    assert parcel_list.status_code == 200
    assert parcel_list.json()["total"] == 1
    assert harvest_list.status_code == 200
    assert harvest_list.json()["items"][0]["id"] == harvest["id"]
    stock_items = await client.get(
        "/api/v1/stocks/items?source=agriculture",
        headers=headers,
    )
    assert stock_items.status_code == 200
    assert stock_items.json()[0]["name"] == "Maïs"
    assert stock_items.json()[0]["balance"] == "1250.750"

    overview = await client.get(
        f"/api/v1/dashboard/overview?year={date.today().year}",
        headers=headers,
    )
    assert overview.status_code == 200
    body = overview.json()
    assert body["production_kg"] == 1250.75
    assert body["harvest_count"] == 1
    assert body["parcel_count"] == 1
    assert len(body["monthly_production_kg"]) == 12
    assert body["monthly_production_kg"][date.today().month - 1]["quantity_kg"] == 1250.75
    assert body["recent_harvests"][0]["id"] == harvest["id"]


@pytest.mark.asyncio
async def test_operator_campaign_responses_hide_financial_details(client: AsyncClient) -> None:
    organization_id, farm, crop = await setup_farm(client)
    headers = {"X-Organization-ID": organization_id}
    parcel = await create_parcel(client, organization_id, farm["id"], crop["id"])
    created_campaign = await client.post(
        "/api/v1/agriculture/campaigns",
        headers=headers,
        json={
            "parcel_id": parcel["id"],
            "crop_id": crop["id"],
            "name": "Campagne confidentielle",
            "season": "2026-Hivernage",
            "start_date": "2026-06-01",
            "expected_harvest_date": "2026-10-30",
            "area_hectares": 2,
            "expected_yield_kg_per_hectare": 1000,
            "expected_price_fcfa_per_kg": 1000,
            "estimated_input_cost_fcfa": 500000,
            "estimated_other_cost_fcfa": 100000,
        },
    )
    assert created_campaign.status_code == 201

    created_operator = await client.post(
        "/api/v1/organizations/users",
        headers=headers,
        json={
            "username": "agri-operator",
            "full_name": "Employé agricole",
            "password": "secret6",
            "role": "operator",
        },
    )
    assert created_operator.status_code == 201
    client.cookies.clear()
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "agri-operator", "password": "secret6"},
    )
    assert login.status_code == 200
    operator_campaign_payload = {
        "parcel_id": parcel["id"],
        "crop_id": crop["id"],
        "name": "Campagne opérateur",
        "season": "2026-Hivernage",
        "start_date": "2026-06-01",
        "expected_harvest_date": "2026-10-30",
        "area_hectares": 2,
        "expected_yield_kg_per_hectare": 1000,
        "expected_price_fcfa_per_kg": 1000,
        "estimated_input_cost_fcfa": 0,
        "estimated_other_cost_fcfa": 0,
    }
    forbidden_campaign = await client.post(
        "/api/v1/agriculture/campaigns",
        headers=headers,
        json=operator_campaign_payload,
    )
    assert forbidden_campaign.status_code == 403
    operational_campaign = await client.post(
        "/api/v1/agriculture/campaigns",
        headers=headers,
        json={
            **operator_campaign_payload,
            "expected_price_fcfa_per_kg": 0,
        },
    )
    assert operational_campaign.status_code == 201, operational_campaign.text
    assert operational_campaign.json()["expected_revenue_fcfa"] is None

    campaigns = await client.get("/api/v1/agriculture/campaigns", headers=headers)
    assert campaigns.status_code == 200
    returned_campaigns = campaigns.json()["items"]
    manager_campaign = next(
        item for item in returned_campaigns if item["id"] == created_campaign.json()["id"]
    )
    assert float(manager_campaign["expected_production_kg"]) == 2000
    assert manager_campaign["expected_revenue_fcfa"] is None
    assert manager_campaign["estimated_total_cost_fcfa"] is None
    assert manager_campaign["estimated_margin_fcfa"] is None
    assert manager_campaign["actual_revenue_fcfa"] is None
    assert manager_campaign["actual_expenses_fcfa"] is None


@pytest.mark.asyncio
async def test_campaign_planning_simulation_start_close_and_sale(
    client: AsyncClient,
) -> None:
    organization_id, farm, crop = await setup_farm(client)
    headers = {"X-Organization-ID": organization_id}
    parcel = await create_parcel(client, organization_id, farm["id"], crop["id"])
    other_crop_response = await client.post(
        "/api/v1/agriculture/crops",
        headers=headers,
        json={"name": "Sésame"},
    )
    assert other_crop_response.status_code == 201
    campaign_payload = {
        "parcel_id": parcel["id"],
        "crop_id": crop["id"],
        "name": "Maïs saison des pluies",
        "season": "2026-Hivernage",
        "start_date": "2026-06-01",
        "expected_harvest_date": "2026-10-30",
        "area_hectares": 2,
        "expected_yield_kg_per_hectare": 1000,
        "expected_price_fcfa_per_kg": 1000,
        "estimated_input_cost_fcfa": 500000,
        "estimated_other_cost_fcfa": 100000,
    }
    mismatch = await client.post(
        "/api/v1/agriculture/campaigns",
        headers=headers,
        json={**campaign_payload, "crop_id": other_crop_response.json()["id"]},
    )
    assert mismatch.status_code == 422
    campaign_response = await client.post(
        "/api/v1/agriculture/campaigns",
        headers=headers,
        json=campaign_payload,
    )
    assert campaign_response.status_code == 201, campaign_response.text
    campaign = campaign_response.json()
    assert campaign["status"] == "planned"
    assert Decimal(campaign["expected_production_kg"]) == Decimal("2000")
    assert campaign["expected_revenue_fcfa"] == 2_000_000
    assert campaign["estimated_margin_fcfa"] == 1_400_000

    simulation = await client.post(
        f"/api/v1/agriculture/campaigns/{campaign['id']}/simulate",
        headers=headers,
    )
    assert simulation.status_code == 200, simulation.text
    assert Decimal(simulation.json()["margin_rate_percent"]) == Decimal("70")
    assert simulation.json()["campaign"]["status"] == "simulated"

    started = await client.patch(
        f"/api/v1/agriculture/campaigns/{campaign['id']}/start",
        headers=headers,
    )
    assert started.status_code == 200
    assert started.json()["status"] == "active"
    harvest = await client.post(
        "/api/v1/agriculture/harvests",
        headers=headers,
        json={
            "parcel_id": parcel["id"],
            "campaign_id": campaign["id"],
            "quantity_kg": 1800,
        },
    )
    assert harvest.status_code == 201
    assert harvest.json()["campaign_name"] == "Maïs saison des pluies"

    expense = await client.post(
        "/api/v1/agriculture/finance/transactions",
        headers=headers,
        json={
            "farm_id": farm["id"],
            "campaign_id": campaign["id"],
            "transaction_type": "expense",
            "category": "input",
            "label": "Engrais NPK",
            "amount_fcfa": 250000,
            "quantity": 50,
            "unit": "kg",
        },
    )
    assert expense.status_code == 201, expense.text

    closed = await client.patch(
        f"/api/v1/agriculture/campaigns/{campaign['id']}/close",
        headers=headers,
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    customer = await client.post(
        "/api/v1/sales/customers",
        headers=headers,
        json={
            "name": "Marché Central",
            "phone": "771234567",
            "company_name": "Marché Central",
            "city": "Dakar",
        },
    )
    assert customer.status_code == 201
    sale = await client.post(
        f"/api/v1/agriculture/campaigns/{campaign['id']}/sales",
        headers=headers,
        json={
            "customer_id": customer.json()["id"],
            "quantity_kg": 900,
            "unit_price_fcfa_per_kg": 1200,
        },
    )
    assert sale.status_code == 201, sale.text
    assert sale.json()["amount_fcfa"] == 1_080_000
    assert sale.json()["customer_id"] == customer.json()["id"]
    customer_transactions = await client.get(
        f"/api/v1/sales/customers/{customer.json()['id']}/transactions",
        headers=headers,
    )
    assert customer_transactions.status_code == 200, customer_transactions.text
    assert customer_transactions.json()[0]["id"] == sale.json()["id"]
    assert customer_transactions.json()[0]["amount_fcfa"] == 1_080_000

    summary = await client.get(
        f"/api/v1/agriculture/finance/summary?year={date.today().year}",
        headers=headers,
    )
    assert summary.status_code == 200
    assert summary.json()["income_fcfa"] == 1_080_000
    assert summary.json()["expenses_fcfa"] == 250_000
    assert summary.json()["input_expenses_fcfa"] == 250_000
    assert summary.json()["balance_fcfa"] == 830_000

    campaign_list = await client.get(
        "/api/v1/agriculture/campaigns?status=closed",
        headers=headers,
    )
    campaign_result = campaign_list.json()["items"][0]
    assert Decimal(campaign_result["actual_production_kg"]) == Decimal("1800")
    assert campaign_result["actual_revenue_fcfa"] == 1_080_000
    assert campaign_result["actual_expenses_fcfa"] == 250_000

    too_much = await client.post(
        f"/api/v1/agriculture/campaigns/{campaign['id']}/sales",
        headers=headers,
        json={"customer_name": "Client B", "quantity_kg": 1000, "unit_price_fcfa_per_kg": 1000},
    )
    assert too_much.status_code == 422
    premature_archive = await client.patch(
        f"/api/v1/agriculture/campaigns/{campaign['id']}/archive",
        headers=headers,
    )
    assert premature_archive.status_code == 409
    remaining_sale = await client.post(
        f"/api/v1/agriculture/campaigns/{campaign['id']}/sales",
        headers=headers,
        json={
            "customer_name": "Marché Central",
            "quantity_kg": 900,
            "unit_price_fcfa_per_kg": 1200,
        },
    )
    assert remaining_sale.status_code == 201
    archived = await client.patch(
        f"/api/v1/agriculture/campaigns/{campaign['id']}/archive",
        headers=headers,
    )
    assert archived.status_code == 200
    active_campaigns = await client.get(
        "/api/v1/agriculture/campaigns?archived=false",
        headers=headers,
    )
    archived_campaigns = await client.get(
        "/api/v1/agriculture/campaigns?archived=true",
        headers=headers,
    )
    assert active_campaigns.json()["total"] == 0
    assert archived_campaigns.json()["total"] == 1


@pytest.mark.asyncio
async def test_farm_photo_is_validated_private_and_archiveable(
    client: AsyncClient,
) -> None:
    organization_id = await admin_organization(client)
    headers = {"X-Organization-ID": organization_id}
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
    created = await client.post(
        "/api/v1/agriculture/farms",
        headers=headers,
        data={"name": "Ferme photo"},
        files={"photo": ("farm.png", png, "image/png")},
    )
    assert created.status_code == 201, created.text
    farm = created.json()
    assert farm["photo_url"] == f"/agriculture/farms/{farm['id']}/photo"
    photo = await client.get(f"/api/v1{farm['photo_url']}", headers=headers)
    assert photo.status_code == 200
    assert photo.content == png

    replacement_png = b"\x89PNG\r\n\x1a\n" + b"\x01" * 24
    replaced = await client.patch(
        f"/api/v1/agriculture/farms/{farm['id']}",
        headers=headers,
        data={"name": "Ferme photo modifiée", "location": "Thiès"},
        files={"photo": ("new-farm.png", replacement_png, "image/png")},
    )
    assert replaced.status_code == 200, replaced.text
    updated_photo = await client.get(f"/api/v1{replaced.json()['photo_url']}", headers=headers)
    assert updated_photo.status_code == 200
    assert updated_photo.content == replacement_png

    removed = await client.patch(
        f"/api/v1/agriculture/farms/{farm['id']}",
        headers=headers,
        data={
            "name": "Ferme photo modifiée",
            "location": "Thiès",
            "remove_photo": "true",
        },
    )
    assert removed.status_code == 200
    assert removed.json()["photo_url"] is None

    bad_photo = await client.post(
        "/api/v1/agriculture/farms",
        headers=headers,
        data={"name": "Format refusé"},
        files={"photo": ("farm.svg", b"<svg/>", "image/svg+xml")},
    )
    assert bad_photo.status_code == 415

    archived = await client.patch(
        f"/api/v1/agriculture/farms/{farm['id']}/archive",
        headers=headers,
    )
    assert archived.status_code == 200
    assert archived.json()["is_active"] is False
    active_farms = await client.get("/api/v1/agriculture/farms?active=true", headers=headers)
    archived_farms = await client.get("/api/v1/agriculture/farms?active=false", headers=headers)
    assert active_farms.json()["total"] == 0
    assert archived_farms.json()["total"] == 1
    restored = await client.patch(
        f"/api/v1/agriculture/farms/{farm['id']}/restore",
        headers=headers,
    )
    assert restored.status_code == 200
    assert restored.json()["is_active"] is True


@pytest.mark.asyncio
async def test_agriculture_validates_inputs_and_organization_access(
    client: AsyncClient,
) -> None:
    organization_id, farm, crop = await setup_farm(client)
    headers = {"X-Organization-ID": organization_id}

    invalid_parcel = await client.post(
        "/api/v1/agriculture/parcels",
        headers=headers,
        json={
            "farm_id": farm["id"],
            "crop_id": crop["id"],
            "name": "Parcelle",
            "area_hectares": 0,
        },
    )
    assert invalid_parcel.status_code == 422

    missing_parcel = await client.post(
        "/api/v1/agriculture/harvests",
        headers=headers,
        json={"parcel_id": str(uuid4()), "quantity_kg": 50},
    )
    assert missing_parcel.status_code == 404

    inaccessible_organization = await client.get(
        "/api/v1/agriculture/parcels",
        headers={"X-Organization-ID": str(uuid4())},
    )
    assert inaccessible_organization.status_code == 403


@pytest.mark.asyncio
async def test_duplicate_parcel_name_and_reader_permissions(
    client: AsyncClient,
) -> None:
    organization_id, farm, crop = await setup_farm(client)
    headers = {"X-Organization-ID": organization_id}
    parcel_data = {
        "farm_id": farm["id"],
        "crop_id": crop["id"],
        "name": "Parcelle Est",
        "area_hectares": 1.25,
    }
    created = await client.post(
        "/api/v1/agriculture/parcels",
        headers=headers,
        json=parcel_data,
    )
    assert created.status_code == 201
    duplicate = await client.post("/api/v1/agriculture/parcels", headers=headers, json=parcel_data)
    assert duplicate.status_code == 409

    user = await client.post(
        "/api/v1/organizations/users",
        headers=headers,
        json={
            "username": "lecteur-agri",
            "full_name": "Lecteur Agriculture",
            "password": "secret6",
            "role": "reader",
        },
    )
    assert user.status_code == 201
    client.cookies.clear()
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "lecteur-agri", "password": "secret6"},
    )
    assert login.status_code == 200
    assert (await client.get("/api/v1/agriculture/parcels", headers=headers)).status_code == 200
    forbidden = await client.post(
        "/api/v1/agriculture/parcels",
        headers=headers,
        json={
            **parcel_data,
            "name": "Parcelle Sud",
        },
    )
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_farms_and_parcels_can_be_edited_archived_and_restored(
    client: AsyncClient,
) -> None:
    organization_id, farm, crop = await setup_farm(client)
    headers = {"X-Organization-ID": organization_id}
    parcel = await create_parcel(client, organization_id, farm["id"], crop["id"])
    planned_campaign = await client.post(
        "/api/v1/agriculture/campaigns",
        headers=headers,
        json={
            "parcel_id": parcel["id"],
            "crop_id": crop["id"],
            "name": "Campagne de contrôle",
            "season": "Saison de contrôle",
            "start_date": date.today().isoformat(),
            "expected_harvest_date": (date.today() + timedelta(days=180)).isoformat(),
            "area_hectares": 2,
            "expected_yield_kg_per_hectare": 1000,
            "expected_price_fcfa_per_kg": 500,
            "estimated_input_cost_fcfa": 100000,
            "estimated_other_cost_fcfa": 50000,
        },
    )
    assert planned_campaign.status_code == 201, planned_campaign.text

    updated_farm = await client.patch(
        f"/api/v1/agriculture/farms/{farm['id']}",
        headers=headers,
        data={"name": "Ferme des Collines rénovée", "location": "Thiès centre"},
    )
    assert updated_farm.status_code == 200, updated_farm.text
    assert updated_farm.json()["name"] == "Ferme des Collines rénovée"
    assert updated_farm.json()["location"] == "Thiès centre"

    updated_parcel = await client.patch(
        f"/api/v1/agriculture/parcels/{parcel['id']}",
        headers=headers,
        json={"name": "Parcelle Sud", "area_hectares": 3},
    )
    assert updated_parcel.status_code == 200, updated_parcel.text
    assert updated_parcel.json()["name"] == "Parcelle Sud"
    assert Decimal(updated_parcel.json()["area_hectares"]) == Decimal("3.00")

    too_small = await client.patch(
        f"/api/v1/agriculture/parcels/{parcel['id']}",
        headers=headers,
        json={"name": "Parcelle Sud", "area_hectares": 0.5},
    )
    assert too_small.status_code == 409

    archived_parcel = await client.patch(
        f"/api/v1/agriculture/parcels/{parcel['id']}/archive",
        headers=headers,
    )
    assert archived_parcel.status_code == 200
    assert archived_parcel.json()["is_active"] is False
    restored_parcel = await client.patch(
        f"/api/v1/agriculture/parcels/{parcel['id']}/restore",
        headers=headers,
    )
    assert restored_parcel.status_code == 200
    assert restored_parcel.json()["is_active"] is True

    archived_farm = await client.patch(
        f"/api/v1/agriculture/farms/{farm['id']}/archive",
        headers=headers,
    )
    assert archived_farm.status_code == 200
    blocked_restore = await client.patch(
        f"/api/v1/agriculture/parcels/{parcel['id']}/restore",
        headers=headers,
    )
    assert blocked_restore.status_code == 409
    restored_farm = await client.patch(
        f"/api/v1/agriculture/farms/{farm['id']}/restore",
        headers=headers,
    )
    assert restored_farm.status_code == 200
    restored_parcel = await client.patch(
        f"/api/v1/agriculture/parcels/{parcel['id']}/restore",
        headers=headers,
    )
    assert restored_parcel.status_code == 200


@pytest.mark.asyncio
async def test_parcel_photos_are_private_validated_replaceable_and_removable(
    client: AsyncClient,
) -> None:
    organization_id, farm, crop = await setup_farm(client)
    headers = {"X-Organization-ID": organization_id}
    parcel = await create_parcel(client, organization_id, farm["id"], crop["id"])
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
    photo_path = f"/api/v1/agriculture/parcels/{parcel['id']}/photo"

    uploaded = await client.post(
        photo_path,
        headers=headers,
        files={"photo": ("parcel.png", png, "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["photo_url"] == f"/agriculture/parcels/{parcel['id']}/photo"
    photo = await client.get(photo_path, headers=headers)
    assert photo.status_code == 200
    assert photo.content == png

    replacement_png = b"\x89PNG\r\n\x1a\n" + b"\x02" * 24
    replaced = await client.post(
        photo_path,
        headers=headers,
        files={"photo": ("parcel-new.png", replacement_png, "image/png")},
    )
    assert replaced.status_code == 200, replaced.text
    replaced_photo = await client.get(photo_path, headers=headers)
    assert replaced_photo.status_code == 200
    assert replaced_photo.content == replacement_png

    invalid_upload = await client.post(
        photo_path,
        headers=headers,
        files={"photo": ("parcel.svg", b"<svg/>", "image/svg+xml")},
    )
    assert invalid_upload.status_code == 415
    retained_photo = await client.get(photo_path, headers=headers)
    assert retained_photo.status_code == 200
    assert retained_photo.content == replacement_png

    client.cookies.clear()
    private_photo = await client.get(photo_path, headers=headers)
    assert private_photo.status_code == 401
    organization_id = await admin_organization(client)
    headers = {"X-Organization-ID": organization_id}

    removed = await client.delete(photo_path, headers=headers)
    assert removed.status_code == 200, removed.text
    assert removed.json()["photo_url"] is None
    missing_photo = await client.get(photo_path, headers=headers)
    assert missing_photo.status_code == 404
