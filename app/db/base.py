from app.db.base_class import Base  # noqa: F401

# Import all models here so that Alembic/FastAPI sees them
from app.models import report  # noqa: F401
from app.models import user  # noqa: F401 
from app.models import task  # noqa: F401 