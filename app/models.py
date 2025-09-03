from pydantic import BaseModel, Field
from typing import Any, Optional, List
from datetime import datetime

class SampleIn(BaseModel):
    user_id: str
    device_os: str
    source: Optional[str] = None
    type: str
    start_time: datetime
    end_time: Optional[datetime] = None
    value: Optional[float] = Field(default=None)
    value_text: Optional[str] = Field(default=None)
    unit: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None

class SamplesBatchIn(BaseModel):
    samples: List[SampleIn]

class SessionIn(BaseModel):
    user_id: str
    type: str
    start_time: datetime
    end_time: Optional[datetime] = None
    summary_json: Optional[dict[str, Any]] = None
