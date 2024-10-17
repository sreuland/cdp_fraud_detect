from collections import OrderedDict
from typing import List

from pydantic import BaseModel, Field

class FraudEvent(BaseModel):
    account_id: str = Field(..., alias="AccountId")
    tx_hash: str = Field(..., alias="TxHash")
    timestamp: int = Field(..., alias="Timestamp")
    event_type: str = Field(..., alias="Type")  # 'Type' is renamed to 'event_type'

    class Config:
        populate_by_name = True  # Allows using the snake_case names
        # Add this to allow both styles:
        str_strip_whitespace = True  # Strips whitespace f

class UserTimeline:
    def __init__(self):
        # An OrderedDict to store events by their timestamp
        self.timeline: OrderedDict[int, List[FraudEvent]] = OrderedDict()

    def add_event(self, event: FraudEvent):
        # Add the event to the timeline, grouped by timestamp
        if event.timestamp not in self.timeline:
            self.timeline[event.timestamp] = []
        self.timeline[event.timestamp].append(event)

    def get_timeline(self)  -> List[FraudEvent]:
        # Return the ordered timeline
        return [event for events in self.timeline.values() for event in events]


class User:
    def __init__(self, name: str, email: str, accounts=None, register_for_all = False):
        if accounts is None:
            accounts = []
        self.name: str = name
        self.email: str = email
        self.accounts: list[str]  = accounts
        self.register_for_all = register_for_all
        self.timeline: UserTimeline = UserTimeline()  # Initialize UserTimeline

    def __str__(self) -> str:
        # Custom string representation for logging
        return f"User(name={self.name}, email={self.email}, accounts={self.accounts}, register_for_all={self.register_for_all})"

    def __repr__(self) -> str:
        # Optional: Custom representation for developers
        return self.__str__()
