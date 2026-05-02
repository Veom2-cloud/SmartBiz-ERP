# config.py
import os
from dotenv import load_dotenv

# load .env from project root
load_dotenv()

class Config:
    MARIADB_USER = os.getenv("MARIADB_USER")
    MARIADB_PASSWORD = os.getenv("MARIADB_PASSWORD")
    MARIADB_HOST = os.getenv("MARIADB_HOST", "127.0.0.1")
    MARIADB_DATABASE = os.getenv("MARIADB_DATABASE")

    SQLALCHEMY_DATABASE_URI = (
        f"mariadb+mariadbconnector://"
        f"{MARIADB_USER}:"
        f"{MARIADB_PASSWORD}@"
        f"{MARIADB_HOST}/"
        f"{MARIADB_DATABASE}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    
    ##mariadb+mariadbconnector://nohria_user:telly123@localhost/Nohria_dies_and_Technology