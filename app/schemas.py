from pydantic import BaseModel


class ExtractedContent(BaseModel):
    url: str
    source_type: str
    title: str
    content: str


class SummaryResult(BaseModel):
    summary: str
