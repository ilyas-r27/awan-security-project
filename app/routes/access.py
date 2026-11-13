from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_buyer
from app.models import User
from app.routes.files import _content_disposition
from app.schemas import (
    AccessApprove, AccessApproved, AccessCodeOut, AccessDataOut, AccessRedeem, AccessRequestCreate,
    AccessRequestList, AccessRequestOut, Algorithm,
)
from app.services import access as service
from app.services.access import AccessError

router = APIRouter(prefix="/access-requests", tags=["access"])


def _run(fn, *args):
    try:
        return fn(*args)
    except AccessError as exc:
        raise HTTPException(exc.status, exc.detail) from None


@router.post("", response_model=AccessRequestOut, status_code=status.HTTP_201_CREATED)
def create(body: AccessRequestCreate, user: User = Depends(require_buyer), db: Session = Depends(get_db)):
    req = _run(service.create_request, db, user, body.username, body.scope.model_dump())
    return service.request_out(db, req)


@router.get("", response_model=AccessRequestList)
def list_requests(box: Literal["incoming", "outgoing"] = "incoming",
                  user: User = Depends(require_buyer), db: Session = Depends(get_db)):
    return {"items": service.list_requests(db, user, box)}


@router.get("/{request_id}", response_model=AccessRequestOut)
def get_request(request_id: int, user: User = Depends(require_buyer), db: Session = Depends(get_db)):
    return _run(service.get_request, db, request_id, user)


@router.post("/{request_id}/approve", response_model=AccessApproved)
def approve(request_id: int, body: AccessApprove | None = None,
            user: User = Depends(require_buyer), db: Session = Depends(get_db)):
    return _run(service.approve, db, user, request_id, (body or AccessApprove()).valid_days)


@router.get("/{request_id}/code", response_model=AccessCodeOut)
def get_code(request_id: int, user: User = Depends(require_buyer), db: Session = Depends(get_db)):
    return _run(service.get_code, db, user, request_id)


@router.post("/{request_id}/reject", response_model=AccessRequestOut)
def reject(request_id: int, user: User = Depends(require_buyer), db: Session = Depends(get_db)):
    return _run(service.reject, db, user, request_id)


@router.post("/{request_id}/revoke", response_model=AccessRequestOut)
def revoke(request_id: int, user: User = Depends(require_buyer), db: Session = Depends(get_db)):
    return _run(service.revoke, db, user, request_id)


@router.post("/{request_id}/redeem", response_model=AccessRequestOut)
def redeem(request_id: int, body: AccessRedeem, user: User = Depends(require_buyer), db: Session = Depends(get_db)):
    return _run(service.redeem, db, user, request_id, body.access_code)


@router.get("/{request_id}/data", response_model=AccessDataOut)
def view_data(request_id: int, user: User = Depends(require_buyer), db: Session = Depends(get_db)):
    return _run(service.view_data, db, user, request_id)


@router.get("/{request_id}/files/{file_id}/download")
def download(request_id: int, file_id: int, alg: Algorithm = "aes",
             user: User = Depends(require_buyer), db: Session = Depends(get_db)):
    dl = _run(service.open_shared_download, db, user, request_id, file_id, alg)
    return StreamingResponse(dl.chunks, media_type=dl.mime_type, headers={
        "Content-Disposition": _content_disposition(dl.name),
        "Content-Length": str(dl.size),
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })
