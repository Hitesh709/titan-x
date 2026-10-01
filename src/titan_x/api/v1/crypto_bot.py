from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated
import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User
from titan_x.models.crypto_bot import CryptoPaperBotState
from titan_x.models.crypto_paper import CryptoPaperAccount, CryptoPaperPosition, CryptoPaperTrade
from titan_x.services.crypto_realtime_market import MARKET
from titan_x.services.crypto_realtime_bot import RUNNER

router=APIRouter(prefix="/crypto-paper-bot",tags=["crypto-paper-bot"])
D=Decimal
TFS=("5m","15m","30m")

async def candles(symbol:str,interval:str):
    async with httpx.AsyncClient(timeout=6) as c:
        r=await c.get("https://api.binance.com/api/v3/klines",params={"symbol":symbol,"interval":interval,"limit":180})
        r.raise_for_status()
        return [{"o":D(str(x[1])),"h":D(str(x[2])),"l":D(str(x[3])),"c":D(str(x[4])),"v":D(str(x[5]))} for x in r.json()]

def ema(vals:list[D],n:int)->list[D]:
    k=D(2)/(n+1);e=vals[0];out=[]
    for i,v in enumerate(vals):
        e=v if i==0 else e+(v-e)*k;out.append(e)
    return out

def sma(vals:list[D],n:int)->D:
    return sum(vals[-n:],D(0))/D(n) if len(vals)>=n else D(0)

def signal(c):
    close=[x["c"] for x in c]; e9=ema(close,9);e20=ema(close,20);e50=ema(close,50);i=-1
    gains=[];losses=[]
    for a,b in zip(close[-15:-1],close[-14:]):
        d=b-a;gains.append(max(d,D(0)));losses.append(max(-d,D(0)))
    rs=sum(gains,D(0))/max(sum(losses,D(0)),D("0.00000001"));rsi=D(100)-D(100)/(D(1)+rs)
    m12=ema(close,12);m26=ema(close,26);mac=[a-b for a,b in zip(m12,m26)];ms=ema(mac,9)
    bull=e9[i]>e20[i]>e50[i] and close[i]>e20[i] and rsi>D(52) and mac[i]>ms[i]
    bear=e9[i]<e20[i]<e50[i] and close[i]<e20[i] and rsi<D(48) and mac[i]<ms[i]
    return ("BUY" if bull else "SELL" if bear else "HOLD"),close[i],rsi,abs(close[i]-e20[i])

async def evaluate(symbol:str):
    results=[]
    for tf in TFS:
        c=await candles(symbol,tf);d,p,rsi,atr_proxy=signal(c);results.append({"timeframe":tf,"decision":d,"price":float(p),"rsi":float(rsi),"atr_proxy":float(atr_proxy)})
    final="BUY" if all(x["decision"]=="BUY" for x in results) else "SELL" if all(x["decision"]=="SELL" for x in results) else "HOLD"
    return final,results

async def get_state(session,user_id:int):
    s=(await session.execute(select(CryptoPaperBotState).where(CryptoPaperBotState.user_id==user_id))).scalar_one_or_none()
    if s is None:
        s=CryptoPaperBotState(user_id=user_id);session.add(s);await session.flush()
    return s

@router.get("/realtime-status")
async def realtime_status(current_user:Annotated[User,Depends(get_current_active_user)]):
    return {"market_connected":MARKET.connected,"messages":MARKET.messages,"last_event_ms":MARKET.last_event_ms,"enabled_users":RUNNER.enabled_users,"cycles":RUNNER.cycles,"paper_trades":RUNNER.trades,"last_cycle_ms":RUNNER.last_cycle_ms}

@router.get("/status")
async def status(current_user:Annotated[User,Depends(get_current_active_user)],session:Annotated[AsyncSession,Depends(request_session)]):
    s=await get_state(session,current_user.id)
    return {"symbol":s.symbol,"enabled":s.enabled,"risk_per_trade":float(s.risk_per_trade),"max_position_pct":float(s.max_position_pct),"last_decision":s.last_decision,"last_reason":s.last_reason,"last_run_at":s.last_run_at.isoformat() if s.last_run_at else None}

@router.post("/configure")
async def configure(current_user:Annotated[User,Depends(get_current_active_user)],session:Annotated[AsyncSession,Depends(request_session)],symbol:str="BTCUSDT",enabled:bool=False,risk_per_trade:float=1,max_position_pct:float=25):
    if not symbol.endswith("USDT") or not 0<risk_per_trade<=5 or not 1<=max_position_pct<=25: raise HTTPException(400,"Invalid bot configuration")
    s=await get_state(session,current_user.id);s.symbol=symbol.upper();s.enabled=enabled;s.risk_per_trade=risk_per_trade;s.max_position_pct=max_position_pct
    await session.commit();return {"symbol":s.symbol,"enabled":s.enabled,"risk_per_trade":float(s.risk_per_trade),"max_position_pct":float(s.max_position_pct)}

@router.post("/run")
async def run(current_user:Annotated[User,Depends(get_current_active_user)],session:Annotated[AsyncSession,Depends(request_session)]):
    s=await get_state(session,current_user.id);final,details=await evaluate(s.symbol);s.last_decision=final;s.last_reason=" / ".join(f'{x["timeframe"]}:{x["decision"]}' for x in details);s.last_run_at=datetime.now(timezone.utc)
    account=(await session.execute(select(CryptoPaperAccount).where(CryptoPaperAccount.user_id==current_user.id))).scalar_one_or_none()
    action="HOLD"
    if s.enabled and account:
        p=(await session.execute(select(CryptoPaperPosition).where(CryptoPaperPosition.account_id==account.id,CryptoPaperPosition.symbol==s.symbol))).scalar_one_or_none()
        price=D(str(details[1]["price"]))
        if final=="BUY" and p is None:
            max_notional=account.initial_capital*D(str(float(s.max_position_pct)))/100
            notional=min(account.cash_balance,max_notional)
            qty=(notional/price).quantize(D("0.00000001"))
            if qty>0:
                account.cash_balance-=qty*price
                p=CryptoPaperPosition(account_id=account.id,user_id=current_user.id,symbol=s.symbol,quantity=qty,average_price=price,current_price=price)
                session.add(p);session.add(CryptoPaperTrade(account_id=account.id,user_id=current_user.id,symbol=s.symbol,side="BUY",quantity=qty,price=price,reason="crypto-bot MTF BUY"));action="BUY"
        elif final=="SELL" and p is not None and p.quantity>0:
            proceeds=p.quantity*price;realized=(price-p.average_price)*p.quantity;account.cash_balance+=proceeds
            session.add(CryptoPaperTrade(account_id=account.id,user_id=current_user.id,symbol=s.symbol,side="SELL",quantity=p.quantity,price=price,realized_pnl=realized,reason="crypto-bot MTF SELL"));await session.delete(p);action="SELL"
    await session.commit()
    return {"symbol":s.symbol,"decision":final,"action":action,"timeframes":details,"enabled":s.enabled}
