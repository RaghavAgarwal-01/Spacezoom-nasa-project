from db import SessionLocal
from models import User, Image
from passlib.context import CryptContext
from PIL import Image as PILImage  # Add Pillow for getting dimensions

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
db = SessionLocal()
db.query(Image).delete()
db.commit()

# Add your real test image (auto-get dimensions)
image_path = "../backend-api/images/land_shallow_topo_east.tif"
with PILImage.open(image_path) as im:
    img_width, img_height = im.size

real_image = Image(
    filename="land_shallow_topo_east.tif",  # Match your actual images/ folder filename!
    title="Land Shallow Topo East",
    description="NASA sample",
    width=img_width,
    height=img_height,
)

db.add(real_image)
db.commit()

print("Seeded actual test image.")

db.close()
