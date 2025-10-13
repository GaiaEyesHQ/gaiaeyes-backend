from pydantic import BaseModel, HttpUrl, Field
from datetime import datetime
from typing import List

class Item(BaseModel):
    id_hash: str
    url: HttpUrl
    title: str
    summary: str
    source: str
    published_at: datetime
    topics: List[str] = []
    score: float = 0.0

class Sections(BaseModel):
    tldr: str
    what_happened: str
    why_it_matters: str
    details_today: str
    next_72h: str
    impacts_plain: str

class Draft(BaseModel):
    scientific: Sections
    mystical: Sections
    tags: List[str] = Field(default_factory=list)