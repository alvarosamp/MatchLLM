from fastapi import APIRouter, Depends, HTTPException, status

from api.auth.schemas import LoginRequest, MeResponse, RegisterRequest, TokenResponse, UserPublic
from api.auth.security import create_access_token, get_password_hash, verify_password
from db.repositories.user_repo import create_user, get_by_email

from api.auth.deps import get_current_user, get_db


router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserPublic)
def register(payload: RegisterRequest, db=Depends(get_db)):
    existing = get_by_email(db, payload.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email já cadastrado")

    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Senha muito curta (min 6)")

    user = create_user(db, email=payload.email, hashed_password=get_password_hash(payload.password))
    return UserPublic(id=user.id, email=user.email)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db=Depends(get_db)):
    user = get_by_email(db, payload.email)
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")

    token = create_access_token(subject=user.email)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=MeResponse)
def me(user=Depends(get_current_user)):
    return MeResponse(user=UserPublic(id=user.id, email=user.email))
