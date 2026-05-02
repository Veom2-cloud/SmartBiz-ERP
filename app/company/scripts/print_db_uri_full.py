import os
from dotenv import load_dotenv

load_dotenv()

uri = (
    f"mariadb+mariadbconnector://"
    f"{os.getenv('MARIADB_USER')}:"
    f"{os.getenv('MARIADB_PASSWORD')}@"
    f"{os.getenv('MARIADB_HOST')}/"
    f"{os.getenv('MARIADB_DATABASE')}"
)

print("SQLALCHEMY_DATABASE_URI =")
print(uri)

##SQLALCHEMY_DATABASE_URI =mariadb+mariadbconnector://nohria_user:telly123@localhost/Nohria_dies_and_Technology