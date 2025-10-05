from fastapi import FastAPI, HTTPException, Depends, Response
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from functools import lru_cache
from typing import List, Optional, Dict
from pathlib import Path
from io import BytesIO
import aiofiles
import os

# Pillow for TIFF handling
from PIL import Image as PILImage, UnidentifiedImageError, ImageFile

# Disable decompression bomb limit for large GeoTIFFs (or set a high cap)
ImageFile.LOAD_TRUNCATED_IMAGES = True
PILImage.MAX_IMAGE_PIXELS = None  # set to a large int for stricter guard, e.g., 3_000_000_000

# DB session and models
from database.db import get_db
from database.models import Image, Annotation, User

# ---------- App & CORS ----------
app = FastAPI(title="Space Zoom API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional: catch-all to keep 500s JSON (helps avoid misleading CORS messages)
@app.middleware("http")
async def catch_exceptions_middleware(request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        print("Unhandled error:", repr(e))
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

# ---------- Paths ----------
HERE = Path(__file__).resolve().parent              # .../backend-api
PROJECT_ROOT = HERE.parent                          # .../root_directory
IMAGES_DIR = HERE / "images"                        # .../backend-api/images
TILES_DIR = HERE / "tiles"                          # .../backend-api/tiles
print("Using IMAGES_DIR:", IMAGES_DIR)

# ---------- Health ----------
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
def read_root():
    return {"message": "Server is running!"}

# ---------- Image streaming (TIFF -> PNG preview) ----------
@app.get("/images/{image_name}")
async def get_image(image_name: str):
    file_path = IMAGES_DIR / image_name
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Image file not found")

    ext = file_path.suffix.lower()

    if ext in (".tif", ".tiff"):
        try:
            pil = PILImage.open(file_path)
            try:
                pil.seek(0)  # first frame if multipage
            except Exception:
                pass
            if pil.mode not in ("RGB", "RGBA"):
                pil = pil.convert("RGBA")
            # Downscale very large images to keep preview light
            max_side = max(pil.size)
            if max_side > 4096:
                scale = 4096 / float(max_side)
                new_size = (int(pil.width * scale), int(pil.height * scale))
                pil = pil.resize(new_size, PILImage.BILINEAR)
            buf = BytesIO()
            pil.save(buf, format="PNG", optimize=False)
            buf.seek(0)
            return StreamingResponse(buf, media_type="image/png")
        except UnidentifiedImageError:
            raise HTTPException(status_code=415, detail="Unsupported TIFF format")
        except Exception as e:
            print("TIFF convert error:", repr(e))
            raise HTTPException(status_code=500, detail="TIFF conversion failed")

    # Native web formats
    media = "image/jpeg"
    if ext == ".png":
        media = "image/png"
    elif ext == ".webp":
        media = "image/webp"

    f = await aiofiles.open(file_path, "rb")
    return StreamingResponse(f, media_type=media)

# ---------- Tiles with small cache ----------
@lru_cache(maxsize=1024)
def get_tile_from_disk(tile_path: str) -> bytes:
    with open(tile_path, "rb") as f:
        return f.read()

@app.get("/tiles/{image_name}/{z}/{x}/{y}")
def get_tile(image_name: str, z: int, x: int, y: int, tile_size: int = 256):
    img_dir = Path(os.path.splitext(image_name)[0])
    tile_filename = f"{img_dir.name}_tile_{x}_{y}.jpg"
    tile_path = TILES_DIR / img_dir / tile_filename
    if not tile_path.is_file():
        raise HTTPException(status_code=404, detail=f"Tile not found {z}")
    tile_data = get_tile_from_disk(str(tile_path))
    headers = {"Cache-Control": "public, max-age=86400"}
    return Response(content=tile_data, media_type="image/jpeg", headers=headers)

# ---------- Images list (DB first, FS fallback) ----------
@app.get("/images")
def list_images(db: Session = Depends(get_db)) -> Dict[str, List[dict]]:
    out: List[dict] = []
    # DB
    try:
        rows = db.query(Image).all()
        if rows:
            out = [
                {
                    "filename": r.filename,
                    "title": r.title or r.filename,
                    "description": r.description or "",
                    "width": r.width,
                    "height": r.height,
                }
                for r in rows
            ]
    except Exception as e:
        print("DB list_images error:", repr(e))

    # Fallback FS
    if not out:
        try:
            if IMAGES_DIR.is_dir():
                for name in sorted(os.listdir(IMAGES_DIR)):
                    lower = name.lower()
                    if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff")):
                        out.append(
                            {
                                "filename": name,
                                "title": name,
                                "description": "",
                                "width": None,
                                "height": None,
                            }
                        )
            else:
                print("IMAGES_DIR is not a directory:", IMAGES_DIR)
        except Exception as e:
            print("FS fallback error:", repr(e))
    return {"images": out}

# ---------- Annotations ----------
@app.get("/annotations/{image_name}")
def get_annotations(image_name: str, db: Session = Depends(get_db)):
    try:
        anns = (
            db.query(Annotation)
            .filter(Annotation.image_filename == image_name)
            .all()
        )
        out = [
            {"x": a.x, "y": a.y, "label": a.label, "user_id": a.user_id}
            for a in anns
        ]
        return {"annotations": out}
    except Exception as e:
        print("get_annotations error:", repr(e))
        return {"annotations": []}

class AnnotationItem(BaseModel):
    x: float
    y: float
    label: Optional[str] = None
    user_id: Optional[int] = 0
    w: Optional[float] = None
    h: Optional[float] = None

class AnnotationBatch(BaseModel):
    annotations: List[AnnotationItem]

# Batch route used by the new frontend
@app.post("/annotations/{image_id}")
def add_annotations(image_id: str, batch: AnnotationBatch, db: Session = Depends(get_db)):
    created = []
    try:
        for a in batch.annotations:
            new_annot = Annotation(
                x=a.x,
                y=a.y,
                label=a.label or "",
                image_filename=image_id,
                user_id=a.user_id or 0,
            )
            db.add(new_annot)
            db.flush()
            created.append(
                {"x": new_annot.x, "y": new_annot.y, "label": new_annot.label, "user_id": new_annot.user_id}
            )
        db.commit()
    except Exception as e:
        db.rollback()
        print("add_annotations error:", repr(e))
        raise HTTPException(status_code=500, detail="Failed to save annotations")
    return {"message": "ok", "annotations": created}

# Keep your original single-insert route (optional)
class AnnotationIn(BaseModel):
    x: float
    y: float
    label: str
    image_filename: str
    user_id: int

@app.post("/annotations")
def add_annotation(annotation: AnnotationIn, db: Session = Depends(get_db)):
    image = db.query(Image).filter(Image.filename == annotation.image_filename).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found in DB")
    new_annot = Annotation(
        x=annotation.x,
        y=annotation.y,
        label=annotation.label,
        image_filename=annotation.image_filename,
        user_id=annotation.user_id,
    )
    db.add(new_annot)
    db.commit()
    db.refresh(new_annot)
    return {
        "message": "Annotation added",
        "annotation": {
            "x": new_annot.x,
            "y": new_annot.y,
            "label": new_annot.label,
            "user_id": new_annot.user_id,
        },
    }
