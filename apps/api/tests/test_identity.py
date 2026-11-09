from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_default_admin_is_created_on_first_login(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "MAMARI", "password": "passer123m"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "mamari"
    assert body["full_name"] == "Administrateur Mamari"
    assert body["memberships"][0]["role"] == "owner"
    assert body["memberships"][0]["organization_name"] == "Mamari"
    assert "passer123m" not in response.text
    assert "HttpOnly" in response.headers["set-cookie"]

    organization_id = body["memberships"][0]["organization_id"]
    current = await client.get(
        "/api/v1/organizations/current",
        headers={"X-Organization-ID": organization_id},
    )
    assert current.status_code == 200
    assert current.json()["slug"] == "mamari"
    crops = await client.get(
        "/api/v1/agriculture/crops",
        headers={"X-Organization-ID": organization_id},
    )
    assert crops.status_code == 200
    assert "Maïs" in {crop["name"] for crop in crops.json()}


@pytest.mark.asyncio
async def test_login_and_logout_manage_the_session(client: AsyncClient) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "mamari", "password": "passer123m"},
    )
    assert login.status_code == 200
    assert (await client.get("/api/v1/auth/me")).status_code == 200

    logout = await client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    client.cookies.clear()
    assert (await client.get("/api/v1/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_public_auth_status_is_safe_for_anonymous_visitors(
    client: AsyncClient,
) -> None:
    anonymous = await client.get("/api/v1/auth/public-status")
    assert anonymous.status_code == 200
    assert anonymous.json() == {"customer_account": False}

    client.cookies.set("access_token", "invalid-token")
    invalid_session = await client.get("/api/v1/auth/public-status")
    assert invalid_session.status_code == 200
    assert invalid_session.json() == {"customer_account": False}
    client.cookies.clear()

    registration = await client.post(
        "/api/v1/auth/customer/register",
        json={
            "full_name": "Client public",
            "phone": "771234567",
            "email": "public-status-client@example.com",
            "password": "clientpass",
        },
    )
    assert registration.status_code == 201
    authenticated_customer = await client.get("/api/v1/auth/public-status")
    assert authenticated_customer.status_code == 200
    assert authenticated_customer.json() == {"customer_account": True}


@pytest.mark.asyncio
async def test_admin_employee_and_customer_can_change_their_password(
    client: AsyncClient,
) -> None:
    unauthenticated_change = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "currentpass", "new_password": "newpass123"},
    )
    assert unauthenticated_change.status_code == 401
    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": "mamari", "password": "passer123m"},
    )
    assert admin_login.status_code == 200
    organization_id = admin_login.json()["memberships"][0]["organization_id"]
    wrong_current_password = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "incorrect", "new_password": "newpass123"},
    )
    assert wrong_current_password.status_code == 400

    changed_admin_password = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "passer123m", "new_password": "adminpass123"},
    )
    assert changed_admin_password.status_code == 200
    client.cookies.clear()
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"username": "mamari", "password": "passer123m"},
        )
    ).status_code == 401
    client.cookies.clear()
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"username": "mamari", "password": "adminpass123"},
        )
    ).status_code == 200

    employee = await client.post(
        "/api/v1/organizations/users",
        headers={"X-Organization-ID": organization_id},
        json={
            "username": "password-member",
            "full_name": "Membre",
            "password": "memberpass",
            "role": "operator",
        },
    )
    assert employee.status_code == 201
    client.cookies.clear()
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"username": "password-member", "password": "memberpass"},
        )
    ).status_code == 200
    changed_employee_password = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "memberpass", "new_password": "updatedpass"},
    )
    assert changed_employee_password.status_code == 200
    client.cookies.clear()
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"username": "password-member", "password": "memberpass"},
        )
    ).status_code == 401
    client.cookies.clear()
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"username": "password-member", "password": "updatedpass"},
        )
    ).status_code == 200

    client.cookies.clear()
    registration = await client.post(
        "/api/v1/auth/customer/register",
        json={
            "full_name": "Client Mamari",
            "phone": "771234567",
            "email": "password-client@example.com",
            "password": "clientpass",
        },
    )
    assert registration.status_code == 201
    changed_customer_password = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "clientpass", "new_password": "customerpass"},
    )
    assert changed_customer_password.status_code == 200
    client.cookies.clear()
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={
                "username": "password-client@example.com",
                "password": "clientpass",
            },
        )
    ).status_code == 401
    client.cookies.clear()
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"username": "password-client@example.com", "password": "customerpass"},
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_bad_credentials_and_public_registration_are_rejected(
    client: AsyncClient,
) -> None:
    invalid_password = "wrongpass"
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "mamari", "password": invalid_password},
    )
    assert login.status_code == 401
    assert invalid_password not in login.text
    assert (await client.post("/api/v1/auth/register", json={})).status_code == 404


@pytest.mark.asyncio
async def test_organization_membership_is_required(client: AsyncClient) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "mamari", "password": "passer123m"},
    )
    assert login.status_code == 200
    response = await client.get(
        "/api/v1/organizations/current",
        headers={"X-Organization-ID": str(uuid4())},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_create_a_user_for_mamari(client: AsyncClient) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "mamari", "password": "passer123m"},
    )
    organization_id = login.json()["memberships"][0]["organization_id"]

    created = await client.post(
        "/api/v1/organizations/users",
        headers={"X-Organization-ID": organization_id},
        json={
            "username": "equipe",
            "full_name": "Membre Mamari",
            "password": "secret6",
            "role": "operator",
            "phone": "+221 77 123 45 67",
        },
    )
    assert created.status_code == 201
    assert created.json()["username"] == "equipe"
    assert created.json()["role"] == "operator"
    assert created.json()["phone"] == "+221 77 123 45 67"
    members = await client.get(
        "/api/v1/organizations/users",
        headers={"X-Organization-ID": organization_id},
    )
    assert members.status_code == 200
    member = next(user for user in members.json() if user["id"] == created.json()["id"])
    assert member["phone"] == "+221 77 123 45 67"
    updated = await client.patch(
        f"/api/v1/organizations/users/{created.json()['id']}",
        headers={"X-Organization-ID": organization_id},
        json={"role": "manager", "phone": "+221 76 555 12 34"},
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "manager"
    assert updated.json()["phone"] == "+221 76 555 12 34"

    client.cookies.clear()
    member_login = await client.post(
        "/api/v1/auth/login",
        json={"username": "equipe", "password": "secret6"},
    )
    assert member_login.status_code == 200
    assert member_login.json()["memberships"][0]["organization_id"] == organization_id
    forbidden = await client.post(
        "/api/v1/organizations/users",
        headers={"X-Organization-ID": organization_id},
        json={
            "username": "autre",
            "full_name": "Autre membre",
            "password": "secret6",
            "role": "reader",
        },
    )
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_employee_can_update_own_profile(client: AsyncClient) -> None:
    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": "mamari", "password": "passer123m"},
    )
    organization_id = admin_login.json()["memberships"][0]["organization_id"]
    employee = await client.post(
        "/api/v1/organizations/users",
        headers={"X-Organization-ID": organization_id},
        json={
            "username": "profile-member",
            "full_name": "Membre",
            "password": "memberpass",
            "role": "operator",
            "phone": "+221 77 123 45 67",
        },
    )
    assert employee.status_code == 201

    client.cookies.clear()
    employee_login = await client.post(
        "/api/v1/auth/login",
        json={"username": "profile-member", "password": "memberpass"},
    )
    assert employee_login.status_code == 200
    update = await client.patch(
        "/api/v1/auth/me",
        headers={"X-Organization-ID": organization_id},
        json={"full_name": "Membre Mis à jour", "phone": "+221 76 987 65 43"},
    )

    assert update.status_code == 200
    assert update.json()["full_name"] == "Membre Mis à jour"
    assert update.json()["phone"] == "+221 76 987 65 43"
    current = await client.get("/api/v1/auth/me")
    assert current.json()["full_name"] == "Membre Mis à jour"

    missing_organization = await client.patch(
        "/api/v1/auth/me",
        json={"full_name": "Autre nom"},
    )
    assert missing_organization.status_code == 422


@pytest.mark.asyncio
async def test_member_profile_photo_is_private_and_organization_scoped(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "mamari", "password": "passer123m"},
    )
    organization_id = login.json()["memberships"][0]["organization_id"]
    monkeypatch.setattr(
        "mamari_api.modules.organizations.router.get_settings",
        lambda: SimpleNamespace(upload_directory=tmp_path),
    )
    created = await client.post(
        "/api/v1/organizations/users",
        headers={"X-Organization-ID": organization_id},
        json={
            "username": "photo-member",
            "full_name": "Membre photo",
            "password": "secret6",
            "role": "operator",
        },
    )
    assert created.status_code == 201
    response = await client.put(
        f"/api/v1/organizations/users/{created.json()['id']}/photo",
        headers={"X-Organization-ID": organization_id},
        files={"photo": ("profile.png", b"\x89PNG\r\n\x1a\nprofile", "image/png")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["photo_url"]
    photo = await client.get(
        f"/api/v1{response.json()['photo_url']}",
        headers={"X-Organization-ID": organization_id},
    )
    assert photo.status_code == 200, photo.text
    assert photo.content.startswith(b"\x89PNG\r\n\x1a\n")

    other_member = await client.post(
        "/api/v1/organizations/users",
        headers={"X-Organization-ID": organization_id},
        json={
            "username": "other-photo-member",
            "full_name": "Autre membre photo",
            "password": "secret6",
            "role": "operator",
        },
    )
    other_photo = await client.put(
        f"/api/v1/organizations/users/{other_member.json()['id']}/photo",
        headers={"X-Organization-ID": organization_id},
        files={"photo": ("profile.png", b"\x89PNG\r\n\x1a\nprofile", "image/png")},
    )
    assert other_photo.status_code == 200
    client.cookies.clear()
    employee_login = await client.post(
        "/api/v1/auth/login",
        json={"username": "photo-member", "password": "secret6"},
    )
    assert employee_login.status_code == 200
    assert employee_login.json()["memberships"][0]["role"] == "operator"
    assert employee_login.json()["id"] == created.json()["id"]
    forbidden = await client.get(
        f"/api/v1{other_photo.json()['photo_url']}",
        headers={"X-Organization-ID": organization_id},
    )
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_operator_can_update_operations_but_not_admin_or_finances(
    client: AsyncClient,
) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "mamari", "password": "passer123m"},
    )
    organization_id = login.json()["memberships"][0]["organization_id"]
    headers = {"X-Organization-ID": organization_id}
    created = await client.post(
        "/api/v1/organizations/users",
        headers=headers,
        json={
            "username": "limited-worker",
            "full_name": "Employé limité",
            "password": "secret6",
            "role": "operator",
        },
    )
    assert created.status_code == 201
    client.cookies.clear()
    employee_login = await client.post(
        "/api/v1/auth/login",
        json={"username": "limited-worker", "password": "secret6"},
    )
    assert employee_login.status_code == 200
    member_list = await client.get("/api/v1/organizations/users", headers=headers)

    farm = await client.post(
        "/api/v1/agriculture/farms",
        headers=headers,
        data={"name": "Ferme opérationnelle"},
    )
    facility = await client.post(
        "/api/v1/livestock/facilities",
        headers=headers,
        json={"name": "Poulailler opérationnel"},
    )
    customer = await client.post(
        "/api/v1/sales/customers",
        headers=headers,
        json={"name": "Client opérationnel", "phone": "771234567"},
    )
    finance_summary = await client.get("/api/v1/finance/summary", headers=headers)
    agriculture_finances = await client.get(
        "/api/v1/agriculture/finance/summary", headers=headers
    )
    livestock_finances = await client.get(
        "/api/v1/livestock/finance/summary", headers=headers
    )
    overview = await client.get("/api/v1/dashboard/overview", headers=headers)

    assert farm.status_code == 201
    assert facility.status_code == 201
    assert customer.status_code == 201
    assert finance_summary.status_code == 403
    assert agriculture_finances.status_code == 403
    assert livestock_finances.status_code == 403
    assert overview.status_code == 200
    assert overview.json()["revenue_fcfa"] is None
    assert overview.json()["average_order_fcfa"] is None
    assert member_list.status_code == 403


@pytest.mark.asyncio
async def test_user_creation_requires_admin_and_rejects_duplicate_usernames(
    client: AsyncClient,
) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "mamari", "password": "passer123m"},
    )
    organization_id = login.json()["memberships"][0]["organization_id"]
    payload = {
        "username": "equipe",
        "full_name": "Membre Mamari",
        "password": "secret6",
        "role": "reader",
    }

    created = await client.post(
        "/api/v1/organizations/users",
        headers={"X-Organization-ID": organization_id},
        json=payload,
    )
    assert created.status_code == 201
    duplicate = await client.post(
        "/api/v1/organizations/users",
        headers={"X-Organization-ID": organization_id},
        json=payload,
    )
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_untrusted_origin_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "mamari", "password": "passer123m"},
        headers={"Origin": "https://attacker.example"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cors_headers_are_preserved_on_server_errors(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_authentication(*args, **kwargs):
        raise RuntimeError("Database unavailable")

    monkeypatch.setattr(
        "mamari_api.modules.identity.router.authenticate_user",
        fail_authentication,
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "mamari", "password": "passer123m"},
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


@pytest.mark.asyncio
async def test_cors_allows_local_frontend_on_auth_response(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "inconnu", "password": "secret6"},
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


@pytest.mark.asyncio
async def test_cors_allows_the_organization_scope_header(client: AsyncClient) -> None:
    response = await client.options(
        "/api/v1/organizations/current",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-organization-id",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "x-organization-id" in response.headers["access-control-allow-headers"].lower()


@pytest.mark.asyncio
async def test_password_validation_uses_six_character_minimum(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "mamari", "password": "short"},
    )

    assert response.status_code == 422
    assert '"input":"short"' not in response.text
