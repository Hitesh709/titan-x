import random
from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.core.config import get_settings
from titan_x.db.repository import BaseRepository
from titan_x.infrastructure.market_data_providers import get_market_data_provider
from titan_x.models.company import Company
from titan_x.models.paper_trading import PaperAccount, PaperOrder, PaperPosition, PaperTrade, SimulatedOrder
from titan_x.models.price import DailyPrice
from titan_x.services.market_data_service import MarketDataService
from titan_x.services.price_service import PriceService

logger = structlog.get_logger(__name__)
COMMISSION_RATE = Decimal("0.001")

class PaperTradingError(ValueError): pass

class PaperTradingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session=session; self._account_repo=BaseRepository(session,PaperAccount); self._order_repo=BaseRepository(session,PaperOrder); self._position_repo=BaseRepository(session,PaperPosition); self._trade_repo=BaseRepository(session,PaperTrade); self._simulated_repo=BaseRepository(session,SimulatedOrder); self._price_service=PriceService(session)
    async def create_account(self,user_id:int,initial_capital:Decimal=Decimal("100000.00"))->PaperAccount:
        existing=await self.get_account(user_id)
        if existing is not None:return existing
        return await self._account_repo.create(user_id=user_id,initial_capital=initial_capital,cash_balance=initial_capital)
    async def get_account(self,user_id:int)->PaperAccount|None:
        return (await self._session.execute(select(PaperAccount).where(PaperAccount.user_id==user_id))).scalar_one_or_none()
    async def get_account_summary(self,user_id:int)->dict[str,Any]|None:
        account=await self.get_account(user_id)
        if account is None:return None
        positions=(await self._session.execute(select(PaperPosition).where(PaperPosition.account_id==account.id,PaperPosition.user_id==user_id))).scalars().all()
        invested=Decimal("0"); current=Decimal("0"); unrealized=Decimal("0"); realized=Decimal("0")
        for p in positions:
            invested+=p.cost_basis; realized+=p.realized_pnl
            if p.current_price and p.quantity:
                mv=p.current_price*p.quantity; current+=mv; unrealized+=mv-p.cost_basis
        total=realized+unrealized
        return {"account_id":account.id,"initial_capital":float(account.initial_capital),"cash_balance":float(account.cash_balance),"portfolio_value":float(account.cash_balance+current),"total_invested":float(invested),"total_realized_pnl":float(realized),"total_unrealized_pnl":float(unrealized),"total_pnl":float(total),"total_pnl_pct":round(float(total/account.initial_capital*100),2) if account.initial_capital else 0,"positions_count":len(positions),"is_active":account.is_active}
    async def place_order(self,user_id:int,symbol:str,side:str,order_type:str,quantity:int,price:Decimal|None=None,stop_price:Decimal|None=None,time_in_force:str="day")->PaperOrder:
        account=await self.get_account(user_id)
        if account is None:raise PaperTradingError("No paper account")
        if not account.is_active:raise PaperTradingError("Account is inactive")
        if quantity<=0:raise PaperTradingError("Quantity must be positive")
        if side not in ("buy","sell"):raise PaperTradingError("Side must be 'buy' or 'sell'")
        if order_type not in ("market","limit","stop","stop_limit"):raise PaperTradingError("Invalid order type")
        order=await self._order_repo.create(account_id=account.id,user_id=user_id,symbol=symbol.upper(),side=side,order_type=order_type,quantity=quantity,price=price,stop_price=stop_price,time_in_force=time_in_force,status="pending")
        latest=await self._price_service.get_latest_price(symbol); current=Decimal(str(latest.close)) if latest else None
        if current is None and order_type=="market":current=await self._try_fetch_market_price(symbol)
        if order_type=="market" and current:await self._fill_order(order,account,current)
        elif order_type=="limit" and price and current:
            if (side=="buy" and current<=price) or (side=="sell" and current>=price):await self._fill_order(order,account,current)
            else:order.status="open";await self._session.flush()
        elif order_type=="stop" and stop_price and current:
            if (side=="buy" and current>=stop_price) or (side=="sell" and current<=stop_price):await self._fill_order(order,account,current)
            else:order.status="open";await self._session.flush()
        else:order.status="open";await self._session.flush()
        await self._session.refresh(order);return order
    async def _try_fetch_market_price(self,symbol:str)->Decimal|None:
        try:
            settings=get_settings()
            if settings.market_data_provider.lower()=="mock":return None
            q=(await MarketDataService(self._session).get_quotes([symbol])).get("quotes") or [None]; q=q[0]
            if not q:return None
            if str(q.get("source") or "").lower() in ("mock","yahoo-fallback","alphavantage-fallback"):return None
            value=q.get("last_price"); price=Decimal(str(value)) if value is not None else None
            return price if price and price>0 else None
        except Exception:logger.warning("market_quote_unavailable",symbol=symbol);return None
    async def cancel_order(self,order_id:int,user_id:int)->bool:
        order=await self._order_repo.get(order_id)
        if order is None or order.user_id!=user_id:return False
        if order.status in ("filled","cancelled","rejected"):return False
        order.status="cancelled";await self._session.flush();return True
    async def list_orders(self,user_id:int,status:str|None=None,skip:int=0,limit:int=50)->tuple[Sequence[PaperOrder],int]:
        stmt=select(PaperOrder).where(PaperOrder.user_id==user_id); count=select(func.count()).select_from(PaperOrder).where(PaperOrder.user_id==user_id)
        if status:stmt=stmt.where(PaperOrder.status==status);count=count.where(PaperOrder.status==status)
        total=(await self._session.execute(count)).scalar() or 0; rows=(await self._session.execute(stmt.order_by(desc(PaperOrder.created_at)).offset(skip).limit(limit))).scalars().all();return list(rows),total
    async def get_order(self,order_id:int,user_id:int)->PaperOrder|None:
        o=await self._order_repo.get(order_id);return o if o and o.user_id==user_id else None
    async def process_open_orders(self,symbol:str)->int:
        latest=await self._price_service.get_latest_price(symbol)
        if not latest:return 0
        current=Decimal(str(latest.close));filled=0
        orders=(await self._session.execute(select(PaperOrder).where(PaperOrder.symbol==symbol,PaperOrder.status=="open"))).scalars().all()
        for order in orders:
            account=await self._session.get(PaperAccount,order.account_id)
            if not account or not account.is_active:continue
            should=(order.order_type=="limit" and order.price and ((order.side=="buy" and current<=order.price) or (order.side=="sell" and current>=order.price))) or (order.order_type=="stop" and order.stop_price and ((order.side=="buy" and current>=order.stop_price) or (order.side=="sell" and current<=order.stop_price))) or (order.order_type=="stop_limit" and order.price and order.stop_price and ((order.side=="buy" and current>=order.stop_price and current<=order.price) or (order.side=="sell" and current<=order.stop_price and current>=order.price)))
            if should:await self._fill_order(order,account,current);filled+=1
        return filled
    def _compute_slippage(self,order:PaperOrder,fill_price:Decimal)->Decimal|None:
        ref=order.price if order.order_type=="limit" and order.price else order.stop_price if order.order_type in ("stop","stop_limit") else None
        return (fill_price-ref).quantize(Decimal("0.01")) if ref is not None else None
    async def _fill_order(self,order:PaperOrder,account:PaperAccount,fill_price:Decimal)->None:
        quantity=order.quantity-order.filled_quantity
        if quantity<=0:return
        commission=(fill_price*quantity*COMMISSION_RATE).quantize(Decimal("0.01"));total=fill_price*quantity+commission;now=datetime.now(timezone.utc)
        pos=(await self._session.execute(select(PaperPosition).where(PaperPosition.account_id==account.id,PaperPosition.user_id==order.user_id,PaperPosition.symbol==order.symbol))).scalar_one_or_none()
        if order.side=="buy":
            if account.cash_balance<total:order.status="rejected";order.rejection_reason="Insufficient cash";await self._session.flush();return
            account.cash_balance-=total
            if pos:
                shares=pos.quantity+quantity;cost=pos.cost_basis+fill_price*quantity;pos.average_price=(cost/shares).quantize(Decimal("0.01"));pos.quantity=shares;pos.cost_basis=cost
            else:pos=await self._position_repo.create(account_id=account.id,user_id=order.user_id,symbol=order.symbol,quantity=quantity,average_price=fill_price,cost_basis=fill_price*quantity)
            realized=None
        else:
            if not pos or pos.quantity<quantity:order.status="rejected";order.rejection_reason="Insufficient shares";await self._session.flush();return
            account.cash_balance+=fill_price*quantity-commission;realized=(fill_price-pos.average_price)*quantity;pos.quantity-=quantity;pos.realized_pnl+=realized;pos.cost_basis=pos.average_price*pos.quantity
        order.slippage=self._compute_slippage(order,fill_price);order.filled_quantity+=quantity;order.status="filled" if order.filled_quantity>=order.quantity else "partially_filled";order.filled_at=now
        trade=await self._trade_repo.create(order_id=order.id,account_id=account.id,user_id=order.user_id,symbol=order.symbol,side=order.side,quantity=quantity,price=fill_price,commission=commission,realized_pnl=realized)
        if pos:pos.current_price=fill_price
        await self._session.flush();await self._track_simulated_order(order,account,trade,fill_price,commission,realized,now)
    async def _track_simulated_order(self,order,account,trade,fill_price,commission,realized_pnl,now):
        if order.side=="buy":
            await self._simulated_repo.create(account_id=account.id,user_id=order.user_id,symbol=order.symbol,direction="long",entry_price=fill_price,quantity=order.filled_quantity,entry_fee=commission,total_fees=commission,slippage=order.slippage,entry_order_id=order.id,entry_trade_id=trade.id,entry_date=now,status="open");return
        sim=(await self._session.execute(select(SimulatedOrder).where(SimulatedOrder.account_id==account.id,SimulatedOrder.user_id==order.user_id,SimulatedOrder.symbol==order.symbol,SimulatedOrder.status=="open").order_by(SimulatedOrder.entry_date).limit(1))).scalar_one_or_none()
        if sim is None:return
        qty=min(order.filled_quantity,sim.quantity);gross=(fill_price-sim.entry_price)*qty;fee=(sim.entry_fee/sim.quantity)*qty if sim.quantity else Decimal("0");net=gross-fee-commission;sim.gross_pnl=(sim.gross_pnl or 0)+gross;sim.net_pnl=(sim.net_pnl or 0)+net;sim.exit_price=fill_price;sim.exit_fee=commission;sim.total_fees+=commission;sim.exit_order_id=order.id;sim.exit_trade_id=trade.id;sim.exit_date=now;sim.quantity-=qty;sim.entry_fee-=fee
        if sim.quantity<=0:sim.status="closed";sim.outcome="win" if sim.net_pnl>0 else "loss" if sim.net_pnl<0 else "breakeven"
        await self._session.flush()
    async def get_portfolio(self,user_id:int)->list[dict[str,Any]]:
        account=await self.get_account(user_id)
        if account is None:return []
        positions=(await self._session.execute(select(PaperPosition).where(PaperPosition.account_id==account.id,PaperPosition.user_id==user_id,PaperPosition.quantity>0))).scalars().all();result=[]
        for p in positions:
            mv=p.current_price*p.quantity if p.current_price else Decimal("0");up=mv-p.cost_basis if p.current_price else Decimal("0");pct=round(float((p.current_price-p.average_price)/p.average_price*100),2) if p.current_price and p.average_price else 0;sector=await self._position_sector(p.symbol);result.append({"symbol":p.symbol,"sector":sector,"quantity":p.quantity,"average_price":float(p.average_price),"current_price":float(p.current_price) if p.current_price else None,"cost_basis":float(p.cost_basis),"market_value":float(mv),"realized_pnl":float(p.realized_pnl),"unrealized_pnl":float(up),"unrealized_pnl_pct":pct,"allocation_pct":round(float(p.cost_basis/account.cash_balance*100),2) if account.cash_balance else 0})
        return sorted(result,key=lambda x:x["market_value"],reverse=True)
    async def _position_sector(self,symbol:str)->str|None:return (await self._session.execute(select(Company.sector).where(Company.symbol==symbol.upper()))).scalar_one_or_none()
    async def get_sector_exposure(self,user_id:int)->list[dict]:
        portfolio=await self.get_portfolio(user_id);total=sum(p["market_value"] for p in portfolio) or 1;exposure={}
        for p in portfolio:
            sector=p["sector"] or "Unknown";e=exposure.setdefault(sector,{"sector":sector,"market_value":0.0,"positions":0});e["market_value"]+=p["market_value"];e["positions"]+=1
        for e in exposure.values():e["allocation_pct"]=round(e["market_value"]/total*100,2)
        return sorted(exposure.values(),key=lambda x:x["market_value"],reverse=True)
    async def get_equity_curve(self,user_id:int)->list[dict]:
        account=await self.get_account(user_id)
        if account is None:return []
        closed=(await self._session.execute(select(SimulatedOrder).where(SimulatedOrder.user_id==user_id,SimulatedOrder.status=="closed").order_by(SimulatedOrder.exit_date))).scalars().all();positions=(await self._session.execute(select(PaperPosition).where(PaperPosition.account_id==account.id,PaperPosition.user_id==user_id))).scalars().all();unrealized=sum((p.current_price*p.quantity-p.cost_basis for p in positions if p.current_price and p.quantity),Decimal("0"));curve=[];running=account.initial_capital
        for sim in closed:running+=sim.net_pnl or Decimal("0");curve.append({"date":(sim.exit_date or datetime.now(timezone.utc)).isoformat(),"equity":round(float(running),2),"event":f"{sim.symbol} {sim.outcome or 'closed'}"})
        running+=unrealized;curve.append({"date":datetime.now(timezone.utc).isoformat(),"equity":round(float(running),2),"event":"current"});return curve
    async def refresh_prices(self,user_id:int)->int:
        settings=get_settings();account=await self.get_account(user_id)
        if account is None:return 0
        positions=(await self._session.execute(select(PaperPosition).where(PaperPosition.account_id==account.id,PaperPosition.user_id==user_id,PaperPosition.quantity>0))).scalars().all();updated=0
        for p in positions:
            latest=await self._price_service.get_latest_price(p.symbol)
            if latest is None:continue
            base=Decimal(str(latest.close));p.current_price=(base*Decimal(str(1+random.uniform(-0.015,0.015)))).quantize(Decimal("0.01")) if settings.paper_demo_prices else base;updated+=1
        await self._session.flush();return updated
    async def get_pnl_summary(self,user_id:int)->dict[str,Any]:
        account=await self.get_account(user_id)
        if account is None:return {"total_realized_pnl":0,"total_unrealized_pnl":0,"total_pnl":0,"total_pnl_pct":0}
        positions=(await self._session.execute(select(PaperPosition).where(PaperPosition.account_id==account.id,PaperPosition.user_id==user_id))).scalars().all();realized=sum((p.realized_pnl for p in positions),Decimal("0"));unrealized=sum((p.current_price*p.quantity-p.cost_basis for p in positions if p.current_price and p.quantity),Decimal("0"));total=realized+unrealized
        return {"initial_capital":float(account.initial_capital),"cash_balance":float(account.cash_balance),"total_realized_pnl":float(realized),"total_unrealized_pnl":float(unrealized),"total_pnl":float(total),"total_pnl_pct":round(float(total/account.initial_capital*100),2) if account.initial_capital else 0}
    async def get_trade_history(self,user_id:int,skip:int=0,limit:int=50)->tuple[Sequence[PaperTrade],int]:
        total=(await self._session.execute(select(func.count()).select_from(PaperTrade).where(PaperTrade.user_id==user_id))).scalar() or 0;rows=(await self._session.execute(select(PaperTrade).where(PaperTrade.user_id==user_id).order_by(desc(PaperTrade.trade_time)).offset(skip).limit(limit))).scalars().all();return list(rows),total
    async def list_simulated_orders(self,user_id:int,status:str|None=None,outcome:str|None=None,skip:int=0,limit:int=50)->tuple[Sequence[SimulatedOrder],int]:
        stmt=select(SimulatedOrder).where(SimulatedOrder.user_id==user_id);count=select(func.count()).select_from(SimulatedOrder).where(SimulatedOrder.user_id==user_id)
        if status:stmt=stmt.where(SimulatedOrder.status==status);count=count.where(SimulatedOrder.status==status)
        if outcome:stmt=stmt.where(SimulatedOrder.outcome==outcome);count=count.where(SimulatedOrder.outcome==outcome)
        total=(await self._session.execute(count)).scalar() or 0;rows=(await self._session.execute(stmt.order_by(desc(SimulatedOrder.entry_date)).offset(skip).limit(limit))).scalars().all();return list(rows),total
    async def get_simulated_order(self,order_id:int,user_id:int)->SimulatedOrder|None:
        sim=await self._simulated_repo.get(order_id);return sim if sim and sim.user_id==user_id else None
    async def get_performance_report(self,user_id:int)->dict[str,Any]:
        account=await self.get_account(user_id)
        if account is None:return {}
        summary=await self.get_account_summary(user_id);total_trades=(await self._session.execute(select(func.count()).select_from(PaperTrade).where(PaperTrade.user_id==user_id))).scalar() or 0;filled=(await self._session.execute(select(func.count()).select_from(PaperOrder).where(PaperOrder.user_id==user_id,PaperOrder.status=="filled"))).scalar() or 0;cancelled=(await self._session.execute(select(func.count()).select_from(PaperOrder).where(PaperOrder.user_id==user_id,PaperOrder.status=="cancelled"))).scalar() or 0;wins=(await self._session.execute(select(func.count()).select_from(PaperTrade).where(PaperTrade.user_id==user_id,PaperTrade.side=="sell",PaperTrade.realized_pnl.isnot(None),PaperTrade.realized_pnl>0))).scalar() or 0;losses=(await self._session.execute(select(func.count()).select_from(PaperTrade).where(PaperTrade.user_id==user_id,PaperTrade.side=="sell",PaperTrade.realized_pnl.isnot(None),PaperTrade.realized_pnl<0))).scalar() or 0;closed=wins+losses
        return {"account":summary,"total_trades":total_trades,"filled_orders":filled,"cancelled_orders":cancelled,"winning_trades":wins,"losing_trades":losses,"win_rate":round(wins/closed*100,2) if closed else 0}
