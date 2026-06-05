import os
import sys
import datetime
from sqlalchemy import create_engine, Column, Integer, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.compiler import compiles

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(element, compiler, **kw):
    return "TEXT"

Base = declarative_base()

class TestModel(Base):
    __tablename__ = "test"
    id = Column(Integer, primary_key=True)
    metadata_json = Column(JSONB, nullable=False, server_default=text("'{}'"))

engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

# Insert
t = TestModel(id=1, metadata_json={"loc_1": {"latest": "2026-06-02"}})
db.add(t)
db.commit()

# Query
t = db.query(TestModel).first()
print("INITIAL TYPE:", type(t.metadata_json), t.metadata_json)

# Update
t.metadata_json = {"loc_1": {"latest": "2026-06-03"}}
db.commit()

t = db.query(TestModel).first()
print("UPDATED TYPE:", type(t.metadata_json), t.metadata_json)
