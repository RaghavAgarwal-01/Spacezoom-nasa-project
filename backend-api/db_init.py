from database.db import engine, Base
from database.models import *  # Import all your models

# This will create all tables in your SQLite DB
Base.metadata.create_all(bind=engine)
print("Tables created successfully!")
