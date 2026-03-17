from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


# --- Модели для Продуктов ---
# Базовая модель, соответствующая Poducts_in_palet из Django
class ProductBase(BaseModel):
    """Базовая модель продукта."""

    product_name: str = Field(..., max_length=255, description="Наименование товара")


class ProductCreate(ProductBase):
    """Модель для создания нового продукта."""

    pass


class ProductUpdate(ProductBase):
    """Модель для обновления продукта."""

    pass


class Product(ProductBase):
    """Полная модель продукта, включая ID."""

    id: int = Field(..., description="Уникальный идентификатор продукта")

    class Config:
        orm_mode = True


# --- Модели для Паллет ---


# Это аналог "связующей" модели Poducts_in_palet_quantity
# Он будет использоваться внутри модели паллеты для указания количества
class ProductOnPallet(BaseModel):
    """Описывает один вид продукта и его количество на паллете."""

    product_id: int = Field(..., description="ID продукта из общего справочника")
    quantity: int = Field(..., gt=0, description="Количество единиц продукта")
    # Добавим имя для удобства при отображении, чтобы не "джойнить" каждый раз
    product_name: str = Field(..., description="Наименование товара")

    class Config:
        orm_mode = True


# Базовая модель, соответствующая Palet из Django
class PalletBase(BaseModel):
    """Базовая модель паллеты."""

    number: int = Field(..., description="Номер палеты")
    pallets_from_the_date: date = Field(..., description="Дата поступления")
    pallet_pick_up_date: Optional[date] = Field(None, description="Дата получения")


class PalletCreate(PalletBase):
    """Модель для создания новой паллеты (без продуктов)."""

    pass


class Pallet(PalletBase):
    """Полная модель паллеты, включая её ID и список продуктов."""

    id: int = Field(..., description="Уникальный идентификатор паллеты")
    products: List[ProductOnPallet] = Field(
        default_factory=list, description="Список продукции на паллете"
    )

    class Config:
        orm_mode = True


class PalletUpdate(BaseModel):
    """Модель для частичного обновления данных паллеты."""

    number: Optional[int] = None
    pallets_from_the_date: Optional[date] = None
    pallet_pick_up_date: Optional[date] = None
    # Обратите внимание: products здесь для полного замещения списка,
    # а не для добавления одного продукта.
    products: Optional[List[ProductOnPallet]] = None
