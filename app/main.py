from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.db.session import engine
from app.db.base import Base
from app.routers import auth, dashboard, reports, admin, files, employee, admin_batch
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi import Request
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


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Redirect browsers (HTML) to login page on 401 instead of JSON error."""
    if exc.status_code == 401 and "text/html" in request.headers.get("accept", ""):
        return RedirectResponse(url="/", status_code=303)
    # Fallback to JSON for other cases
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
