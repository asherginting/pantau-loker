from dataclasses import dataclass
from typing import Optional


@dataclass
class Job:
    id: str
    source: str
    title: str
    company: str = ""
    location: str = ""
    url: str = ""
    description: str = ""
    published_at: Optional[str] = None
