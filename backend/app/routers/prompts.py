from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PromptTemplate
from app.schemas import PromptTemplateResponse, PromptTemplateUpdate

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


@router.get("", response_model=list[PromptTemplateResponse])
def list_prompts(db: Session = Depends(get_db)):
    return db.query(PromptTemplate).order_by(PromptTemplate.analysis_type).all()


@router.get("/{analysis_type}", response_model=PromptTemplateResponse)
def get_prompt(analysis_type: str, db: Session = Depends(get_db)):
    template = db.query(PromptTemplate).filter_by(analysis_type=analysis_type).first()
    if not template:
        raise HTTPException(404, f"프롬프트를 찾을 수 없습니다: {analysis_type}")
    return template


@router.put("/{analysis_type}", response_model=PromptTemplateResponse)
def update_prompt(
    analysis_type: str,
    body: PromptTemplateUpdate,
    db: Session = Depends(get_db),
):
    template = db.query(PromptTemplate).filter_by(analysis_type=analysis_type).first()
    if not template:
        raise HTTPException(404, f"프롬프트를 찾을 수 없습니다: {analysis_type}")
    template.system_prompt = body.system_prompt
    template.user_prompt_template = body.user_prompt_template
    db.commit()
    db.refresh(template)
    return template
