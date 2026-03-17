from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.pallets_service.database import Pallet, Product

from .. import crud, models


# Зависимость для получения сессии БД
def get_db(request: Request):
    return request.state.db


# Этот роутер теперь будет чисто для JSON API операций с паллетами
router = APIRouter(
    prefix="/pallets",
    tags=["Pallets API"],
    responses={404: {"description": "Not found"}},
)


@router.get(
    "/",
    response_model=List[models.Pallet],
    summary="Получить список всех паллет",
)
async def get_all_pallets(db: AsyncSession = Depends(get_db)) -> List[Pallet]:
    """
    Возвращает полный список всех паллет со всеми вложенными продуктами.
    """
    return await crud.get_all_pallets(db=db)


@router.post(
    "/",
    response_model=models.Pallet,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новую пустую паллету",
)
async def create_pallet(
    pallet_in: models.PalletCreate, db: AsyncSession = Depends(get_db)
):
    """
    Создает новую паллету. Продукты на паллету добавляются отдельно.
    """
    return await crud.create_pallet(db=db, pallet_in=pallet_in)


@router.get(
    "/{pallet_id}",
    response_model=models.Pallet,
    summary="Получить информацию о конкретной паллете",
)
async def get_pallet_by_id(pallet_id: int, db: AsyncSession = Depends(get_db)):
    """
    Возвращает одну паллету по её ID, включая список продуктов на ней.
    """
    pallet = await crud.get_pallet_by_id(db=db, pallet_id=pallet_id)
    if not pallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Паллета с ID {pallet_id} не найдена.",
        )
    return pallet


@router.patch(
    "/{pallet_id}",
    response_model=models.Pallet,
    summary="Частично обновить данные паллеты",
)
async def partial_update_pallet(
    pallet_id: int,
    pallet_in: models.PalletUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Частично обновляет данные паллеты, такие как номер или даты.
    Примечание: для добавления/изменения продуктов используйте
    предназначенные для этого эндпоинты.
    """
    updated_pallet = await crud.partial_update_pallet(
        db=db, pallet_id=pallet_id, pallet_in=pallet_in
    )
    if not updated_pallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Паллета с ID {pallet_id} не найдена для обновления.",
        )
    return updated_pallet


# --- Дополнительный роутер для управления продуктами ---
# Имеет смысл вынести управление продуктами в отдельный роутер,
# чтобы следовать принципам REST.

products_router = APIRouter(
    prefix="/products",
    tags=["Products API"],
    responses={404: {"description": "Not found"}},
)


@products_router.get(
    "/",
    response_model=List[models.Product],
    summary="Получить справочник всех продуктов",
)
async def get_all_products(db: AsyncSession = Depends(get_db)) -> List[Product]:
    """
    Возвращает список всех возможных продуктов, которые могут быть добавлены на паллеты.
    """
    return await crud.get_all_products(db=db)


@products_router.post(
    "/",
    response_model=models.Product,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новый продукт в справочнике",
)
async def create_product(
    product_in: models.ProductCreate, db: AsyncSession = Depends(get_db)
) -> models.Product:
    """
    Создает новый продукт в общем справочнике. Если продукт с таким именем
    (без учета регистра) уже существует, возвращает ошибку 409 Conflict.
    """
    new_product = await crud.create_product(db=db, product_in=product_in)
    if not new_product:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Продукт с именем «{product_in.product_name}» уже существует.",
        )
    return new_product
