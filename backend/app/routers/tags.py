from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Tag
from app.schemas import TagResponse, TagCreate, TagUpdate

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("", response_model=list[TagResponse])
def list_tags(db: Session = Depends(get_db)):
    return db.query(Tag).order_by(Tag.name).all()


@router.post("", response_model=TagResponse, status_code=201)
def create_tag(body: TagCreate, db: Session = Depends(get_db)):
    if db.query(Tag).filter(Tag.name == body.name).first():
        raise HTTPException(409, f"이미 존재하는 태그입니다: {body.name}")
    tag = Tag(**body.model_dump())
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


@router.put("/{tag_id}", response_model=TagResponse)
def update_tag(tag_id: int, body: TagUpdate, db: Session = Depends(get_db)):
    tag = db.query(Tag).get(tag_id)
    if not tag:
        raise HTTPException(404, "태그를 찾을 수 없습니다.")
    if body.name and body.name != tag.name:
        if db.query(Tag).filter(Tag.name == body.name).first():
            raise HTTPException(409, f"이미 존재하는 태그입니다: {body.name}")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(tag, key, val)
    db.commit()
    db.refresh(tag)
    return tag


@router.delete("/{tag_id}", status_code=204)
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    tag = db.query(Tag).get(tag_id)
    if not tag:
        raise HTTPException(404, "태그를 찾을 수 없습니다.")
    db.delete(tag)
    db.commit()
