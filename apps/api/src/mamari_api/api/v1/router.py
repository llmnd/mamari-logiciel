from fastapi import APIRouter

from mamari_api.modules.agriculture.router import router as agriculture_router
from mamari_api.modules.audit.router import router as audit_router
from mamari_api.modules.communication.router import router as communication_router
from mamari_api.modules.dashboard.router import router as dashboard_router
from mamari_api.modules.finances.router import router as finances_router
from mamari_api.modules.health.router import router as health_router
from mamari_api.modules.human_resources.router import router as human_resources_router
from mamari_api.modules.identity.router import router as identity_router
from mamari_api.modules.livestock.router import router as livestock_router
from mamari_api.modules.operations.router import router as operations_router
from mamari_api.modules.organizations.router import router as organizations_router
from mamari_api.modules.public_site.router import router as public_site_router
from mamari_api.modules.sales.router import router as sales_router
from mamari_api.modules.stocks.router import router as stocks_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(audit_router, tags=["audit"])
api_router.include_router(dashboard_router, tags=["dashboard"])
api_router.include_router(identity_router, tags=["authentication"])
api_router.include_router(organizations_router, tags=["organizations"])
api_router.include_router(public_site_router, tags=["public-site"])
api_router.include_router(agriculture_router, tags=["agriculture"])
api_router.include_router(operations_router, tags=["operations"])
api_router.include_router(livestock_router, tags=["livestock"])
api_router.include_router(sales_router, tags=["sales"])
api_router.include_router(stocks_router, tags=["stocks"])
api_router.include_router(finances_router, tags=["finances"])
api_router.include_router(human_resources_router, tags=["human-resources"])
api_router.include_router(communication_router, tags=["communication"])
