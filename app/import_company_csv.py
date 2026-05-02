import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# --- Database setup ---
DATABASE_URL = "mariadb+mariadbconnector://nohria_user:telly123@localhost/Nohria_dies_and_Technology"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()
Base = declarative_base()

# --- Company model ---
class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True)
    company_name = Column(String(200), nullable=False)
    location = Column(String(200), nullable=False)
    state_code = Column(String(10), nullable=False)
    state = Column(String(100), nullable=False)
    gst_no = Column(String(50), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)

# --- Column mapping ---
column_map = {
    "name": "company_name",
    "address": "location",
    "state": "state",
    "Gstn": "gst_no",
}

# --- GST State Codes (India) ---
state_code_map = {
    "Haryana": "06",
    "Delhi": "07",
    "Maharashtra": "27",
    "Uttar Pradesh": "09",
    "Punjab": "03",
    "Gujarat": "24",
    "Karnataka": "29",
    "Tamil Nadu": "33",
    "Kerala": "32",
    "West Bengal": "19",
    # Add more states as needed...
}

def import_companies_from_csv(csv_path):
    df = pd.read_csv(csv_path)
    df.rename(columns=column_map, inplace=True)

    for _, row in df.iterrows():
        # Replace missing values with "NA"
        company_name = row.get("company_name") if pd.notna(row.get("company_name")) else "NA"
        location = row.get("location") if pd.notna(row.get("location")) else "NA"
        gst_no = row.get("gst_no") if pd.notna(row.get("gst_no")) else "NA"
        state_name = row.get("state") if pd.notna(row.get("state")) else "NA"

        # Lookup state code, default "NA" if not found
        state_code = state_code_map.get(state_name, "NA")

        company = Company(
            company_name=company_name,
            location=location,
            state=state_name,
            state_code=state_code,
            gst_no=gst_no,
        )
        session.add(company)

    session.commit()
    print("Company data imported successfully!")

if __name__ == "__main__":
    import_companies_from_csv("C:/Users/vibhu/Downloads/Backup_mern.customers.csv")
