from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Request, Response, Depends, Header, Query
from fastapi.responses import Response as FastAPIResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import requests
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime, timezone, timedelta


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(mongo_url)
db_name = os.environ.get('DB_NAME', 'halawayat_attar')
db = client[db_name]
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '').strip().lower()
APP_NAME = os.environ.get('APP_NAME', 'halawayat-attar')
EMERGENT_KEY = os.environ.get('EMERGENT_LLM_KEY')

STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================== STORAGE ==============================
storage_key = None

def init_storage(force: bool = False):
    global storage_key
    if storage_key and not force:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key

def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120
    )
    resp.raise_for_status()
    return resp.json()

def get_object(path: str):
    key = init_storage()
    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key}, timeout=60
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

# ============================== MODELS ==============================
def now_iso():
    return datetime.now(timezone.utc).isoformat()

class Category(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name_ar: str
    name_en: str
    slug: str
    order: int = 0

class CategoryCreate(BaseModel):
    name_ar: str
    name_en: str
    slug: str
    order: int = 0

class Product(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name_ar: str
    name_en: str
    description_ar: str = ""
    description_en: str = ""
    price: float
    category_id: Optional[str] = None
    image_url: Optional[str] = None
    is_bestseller: bool = False
    is_available: bool = True
    created_at: str = Field(default_factory=now_iso)

class ProductCreate(BaseModel):
    name_ar: str
    name_en: str
    description_ar: str = ""
    description_en: str = ""
    price: float
    category_id: Optional[str] = None
    image_url: Optional[str] = None
    is_bestseller: bool = False
    is_available: bool = True

class Review(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    author_name: str
    rating: float
    comment_ar: str = ""
    comment_en: str = ""
    is_approved: bool = True
    created_at: str = Field(default_factory=now_iso)

class ReviewCreate(BaseModel):
    author_name: str
    rating: float
    comment_ar: str = ""
    comment_en: str = ""
    is_approved: bool = True

class ReviewPublicCreate(BaseModel):
    author_name: str
    rating: float
    comment: str

class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = "singleton"
    phone: str = "052 347 6628"
    whatsapp: str = "971523476628"
    hours_ar: str = "يومياً من 8 صباحاً حتى 12 منتصف الليل"
    hours_en: str = "Daily 8 AM – 12 AM"
    address_ar: str = "الخان، الشارقة، الإمارات العربية المتحدة"
    address_en: str = "Al Khan, Sharjah, United Arab Emirates"
    map_url: str = "https://www.google.com/maps/search/?api=1&query=Al+Khan+Sharjah+UAE"
    customer_count: int = 5000
    rating: float = 4.5
    reviews_count: int = 25
    instagram: str = ""
    tiktok: str = ""
    facebook: str = ""
    snapchat: str = ""
    google_reviews_url: str = ""
    hero_tagline_ar: str = "طعم يجمعنا… وحلا يستاهل التجربة"
    hero_tagline_en: str = "A Taste That Brings Us Together"
    hero_description_ar: str = "نقدم لكم تشكيلة مميزة من الحلويات والمخبوزات الطازجة بجودة عالية وطعم لا يُنسى."
    hero_description_en: str = "A curated selection of fresh sweets and baked goods, crafted with quality and unforgettable taste."

class SettingsUpdate(BaseModel):
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    hours_ar: Optional[str] = None
    hours_en: Optional[str] = None
    address_ar: Optional[str] = None
    address_en: Optional[str] = None
    map_url: Optional[str] = None
    customer_count: Optional[int] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    instagram: Optional[str] = None
    tiktok: Optional[str] = None
    facebook: Optional[str] = None
    snapchat: Optional[str] = None
    google_reviews_url: Optional[str] = None
    hero_tagline_ar: Optional[str] = None
    hero_tagline_en: Optional[str] = None
    hero_description_ar: Optional[str] = None
    hero_description_en: Optional[str] = None

class OrderItem(BaseModel):
    product_id: str
    name: str
    price: float
    quantity: int

class OrderCreate(BaseModel):
    customer_name: str
    customer_phone: Optional[str] = ""
    notes: Optional[str] = ""
    order_type: str = "delivery"  # delivery | pickup
    payment_method: str = "cash"  # cash | card
    address: Optional[str] = ""
    items: List[OrderItem]
    total: float

class Order(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    customer_name: str
    customer_phone: str = ""
    notes: str = ""
    order_type: str = "delivery"
    payment_method: str = "cash"
    address: str = ""
    items: List[OrderItem]
    total: float
    status: str = "new"
    is_paid: bool = False
    paid_at: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)

# ============================== AUTH ==============================
async def get_current_user(request: Request, authorization: Optional[str] = Header(None)):
    token = request.cookies.get("session_token")
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    expires_at = session["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def is_admin_email(email: str) -> bool:
    email = (email or "").strip().lower()
    if not email:
        return False
    if email == ADMIN_EMAIL:
        return True
    doc = await db.admins.find_one({"email": email}, {"_id": 0})
    return doc is not None

async def require_admin(user=Depends(get_current_user)):
    if not await is_admin_email(user.get("email", "")):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

class SessionExchangeRequest(BaseModel):
    session_id: str

@api_router.post("/auth/session")
async def auth_session(payload: SessionExchangeRequest, response: Response):
    # REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    resp = requests.get(
        "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
        headers={"X-Session-ID": payload.session_id}, timeout=15
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session_id")
    data = resp.json()
    email = data["email"].strip().lower()
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one({"user_id": user_id}, {"$set": {"name": data.get("name", ""), "picture": data.get("picture", "")}})
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": data.get("name", ""),
            "picture": data.get("picture", ""),
            "created_at": now_iso(),
        })
    session_token = data["session_token"]
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at,
        "created_at": now_iso(),
    })
    response.set_cookie(
        key="session_token", value=session_token,
        max_age=7*24*3600, httponly=True, secure=True, samesite="none", path="/"
    )
    is_admin = await is_admin_email(email)
    return {"user_id": user_id, "email": email, "name": data.get("name", ""), "picture": data.get("picture", ""), "is_admin": is_admin}

@api_router.get("/auth/me")
async def auth_me(user=Depends(get_current_user)):
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "name": user.get("name", ""),
        "picture": user.get("picture", ""),
        "is_admin": await is_admin_email(user.get("email", "")),
        "is_owner": user.get("email", "").strip().lower() == ADMIN_EMAIL,
    }

@api_router.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/", samesite="none", secure=True)
    return {"ok": True}

# ============================== ADMIN USERS (MULTI-ADMIN) ==============================
class AdminEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    added_by: str = ""
    created_at: str = Field(default_factory=now_iso)

class AdminEntryCreate(BaseModel):
    email: str

async def require_owner(user=Depends(get_current_user)):
    if user.get("email", "").strip().lower() != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Owner access required")
    return user

@api_router.get("/admins", response_model=List[AdminEntry])
async def list_admins(_owner=Depends(require_owner)):
    docs = await db.admins.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return docs

@api_router.post("/admins", response_model=AdminEntry)
async def add_admin(payload: AdminEntryCreate, owner=Depends(require_owner)):
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email")
    if email == ADMIN_EMAIL:
        raise HTTPException(status_code=400, detail="Owner is already admin")
    existing = await db.admins.find_one({"email": email}, {"_id": 0})
    if existing:
        return existing
    entry = AdminEntry(email=email, added_by=owner.get("email", ""))
    await db.admins.insert_one(entry.model_dump())
    return entry

@api_router.delete("/admins/{aid}")
async def remove_admin(aid: str, _owner=Depends(require_owner)):
    await db.admins.delete_one({"id": aid})
    return {"ok": True}

# ============================== CATEGORIES ==============================
@api_router.get("/categories", response_model=List[Category])
async def list_categories():
    docs = await db.categories.find({}, {"_id": 0}).sort("order", 1).to_list(1000)
    return docs

@api_router.post("/categories", response_model=Category)
async def create_category(payload: CategoryCreate, _admin=Depends(require_admin)):
    cat = Category(**payload.model_dump())
    await db.categories.insert_one(cat.model_dump())
    return cat

@api_router.put("/categories/{cid}", response_model=Category)
async def update_category(cid: str, payload: CategoryCreate, _admin=Depends(require_admin)):
    updates = payload.model_dump()
    await db.categories.update_one({"id": cid}, {"$set": updates})
    doc = await db.categories.find_one({"id": cid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Category not found")
    return doc

@api_router.delete("/categories/{cid}")
async def delete_category(cid: str, _admin=Depends(require_admin)):
    await db.categories.delete_one({"id": cid})
    return {"ok": True}

# ============================== PRODUCTS ==============================
@api_router.get("/products", response_model=List[Product])
async def list_products(category_id: Optional[str] = None, bestseller: Optional[bool] = None):
    q = {}
    if category_id:
        q["category_id"] = category_id
    if bestseller is not None:
        q["is_bestseller"] = bestseller
    docs = await db.products.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return docs

@api_router.post("/products", response_model=Product)
async def create_product(payload: ProductCreate, _admin=Depends(require_admin)):
    p = Product(**payload.model_dump())
    await db.products.insert_one(p.model_dump())
    return p

@api_router.put("/products/{pid}", response_model=Product)
async def update_product(pid: str, payload: ProductCreate, _admin=Depends(require_admin)):
    updates = payload.model_dump()
    await db.products.update_one({"id": pid}, {"$set": updates})
    doc = await db.products.find_one({"id": pid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")
    return doc

@api_router.delete("/products/{pid}")
async def delete_product(pid: str, _admin=Depends(require_admin)):
    await db.products.delete_one({"id": pid})
    return {"ok": True}

# ============================== REVIEWS ==============================
@api_router.get("/reviews", response_model=List[Review])
async def list_reviews(include_pending: bool = False):
    q = {} if include_pending else {"is_approved": True}
    docs = await db.reviews.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return docs

@api_router.get("/reviews/pending", response_model=List[Review])
async def list_pending_reviews(_admin=Depends(require_admin)):
    docs = await db.reviews.find({"is_approved": False}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return docs

@api_router.post("/reviews/public", response_model=Review)
async def submit_public_review(payload: ReviewPublicCreate):
    rating = max(0.0, min(5.0, float(payload.rating)))
    name = payload.author_name.strip()[:60] or "زائر"
    comment = payload.comment.strip()[:600]
    if not comment:
        raise HTTPException(status_code=400, detail="Comment is required")
    # Store as pending; put same text in both fields; admin can localize later.
    r = Review(author_name=name, rating=rating, comment_ar=comment, comment_en=comment, is_approved=False)
    await db.reviews.insert_one(r.model_dump())
    return r

@api_router.post("/reviews", response_model=Review)
async def create_review(payload: ReviewCreate, _admin=Depends(require_admin)):
    r = Review(**payload.model_dump())
    await db.reviews.insert_one(r.model_dump())
    return r

@api_router.put("/reviews/{rid}", response_model=Review)
async def update_review(rid: str, payload: ReviewCreate, _admin=Depends(require_admin)):
    updates = payload.model_dump()
    await db.reviews.update_one({"id": rid}, {"$set": updates})
    doc = await db.reviews.find_one({"id": rid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Review not found")
    return doc

@api_router.post("/reviews/{rid}/approve", response_model=Review)
async def approve_review(rid: str, _admin=Depends(require_admin)):
    await db.reviews.update_one({"id": rid}, {"$set": {"is_approved": True}})
    doc = await db.reviews.find_one({"id": rid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Review not found")
    return doc

@api_router.delete("/reviews/{rid}")
async def delete_review(rid: str, _admin=Depends(require_admin)):
    await db.reviews.delete_one({"id": rid})
    return {"ok": True}

# ============================== BANNERS / OFFERS ==============================
class Banner(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title_ar: str
    title_en: str
    subtitle_ar: str = ""
    subtitle_en: str = ""
    image_url: Optional[str] = None
    cta_text_ar: str = ""
    cta_text_en: str = ""
    cta_link: str = ""
    is_active: bool = True
    order: int = 0
    created_at: str = Field(default_factory=now_iso)

class BannerCreate(BaseModel):
    title_ar: str
    title_en: str
    subtitle_ar: str = ""
    subtitle_en: str = ""
    image_url: Optional[str] = None
    cta_text_ar: str = ""
    cta_text_en: str = ""
    cta_link: str = ""
    is_active: bool = True
    order: int = 0

@api_router.get("/banners", response_model=List[Banner])
async def list_banners(only_active: bool = True):
    q = {"is_active": True} if only_active else {}
    docs = await db.banners.find(q, {"_id": 0}).sort("order", 1).to_list(200)
    return docs

@api_router.post("/banners", response_model=Banner)
async def create_banner(payload: BannerCreate, _admin=Depends(require_admin)):
    b = Banner(**payload.model_dump())
    await db.banners.insert_one(b.model_dump())
    return b

@api_router.put("/banners/{bid}", response_model=Banner)
async def update_banner(bid: str, payload: BannerCreate, _admin=Depends(require_admin)):
    await db.banners.update_one({"id": bid}, {"$set": payload.model_dump()})
    doc = await db.banners.find_one({"id": bid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Banner not found")
    return doc

@api_router.delete("/banners/{bid}")
async def delete_banner(bid: str, _admin=Depends(require_admin)):
    await db.banners.delete_one({"id": bid})
    return {"ok": True}

# ============================== STATS ==============================
@api_router.get("/stats/summary")
async def stats_summary(_admin=Depends(require_admin)):
    now = datetime.now(timezone.utc)
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    start_week = (now - timedelta(days=7)).isoformat()
    # Stats count PAID orders only
    paid_filter = {"is_paid": True}
    total_orders = await db.orders.count_documents(paid_filter)
    orders_today = await db.orders.count_documents({**paid_filter, "created_at": {"$gte": start_today}})
    orders_week = await db.orders.count_documents({**paid_filter, "created_at": {"$gte": start_week}})
    pipeline_total = [{"$match": paid_filter}, {"$group": {"_id": None, "sum": {"$sum": "$total"}}}]
    total_revenue_doc = await db.orders.aggregate(pipeline_total).to_list(1)
    revenue_total = total_revenue_doc[0]["sum"] if total_revenue_doc else 0
    pipeline_week = [{"$match": {**paid_filter, "created_at": {"$gte": start_week}}}, {"$group": {"_id": None, "sum": {"$sum": "$total"}}}]
    revenue_week_doc = await db.orders.aggregate(pipeline_week).to_list(1)
    revenue_week = revenue_week_doc[0]["sum"] if revenue_week_doc else 0
    pending_reviews = await db.reviews.count_documents({"is_approved": False})
    unpaid_orders = await db.orders.count_documents({"is_paid": False})
    return {
        "total_orders": total_orders,
        "orders_today": orders_today,
        "orders_week": orders_week,
        "revenue_total": round(revenue_total, 2),
        "revenue_week": round(revenue_week, 2),
        "pending_reviews": pending_reviews,
        "unpaid_orders": unpaid_orders,
        "products_count": await db.products.count_documents({}),
    }

@api_router.get("/stats/top-items")
async def stats_top_items(days: int = 7, limit: int = 8, _admin=Depends(require_admin)):
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days)).isoformat()
    pipeline = [
        {"$match": {"is_paid": True, "created_at": {"$gte": start}}},
        {"$unwind": "$items"},
        {"$group": {"_id": "$items.name", "quantity": {"$sum": "$items.quantity"}, "revenue": {"$sum": {"$multiply": ["$items.price", "$items.quantity"]}}}},
        {"$sort": {"quantity": -1}},
        {"$limit": limit},
    ]
    rows = await db.orders.aggregate(pipeline).to_list(limit)
    return [{"name": r["_id"], "quantity": r["quantity"], "revenue": round(r["revenue"], 2)} for r in rows]

# ============================== SETTINGS ==============================
@api_router.get("/settings", response_model=Settings)
async def get_settings():
    doc = await db.settings.find_one({"id": "singleton"}, {"_id": 0})
    if not doc:
        s = Settings()
        await db.settings.insert_one(s.model_dump())
        return s
    return doc

@api_router.put("/settings", response_model=Settings)
async def update_settings(payload: SettingsUpdate, _admin=Depends(require_admin)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    await db.settings.update_one({"id": "singleton"}, {"$set": updates}, upsert=True)
    doc = await db.settings.find_one({"id": "singleton"}, {"_id": 0})
    return doc

# ============================== ORDERS ==============================
@api_router.post("/orders", response_model=Order)
async def create_order(payload: OrderCreate):
    o = Order(**payload.model_dump())
    doc = o.model_dump()
    await db.orders.insert_one(doc)
    return o

@api_router.get("/orders", response_model=List[Order])
async def list_orders(_admin=Depends(require_admin)):
    docs = await db.orders.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return docs

@api_router.put("/orders/{oid}/status")
async def update_order_status(oid: str, status: str, _admin=Depends(require_admin)):
    await db.orders.update_one({"id": oid}, {"$set": {"status": status}})
    return {"ok": True}

@api_router.put("/orders/{oid}/paid")
async def mark_order_paid(oid: str, paid: bool = True, _admin=Depends(require_admin)):
    updates = {"is_paid": paid, "paid_at": now_iso() if paid else None}
    await db.orders.update_one({"id": oid}, {"$set": updates})
    return {"ok": True, "is_paid": paid}

@api_router.delete("/orders/all")
async def delete_all_orders(_admin=Depends(require_admin)):
    res = await db.orders.delete_many({})
    return {"deleted": res.deleted_count}

@api_router.delete("/orders/{oid}")
async def delete_order(oid: str, _admin=Depends(require_admin)):
    await db.orders.delete_one({"id": oid})
    return {"ok": True}

# ============================== UPLOAD / FILES ==============================
MIME_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}

@api_router.post("/upload")
async def upload(file: UploadFile = File(...), _admin=Depends(require_admin)):
    ext = (file.filename.rsplit(".", 1)[-1] if "." in (file.filename or "") else "bin").lower()
    if ext not in MIME_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image type")
    file_id = str(uuid.uuid4())
    path = f"{APP_NAME}/products/{file_id}.{ext}"
    data = await file.read()
    result = put_object(path, data, MIME_TYPES[ext])
    await db.files.insert_one({
        "id": file_id,
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": MIME_TYPES[ext],
        "size": result["size"],
        "is_deleted": False,
        "created_at": now_iso(),
    })
    return {"id": file_id, "url": f"/api/files/{result['path']}", "path": result["path"]}

@api_router.get("/files/{path:path}")
async def download(path: str):
    record = await db.files.find_one({"storage_path": path, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    data, content_type = get_object(path)
    return FastAPIResponse(content=data, media_type=record.get("content_type", content_type))

# ============================== SEED MENU FROM NOON ==============================
NOON_MENU = [
    ("غريبة", "Ghraybeh", "غريبة بلسمن الحيواني 500 جرام", "Arabic butter cookies with pure ghee — 500g", 26.25, "sweets", True, "cdluirw6_0.jpg"),
    ("هريسة بالقشطة", "Harissa with Cream", "هريسة بالقشطة 500 جرام", "Semolina cake with cream — 500g", 33.25, "sweets", True, "9ir5otvp_0.jpg"),
    ("معمول فستق", "Maamoul Pistachio", "معمول فستق بلسمن الحيواني 500 جرام", "Pistachio maamoul with pure ghee — 500g", 49.50, "sweets", True, "cyt0tjot_0.jpg"),
    ("معمول مد بالفستق", "Maamoul Mad Pistachio", "معمول مد بالفستق والناطف", "Layered maamoul with pistachio & natif", 39.50, "sweets", True, "z9fr90ai_0.jpg"),
    ("بوكس عربي صغير", "Small Arabic Box", "عربي بوكس صغير 500 جرام / 8 أصناف فستق", "Arabic sweets assortment box — 500g / 8 varieties", 92.50, "arabic-sweets", True, "q4ytnuzm_0.jpg"),
    ("مدلوقة", "Madlouka", "مدلوقة بالقشطة 500 جرام", "Madlouka with cream — 500g", 31.25, "sweets", True, "xz76muhj_0.jpg"),
    ("عش البلبل بلحم", "Bulbul Nest with Meat", "عش البلبل لحم نعيمي", "Bulbul nest with premium meat", 62.50, "pastries", False, "8tc2i04v_0.jpg"),
    ("معمول جوز", "Maamoul Walnut", "معمول جوز بلسمن الحيواني 500 جرام", "Walnut maamoul with pure ghee — 500g", 43.50, "sweets", False, "v74a1xeh_0.jpg"),
    ("معمول تمر", "Maamoul Date", "معمول تمر بلسمن الحيواني 500 جرام", "Date maamoul with pure ghee — 500g", 26.25, "sweets", False, "ixb9tb67_0.jpg"),
    ("حلاوة الجبن", "Cheese Halawa", "حلاوة الجبن بالقشطة العربية 500 جرام", "Cheese halawa with Arabic cream — 500g", 25.00, "arabic-sweets", False, "xew05we4_0.jpg"),
    ("قطع كيك", "Cake Slices", "قطع كيك بنكهات متنوعة", "Assorted cake slices", 10.00, "cakes", False, None),
    ("معجوقة", "Maajouqa", "معجوقة بالقشطة 500 جرام", "Maajouqa with cream — 500g", 26.25, "sweets", False, "2m5xpy1s_0.jpg"),
    ("إكلير", "Éclair", "إكلير بالقطعة", "Éclair — per piece", 5.00, "pastries", False, "ajykjoss_0.jpg"),
    ("برازق", "Barazek", "برازق شامية 500 جرام", "Damascene barazek — 500g", 33.25, "sweets", False, "ordprjlh_0.jpg"),
    ("بيتيفور", "Petit Four", "بيتيفور بالزبدة الحيواني 500 جرام", "Petit four with pure butter — 500g", 36.25, "sweets", False, "q745cly9_0.jpg"),
    ("بقلاوة تركية", "Turkish Baklava", "بقلاوة تركية 1.5 كيلو", "Turkish baklava — 1.5kg", 171.50, "arabic-sweets", False, "12_cropped_30Nov2025113559.png"),
    ("هريسة فستق", "Harissa Pistachio", "هريسة فستق بالسمن الحيواني 500 جرام", "Pistachio harissa with pure ghee — 500g", 33.25, "sweets", False, "13_cropped_30Nov2025113628.png"),
    ("وربات قشطة", "Warbat Cream", "وربات بالقشطة 500 جرام بلدية", "Warbat with cream — 500g", 33.25, "sweets", False, "cddvbl1j_0.jpg"),
    ("وربات فستق", "Warbat Pistachio", "وربات فستق حلبي 500 جرام", "Warbat with Aleppo pistachio — 500g", 52.50, "sweets", False, "g752iek4_0.jpg"),
    ("ليالينا", "Layalina", "ليالينا 500 جرام", "Layali Lubnan — 500g", 33.25, "sweets", False, "5e1go3fk_0.jpg"),
    ("فيصلية فستق", "Faisaliya Pistachio", "فيصليات قشطة الحلبي 500 جرام", "Faisaliya with Aleppo pistachio — 500g", 52.50, "sweets", False, "1pbxkdms_0.jpg"),
    ("كعك بماء الجبن", "Cheese Water Kaak", "كعك بماء الجبن 500 جرام", "Kaak with cheese water — 500g", 26.50, "bakery", False, "5lsu37gw_0.jpg"),
    ("قالب كيك شوكولاتة صغير", "Small Chocolate Cake", "قالب كيك صغير بالشوكولاتة", "Small chocolate cake", 66.25, "cakes", False, "19_cropped_30Nov2025113714.png"),
    ("بوكس عربي كبير", "Large Arabic Box", "عربي بوكس كبير 1000 جرام / 8 أصناف فستق", "Arabic sweets box — 1kg / 8 varieties", 184.50, "arabic-sweets", False, "9kg5mq2o_0.jpg"),
    ("كعك حليب", "Milk Kaak", "كعك سمسم/حليب/حبة بركة/يانسون 500 جرام", "Assorted kaak — 500g", 13.25, "bakery", False, "0qmqvo04_0.jpg"),
    ("محلاي مكسرات", "Muhalay Nuts", "محلاي بالمكسرات", "Muhalay with mixed nuts", 9.00, "sweets", False, "23_cropped_27Nov2025074055.png"),
    ("أقراص تمر", "Date Discs", "أقراص تمر بالحبة", "Date discs — per piece", 4.50, "sweets", False, "8n2y3dm6_0.jpg"),
    ("ميديا جوز", "Media Walnut", "ميديا بالجوز", "Media with walnut", 33.25, "sweets", False, "l3pw5dys_0.jpg"),
    ("سابليه", "Sablé", "سابليه", "Sablé cookies", 4.00, "sweets", False, "60gocjs5_0.jpg"),
    ("بسبوسة", "Basbousa", "بسبوسة جوز الهند", "Coconut basbousa", 20.00, "sweets", False, "bor5w1du_0.jpg"),
    ("مكس قشطيات", "Cream Mix", "مكس قشطيات", "Mixed cream sweets", 39.50, "sweets", False, "eh3bokpf_0.jpg"),
    ("بقلاوة فستق", "Pistachio Baklava", "بقلاوة فستق 500 جرام", "Pistachio baklava — 500g", 55.50, "arabic-sweets", False, None),
]

NOON_IMG_BASE = "https://f.nooncdn.com/food_production/food/menu/M7426104109879392600767167A/"

@api_router.post("/seed/menu")
async def seed_menu(_admin=Depends(require_admin)):
    # Fetch category slugs -> ids
    cats = await db.categories.find({}, {"_id": 0}).to_list(1000)
    slug_map = {c["slug"]: c["id"] for c in cats}
    inserted = 0
    for name_ar, name_en, desc_ar, desc_en, price, slug, best, img in NOON_MENU:
        # Skip if same name exists
        existing = await db.products.find_one({"name_ar": name_ar}, {"_id": 0})
        if existing:
            continue
        img_url = f"{NOON_IMG_BASE}{img}" if img else None
        p = Product(
            name_ar=name_ar, name_en=name_en,
            description_ar=desc_ar, description_en=desc_en,
            price=price, category_id=slug_map.get(slug),
            image_url=img_url, is_bestseller=best, is_available=True,
        )
        await db.products.insert_one(p.model_dump())
        inserted += 1
    return {"inserted": inserted, "total_available": len(NOON_MENU)}

@api_router.delete("/seed/menu")
async def clear_seeded_menu(_admin=Depends(require_admin)):
    names = [m[0] for m in NOON_MENU]
    res = await db.products.delete_many({"name_ar": {"$in": names}})
    return {"deleted": res.deleted_count}

# ============================== STARTUP ==============================
@app.on_event("startup")
async def on_startup():
    try:
        init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    # Ensure settings exists
    exists = await db.settings.find_one({"id": "singleton"}, {"_id": 0})
    if not exists:
        await db.settings.insert_one(Settings().model_dump())
    # Seed fake reviews if empty
    if await db.reviews.count_documents({}) == 0:
        sample_reviews = [
            ("سارة الشحي", 5, "أطيب معمول تذوقته! الطعم أصلي والتغليف راقي جداً."),
            ("أحمد الكعبي", 5, "حلويات ممتازة، والخدمة سريعة. جربت البقلاوة التركية وكانت رهيبة."),
            ("منى العلي", 4, "الغريبة ذابت بفمي! صراحة جودة عالية وأسعار مناسبة."),
            ("خالد المرزوقي", 5, "طلبت عربي بوكس لمناسبة وعجب الجميع. توصيل سريع وترتيب جميل."),
            ("هند الظاهري", 5, "معمول الفستق روعة، من أفضل محلات الحلويات في الشارقة."),
            ("عبدالله بن ناصر", 4, "طعم الهريسة بالقشطة يذكرني بطعم البيت. أنصح فيه."),
            ("مريم الحوسني", 5, "الوربات بالفستق ما فيها كلام! والكيك الصغير كان لذيذ جداً."),
            ("سلطان الجسمي", 4, "محل موثوق ونظافة عالية. جربت البرازك والليالينا."),
            ("فاطمة النعيمي", 5, "الحلاوة الجبن ما تنوصف، والبيتيفور طعم الطفولة."),
            ("راشد الشامسي", 5, "من أفضل محلات حلويات في الخان. كل شيء طازج."),
            ("نورة الكندي", 4, "أحب الكعك بماء الجبن، طعم أصيل ومختلف."),
            ("ماجد البدواوي", 5, "طلبت اكثر من مرة، ما خيبوا الظن أبداً. شكراً حلويات عطار."),
        ]
        for name, rating, comment in sample_reviews:
            r = Review(author_name=name, rating=rating, comment_ar=comment, comment_en=comment, is_approved=True)
            await db.reviews.insert_one(r.model_dump())
    if await db.categories.count_documents({}) == 0:
        defaults = [
            {"name_ar": "الأكثر طلبًا", "name_en": "Best Sellers", "slug": "bestsellers", "order": 1},
            {"name_ar": "الحلويات العربية", "name_en": "Arabic Sweets", "slug": "arabic-sweets", "order": 2},
            {"name_ar": "الكيك", "name_en": "Cakes", "slug": "cakes", "order": 3},
            {"name_ar": "المعجنات", "name_en": "Pastries", "slug": "pastries", "order": 4},
            {"name_ar": "المخبوزات", "name_en": "Bakery", "slug": "bakery", "order": 5},
            {"name_ar": "الحلويات", "name_en": "Sweets", "slug": "sweets", "order": 6},
        ]
        for d in defaults:
            await db.categories.insert_one(Category(**d).model_dump())

@api_router.get("/")
async def root():
    return {"message": "Halawayat Attar API"}

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
