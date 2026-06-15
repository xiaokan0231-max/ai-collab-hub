from fastapi import Request
from sqlalchemy.orm import Session

from ai_collab_hub.neurogolf_plugin import neurogolf_status


def handle_request(action: str, req: Request, db: Session):
    if action == "status":
        return neurogolf_status("neurogolf", db)
    return {"error": "Unknown action"}
