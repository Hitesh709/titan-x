from collections.abc import Sequence
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.company import Company


class CompanyService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BaseRepository(session, Company)

    async def create(
        self,
        symbol: str,
        company_name: str,
        isin: str,
        exchange: str,
        sector: str | None = None,
        industry: str | None = None,
        market_cap: int | None = None,
        listing_date: date | None = None,
        description: str | None = None,
        website: str | None = None,
    ) -> Company:
        existing = await self._session.execute(
            select(Company).where(
                or_(Company.symbol == symbol, Company.isin == isin)
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError("Company with this symbol or ISIN already exists")
        return await self._repo.create(
            symbol=symbol.upper(),
            company_name=company_name,
            isin=isin,
            exchange=exchange.upper(),
            sector=sector,
            industry=industry,
            market_cap=market_cap,
            listing_date=listing_date,
            description=description,
            website=website,
        )

    async def get_by_id(self, company_id: int) -> Company | None:
        return await self._repo.get(company_id)

    async def get_by_symbol(self, symbol: str) -> Company | None:
        result = await self._session.execute(
            select(Company).where(Company.symbol == symbol.upper())
        )
        return result.scalar_one_or_none()

    async def get_by_isin(self, isin: str) -> Company | None:
        result = await self._session.execute(
            select(Company).where(Company.isin == isin)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        order_by: str = "symbol",
        descending: bool = False,
        search: str | None = None,
        exchange: str | None = None,
        sector: str | None = None,
        industry: str | None = None,
        status: str | None = None,
    ) -> tuple[Sequence[Company], int]:
        stmt = select(Company)

        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Company.symbol.ilike(pattern),
                    Company.company_name.ilike(pattern),
                    Company.isin.ilike(pattern),
                )
            )
        if exchange:
            stmt = stmt.where(Company.exchange == exchange.upper())
        if sector:
            stmt = stmt.where(Company.sector == sector)
        if industry:
            stmt = stmt.where(Company.industry == industry)
        if status:
            stmt = stmt.where(Company.status == status)

        count_stmt = stmt
        total_result = await self._session.execute(count_stmt)
        total = len(total_result.scalars().all())

        order_column = getattr(Company, order_by, Company.symbol)
        stmt = stmt.order_by(order_column.desc() if descending else order_column.asc())
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        companies = result.scalars().all()

        return companies, total

    async def update(
        self,
        company_id: int,
        *,
        company_name: str | None = None,
        sector: str | None = None,
        industry: str | None = None,
        market_cap: int | None = None,
        listing_date: date | None = None,
        description: str | None = None,
        website: str | None = None,
        status: str | None = None,
    ) -> Company | None:
        company = await self._repo.get(company_id)
        if company is None:
            return None

        update_kwargs: dict = {}
        if company_name is not None:
            update_kwargs["company_name"] = company_name
        if sector is not None:
            update_kwargs["sector"] = sector
        if industry is not None:
            update_kwargs["industry"] = industry
        if market_cap is not None:
            update_kwargs["market_cap"] = market_cap
        if listing_date is not None:
            update_kwargs["listing_date"] = listing_date
        if description is not None:
            update_kwargs["description"] = description
        if website is not None:
            update_kwargs["website"] = website
        if status is not None:
            update_kwargs["status"] = status

        if not update_kwargs:
            return company

        return await self._repo.update(company_id, **update_kwargs)

    async def delete(self, company_id: int) -> bool:
        return await self._repo.delete(company_id)

    async def list_sectors(self) -> Sequence[str]:
        result = await self._session.execute(
            select(Company.sector).distinct().where(Company.sector.isnot(None)).order_by(Company.sector)
        )
        return list(result.scalars().all())

    async def list_industries(self) -> Sequence[str]:
        result = await self._session.execute(
            select(Company.industry).distinct().where(Company.industry.isnot(None)).order_by(Company.industry)
        )
        return list(result.scalars().all())

    async def list_exchanges(self) -> Sequence[str]:
        result = await self._session.execute(
            select(Company.exchange).distinct().order_by(Company.exchange)
        )
        return list(result.scalars().all())
