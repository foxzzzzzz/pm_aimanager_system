from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from project_manager_api.api.routes import router
from project_manager_api.db.session import create_database
from project_manager_api.imports.registry import ParserRegistry
from project_manager_api.services.errors import ServiceError
from project_manager_api.settings import AppSettings
from project_manager_api.storage.local import LocalImportStorage
from project_manager_api.storage.s3 import S3ImportStorage


def create_app(settings: AppSettings | None = None) -> FastAPI:
    resolved_settings = settings or AppSettings.from_environment()
    engine, session_factory = create_database(resolved_settings.database_url)
    app = FastAPI(title="AI Project Manager API", version="0.4.0")
    app.state.settings = resolved_settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.parser_registry = ParserRegistry.from_manifest_paths(resolved_settings.manifest_paths)
    if resolved_settings.storage_backend == "s3":
        if (
            not resolved_settings.object_storage_endpoint
            or not resolved_settings.object_storage_bucket
        ):
            raise ValueError("S3 storage requires an endpoint and bucket")
        app.state.import_storage = S3ImportStorage(
            endpoint=resolved_settings.object_storage_endpoint,
            bucket=resolved_settings.object_storage_bucket,
            region=resolved_settings.object_storage_region,
            staging_root=resolved_settings.import_storage_path,
            access_key=resolved_settings.object_storage_access_key,
            secret_key=resolved_settings.object_storage_secret_key,
        )
    else:
        app.state.import_storage = LocalImportStorage(resolved_settings.import_storage_path)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.exception_handler(ServiceError)
    async def handle_service_error(_request: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"service": "project-manager-api", "status": "ok"}

    return app
