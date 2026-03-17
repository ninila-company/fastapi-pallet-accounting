from datetime import date

from sqlalchemy import Column, Date, ForeignKey, Integer, String, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

# --- Настройка подключения к базе данных ---
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./pallet_accounting.db"

engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, autocommit=False, autoflush=False, expire_on_commit=False
)

Base = declarative_base()


# --- Модели SQLAlchemy (таблицы в БД) ---


class Product(Base):
    __tablename__ = "products"

    id = Column[int](Integer, primary_key=True, index=True)
    product_name = Column[str](String, unique=True, index=True, nullable=False)

    # Связь для удобного доступа, но не является колонкой в таблице products
    pallets = relationship("ProductOnPallet", back_populates="product")


class Pallet(Base):
    __tablename__ = "pallets"

    id = Column[int](Integer, primary_key=True, index=True)
    number = Column[int](Integer, nullable=False)
    pallets_from_the_date = Column[date](Date, nullable=False)
    pallet_pick_up_date = Column[date](Date, nullable=True)

    products = relationship("ProductOnPallet", back_populates="pallet")


class ProductOnPallet(Base):
    __tablename__ = "products_on_pallets"

    pallet_id = Column[int](Integer, ForeignKey("pallets.id"), primary_key=True)
    product_id = Column[int](Integer, ForeignKey("products.id"), primary_key=True)
    quantity = Column[int](Integer, nullable=False)

    pallet = relationship("Pallet", back_populates="products")
    product = relationship("Product", back_populates="pallets")


# Виртуальная таблица FTS5 для поиска паллет по названиям продуктов на них
PALLET_FTS_TABLE = "pallet_fts"


async def create_db_and_tables():
    """Создаёт таблицы в БД и FTS5-индекс. Вызывать при старте приложения."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # FTS5: pallet_id — для связи, content — индексируемый текст (названия продуктов)
        await conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS pallet_fts USING fts5("
                "pallet_id UNINDEXED, "
                "content, "
                "tokenize='unicode61'"
                ")"
            )
        )
