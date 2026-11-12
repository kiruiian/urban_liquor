from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.modules.auth.router import router as auth_router
from app.modules.inventory.router import router as inventory_router
from app.modules.sales.router import router as sales_router
from app.modules.suppliers.router import router as suppliers_router
from app.modules.wholesale.router import router as wholesale_router

settings = get_settings()
frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
frontend_assets = frontend_dist / "assets"

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Urban Liquor Store Operating System API",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.app_env,
    }


app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(inventory_router, prefix="/api/v1/inventory", tags=["Inventory"])
app.include_router(sales_router, prefix="/api/v1/sales", tags=["Sales"])
app.include_router(suppliers_router, prefix="/api/v1/suppliers", tags=["Suppliers"])
app.include_router(wholesale_router, prefix="/api/v1/wholesale", tags=["Wholesale"])

if frontend_assets.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(frontend_assets)),
        name="frontend-assets",
    )


@app.get("/", include_in_schema=False)
async def serve_frontend() -> FileResponse:
    index_file = frontend_dist / "index.html"
    if not index_file.is_file():
        raise HTTPException(
            status_code=503,
            detail="Frontend build not found. Run `npm run build` from the frontend directory.",
        )
    return FileResponse(index_file)
