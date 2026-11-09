import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from mamari_api.core.base import Base
from mamari_api.core.database import get_session
from mamari_api.main import api_app, app
from mamari_api.modules.agriculture import models as agriculture_models  # noqa: F401
from mamari_api.modules.audit import models as audit_models  # noqa: F401
from mamari_api.modules.communication import models as communication_models  # noqa: F401
from mamari_api.modules.human_resources import models as human_resources_models  # noqa: F401
from mamari_api.modules.identity import models as identity_models  # noqa: F401
from mamari_api.modules.livestock import models as livestock_models  # noqa: F401
from mamari_api.modules.operations import models as operations_models  # noqa: F401
from mamari_api.modules.public_site import models as public_site_models  # noqa: F401
from mamari_api.modules.sales import models as sales_models  # noqa: F401
from mamari_api.modules.stocks import models as stocks_models  # noqa: F401


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with session_factory() as session:
            yield session

    api_app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as test_client:
            yield test_client
    finally:
        api_app.dependency_overrides.pop(get_session, None)
        await engine.dispose()
