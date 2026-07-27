from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User
from titan_x.services.ai_registry_service import AIModelRegistryService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/ai-models", tags=["ai-models"])


async def get_ai_registry_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> AIModelRegistryService:
    return AIModelRegistryService(session)


@router.post("")
async def register_model(
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[AIModelRegistryService, Depends(get_ai_registry_service)],
    name: str = Query(...),
    version: str = Query(...),
    model_type: str = Query(...),
    description: str | None = Query(None),
    model_metadata_json: str | None = Query(None),
    source: str | None = Query(None),
    metrics_json: str | None = Query(None),
):
    try:
        model = await svc.register(
            name=name, version=version, model_type=model_type,
            description=description, model_metadata_json=model_metadata_json,
            source=source, metrics_json=metrics_json,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return model


@router.get("")
async def list_models(
    svc: Annotated[AIModelRegistryService, Depends(get_ai_registry_service)],
    model_type: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    rows, total = await svc.list(
        model_type=model_type, status=status, limit=limit, offset=offset,
    )
    return {"items": rows, "total": total}


@router.get("/by-name/{name}")
async def get_model_by_name(
    name: str,
    svc: Annotated[AIModelRegistryService, Depends(get_ai_registry_service)],
):
    return await svc.get_by_name(name)


@router.get("/{model_id}")
async def get_model(
    model_id: int,
    svc: Annotated[AIModelRegistryService, Depends(get_ai_registry_service)],
):
    model = await svc.get(model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    return model


@router.put("/{model_id}")
async def update_model(
    model_id: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[AIModelRegistryService, Depends(get_ai_registry_service)],
    description: str | None = Query(None),
    model_metadata_json: str | None = Query(None),
    metrics_json: str | None = Query(None),
    source: str | None = Query(None),
):
    model = await svc.update(
        model_id,
        description=description,
        model_metadata_json=model_metadata_json,
        metrics_json=metrics_json,
        source=source,
    )
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    return model


@router.post("/{model_id}/status")
async def change_status(
    model_id: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[AIModelRegistryService, Depends(get_ai_registry_service)],
    status: str = Query(...),
):
    try:
        model = await svc.change_status(model_id, status)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    return model


@router.post("/{model_id}/deploy")
async def deploy_model(
    model_id: int,
    user: Annotated[User, Depends(get_current_active_user)],
    svc: Annotated[AIModelRegistryService, Depends(get_ai_registry_service)],
    environment: str = Query(...),
):
    model = await svc.get(model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    try:
        deployment = await svc.deploy(model_id, environment, deployed_by=user.email)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return deployment


@router.get("/{model_id}/deployments")
async def get_deployments(
    model_id: int,
    svc: Annotated[AIModelRegistryService, Depends(get_ai_registry_service)],
):
    model = await svc.get(model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    return await svc.get_deployments(model_id)


@router.post("/compare")
async def compare_models(
    svc: Annotated[AIModelRegistryService, Depends(get_ai_registry_service)],
    model_ids: list[int] = Query(...),
):
    return await svc.compare(model_ids)
