from contextlib import asynccontextmanager
from datetime import datetime
from typing import List

from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from weasyprint import CSS, HTML

from app.pallets_service import crud, database
from app.pallets_service.database import AsyncSessionLocal
from app.pallets_service.routers import admin
from app.pallets_service.routers.pallets import (
    products_router,
)
from app.pallets_service.routers.pallets import (
    router as pallets_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Создаём таблицы и FTS5 при старте, заполняем FTS для существующих паллет."""
    await database.create_db_and_tables()
    async with AsyncSessionLocal() as db:
        await crud.sync_all_pallets_fts(db)
    yield


app = FastAPI(
    title="Pallet Accounting API",
    description="API для учёта паллет на складе временного хранения (СВХ).",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def db_session_middleware(request: Request, call_next):
    async with AsyncSessionLocal() as session:
        request.state.db = session
        response = await call_next(request)
        return response


# Настройка шаблонов
templates = Jinja2Templates(directory="templates")

# "Монтируем" директорию static, чтобы FastAPI мог отдавать из нее файлы
app.mount("/static", StaticFiles(directory="static"), name="static")

# Подключаем роутеры для API и админки
app.include_router(pallets_router)
app.include_router(products_router)
app.include_router(admin.router)


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, q: str = ""):
    """Главная страница: паллеты на складе, с опциональным поиском по продуктам (FTS5)."""
    db = request.state.db
    query = (q or "").strip()
    if query:
        pallets = await crud.search_pallets_by_products(db=db, query=query)
        pallets = [p for p in pallets if p.pallet_pick_up_date is None]
    else:
        pallets = await crud.get_active_pallets(db=db)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "pallets": pallets, "search_query": query},
    )


@app.get("/received", response_class=HTMLResponse)
async def read_received_pallets(request: Request, q: str = ""):
    """Паллеты с датой получения, с опциональным поиском по продуктам (FTS5)."""
    db = request.state.db
    query = (q or "").strip()
    if query:
        pallets = await crud.search_pallets_by_products(db=db, query=query)
        pallets = [p for p in pallets if p.pallet_pick_up_date is not None]
    else:
        pallets = await crud.get_received_pallets(db=db)
    return templates.TemplateResponse(
        "received.html",
        {"request": request, "pallets": pallets, "search_query": query},
    )


@app.get("/print-pallets", response_class=HTMLResponse)
async def view_print_page_legacy(request: Request):
    """
    Этот эндпоинт больше не используется для генерации, но оставлен,
    чтобы старые ссылки не вызывали ошибок. Перенаправляет на главную.
    """
    return RedirectResponse(url="/")


@app.get("/download-pallets-pdf")
async def download_pallets_pdf(request: Request, id: List[int] = Query(...)):
    """
    Генерирует PDF-документ для выбранных паллет и отдает его для просмотра/скачивания.
    Принимает список ID паллет из GET-параметров.
    """
    db = request.state.db
    pallets_to_print = await crud.get_pallets_by_ids(db=db, pallet_ids=id)

    # Рендерим HTML-шаблон в строку
    html_string = templates.get_template("print.html").render({
        "request": request,
        "pallets": pallets_to_print,
        "now": datetime.utcnow,
    })

    # Загружаем CSS для печати, используя 'with' для гарантии закрытия файла
    with open("static/print.css", "r") as f:
        css = CSS(string=f.read())

    # Генерируем PDF
    pdf_bytes = HTML(string=html_string).write_pdf(stylesheets=[css])

    return Response(content=pdf_bytes, media_type="application/pdf")
