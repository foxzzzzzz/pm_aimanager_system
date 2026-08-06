from typing import Literal, TypedDict

from fastapi import FastAPI


class HealthResponse(TypedDict):
    service: str
    status: Literal["ok"]


app = FastAPI(title="AI Project Manager API", version="0.2.0")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return {
        "service": "project-manager-api",
        "status": "ok",
    }
