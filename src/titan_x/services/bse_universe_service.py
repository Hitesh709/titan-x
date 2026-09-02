"""Load BSE equity listings and attach them to the security universe."""
import re
from datetime import datetime, timezone
from typing import Any
import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from titan_x.models.company import Company
from titan_x.models.company_listing import CompanyListing
logger=structlog.get_logger(__name__)
BSE_LIST_URL="https://api.bseindia.com/BseIndiaAPI/api/ListofScrips/w"
_HEADERS={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36","Accept":"application/json,text/plain,*/*","Referer":"https://www.bseindia.com/"}
class BSEUniverseService:
    def __init__(self,session:AsyncSession)->None:self.session=session
    @staticmethod
    async def _fetch()->Any:
        async with httpx.AsyncClient(headers=_HEADERS,timeout=45.0,follow_redirects=True) as client:
            r=await client.get(BSE_LIST_URL,params={"pageno":1,"pagesize":100000}); r.raise_for_status(); return r.json()
    @staticmethod
    def _walk(value:Any)->list[dict[str,Any]]:
        if isinstance(value,list): return [x for x in value if isinstance(x,dict)]
        if isinstance(value,dict):
            out=[]
            for child in value.values(): out.extend(BSEUniverseService._walk(child))
            return out
        return []
    @staticmethod
    def _pick(row:dict[str,Any],*names:str)->str:
        n={re.sub(r"[^A-Z0-9]","",str(k).upper()):v for k,v in row.items()}
        for name in names:
            v=n.get(re.sub(r"[^A-Z0-9]","",name.upper()))
            if v is not None and str(v).strip(): return str(v).strip()
        return ""
    @classmethod
    def _parse(cls,payload:Any)->list[tuple[str,str,str]]:
        result=[]; seen=set()
        for row in cls._walk(payload):
            symbol=cls._pick(row,"SCRIP_ID","SCRIPID","SCRIP_ID_NEW","SC_NAME","SYMBOL"); code=cls._pick(row,"SCRIP_CD","SCRIPCODE","SCRIP_CODE","SECURITY_CODE"); isin=cls._pick(row,"ISIN","ISIN_NO","ISIN_NUMBER"); name=cls._pick(row,"Scrip_Name","SCRIP_NAME","Security_Name","NAME_OF_COMPANY","COMPANY_NAME")
            symbol=(symbol or code).upper().strip(); isin=isin.upper().strip()
            if not symbol or not isin or (symbol,isin) in seen: continue
            seen.add((symbol,isin)); result.append((symbol,name or symbol,isin))
        return result
    async def load_universe(self)->dict[str,Any]:
        try: rows=self._parse(await self._fetch())
        except Exception as exc:
            logger.warning("bse_universe_fetch_failed",error=str(exc)); return {"source":"bse","loaded":False,"parsed":0,"added":0,"kept":0,"error":str(exc)}
        added=kept=0; now=datetime.now(timezone.utc)
        for symbol,name,isin in rows:
            company=(await self.session.execute(select(Company).where(Company.isin==isin))).scalar_one_or_none()
            if company is None:
                # Keep the actual BSE symbol when it is not already occupied by an NSE security.
                symbol_exists=(await self.session.execute(select(Company).where(Company.symbol==symbol))).scalar_one_or_none()
                company=Company(symbol=(f"BSE_{symbol}"[:16] if symbol_exists else symbol),company_name=name,isin=isin,exchange="BSE",sector="Equity",status="active",created_at=now,updated_at=now)
                self.session.add(company); await self.session.flush(); added+=1
            listing=(await self.session.execute(select(CompanyListing).where(CompanyListing.exchange=="BSE",CompanyListing.symbol==symbol))).scalar_one_or_none()
            if listing is None: self.session.add(CompanyListing(company_id=company.id,exchange="BSE",symbol=symbol,yahoo_symbol=f"{symbol}.BO",is_active=True,created_at=now,updated_at=now))
            else: kept+=1; listing.company_id=company.id; listing.yahoo_symbol=f"{symbol}.BO"; listing.is_active=True; listing.updated_at=now
        await self.session.flush(); return {"source":"bse","loaded":True,"parsed":len(rows),"added":added,"kept":kept}
