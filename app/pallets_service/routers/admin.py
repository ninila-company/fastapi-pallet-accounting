from datetime import date
from typing import List, Optional

from math import ceil
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.templating import _TemplateResponse

from .. import crud, models


def get_db(request: Request):
    return request.state.db


router = APIRouter(
    prefix="/admin",
    tags=["Admin Panel"],
    responses={404: {"description": "Not found"}},
)

templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse, summary="Показать админ-панель")
async def view_admin_panel(
    request: Request, error: str = "", db: AsyncSession = Depends(get_db)
    , page: int = Query(1, ge=1, description="Номер страницы")
    , per_page: int = Query(10, ge=1, le=100, description="Паллет на страницу")
    , sort_by: Optional[str] = Query(None, description="Поле для сортировки")
    , sort_order: str = Query("desc", description="Порядок сортировки (asc/desc)")
    , status_filter: Optional[str] = Query("all", description="Фильтр по статусу")
) -> _TemplateResponse:
    """Отображает HTML-страницу админ-панели."""
    skip = (page - 1) * per_page
    all_pallets, total_pallets = await crud.get_all_pallets(
        db,
        skip=skip,
        limit=per_page,
        sort_by=sort_by,
        sort_order=sort_order,
        status_filter=status_filter,
    )
    all_products = await crud.get_all_products(db)
    total_pages = ceil(total_pallets / per_page) if per_page > 0 else 0
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "all_pallets": all_pallets,
            "all_products": all_products,
            "current_page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "error": error,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "status_filter": status_filter,
        },
    )


@router.post("/products/create", summary="Создать новый продукт в справочнике")
async def create_new_product(
    product_name: str = Form(...), db: AsyncSession = Depends(get_db)
) -> RedirectResponse:
    """Создает новый продукт и перенаправляет на админ-панель."""
    product_in = models.ProductCreate(product_name=product_name)
    new_product = await crud.create_product(db=db, product_in=product_in)

    if not new_product:
        error_message = f"Продукт с именем «{product_name}» уже существует."
        redirect_url = (
            router.url_path_for("view_admin_panel") + f"?error={error_message}"
        )
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    return RedirectResponse(
        url=router.url_path_for("view_admin_panel"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get(
    "/products/{product_id}/edit",
    response_class=HTMLResponse,
    summary="Страница редактирования продукта",
)
async def view_edit_product_page(
    product_id: int, request: Request, db: AsyncSession = Depends(get_db)
) -> _TemplateResponse:
    """Отображает страницу для редактирования названия продукта."""
    product = await crud.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Продукт не найден")
    return templates.TemplateResponse(
        "edit_product.html", {"request": request, "product": product}
    )


@router.post("/products/{product_id}/edit", summary="Обновить название продукта")
async def update_product_name(
    product_id: int,
    product_name: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Обновляет название продукта и перенаправляет на админ-панель."""
    product_in = models.ProductUpdate(product_name=product_name)
    await crud.update_product(db=db, product_id=product_id, product_in=product_in)
    return RedirectResponse(
        url=router.url_path_for("view_admin_panel"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/products/{product_id}/delete", summary="Удалить продукт из справочника")
async def delete_product(
    product_id: int, db: AsyncSession = Depends(get_db)
) -> RedirectResponse:
    """
    Удаляет продукт из справочника.
    Также удаляет все упоминания этого продукта на всех паллетах.
    """
    deleted = await crud.delete_product(db=db, product_id=product_id)
    if not deleted:
        error_message = f"Продукт с ID {product_id} не найден для удаления."
        redirect_url = (
            router.url_path_for("view_admin_panel") + f"?error={error_message}"
        )
        return RedirectResponse(
            url=redirect_url,
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=router.url_path_for("view_admin_panel"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/pallets/{pallet_id}/delete", summary="Удалить паллету")
async def delete_pallet(
    pallet_id: int, db: AsyncSession = Depends(get_db)
) -> RedirectResponse:
    """Полностью удаляет паллету из системы."""
    deleted = await crud.delete_pallet(db=db, pallet_id=pallet_id)
    if not deleted:
        error_message = f"Паллета с ID {pallet_id} не найдена для удаления."
        redirect_url = (
            router.url_path_for("view_admin_panel") + f"?error={error_message}"
        )
        return RedirectResponse(
            url=redirect_url,
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=router.url_path_for("view_admin_panel"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/pallets", summary="Создать паллету из админ-панели")
async def create_pallet_from_admin(
    number: int = Form(...),
    pallets_from_the_date: date = Form(...),
    pallet_pick_up_date: Optional[date] = Form(None),
    is_ordered: bool = Form(False),
    product_id: Optional[List[int]] = Form(None),
    quantity: Optional[List[int]] = Form(None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Создает новую паллету (при необходимости сразу с составом) и перенаправляет на админ-панель."""
    if product_id is not None and quantity is not None:
        if len(product_id) != len(quantity):
            error_message = "Количество выбранных продуктов не совпадает с количеством введённых количеств."
            redirect_url = (
                router.url_path_for("view_admin_panel") + f"?error={error_message}"
            )
            return RedirectResponse(
                url=redirect_url,
                status_code=status.HTTP_303_SEE_OTHER,
            )

    pallet_in = models.PalletCreate(
        number=number,
        pallets_from_the_date=pallets_from_the_date,
        pallet_pick_up_date=pallet_pick_up_date,
        is_ordered=is_ordered,
    )
    new_pallet = await crud.create_pallet(db=db, pallet_in=pallet_in)

    if product_id is not None and quantity is not None:
        for pid, qty in zip(product_id, quantity):
            if qty is None or qty <= 0:
                continue
            await crud.add_product_to_pallet(
                db=db, pallet_id=new_pallet.id, product_id=pid, quantity=qty
            )

    return RedirectResponse(
        url=router.url_path_for("view_admin_panel"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/pallets/add-product", summary="Добавить несколько продуктов на паллету")
async def add_product_to_pallet(
    pallet_id: int = Form(...),
    product_id: List[int] = Form(...),
    quantity: List[int] = Form(...),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Добавляет один или несколько продуктов на паллету и перенаправляет на админ-панель."""
    if len(product_id) != len(quantity):
        error_message = "Количество выбранных продуктов не совпадает с количеством введённых количеств."
        redirect_url = (
            router.url_path_for("view_admin_panel") + f"?error={error_message}"
        )
        return RedirectResponse(
            url=redirect_url,
            status_code=status.HTTP_303_SEE_OTHER,
        )

    updated_pallet = None
    for pid, qty in zip(product_id, quantity):
        if qty is None or qty <= 0:
            continue
        updated_pallet = await crud.add_product_to_pallet(
            db=db, pallet_id=pallet_id, product_id=pid, quantity=qty
        )

    if not updated_pallet:
        error_message = (
            f"Ошибка: Паллета (ID: {pallet_id}) или указанные продукты не найдены."
        )
        redirect_url = (
            router.url_path_for("view_admin_panel") + f"?error={error_message}"
        )
        return RedirectResponse(
            url=redirect_url,
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=router.url_path_for("view_admin_panel"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get(
    "/pallets/{pallet_id}/edit",
    response_class=HTMLResponse,
    response_model=None,
    summary="Редактировать состав конкретной паллеты",
)
async def edit_pallet(
    pallet_id: int,
    request: Request,
    error: str = "",
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse | _TemplateResponse:
    """Отображает страницу редактирования состава выбранной паллеты."""
    pallet = await crud.get_pallet_by_id(db=db, pallet_id=pallet_id)
    if not pallet:
        error_message = f"Паллета (ID: {pallet_id}) не найдена."
        redirect_url = (
            router.url_path_for("view_admin_panel") + f"?error={error_message}"
        )
        return RedirectResponse(
            url=redirect_url,
            status_code=status.HTTP_303_SEE_OTHER,
        )

    all_products = await crud.get_all_products(db)
    return templates.TemplateResponse(
        "edit_pallet.html",
        {
            "request": request,
            "pallet": pallet,
            "all_products": all_products,
            "error": error,
        },
    )


@router.post(
    "/pallets/{pallet_id}/edit",
    summary="Обновить состав паллеты из админ-панели",
)
async def update_pallet_composition(
    pallet_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Обрабатывает изменения состава паллеты (добавление, обновление, удаление).
    Принимает данные из нескольких форм на странице.
    """
    form_data = await request.form()
    action = form_data.get("action")

    if action == "add":
        product_id = int(form_data.get("product_id"))
        quantity = int(form_data.get("quantity"))
        if quantity is None or quantity <= 0:
            error_message = "Количество должно быть больше нуля."
            redirect_url = (
                router.url_path_for("edit_pallet", pallet_id=pallet_id)
                + f"?error={error_message}"
            )
            return RedirectResponse(
                url=redirect_url,
                status_code=status.HTTP_303_SEE_OTHER,
            )
        updated_pallet = await crud.add_product_to_pallet(
            db=db, pallet_id=pallet_id, product_id=product_id, quantity=quantity
        )
    elif action == "update_all":
        product_ids = [int(pid) for pid in form_data.getlist("product_id")]
        quantities = [int(q) for q in form_data.getlist("quantity")]

        # Полностью заменяем состав паллеты на новый
        await crud.replace_products_on_pallet(
            db=db, pallet_id=pallet_id, product_ids=product_ids, quantities=quantities
        )
        updated_pallet = await crud.get_pallet_by_id(db, pallet_id)

    elif action == "delete":
        product_id = int(form_data.get("product_id"))
        if quantity is None:
            error_message = "Не указано новое количество."
            redirect_url = (
                router.url_path_for("edit_pallet", pallet_id=pallet_id)
                + f"?error={error_message}"
            )
            return RedirectResponse(
                url=redirect_url,
                status_code=status.HTTP_303_SEE_OTHER,
            )
        updated_pallet = await crud.set_product_quantity_on_pallet(
            db=db, pallet_id=pallet_id, product_id=product_id, quantity=0
        )
    else:
        error_message = "Неизвестное действие."
        redirect_url = (
            router.url_path_for("edit_pallet", pallet_id=pallet_id)
            + f"?error={error_message}"
        )
        return RedirectResponse(
            url=redirect_url,
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if not updated_pallet:
        error_message = "Паллета или продукт не найдены."
        redirect_url = (
            router.url_path_for("edit_pallet", pallet_id=pallet_id)
            + f"?error={error_message}"
        )
        return RedirectResponse(
            url=redirect_url,
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=router.url_path_for("edit_pallet", pallet_id=pallet_id),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/pallets/{pallet_id}/update-date",
    summary="Обновить даты паллеты из админ-панели",
)
async def update_pallet_dates(
    pallet_id: int,
    pallets_from_the_date: date = Form(...),
    pallet_pick_up_date: Optional[date] = Form(None),
    is_ordered: bool = Form(False),
    db: AsyncSession = Depends(get_db),
):
    """Обновляет дату поступления и/или дату получения паллеты.

    После установки даты паллета перестанет отображаться на главной странице
    и будет видна только в списке полученных паллет.
    """
    pallet_update = models.PalletUpdate(
        pallets_from_the_date=pallets_from_the_date,
        pallet_pick_up_date=pallet_pick_up_date,
        is_ordered=is_ordered,
    )
    updated_pallet = await crud.partial_update_pallet(
        db=db, pallet_id=pallet_id, pallet_in=pallet_update
    )

    if not updated_pallet:
        error_message = "Паллета не найдена для обновления даты получения."
        redirect_url = (
            router.url_path_for("view_admin_panel") + f"?error={error_message}"
        )
        return RedirectResponse(
            url=redirect_url,
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=router.url_path_for("edit_pallet", pallet_id=pallet_id),
        status_code=status.HTTP_303_SEE_OTHER,
    )
