from typing import List, Optional

from sqlalchemy import delete, select, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from . import database, models
from .database import PALLET_FTS_TABLE

# --- CRUD для Продуктов ---


async def get_all_products(db: AsyncSession) -> List[database.Product]:
    """Возвращает список всех продуктов из справочника."""
    result = await db.execute(select(database.Product))
    return list(result.scalars().all())


async def get_product_by_id(
    db: AsyncSession, product_id: int
) -> Optional[database.Product]:
    """Находит продукт в справочнике по его ID."""
    result = await db.execute(
        select(database.Product).where(database.Product.id == product_id)
    )
    return result.scalar_one_or_none()


async def get_product_by_name(
    db: AsyncSession, product_name: str
) -> Optional[database.Product]:
    """Находит продукт по имени, чтобы избежать дубликатов."""
    result = await db.execute(
        select(database.Product).where(
            database.Product.product_name.ilike(product_name)
        )
    )
    return result.scalar_one_or_none()


async def create_product(
    db: AsyncSession, product_in: models.ProductCreate
) -> Optional[database.Product]:
    """Создает новый продукт в общем справочнике.

    Возвращает None, если продукт с таким именем уже существует.
    """
    existing_product = await get_product_by_name(db, product_in.product_name)
    if existing_product:
        return None

    new_product = database.Product(**product_in.model_dump())
    db.add(new_product)
    await db.commit()
    await db.refresh(new_product)
    return new_product


async def update_product(
    db: AsyncSession, product_id: int, product_in: models.ProductUpdate
) -> Optional[database.Product]:
    """Обновляет данные продукта."""
    product = await get_product_by_id(db, product_id)
    if not product:
        return None

    update_data = product_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(product, key, value)

    db.add(product)
    await db.commit()
    await db.refresh(product)
    # После изменения имени продукта нужно обновить FTS-индексы всех паллет, где он есть
    pallets_to_resync = await db.execute(
        select(database.ProductOnPallet.pallet_id).where(
            database.ProductOnPallet.product_id == product_id
        )
    )
    for pallet_id in pallets_to_resync.scalars().all():
        await sync_pallet_fts(db, pallet_id)
    return product


async def delete_product(db: AsyncSession, product_id: int) -> bool:
    """Удаляет продукт из справочника."""
    await db.execute(
        text(
            f"DELETE FROM {PALLET_FTS_TABLE} WHERE pallet_id IN (SELECT pallet_id FROM products_on_pallets WHERE product_id = :pid)"
        ),
        {"pid": product_id},
    )
    await db.execute(
        delete(database.ProductOnPallet).where(
            database.ProductOnPallet.product_id == product_id
        )
    )
    result = await db.execute(
        delete(database.Product).where(database.Product.id == product_id)
    )
    await db.commit()
    return result.rowcount > 0


# --- CRUD для Паллет ---


async def get_all_pallets(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    sort_by: Optional[str] = None,
    sort_order: str = "desc",
    status_filter: Optional[str] = None,
) -> tuple[List[database.Pallet], int]:
    """Возвращает список всех паллет с пагинацией и общее количество."""
    # Базовый запрос для подсчета и выборки
    base_stmt = select(database.Pallet)

    # Затем получаем паллеты для текущей страницы с сортировкой
    stmt = select(database.Pallet).options(
        joinedload(database.Pallet.products).joinedload(
            database.ProductOnPallet.product
        )
    )

    # Применяем фильтр по статусу
    if status_filter == "in_stock":
        stmt = stmt.where(database.Pallet.is_ordered.is_(False), database.Pallet.pallet_pick_up_date.is_(None))
        base_stmt = base_stmt.where(database.Pallet.is_ordered.is_(False), database.Pallet.pallet_pick_up_date.is_(None))
    elif status_filter == "in_transit":
        stmt = stmt.where(database.Pallet.is_ordered.is_(True), database.Pallet.pallet_pick_up_date.is_(None))
        base_stmt = base_stmt.where(database.Pallet.is_ordered.is_(True), database.Pallet.pallet_pick_up_date.is_(None))
    elif status_filter == "received":
        stmt = stmt.where(database.Pallet.pallet_pick_up_date.is_not(None))
        base_stmt = base_stmt.where(database.Pallet.pallet_pick_up_date.is_not(None))

    # Сначала получаем общее количество отфильтрованных паллет для пагинации
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total_count_result = await db.execute(count_stmt)
    total_pallets = total_count_result.scalar_one()

    # Применяем сортировку
    sortable_fields = {
        "number": database.Pallet.number,
        "pallets_from_the_date": database.Pallet.pallets_from_the_date,
        "pallet_pick_up_date": database.Pallet.pallet_pick_up_date,
    }
    if sort_by in sortable_fields:
        column = sortable_fields[sort_by]
        if sort_order == "asc":
            stmt = stmt.order_by(column.asc())
        else:
            stmt = stmt.order_by(column.desc())
    else:
        stmt = stmt.order_by(database.Pallet.id.desc())

    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    pallets = list(result.unique().scalars().all())
    return pallets, total_pallets


async def get_pallets_in_stock(db: AsyncSession) -> List[database.Pallet]:
    """Возвращает паллеты, которые на складе (не заказаны и не получены)."""
    stmt = (
        select(database.Pallet)
        .where(
            database.Pallet.is_ordered.is_(False),
            database.Pallet.pallet_pick_up_date.is_(None),
        )
        .options(
            joinedload(database.Pallet.products).joinedload(
                database.ProductOnPallet.product
            )
        )
    )
    result = await db.execute(stmt)
    return list(result.unique().scalars().all())


async def get_pallets_in_transit(db: AsyncSession) -> List[database.Pallet]:
    """Возвращает паллеты, которые в пути (заказаны, но еще не получены)."""
    stmt = (
        select(database.Pallet)
        .where(
            database.Pallet.is_ordered.is_(True),
            database.Pallet.pallet_pick_up_date.is_(None),
        )
        .options(
            joinedload(database.Pallet.products).joinedload(
                database.ProductOnPallet.product
            )
        )
    )
    result = await db.execute(stmt)
    return list(result.unique().scalars().all())


async def get_active_pallets(db: AsyncSession) -> List[database.Pallet]:
    """Возвращает паллеты, которые ещё находятся на складе (без даты получения)."""
    stmt = (
        select(database.Pallet)
        .where(database.Pallet.pallet_pick_up_date.is_(None))
        .options(
            joinedload(database.Pallet.products).joinedload(
                database.ProductOnPallet.product
            )
        )
    )
    result = await db.execute(stmt)
    return list(result.unique().scalars().all())


async def get_received_pallets(db: AsyncSession) -> List[database.Pallet]:
    """Возвращает паллеты, которые уже были получены (имеют дату получения)."""
    stmt = (
        select(database.Pallet)
        .where(database.Pallet.pallet_pick_up_date.is_not(None))
        .options(
            joinedload(database.Pallet.products).joinedload(
                database.ProductOnPallet.product
            )
        )
    )
    result = await db.execute(stmt)
    return list(result.unique().scalars().all())


async def get_pallet_by_id(
    db: AsyncSession, pallet_id: int
) -> Optional[database.Pallet]:
    """Возвращает одну паллету по её ID."""
    stmt = (
        select(database.Pallet)
        .where(database.Pallet.id == pallet_id)
        .options(
            joinedload(database.Pallet.products).joinedload(
                database.ProductOnPallet.product
            )
        )
    )
    result = await db.execute(stmt)
    return result.unique().scalar_one_or_none()


async def get_pallets_by_ids(
    db: AsyncSession, pallet_ids: List[int]
) -> List[database.Pallet]:
    """Возвращает паллеты по списку ID с загруженными продуктами (порядок как в ids)."""
    if not pallet_ids:
        return []
    stmt = (
        select(database.Pallet)
        .where(database.Pallet.id.in_(pallet_ids))
        .options(
            joinedload(database.Pallet.products).joinedload(
                database.ProductOnPallet.product
            )
        )
    )
    result = await db.execute(stmt)
    pallets = list(result.unique().scalars().all())
    id_order = {pid: i for i, pid in enumerate(pallet_ids)}
    pallets.sort(key=lambda p: id_order.get(p.id, 999))
    return pallets


async def _get_pallet_fts_content(db: AsyncSession, pallet_id: int) -> str:
    """Собирает строку из названий всех продуктов на паллете для FTS."""
    pallet = await get_pallet_by_id(db, pallet_id)
    if not pallet or not pallet.products:
        return ""
    return " ".join(pop.product.product_name for pop in pallet.products)


async def sync_pallet_fts(db: AsyncSession, pallet_id: int) -> None:
    """Обновляет запись в FTS5-таблице для паллеты (после изменения состава)."""
    content = await _get_pallet_fts_content(db, pallet_id)
    await db.execute(
        text(f"DELETE FROM {PALLET_FTS_TABLE} WHERE pallet_id = :pid"),
        {"pid": pallet_id},
    )
    await db.execute(
        text(
            f"INSERT INTO {PALLET_FTS_TABLE} (pallet_id, content) VALUES (:pid, :content)"
        ),
        {"pid": pallet_id, "content": content},
    )
    await db.commit()


async def sync_all_pallets_fts(db: AsyncSession) -> None:
    """Заполняет FTS5 для всех паллет (вызов при старте приложения)."""
    result = await db.execute(select(database.Pallet.id))
    for row in result.all():
        await sync_pallet_fts(db, row[0])


def _build_fts_query(user_query: str) -> Optional[str]:
    """
    Строит безопасный FTS5-запрос из строки пользователя.
    Слова объединяются через OR (паллета подходит, если содержит любое слово).
    Экранируются кавычки в словах.
    """
    words = [w.strip() for w in user_query.strip().split() if w.strip()]
    if not words:
        return None
    escaped = ['"' + w.replace('"', '""') + '"' for w in words]
    return " OR ".join(escaped)


async def search_pallets_by_products(
    db: AsyncSession, query: str
) -> List[database.Pallet]:
    """
    Полнотекстовый поиск паллет по названиям продуктов на них (FTS5).
    Возвращает паллеты с загруженными продуктами, порядок по релевантности (bm25).
    """
    fts_query = _build_fts_query(query)
    if not fts_query:
        return []

    # FTS5: MATCH и опционально ORDER BY bm25 для релевантности
    stmt = text(
        f"SELECT pallet_id, bm25({PALLET_FTS_TABLE}) AS rank "
        f"FROM {PALLET_FTS_TABLE} "
        f"WHERE {PALLET_FTS_TABLE} MATCH :q "
        f"ORDER BY rank"
    )
    result = await db.execute(stmt, {"q": fts_query})
    rows = result.all()
    if not rows:
        return []
    pallet_ids = [r[0] for r in rows]
    return await get_pallets_by_ids(db, pallet_ids)


async def create_pallet(
    db: AsyncSession, pallet_in: models.PalletCreate
) -> database.Pallet:
    """Создает новую пустую паллету и добавляет ее в хранилище."""
    new_pallet = database.Pallet(**pallet_in.model_dump())
    db.add(new_pallet)
    await db.commit()
    await db.refresh(new_pallet)
    await sync_pallet_fts(db, new_pallet.id)
    return new_pallet


async def delete_pallet(db: AsyncSession, pallet_id: int) -> bool:
    """Удаляет паллету и связанные с ней записи."""
    pallet = await get_pallet_by_id(db, pallet_id)
    if not pallet:
        return False

    # 1. Удаляем из FTS-индекса
    await db.execute(
        text(f"DELETE FROM {PALLET_FTS_TABLE} WHERE pallet_id = :pid"),
        {"pid": pallet_id},
    )

    # 2. Удаляем записи из связующей таблицы (SQLAlchemy cascade должен это делать, но для явности)
    await db.execute(
        delete(database.ProductOnPallet).where(database.ProductOnPallet.pallet_id == pallet_id)
    )

    # 3. Удаляем саму паллету
    await db.delete(pallet)
    await db.commit()
    return True


async def add_product_to_pallet(
    db: AsyncSession, pallet_id: int, product_id: int, quantity: int
) -> Optional[database.Pallet]:
    """Добавляет указанное количество продукта на существующую паллету."""
    pallet = await get_pallet_by_id(db, pallet_id)
    product = await get_product_by_id(db, product_id)

    if not pallet or not product:
        return None

    result = await db.execute(
        select(database.ProductOnPallet).where(
            database.ProductOnPallet.pallet_id == pallet_id,
            database.ProductOnPallet.product_id == product_id,
        )
    )
    product_on_pallet = result.scalar_one_or_none()

    if product_on_pallet:
        product_on_pallet.quantity += quantity
    else:
        product_on_pallet = database.ProductOnPallet(
            pallet_id=pallet_id, product_id=product_id, quantity=quantity
        )
        db.add(product_on_pallet)

    await db.commit()
    await db.refresh(pallet)
    await sync_pallet_fts(db, pallet_id)
    return pallet


async def partial_update_pallet(
    db: AsyncSession, pallet_id: int, pallet_in: models.PalletUpdate
) -> Optional[database.Pallet]:
    """Находит паллету и обновляет только переданные поля."""
    existing_pallet = await get_pallet_by_id(db, pallet_id)
    if not existing_pallet:
        return None

    update_data = pallet_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(existing_pallet, key, value)

    db.add(existing_pallet)
    await db.commit()
    await db.refresh(existing_pallet)
    return existing_pallet


async def set_product_quantity_on_pallet(
    db: AsyncSession, pallet_id: int, product_id: int, quantity: int
) -> Optional[database.Pallet]:
    """Устанавливает точное количество продукта на паллете.

    Если quantity <= 0, продукт будет удалён с паллеты.
    Возвращает обновлённую паллету или None, если паллета/продукт не найдены.
    """
    pallet = await get_pallet_by_id(db, pallet_id)
    product = await get_product_by_id(db, product_id)

    if not pallet or not product:
        return None

    result = await db.execute(
        select(database.ProductOnPallet).where(
            database.ProductOnPallet.pallet_id == pallet_id,
            database.ProductOnPallet.product_id == product_id,
        )
    )
    product_on_pallet = result.scalar_one_or_none()

    if quantity <= 0:
        if product_on_pallet:
            await db.delete(product_on_pallet)
            await db.commit()
        await db.refresh(pallet)
        await sync_pallet_fts(db, pallet_id)
        return pallet

    if product_on_pallet:
        product_on_pallet.quantity = quantity
    else:
        product_on_pallet = database.ProductOnPallet(
            pallet_id=pallet_id, product_id=product_id, quantity=quantity
        )
        db.add(product_on_pallet)

    await db.commit()
    await db.refresh(pallet)
    await sync_pallet_fts(db, pallet_id)
    return pallet


async def replace_products_on_pallet(
    db: AsyncSession, pallet_id: int, product_ids: List[int], quantities: List[int]
) -> None:
    """Полностью заменяет состав паллеты на новый.

    Сначала удаляет все старые продукты, затем добавляет новые.
    """
    # 1. Удаляем все текущие продукты с паллеты
    await db.execute(
        delete(database.ProductOnPallet).where(
            database.ProductOnPallet.pallet_id == pallet_id
        )
    )

    # 2. Добавляем новые продукты
    for pid, qty in zip(product_ids, quantities):
        if qty > 0:
            new_product_on_pallet = database.ProductOnPallet(
                pallet_id=pallet_id, product_id=pid, quantity=qty
            )
            db.add(new_product_on_pallet)
    await db.commit()
