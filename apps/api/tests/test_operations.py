from datetime import date, timedelta
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


@pytest.mark.asyncio
async def test_dashboard_summarizes_operational_alerts(client: AsyncClient) -> None:
    organization_id = await admin_organization(client)
    headers = {"X-Organization-ID": organization_id}
    overdue_task = await client.post(
        "/api/v1/operations/tasks",
        headers=headers,
        json={
            "title": "Traiter la commande en retard",
            "due_date": (date.today() - timedelta(days=1)).isoformat(),
        },
    )
    upcoming_task = await client.post(
        "/api/v1/operations/tasks",
        headers=headers,
        json={
            "title": "Préparer le prochain inventaire",
            "due_date": (date.today() + timedelta(days=2)).isoformat(),
        },
    )
    animal = await client.post(
        "/api/v1/livestock/animals",
        headers=headers,
        json={"name": "Awa", "species": "Caprin"},
    )
    overdue_care = await client.post(
        "/api/v1/livestock/records",
        headers=headers,
        json={
            "record_type": "health",
            "category": "checkup",
            "title": "Contrôle vétérinaire",
            "animal_id": animal.json()["id"],
            "next_due_date": (date.today() - timedelta(days=1)).isoformat(),
        },
    )
    empty_stock = await client.post(
        "/api/v1/stocks/items",
        headers=headers,
        json={
            "source": "other",
            "name": "Réserve vide",
            "unit": "kg",
            "minimum_quantity": 1,
        },
    )
    stocked_item = await client.post(
        "/api/v1/stocks/items",
        headers=headers,
        json={
            "source": "other",
            "name": "Réserve disponible",
            "unit": "kg",
            "opening_quantity": 10,
        },
    )
    assert overdue_task.status_code == 201
    assert upcoming_task.status_code == 201
    assert animal.status_code == 201
    assert overdue_care.status_code == 201
    assert empty_stock.status_code == 201
    assert stocked_item.status_code == 201

    dashboard = await client.get("/api/v1/dashboard/overview", headers=headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["open_task_count"] == 2
    assert dashboard.json()["overdue_task_count"] == 1
    assert dashboard.json()["overdue_care_count"] == 1
    assert dashboard.json()["restock_item_count"] == 1


@pytest.mark.asyncio
async def test_tasks_can_be_planned_assigned_searched_and_completed(
    client: AsyncClient,
) -> None:
    organization_id = await admin_organization(client)
    headers = {"X-Organization-ID": organization_id}
    member = await client.post(
        "/api/v1/organizations/users",
        headers=headers,
        json={
            "username": "operations-user",
            "full_name": "Awa Diop",
            "password": "secret6",
            "role": "operator",
        },
    )
    assert member.status_code == 201, member.text
    member_id = member.json()["id"]

    created = await client.post(
        "/api/v1/operations/tasks",
        headers=headers,
        json={
            "title": "Préparer les commandes",
            "description": "Vérifier les quantités avant le départ.",
            "priority": "urgent",
            "due_date": (date.today() - timedelta(days=1)).isoformat(),
            "assigned_user_id": member_id,
        },
    )
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["status"] == "todo"
    assert task["assigned_user_name"] == "Awa Diop"

    second = await client.post(
        "/api/v1/operations/tasks",
        headers=headers,
        json={
            "title": "Ranger les équipements",
            "priority": "normal",
            "due_date": (date.today() + timedelta(days=3)).isoformat(),
        },
    )
    assert second.status_code == 201, second.text
    in_progress = await client.patch(
        f"/api/v1/operations/tasks/{second.json()['id']}",
        headers=headers,
        json={"status": "in_progress"},
    )
    assert in_progress.status_code == 200

    filtered = await client.get(
        "/api/v1/operations/tasks?search=commandes&priority=urgent",
        headers=headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["id"] == task["id"]

    open_tasks = await client.get(
        "/api/v1/operations/tasks?bucket=open&page_size=1",
        headers=headers,
    )
    assert open_tasks.status_code == 200
    assert open_tasks.json()["total"] == 2
    assert len(open_tasks.json()["items"]) == 1
    assert open_tasks.json()["page_size"] == 1

    overdue_tasks = await client.get(
        "/api/v1/operations/tasks?bucket=overdue",
        headers=headers,
    )
    assert overdue_tasks.status_code == 200
    assert overdue_tasks.json()["total"] == 1
    assert overdue_tasks.json()["items"][0]["id"] == task["id"]

    summary = await client.get("/api/v1/operations/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json() == {
        "total": 2,
        "todo": 1,
        "in_progress": 1,
        "done": 0,
        "overdue": 1,
        "due_soon": 1,
    }

    completed = await client.patch(
        f"/api/v1/operations/tasks/{task['id']}",
        headers=headers,
        json={"status": "done"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "done"
    summary = await client.get("/api/v1/operations/summary", headers=headers)
    assert summary.json()["overdue"] == 0
    assert summary.json()["done"] == 1
    no_overdue_tasks = await client.get(
        "/api/v1/operations/tasks?bucket=overdue",
        headers=headers,
    )
    assert no_overdue_tasks.status_code == 200
    assert no_overdue_tasks.json()["total"] == 0

    archived = await client.patch(
        f"/api/v1/operations/tasks/{task['id']}",
        headers=headers,
        json={"status": "archived"},
    )
    assert archived.status_code == 200
    normal_list = await client.get("/api/v1/operations/tasks", headers=headers)
    assert normal_list.json()["total"] == 1
    archived_list = await client.get(
        "/api/v1/operations/tasks?status=archived",
        headers=headers,
    )
    assert archived_list.json()["total"] == 1


@pytest.mark.asyncio
async def test_task_assignments_and_permissions_are_organization_scoped(
    client: AsyncClient,
) -> None:
    organization_id = await admin_organization(client)
    headers = {"X-Organization-ID": organization_id}

    invalid_assignee = await client.post(
        "/api/v1/operations/tasks",
        headers=headers,
        json={"title": "Tâche hors organisation", "assigned_user_id": str(uuid4())},
    )
    assert invalid_assignee.status_code == 404

    created = await client.post(
        "/api/v1/operations/tasks",
        headers=headers,
        json={"title": "Tâche en lecture seule"},
    )
    assert created.status_code == 201

    reader = await client.post(
        "/api/v1/organizations/users",
        headers=headers,
        json={
            "username": "operations-reader",
            "full_name": "Lecteur opérations",
            "password": "secret6",
            "role": "reader",
        },
    )
    assert reader.status_code == 201
    client.cookies.clear()
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "operations-reader", "password": "secret6"},
    )
    assert login.status_code == 200

    assert (await client.get("/api/v1/operations/tasks", headers=headers)).status_code == 200
    forbidden_create = await client.post(
        "/api/v1/operations/tasks",
        headers=headers,
        json={"title": "Création interdite"},
    )
    assert forbidden_create.status_code == 403
    forbidden_update = await client.patch(
        f"/api/v1/operations/tasks/{created.json()['id']}",
        headers=headers,
        json={"status": "done"},
    )
    assert forbidden_update.status_code == 403


@pytest.mark.asyncio
async def test_employees_only_see_and_update_assigned_tasks_with_delay_reasons(
    client: AsyncClient,
) -> None:
    organization_id = await admin_organization(client)
    headers = {"X-Organization-ID": organization_id}
    member = await client.post(
        "/api/v1/organizations/users",
        headers=headers,
        json={
            "username": "field-worker",
            "full_name": "Awa Ndiaye",
            "password": "secret6",
            "role": "operator",
        },
    )
    assert member.status_code == 201
    assigned = await client.post(
        "/api/v1/operations/tasks",
        headers=headers,
        json={
            "title": "Préparer le terrain",
            "due_date": (date.today() - timedelta(days=1)).isoformat(),
            "assigned_user_id": member.json()["id"],
        },
    )
    assert assigned.status_code == 201
    private_task = await client.post(
        "/api/v1/operations/tasks",
        headers=headers,
        json={"title": "Réserver le matériel"},
    )
    assert private_task.status_code == 201

    client.cookies.clear()
    employee_login = await client.post(
        "/api/v1/auth/login",
        json={"username": "field-worker", "password": "secret6"},
    )
    assert employee_login.status_code == 200
    visible = await client.get("/api/v1/operations/tasks", headers=headers)
    assert visible.status_code == 200
    assert [task["id"] for task in visible.json()["items"]] == [assigned.json()["id"]]
    assert visible.json()["items"][0]["assigned_user_phone"] is None

    forbidden = await client.patch(
        f"/api/v1/operations/tasks/{private_task.json()['id']}",
        headers=headers,
        json={"status": "done"},
    )
    assert forbidden.status_code == 403
    unjustified = await client.patch(
        f"/api/v1/operations/tasks/{assigned.json()['id']}",
        headers=headers,
        json={"status": "in_progress"},
    )
    assert unjustified.status_code == 422
    updated = await client.patch(
        f"/api/v1/operations/tasks/{assigned.json()['id']}",
        headers=headers,
        json={
            "status": "in_progress",
            "progress_note": "Préparation commencée",
            "delay_reason": "La pluie a retardé l’équipe.",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "in_progress"
    assert updated.json()["delay_reason"] == "La pluie a retardé l’équipe."
    history = await client.get(
        f"/api/v1/operations/tasks/{assigned.json()['id']}/updates",
        headers=headers,
    )
    assert history.status_code == 200
    assert history.json()[0]["user_name"] == "Awa Ndiaye"
    assert history.json()[0]["note"] == "Préparation commencée"
    assert history.json()[0]["delay_reason"] == "La pluie a retardé l’équipe."

    forbidden_edit = await client.patch(
        f"/api/v1/operations/tasks/{assigned.json()['id']}",
        headers=headers,
        json={"title": "Tâche modifiée"},
    )
    assert forbidden_edit.status_code == 403
