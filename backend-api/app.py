from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
import os
from ai_features.detect import analyze_space_image
from database.db import get_db
from database.models import Image, Annotation, User

app = FastAPI(title="Space Image Analysis API")

class AnalyzeRequest(BaseModel):
    image_filename: str

@app.post("/analyze-image")
def analyze_image(request: AnalyzeRequest):
    
    image_path = os.path.join("images", request.image_filename)

    if not os.path.isfile(image_path):
        raise HTTPException(status_code=404, detail="Image file not found")

    result = analyze_space_image(image_path)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return {
        "message": "Analysis complete",
        "image": request.image_filename,
        "features_found": result["count"],
        "regions": result["regions"]
    }

@app.get("/tiles/{image_name}/{x}/{y}")
def get_tile(image_name: str, x: int, y: int, tile_size: int = 256):
    img_dir = os.path.splitext(image_name)[0]
    tile_filename = f"{img_dir}_tile_{x}_{y}.jpg"
    tile_path = os.path.join("tiles", img_dir, tile_filename)
    if not os.path.isfile(tile_path):
        raise HTTPException(status_code=404, detail="Tile not found")
    return FileResponse(tile_path)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Server is running!"}

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

@app.get("/images/{image_name}")
def get_image(image_name: str, db: Session = Depends(get_db)):
    image = db.query(Image).filter(Image.filename == image_name).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found in DB")
    image_path = os.path.join("images", image_name)
    if not os.path.isfile(image_path):
        raise HTTPException(status_code=404, detail="Image file not found")
    return FileResponse(image_path)

@app.get("/annotations/{image_name}")
def get_annotations(image_name: str, db: Session = Depends(get_db)):
    annotations = db.query(Annotation).filter(
        Annotation.image_filename == image_name
    ).all()
    return {"annotations": [
        {"x": a.x, "y": a.y, "label": a.label, "user_id": a.user_id}
        for a in annotations
    ]}

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
            "label": new_annot.label
        }
    }
