from pydantic import BaseModel


class ExchangeRequest(BaseModel):
    access_token: str


class ExchangeResponse(BaseModel):
    api_key: str
    email: str
    tenant_id: str
