from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth.router import router as auth_router
from app.api.users.router import router as users_router
from app.api.content.router import router as config_router
from app.api.wheel.router import router as wheel_router
from app.api.spin.router import router as spin_router
from app.api.purchases.router import router as purchases_router
from app.api.inventory.router import router as inventory_router
from app.api.delivery.router import router as delivery_router
from app.api.admin.router import router as admin_router
from app.api.admin.content import router as admin_content_router
from app.api.admin.media import router as admin_media_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Soft Limit", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="frontend"), name="static")

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(config_router)
app.include_router(wheel_router)
app.include_router(spin_router)
app.include_router(purchases_router)
app.include_router(inventory_router)
app.include_router(delivery_router)
app.include_router(admin_router)
app.include_router(admin_content_router)
app.include_router(admin_media_router)


@app.get("/")
async def root():
    return {"status": "ok", "app": "soft-limit"}
