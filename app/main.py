from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.db.session import engine
from app.db.base import Base
from app.routers import auth, dashboard, reports, admin, files, employee, admin_batch

# Create DB tables (if they do not exist)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Project Tracker", openapi_url="/openapi.json", docs_url="/docs")
app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
# Register routers
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(reports.router)
app.include_router(admin.router)
app.include_router(files.router)
app.include_router(employee.router)
app.include_router(admin_batch.router)

# Static assets
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploaded_files", StaticFiles(directory="uploaded_files"), name="uploaded_files")

@app.get("/health", tags=["Health"])
async def health_check():
    """Simple health check endpoint used by reverse proxies and container orchestrators."""
    return {"status": "ok"}