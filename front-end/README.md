# MatchLLM Front-end (React + TS)

## Rodar

1) Instalar deps:

`npm install`

2) (Opcional) configurar backend:

- Copie `.env.example` para `.env`
- Ajuste `VITE_API_URL` se necessário

3) Subir o front:

`npm run dev`

## Fluxo

- `/register` cria usuário (email/senha)
- `/login` retorna `access_token` (JWT)
- Token é salvo no `localStorage` e enviado como `Authorization: Bearer <token>`

## Backend

Por padrão o front espera o backend em `http://localhost:8000` e o backend já está com CORS liberado para `http://localhost:5173`.
