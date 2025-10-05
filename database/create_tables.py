# backend/create_tables.py
from database.db import Base, engine
from database.models import Image  # import all models here

print("Creating tables...")
Base.metadata.create_all(bind=engine)
print("Tables created successfully!")
