from pydantic import BaseModel, Field

class User:
    def __init__(self, name: str, email: str, accounts=None, register_for_all = False):
        if accounts is None:
            accounts = []
        self.name: str = name
        self.email: str = email
        self.accounts: list[str]  = accounts
        self.register_for_all = register_for_all





class FraudEvent(BaseModel):
    account_id: str = Field(..., alias="AccountId")
    tx_hash: str = Field(..., alias="TxHash")
    timestamp: int = Field(..., alias="Timestamp")
    event_type: str = Field(..., alias="Type")  # 'Type' is renamed to 'event_type'

    class Config:
        populate_by_name = True  # Allows using the snake_case names
        # Add this to allow both styles:
        str_strip_whitespace = True  # Strips whitespace from string fields