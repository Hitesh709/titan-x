from decimal import Decimal
from typing import Annotated
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User
from titan_x.models.crypto_paper import CryptoPaperAccount, CryptoPaperPosition, CryptoPaperTrade

router=APIRouter(prefix="/crypto-paper",tags=["crypto-paper"])
D=Decimal
async def price(symbol:str)->D:
    async with httpx.AsyncClient(timeout=5) as c:
        r=await c.get("https://api.binance.com/api/v3/ticker/price",params={"symbol":symbol.upper()})
        r.raise_for_status()
        return D(str(r.json()["price"]))
async def account(session,user_id:int):
    a=(await session.execute(select(CryptoPaperAccount).where(CryptoPaperAccount.user_id==user_id))).scalar_one_or_none()
    if a is None:
        a=CryptoPaperAccount(user_id=user_id,initial_capital=D("100000"),cash_balance=D("100000"),currency="USDT")
        session.add(a);await session.flush()
    return a

@router.get("/account")
async def get_account(current_user:Annotated[User,Depends(get_current_active_user)],session:Annotated[AsyncSession,Depends(request_session)]):
    a=await account(session,current_user.id);await session.commit()
    return {"id":a.id,"initial_capital":float(a.initial_capital),"cash_balance":float(a.cash_balance),"currency":a.currency}

@router.get("/portfolio")
async def portfolio(current_user:Annotated[User,Depends(get_current_active_user)],session:Annotated[AsyncSession,Depends(request_session)]):
    a=await account(session,current_user.id)
    rows=(await session.execute(select(CryptoPaperPosition).where(CryptoPaperPosition.account_id==a.id,CryptoPaperPosition.quantity>0))).scalars().all()
    out=[];market= D("0")
    for p in rows:
        try:p.current_price=await price(p.symbol)
        except Exception: pass
        mv=(p.current_price or D("0"))*p.quantity;market+=mv
        out.append({"symbol":p.symbol,"quantity":float(p.quantity),"average_price":float(p.average_price),"current_price":float(p.current_price) if p.current_price else None,"market_value":float(mv),"unrealized_pnl":float((p.current_price-p.average_price)*p.quantity) if p.current_price else 0,"realized_pnl":float(p.realized_pnl),"stop_price":float(p.stop_price) if p.stop_price else None,"take_price":float(p.take_price) if p.take_price else None})
    await session.commit()
    equity=a.cash_balance+market
    return {"cash_balance":float(a.cash_balance),"market_value":float(market),"equity":float(equity),"positions":out}

@router.post("/trade")
async def trade(current_user:Annotated[User,Depends(get_current_active_user)],session:Annotated[AsyncSession,Depends(request_session)],symbol:str=Query(...,min_length=5,max_length=20),side:str=Query(...,pattern="^(BUY|SELL)$"),quantity:float=Query(...,gt=0),stop_price:float|None=Query(None,gt=0),take_price:float|None=Query(None,gt=0)):
    symbol=symbol.upper();a=await account(session,current_user.id);px=await price(symbol);q=D(str(quantity));cost=px*q
    p=(await session.execute(select(CryptoPaperPosition).where(CryptoPaperPosition.account_id==a.id,CryptoPaperPosition.symbol==symbol))).scalar_one_or_none()
    if side=="BUY":
        if cost>a.cash_balance:raise HTTPException(400,"Insufficient crypto paper cash")
        if cost>(a.initial_capital*D("0.25")):raise HTTPException(400,"Risk limit: max 25% of initial capital per order")
        a.cash_balance-=cost
        if p is None:p=CryptoPaperPosition(account_id=a.id,user_id=current_user.id,symbol=symbol,quantity=q,average_price=px,current_price=px,stop_price=D(str(stop_price)) if stop_price else None,take_price=D(str(take_price)) if take_price else None);session.add(p)
        else:
            total=p.quantity+q;p.average_price=(p.average_price*p.quantity+px*q)/total;p.quantity=total;p.current_price=px
            if stop_price is not None:p.stop_price=D(str(stop_price))
            if take_price is not None:p.take_price=D(str(take_price))
        realized=None
    else:
        if p is None or p.quantity<q:raise HTTPException(400,"Insufficient crypto position")
        a.cash_balance+=cost;realized=(px-p.average_price)*q;p.realized_pnl+=realized;p.quantity-=q
        if p.quantity<=0:await session.delete(p)
    t=CryptoPaperTrade(account_id=a.id,user_id=current_user.id,symbol=symbol,side=side,quantity=q,price=px,realized_pnl=realized,reason="manual")
    session.add(t);await session.commit()
    return {"symbol":symbol,"side":side,"quantity":float(q),"price":float(px),"realized_pnl":float(realized) if realized is not None else None}

@router.get("/trades")
async def trades(current_user:Annotated[User,Depends(get_current_active_user)],session:Annotated[AsyncSession,Depends(request_session)],limit:int=Query(100,ge=1,le=500)):
    rows=(await session.execute(select(CryptoPaperTrade).where(CryptoPaperTrade.user_id==current_user.id).order_by(CryptoPaperTrade.trade_time.desc()).limit(limit))).scalars().all()
    return [{"id":r.id,"symbol":r.symbol,"side":r.side,"quantity":float(r.quantity),"price":float(r.price),"realized_pnl":float(r.realized_pnl) if r.realized_pnl is not None else None,"reason":r.reason,"trade_time":r.trade_time.isoformat()} for r in rows]

@router.get("/analytics")
async def analytics(current_user:Annotated[User,Depends(get_current_active_user)],session:Annotated[AsyncSession,Depends(request_session)]):
    a=await account(session,current_user.id);rows=(await session.execute(select(CryptoPaperTrade).where(CryptoPaperTrade.user_id==current_user.id))).scalars().all()
    sells=[r for r in rows if r.side=="SELL" and r.realized_pnl is not None];wins=[r for r in sells if r.realized_pnl>D("0")];realized=sum((r.realized_pnl or D("0") for r in sells),D("0"));gross_profit=sum((r.realized_pnl for r in wins),D("0"));gross_loss=-sum((r.realized_pnl for r in sells if r.realized_pnl<D("0")),D("0"))
    pf=gross_profit/gross_loss if gross_loss else (D("999") if gross_profit else D("0"))
    return {"initial_capital":float(a.initial_capital),"cash_balance":float(a.cash_balance),"realized_pnl":float(realized),"closed_trades":len(sells),"winning_trades":len(wins),"losing_trades":len(sells)-len(wins),"win_rate":round(len(wins)/len(sells)*100,2) if sells else 0,"profit_factor":float(pf)}
