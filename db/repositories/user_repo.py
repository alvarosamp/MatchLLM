from sqlalchemy.orm import Session

from db.models.users import User


def get_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def create_user(db: Session, *, email: str, hashed_password: str) -> User:
    rec = User(email=email, hashed_password=hashed_password)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec
