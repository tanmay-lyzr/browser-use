import logging
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient  # New import for MongoDB

from browser_use.telemetry.views import BaseTelemetryEvent
from browser_use.utils import singleton

load_dotenv()

logger = logging.getLogger(__name__)

# You can keep these extra settings if you wish to merge them into your events.
TELEMETRY_EVENT_SETTINGS = {
    'process_person_profile': True,
}


@singleton
class ProductTelemetry:
    """
    Service for capturing anonymized telemetry data.

    If the environment variable `ANONYMIZED_TELEMETRY=False`, telemetry will be disabled.
    Instead of sending data to Posthog, telemetry events are stored locally in MongoDB.
    """

    USER_ID_PATH = str(Path.home() / '.cache' / 'browser_use' / 'telemetry_user_id')
    # MongoDB connection parameters (adjust as needed)
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://admin:admin@localhost:27017/?authSource=admin")
    DATABASE_NAME = "browser_use"
    COLLECTION_NAME = "telemetry_events"
    UNKNOWN_USER_ID = "UNKNOWN"

    _curr_user_id = None

    def __init__(self) -> None:
        telemetry_disabled = os.getenv("ANONYMIZED_TELEMETRY", "true").lower() == "false"
        self.debug_logging = os.getenv("BROWSER_USE_LOGGING_LEVEL", "info").lower() == "debug"

        if telemetry_disabled:
            self._mongo_client = None
            logger.debug("Telemetry disabled via environment variable.")
        else:
            try:
                logger.info("Telemetry enabled. Storing telemetry events in MongoDB.")
                self._mongo_client = MongoClient(self.MONGO_URI)
                self._db = self._mongo_client[self.DATABASE_NAME]
                self._collection = self._db[self.COLLECTION_NAME]
            except Exception as e:
                logger.error(f"Failed to connect to MongoDB: {e}")
                self._mongo_client = None

    def capture(self, event: BaseTelemetryEvent) -> None:
        if self._mongo_client is None:
            return

        if self.debug_logging:
            logger.debug(f"Telemetry event: {event.name} {event.properties}")
        self._direct_capture(event)

    def _direct_capture(self, event: BaseTelemetryEvent) -> None:
        """
        Store the telemetry event into the local MongoDB collection.
        """
        if self._mongo_client is None:
            return

        try:
            doc = {
                "user_id": self.user_id,
                "event_name": event.name,
                "properties": {**event.properties, **TELEMETRY_EVENT_SETTINGS},
                "timestamp": uuid.uuid1().time,  # Alternatively, you can use datetime.utcnow()
            }
            self._collection.insert_one(doc)
            if self.debug_logging:
                logger.debug(f"Stored telemetry event: {doc}")
        except Exception as e:
            logger.error(f"Failed to store telemetry event {event.name}: {e}")

    @property
    def user_id(self) -> str:
        if self._curr_user_id:
            return self._curr_user_id

        try:
            if not os.path.exists(self.USER_ID_PATH):
                os.makedirs(os.path.dirname(self.USER_ID_PATH), exist_ok=True)
                with open(self.USER_ID_PATH, "w") as f:
                    new_user_id = str(uuid.uuid4())
                    f.write(new_user_id)
                self._curr_user_id = new_user_id
            else:
                with open(self.USER_ID_PATH, "r") as f:
                    self._curr_user_id = f.read().strip()
        except Exception:
            self._curr_user_id = self.UNKNOWN_USER_ID
        return self._curr_user_id
