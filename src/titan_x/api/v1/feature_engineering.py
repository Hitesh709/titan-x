from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.feature_engineering import FeatureDefinition, FeatureValue
from titan_x.models.user import User
from titan_x.services.feature_engineering_service import FeatureEngineeringService

router = APIRouter(
    prefix="/features",
    tags=["feature-engineering"],
)


# ---- Pydantic Schemas ----

class FeatureDefinitionResponse(BaseModel):
    id: int
    name: str
    category: str
    version: str
    description: str | None = None
    formula: str | None = None
    parameters: Any = None
    source: str | None = None
    is_active: bool = True

    @classmethod
    def from_orm(cls, fd: FeatureDefinition) -> "FeatureDefinitionResponse":
        import json
        params = None
        if fd.parameters:
            try:
                params = json.loads(fd.parameters)
            except (json.JSONDecodeError, TypeError):
                params = fd.parameters
        return cls(
            id=fd.id, name=fd.name, category=fd.category, version=fd.version,
            description=fd.description, formula=fd.formula,
            parameters=params, source=fd.source, is_active=fd.is_active,
        )


class FeatureValueResponse(BaseModel):
    id: int
    feature_name: str
    feature_version: str
    category: str
    symbol: str
    as_of_date: date
    value: float
    metadata: Any = None

    @classmethod
    def from_orm(cls, fv: FeatureValue) -> "FeatureValueResponse":
        import json
        meta = None
        if fv.metadata_json:
            try:
                meta = json.loads(fv.metadata_json)
            except (json.JSONDecodeError, TypeError):
                meta = fv.metadata_json
        return cls(
            id=fv.id, feature_name=fv.definition.name,
            feature_version=fv.definition.version, category=fv.definition.category,
            symbol=fv.symbol, as_of_date=fv.as_of_date, value=fv.value, metadata=meta,
        )


class RegisterFeatureRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    category: str = Field(..., pattern="^(price|volume|momentum|volatility|financial|news|macro|breadth)$")
    description: str | None = None
    formula: str | None = None
    parameters: dict[str, Any] | None = None
    source: str | None = None


class CreateVersionRequest(BaseModel):
    description: str | None = None
    formula: str | None = None
    parameters: dict[str, Any] | None = None
    source: str | None = None
    change_notes: str | None = None


class ComputeAllResponse(BaseModel):
    symbol: str
    as_of_date: date
    features_computed: int
    by_category: dict[str, int]


class FeatureValueList(BaseModel):
    items: list[FeatureValueResponse]
    total: int


# ---- Dependency ----

async def get_fe_service(
    session: Annotated[AsyncSession, Depends(request_session)],
) -> FeatureEngineeringService:
    return FeatureEngineeringService(session)


# ---- Endpoints ----

@router.post("/definitions", response_model=FeatureDefinitionResponse, status_code=status.HTTP_201_CREATED)
async def register_feature(
    req: RegisterFeatureRequest,
    svc: Annotated[FeatureEngineeringService, Depends(get_fe_service)],
    _user: Annotated[User, Depends(get_current_active_user)],
):
    fd = await svc.register_feature(
        req.name, req.category, description=req.description,
        formula=req.formula, parameters=req.parameters, source=req.source,
    )
    return FeatureDefinitionResponse.from_orm(fd)


@router.get("/definitions", response_model=list[FeatureDefinitionResponse])
async def list_definitions(
    svc: Annotated[FeatureEngineeringService, Depends(get_fe_service)],
    _user: Annotated[User, Depends(get_current_active_user)],
    category: str | None = Query(None, pattern="^(price|volume|momentum|volatility|financial|news|macro|breadth)$"),
):
    fds = await svc.list_definitions(category=category)
    return [FeatureDefinitionResponse.from_orm(fd) for fd in fds]


@router.get("/definitions/{name}", response_model=list[FeatureDefinitionResponse])
async def get_feature_definition(
    name: str,
    svc: Annotated[FeatureEngineeringService, Depends(get_fe_service)],
    _user: Annotated[User, Depends(get_current_active_user)],
):
    fd = await svc.get_feature_definition(name)
    if not fd:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Feature '{name}' not found")
    # Return all versions
    all_fds = [fd]
    # Check for other versions
    r = await svc.list_definitions()
    all_versions = [f for f in r if f.name == name]
    return [FeatureDefinitionResponse.from_orm(f) for f in all_versions]


@router.post("/definitions/{name}/versions", response_model=FeatureDefinitionResponse)
async def create_feature_version(
    name: str,
    req: CreateVersionRequest,
    svc: Annotated[FeatureEngineeringService, Depends(get_fe_service)],
    _user: Annotated[User, Depends(get_current_active_user)],
):
    existing = await svc.get_feature_definition(name)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Feature '{name}' not found")
    fd = await svc.create_new_version(name, **req.model_dump(exclude_none=True))
    return FeatureDefinitionResponse.from_orm(fd)


@router.post("/compute/{symbol}", response_model=ComputeAllResponse)
async def compute_all_features(
    symbol: str,
    svc: Annotated[FeatureEngineeringService, Depends(get_fe_service)],
    _user: Annotated[User, Depends(get_current_active_user)],
    as_of_date: date | None = None,
):
    results = await svc.compute_all_features(symbol.upper(), as_of_date)
    total = sum(results.values())
    return ComputeAllResponse(
        symbol=symbol.upper(),
        as_of_date=as_of_date or date.today(),
        features_computed=total,
        by_category=results,
    )


@router.post("/compute/{symbol}/{feature_name}")
async def compute_single_feature(
    symbol: str,
    feature_name: str,
    svc: Annotated[FeatureEngineeringService, Depends(get_fe_service)],
    _user: Annotated[User, Depends(get_current_active_user)],
    as_of_date: date | None = None,
):
    value = await svc.compute_feature(feature_name, symbol.upper(), as_of_date)
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not compute '{feature_name}' for {symbol.upper()}",
        )
    return {"symbol": symbol.upper(), "feature": feature_name, "value": value, "as_of_date": as_of_date or date.today()}


@router.get("/values", response_model=FeatureValueList)
async def get_feature_values(
    svc: Annotated[FeatureEngineeringService, Depends(get_fe_service)],
    _user: Annotated[User, Depends(get_current_active_user)],
    symbol: str | None = Query(None),
    feature_name: str | None = Query(None),
    category: str | None = Query(None, pattern="^(price|volume|momentum|volatility|financial|news|macro|breadth)$"),
    as_of_date: date | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    items = await svc.get_values(
        symbol=symbol, feature_name=feature_name, category=category,
        as_of_date=as_of_date, limit=limit, offset=offset,
    )
    return FeatureValueList(
        items=[FeatureValueResponse.from_orm(fv) for fv in items],
        total=len(items),
    )


@router.get("/values/{symbol}", response_model=list[FeatureValueResponse])
async def get_symbol_feature_values(
    symbol: str,
    svc: Annotated[FeatureEngineeringService, Depends(get_fe_service)],
    _user: Annotated[User, Depends(get_current_active_user)],
    as_of_date: date | None = None,
):
    items = await svc.get_values(symbol=symbol.upper(), as_of_date=as_of_date)
    return [FeatureValueResponse.from_orm(fv) for fv in items]


@router.delete("/values/old")
async def clear_old_values(
    svc: Annotated[FeatureEngineeringService, Depends(get_fe_service)],
    _user: Annotated[User, Depends(get_current_active_user)],
    older_than_days: int = Query(90, ge=1),
):
    deleted = await svc.clear_old_values(older_than_days)
    return {"deleted": deleted}
