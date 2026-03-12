# Cantina Colégio Curso Raiz — Versão Web (Flask)

## Estrutura
```
cantina_web/
├── app.py               ← Backend Flask + banco de dados
├── requirements.txt     ← Dependências Python
├── Procfile             ← Comando para o Render
└── templates/
    └── index.html       ← Frontend completo (HTML + CSS + JS)
```

## Deploy no Render

### 1. Suba para o GitHub
```bash
git init
git add .
git commit -m "Cantina web v1"
git remote add origin https://github.com/SEU_USUARIO/cantina-raiz.git
git push origin main
```

### 2. No Render (render.com)
- New → Web Service
- Conecte o repositório
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn app:app`

### 3. Variáveis de ambiente no Render
| Variável | Valor |
|----------|-------|
| `DATABASE_URL` | URL do PostgreSQL (Render cria automaticamente) |
| `SECRET_KEY` | Uma senha qualquer (ex: `cantina-raiz-2024`) |

### 4. Banco de dados
- No Render: New → PostgreSQL
- Copie a **Internal Database URL** e cole em `DATABASE_URL`
- O sistema cria as tabelas automaticamente na primeira execução

## Atualizar sem perder dados
Os dados ficam no PostgreSQL — basta fazer push no GitHub:
```bash
git add .
git commit -m "descrição da mudança"
git push origin main
```
O Render faz o redeploy automaticamente. ✅

## Funcionalidades
- 🛒 Venda com carrinho (adicionar, remover, **trocar itens**)
- 💰 Formas de pagamento: Dinheiro, Pix, Cartão, A Pagar
- 👥 Contas de alunos e funcionários com extrato
- 💰 Fechamento de caixa diário com totais por forma
- 📊 Histórico mensal de fechamentos
- 📦 Controle de estoque
- 📥 Exportação em Excel (extrato, estoque, fechamento, relatório mensal)
