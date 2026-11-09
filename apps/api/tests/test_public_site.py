import pytest
from httpx import AsyncClient


async def admin_headers(client: AsyncClient) -> tuple[str, dict[str, str]]:
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "mamari", "password": "passer123m"},
    )
    assert login.status_code == 200
    organization_id = login.json()["memberships"][0]["organization_id"]
    return organization_id, {"X-Organization-ID": organization_id}


@pytest.mark.asyncio
async def test_public_newsletter_consent_unsubscribe_and_manager_inbox(
    client: AsyncClient,
) -> None:
    _, headers = await admin_headers(client)
    subscribed = await client.post(
        "/api/v1/public/newsletter",
        json={"email": "News@Example.com", "consent": True},
    )
    assert subscribed.status_code == 201, subscribed.text
    token = subscribed.json()["unsubscribe_token"]
    assert token
    duplicate = await client.post(
        "/api/v1/public/newsletter",
        json={"email": "news@example.com", "consent": True},
    )
    assert duplicate.status_code == 201, duplicate.text
    assert duplicate.json()["already_subscribed"] is True
    assert duplicate.json()["unsubscribe_token"] is None

    inquiry = await client.post(
        "/api/v1/public/contact",
        json={
            "full_name": "Awa Diop",
            "email": "awa@example.com",
            "subject": "Produits",
            "message": "Je souhaite avoir des informations sur vos produits.",
            "consent": True,
        },
    )
    assert inquiry.status_code == 201, inquiry.text
    assert inquiry.json()["status"] == "new"

    inbox = await client.get("/api/v1/public/inbox", headers=headers)
    assert inbox.status_code == 200, inbox.text
    assert inbox.json()["inquiry_total"] == 1
    assert inbox.json()["subscriber_total"] == 1

    marked_read = await client.patch(
        f"/api/v1/public/inbox/{inquiry.json()['id']}",
        headers=headers,
        json={"status": "read"},
    )
    assert marked_read.status_code == 200
    assert marked_read.json()["status"] == "read"

    unsubscribed = await client.post(
        "/api/v1/public/newsletter/unsubscribe",
        json={"token": token},
    )
    assert unsubscribed.status_code == 204
    inbox = await client.get("/api/v1/public/inbox", headers=headers)
    assert inbox.json()["subscriber_total"] == 0

    operator = await client.post(
        "/api/v1/organizations/users",
        headers=headers,
        json={
            "username": "public-inbox-operator",
            "full_name": "Operator Mamari",
            "password": "passer123m",
            "role": "operator",
        },
    )
    assert operator.status_code == 201
    client.cookies.clear()
    await client.post(
        "/api/v1/auth/login",
        json={"username": "public-inbox-operator", "password": "passer123m"},
    )
    denied = await client.get("/api/v1/public/inbox", headers=headers)
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_public_contact_form_requires_consent_and_honeypot_is_not_saved(
    client: AsyncClient,
) -> None:
    _, headers = await admin_headers(client)
    missing_consent = await client.post(
        "/api/v1/public/contact",
        json={
            "full_name": "Awa Diop",
            "email": "awa@example.com",
            "subject": "Question",
            "message": "Un message suffisamment long.",
        },
    )
    assert missing_consent.status_code == 422

    bot_submission = await client.post(
        "/api/v1/public/contact",
        json={
            "full_name": "Robot",
            "email": "bot@example.com",
            "subject": "Spam",
            "message": "Un message suffisamment long pour passer la validation.",
            "consent": True,
            "website": "https://spam.example",
        },
    )
    assert bot_submission.status_code == 201
    inbox = await client.get("/api/v1/public/inbox", headers=headers)
    assert inbox.json()["inquiry_total"] == 0
