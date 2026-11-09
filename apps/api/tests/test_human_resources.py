from datetime import date, timedelta

from httpx import AsyncClient


async def admin_session(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "mamari", "password": "passer123m"},
    )
    assert response.status_code == 200
    return response.json()["memberships"][0]["organization_id"]


async def create_member(
    client: AsyncClient,
    organization_id: str,
    username: str,
    role: str,
) -> dict:
    response = await client.post(
        "/api/v1/organizations/users",
        headers={"X-Organization-ID": organization_id},
        json={
            "username": username,
            "full_name": f"Membre {username}",
            "password": "secret6",
            "role": role,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def login_as(client: AsyncClient, username: str) -> None:
    client.cookies.clear()
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "username": username,
            "password": "passer123m" if username == "mamari" else "secret6",
        },
    )
    assert response.status_code == 200, response.text


async def test_human_resources_manage_employee_profiles_and_restrict_roles(
    client: AsyncClient,
) -> None:
    organization_id = await admin_session(client)
    employee = await create_member(client, organization_id, "employe-rh", "operator")
    await create_member(client, organization_id, "manager-rh", "manager")
    await create_member(client, organization_id, "lecteur-rh", "reader")
    headers = {"X-Organization-ID": organization_id}

    updated = await client.patch(
        f"/api/v1/human-resources/employees/{employee['id']}",
        headers=headers,
        json={
            "job_title": "Responsable de ferme",
            "department": "Agriculture",
            "hire_date": "2024-03-15",
            "employment_type": "permanent",
            "employment_status": "active",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["job_title"] == "Responsable de ferme"
    assert updated.json()["department"] == "Agriculture"
    assert updated.json()["hire_date"] == "2024-03-15"

    filtered = await client.get(
        "/api/v1/human-resources/employees?search=ferme&status=active",
        headers=headers,
    )
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["id"] == employee["id"]
    assert filtered.json()["summary"]["total"] == 4
    assert filtered.json()["summary"]["active"] == 4

    await login_as(client, "manager-rh")
    manager_update = await client.patch(
        f"/api/v1/human-resources/employees/{employee['id']}",
        headers=headers,
        json={"employment_status": "on_leave"},
    )
    assert manager_update.status_code == 200, manager_update.text
    assert manager_update.json()["employment_status"] == "on_leave"
    assert (
        await client.patch(
            f"/api/v1/human-resources/employees/{employee['id']}",
            headers=headers,
            json={"role": "admin"},
        )
    ).status_code == 422

    await login_as(client, "lecteur-rh")
    assert (
        await client.get("/api/v1/human-resources/employees", headers=headers)
    ).status_code == 403

    await login_as(client, "mamari")
    missing = await client.get(
        "/api/v1/human-resources/employees",
        headers={"X-Organization-ID": "00000000-0000-0000-0000-000000000001"},
    )
    assert missing.status_code == 403


async def test_payroll_payment_flows_to_finances_and_absences_need_approval(
    client: AsyncClient,
) -> None:
    organization_id = await admin_session(client)
    employee = await create_member(client, organization_id, "employe-paie", "operator")
    await create_member(client, organization_id, "manager-absence", "manager")
    headers = {"X-Organization-ID": organization_id}
    period = {"pay_year": date.today().year, "pay_month": date.today().month}

    payroll = await client.post(
        "/api/v1/human-resources/payroll",
        headers=headers,
        json={
            "user_id": employee["id"],
            **period,
            "gross_pay_fcfa": 200000,
            "bonus_fcfa": 25000,
            "deductions_fcfa": 10000,
        },
    )
    assert payroll.status_code == 201, payroll.text
    assert payroll.json()["net_pay_fcfa"] == 215000
    duplicate = await client.post(
        "/api/v1/human-resources/payroll",
        headers=headers,
        json={
            "user_id": employee["id"],
            **period,
            "gross_pay_fcfa": 200000,
        },
    )
    assert duplicate.status_code == 409
    excessive_deduction = await client.post(
        "/api/v1/human-resources/payroll",
        headers=headers,
        json={
            "user_id": employee["id"],
            "pay_year": period["pay_year"],
            "pay_month": (period["pay_month"] % 12) + 1,
            "gross_pay_fcfa": 200000,
            "deductions_fcfa": 200001,
        },
    )
    assert excessive_deduction.status_code == 422

    await login_as(client, "employe-paie")
    own_payroll = await client.get(
        f"/api/v1/human-resources/payroll?year={period['pay_year']}&month={period['pay_month']}",
        headers=headers,
    )
    assert own_payroll.status_code == 200
    assert own_payroll.json()["total"] == 1
    assert own_payroll.json()["items"][0]["net_pay_fcfa"] == 215000

    summary_before_payment = await client.get(
        f"/api/v1/finance/summary?year={period['pay_year']}",
        headers=headers,
    )
    assert summary_before_payment.status_code == 403

    absence_start = date.today() + timedelta(days=30)
    absence_end = absence_start + timedelta(days=4)
    absence = await client.post(
        "/api/v1/human-resources/absences",
        headers=headers,
        json={
            "absence_type": "annual_leave",
            "start_date": absence_start.isoformat(),
            "end_date": absence_end.isoformat(),
            "reason": "Congé familial",
        },
    )
    assert absence.status_code == 201, absence.text
    assert absence.json()["status"] == "pending"
    overlap = await client.post(
        "/api/v1/human-resources/absences",
        headers=headers,
        json={
            "absence_type": "other",
            "start_date": (absence_start + timedelta(days=2)).isoformat(),
            "end_date": (absence_end + timedelta(days=1)).isoformat(),
            "reason": "Rendez-vous",
        },
    )
    assert overlap.status_code == 409
    reversed_dates = await client.post(
        "/api/v1/human-resources/absences",
        headers=headers,
        json={
            "absence_type": "other",
            "start_date": absence_end.isoformat(),
            "end_date": absence_start.isoformat(),
            "reason": "Dates incohérentes",
        },
    )
    assert reversed_dates.status_code == 422

    await login_as(client, "manager-absence")
    summary_before_payment = await client.get(
        f"/api/v1/finance/summary?year={period['pay_year']}",
        headers=headers,
    )
    assert summary_before_payment.status_code == 200
    assert summary_before_payment.json()["expenses_fcfa"] == 0
    manager_payroll = await client.get(
        f"/api/v1/human-resources/payroll?year={period['pay_year']}&month={period['pay_month']}",
        headers=headers,
    )
    assert manager_payroll.status_code == 200
    assert manager_payroll.json()["total"] == 0
    absence_list = await client.get("/api/v1/human-resources/absences", headers=headers)
    assert absence_list.status_code == 200
    request_id = absence_list.json()["items"][0]["id"]
    approved = await client.patch(
        f"/api/v1/human-resources/absences/{request_id}",
        headers=headers,
        json={"status": "approved"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert (
        await client.patch(
            f"/api/v1/human-resources/absences/{request_id}",
            headers=headers,
            json={"status": "rejected"},
        )
    ).status_code == 409

    await login_as(client, "mamari")
    paid = await client.post(
        f"/api/v1/human-resources/payroll/{payroll.json()['id']}/mark-paid",
        headers=headers,
    )
    assert paid.status_code == 200
    assert paid.json()["payment_status"] == "paid"
    assert paid.json()["paid_at"] == date.today().isoformat()
    paid_summary = await client.get(
        f"/api/v1/finance/summary?year={period['pay_year']}",
        headers=headers,
    )
    assert paid_summary.status_code == 200
    assert paid_summary.json()["expenses_fcfa"] == 215000
    source_summary = {item["source"]: item for item in paid_summary.json()["by_source"]}
    assert source_summary["payroll"]["expenses_fcfa"] == 215000
    finances = await client.get(
        f"/api/v1/finance/transactions?year={period['pay_year']}&source=payroll",
        headers=headers,
    )
    assert finances.status_code == 200, finances.text
    assert finances.json()["total"] == 1
    assert finances.json()["items"][0]["amount_fcfa"] == 215000
    assert finances.json()["items"][0]["transaction_type"] == "expense"

    await login_as(client, "employe-paie")
    restricted_finances = await client.get(
        f"/api/v1/finance/transactions?year={period['pay_year']}&source=payroll",
        headers=headers,
    )
    assert restricted_finances.status_code == 403
    private_summary = await client.get(
        f"/api/v1/finance/summary?year={period['pay_year']}",
        headers=headers,
    )
    assert private_summary.status_code == 403
