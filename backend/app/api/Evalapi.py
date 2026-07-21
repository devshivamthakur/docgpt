import logging
from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.rate_limiter import rate_limit
from app.core.middleware import get_current_user
from app.models.user import User
from app.tasks.arq_app import enqueue_eval_and_email

router = APIRouter(prefix="/eval", tags=['eval pipeline'])

@router.get("/eval")
@rate_limit(max_requests=30, window_seconds=60, scope="eval pipeline")
async def getEvalOutput(current_user: User = Depends(get_current_user)):
    admin_email = settings.ADMIN_EMAIL or current_user.email
    await enqueue_eval_and_email(admin_email)
    
    return JSONResponse(
        status_code=200,
        content=f"eval pipeline has started, will send an email report to {admin_email}"
    )


