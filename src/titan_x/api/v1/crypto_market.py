from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from titan_x.api.dependencies import get_current_active_user
from titan_x.models.user import User
from titan_x.services.crypto_market_data import candles, derivatives_overview, market_overview, ticker, universe

router=APIRouter(prefix="/crypto-market",tags=["crypto-market"])

@router.get("/universe")
async def get_universe(current_user:Annotated[User,Depends(get_current_active_user)],q:str="",limit:int=Query(250,ge=1,le=1000)):
    try:return await universe(q,limit)
    except Exception as exc:raise HTTPException(502,f"Crypto universe unavailable: {exc}") from exc

@router.get("/overview")
async def get_overview(current_user:Annotated[User,Depends(get_current_active_user)]):
    try:return await market_overview()
    except Exception as exc:raise HTTPException(502,f"Crypto market unavailable: {exc}") from exc

@router.get("/ticker")
async def get_ticker(current_user:Annotated[User,Depends(get_current_active_user)],symbol:str=Query(...,min_length=5,max_length=30)):
    try:return (lambda x: {"provider":x[1],"ticker":x[0]})(await ticker(symbol))
    except Exception as exc:raise HTTPException(502,f"Crypto ticker unavailable: {exc}") from exc

@router.get("/candles")
async def get_candles(current_user:Annotated[User,Depends(get_current_active_user)],symbol:str=Query(...),interval:str=Query("15m"),limit:int=Query(220,ge=50,le=1000)):
    if interval not in {"1m","3m","5m","15m","30m","1h","2h","4h","6h","12h","1d","1w","1M"}:
        raise HTTPException(400,"Unsupported crypto timeframe")
    try:
        rows,provider=await candles(symbol,interval,limit)
        return {"symbol":symbol.upper(),"interval":interval,"provider":provider,"candles":rows}
    except Exception as exc:raise HTTPException(502,f"Crypto candles unavailable: {exc}") from exc


@router.get("/derivatives")
async def get_derivatives(current_user:Annotated[User,Depends(get_current_active_user)],limit:int=Query(100,ge=1,le=500)):
    try:return await derivatives_overview(limit)
    except Exception as exc:raise HTTPException(502,f"Crypto derivatives unavailable: {exc}") from exc
