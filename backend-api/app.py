from fastapi import FastAPI, HTTPException, Depends, Response
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from functools import lru_cache
import aiofiles
import os

# Import database session manager and ORM models
from database.db import get_db
from database.models import Image, Annotation, User

app = FastAPI()

# 1. Frontend access for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Server health/status endpoint
@app.get("/")
def read_root():
    return {"message": "Server is running!"}

# 3. Asynchronous streaming for large images
@app.get("/images/{image_name}")
async def get_image(image_name: str):
    file_path = os.path.join("images", image_name)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Image file not found")
    async with aiofiles.open(file_path, 'rb') as f:
        return StreamingResponse(f, media_type="image/jpeg")

# 4. In-memory cache for fast/repeated tile access
@lru_cache(maxsize=1024)
def get_tile_from_disk(tile_path):
    with open(tile_path, 'rb') as f:
        return f.read()

# 5. Serve 256x256 image tiles (for zoom, performance)
@app.get("/tiles/{image_name}/{x}/{y}")
def get_tile(image_name: str, x: int, y: int, tile_size: int = 256):
    img_dir = os.path.splitext(image_name)[0]
    tile_filename = f"{img_dir}_tile_{x}_{y}.jpg"
    tile_path = os.path.join("tiles", img_dir, tile_filename)
    if not os.path.isfile(tile_path):
        raise HTTPException(status_code=404, detail="Tile not found")
    tile_data = get_tile_from_disk(tile_path)
    headers = {"Cache-Control": "public, max-age=86400"}
    return Response(content=tile_data, media_type="image/jpeg", headers=headers)

# 6. Return all images with metadata for gallery/search
@app.get("/images")
def list_images(db: Session = Depends(get_db)):
    images = db.query(Image).all()
    return {"images": [
        {
            "filename": img.filename,
            "title": img.title,
            "description": img.description,
            "width": img.width,
            "height": img.height
        } for img in images
    ]}

# 7. Search endpoint for filtering images by query string
@app.get("/search")
def search_images(query: str, db: Session = Depends(get_db)):
    results = db.query(Image).filter(
        Image.title.ilike(f"%{query}%") | Image.description.ilike(f"%{query}%")
    ).all()
    return {"results": [
        {
            "filename": img.filename,
            "title": img.title,
            "description": img.description,
        } for img in results
    ]}

# 8. Retrieve all annotations for a specific image (multi-user)
@app.get("/annotations/{image_name}")
def get_annotations(image_name: str, db: Session = Depends(get_db)):
    annotations = db.query(Annotation).filter(
        Annotation.image_filename == image_name
    ).all()
    return {"annotations": [
        {"x": a.x, "y": a.y, "label": a.label, "user_id": a.user_id}
        for a in annotations
    ]}

# 9. Save a new annotation (handles concurrent users)
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
        user_id=annotation.user_id
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
            "user_id": new_annot.user_id
        }
    }
