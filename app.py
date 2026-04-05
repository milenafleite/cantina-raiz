from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import os, json, io, uuid
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cantina-raiz-secret-2024")

# ─── BANCO DE DADOS ────────────────────────────────────────────────────────────
# Suporte a PostgreSQL (Railway) ou SQLite local
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///cantina.db")
# Railway às vezes entrega "postgres://" — SQLAlchemy 1.4+ exige "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

PIX_CHAVE = os.environ.get("PIX_CHAVE", "cantina@colegioraiz.com.br")
PIX_NOME  = os.environ.get("PIX_NOME",  "Cantina Colegio Curso Raiz")

db = SQLAlchemy(app)

# ─── MODELOS ──────────────────────────────────────────────────────────────────

class Produto(db.Model):
    __tablename__ = "produtos"
    id         = db.Column(db.Integer, primary_key=True)
    nome       = db.Column(db.String(100), nullable=False)
    categoria  = db.Column(db.String(50), nullable=False)
    preco      = db.Column(db.Float, nullable=False)
    estoque    = db.Column(db.Integer, default=0)
    foto_b64   = db.Column(db.Text, nullable=True)
    ativo      = db.Column(db.Boolean, default=True)

class Pessoa(db.Model):
    __tablename__ = "pessoas"
    id           = db.Column(db.Integer, primary_key=True)
    nome         = db.Column(db.String(150), nullable=False)
    tipo         = db.Column(db.String(20), nullable=False)
    turma_cargo  = db.Column(db.String(100))
    contato      = db.Column(db.String(150))
    obs          = db.Column(db.Text)
    matricula    = db.Column(db.String(50), nullable=True)
    vendas       = db.relationship("Venda", backref="pessoa", lazy=True)

class Venda(db.Model):
    __tablename__ = "vendas"
    id               = db.Column(db.Integer, primary_key=True)
    data             = db.Column(db.DateTime, default=datetime.now)
    # data_quitacao: quando uma venda "A Pagar" é quitada, registramos aqui
    data_quitacao    = db.Column(db.DateTime, nullable=True)
    total            = db.Column(db.Float, nullable=False)
    forma_pagamento  = db.Column(db.String(100), default="Dinheiro")  # agora pode ser JSON p/ parcial
    pago             = db.Column(db.Boolean, default=True)
    pessoa_id        = db.Column(db.Integer, db.ForeignKey("pessoas.id"), nullable=True)
    itens            = db.relationship("ItemVenda", backref="venda", lazy=True, cascade="all, delete-orphan")

class ItemVenda(db.Model):
    __tablename__ = "itens_venda"
    id           = db.Column(db.Integer, primary_key=True)
    venda_id     = db.Column(db.Integer, db.ForeignKey("vendas.id"), nullable=False)
    produto_nome = db.Column(db.String(100))
    qtd          = db.Column(db.Integer)
    preco_unit   = db.Column(db.Float)
    subtotal     = db.Column(db.Float)

class SaldoAluno(db.Model):
    __tablename__ = "saldo_aluno"
    id        = db.Column(db.Integer, primary_key=True)
    pessoa_id = db.Column(db.Integer, db.ForeignKey("pessoas.id"), unique=True, nullable=False)
    saldo     = db.Column(db.Float, default=0.0)
    pessoa    = db.relationship("Pessoa", backref=db.backref("saldo_obj", uselist=False))

class RecargaSaldo(db.Model):
    __tablename__ = "recargas_saldo"
    id         = db.Column(db.Integer, primary_key=True)
    pessoa_id  = db.Column(db.Integer, db.ForeignKey("pessoas.id"), nullable=False)
    valor      = db.Column(db.Float, nullable=False)
    data       = db.Column(db.DateTime, default=datetime.now)
    confirmado = db.Column(db.Boolean, default=False)
    obs        = db.Column(db.String(200))
    pessoa     = db.relationship("Pessoa", backref="recargas")

class PedidoTablet(db.Model):
    __tablename__ = "pedidos_tablet"
    id        = db.Column(db.Integer, primary_key=True)
    pessoa_id = db.Column(db.Integer, db.ForeignKey("pessoas.id"), nullable=False)
    data      = db.Column(db.DateTime, default=datetime.now)
    total     = db.Column(db.Float, nullable=False)
    status    = db.Column(db.String(20), default="aguardando")
    itens_json= db.Column(db.Text)
    pessoa    = db.relationship("Pessoa", backref="pedidos_tablet")

class FechamentoCaixa(db.Model):
    __tablename__ = "fechamentos_caixa"
    id              = db.Column(db.Integer, primary_key=True)
    data            = db.Column(db.Date, default=date.today)
    hora_fechamento = db.Column(db.String(10))
    total_dia       = db.Column(db.Float, default=0)
    total_dinheiro  = db.Column(db.Float, default=0)
    total_pix       = db.Column(db.Float, default=0)
    total_cartao    = db.Column(db.Float, default=0)
    total_apagar    = db.Column(db.Float, default=0)
    total_recebido  = db.Column(db.Float, default=0)
    qtd_vendas      = db.Column(db.Integer, default=0)
    observacoes     = db.Column(db.Text)

# ─── INICIALIZAÇÃO ─────────────────────────────────────────────────────────────

def seed_produtos():
    if Produto.query.count() == 0:
        produtos = [
            Produto(nome="Coxinha",          categoria="Salgado",  preco=4.50, estoque=20),
            Produto(nome="Pao de Queijo",    categoria="Salgado",  preco=3.00, estoque=30),
            Produto(nome="Esfiha",           categoria="Salgado",  preco=4.00, estoque=15),
            Produto(nome="Biscoito Recheado",categoria="Biscoito", preco=2.50, estoque=40),
            Produto(nome="Rosquinha",        categoria="Biscoito", preco=2.00, estoque=35),
            Produto(nome="Brigadeiro",       categoria="Doce",     preco=3.50, estoque=25),
            Produto(nome="Bolo Fatia",       categoria="Doce",     preco=5.00, estoque=12),
            Produto(nome="Suco de Laranja",  categoria="Bebida",   preco=5.00, estoque=20),
            Produto(nome="Agua",             categoria="Bebida",   preco=2.00, estoque=50),
            Produto(nome="Refrigerante",     categoria="Bebida",   preco=4.00, estoque=25),
        ]
        db.session.add_all(produtos)
        db.session.commit()

with app.app_context():
    db.create_all()
    seed_produtos()

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def borda_cel():
    s = Side(style='thin', color="DDDDDD")
    return Border(left=s, right=s, top=s, bottom=s)

def forma_display(forma_pagamento):
    """Retorna string legível da forma de pagamento (suporta JSON parcial)."""
    try:
        partes = json.loads(forma_pagamento)
        if isinstance(partes, list):
            return " + ".join(f"{p['forma']} R${p['valor']:.2f}" for p in partes)
    except Exception:
        pass
    return forma_pagamento or "—"

def forma_totais_do_dia(vendas):
    """
    Calcula totais por forma de pagamento para o fechamento de caixa.
    Inclui:
    - Vendas normais do dia
    - Vendas "A Pagar" quitadas hoje (data_quitacao = hoje)
    Exclui:
    - Vendas "A Pagar" ainda pendentes (não contabilizam no caixa até quitação)
    """
    totais = {"Dinheiro": 0.0, "Pix": 0.0, "Cartão": 0.0, "A Pagar": 0.0}
    qtd    = {"Dinheiro": 0,   "Pix": 0,   "Cartão": 0,   "A Pagar": 0}

    for v in vendas:
        if not v.pago:
            # pendente: conta como "A Pagar" para visualização mas não no recebido
            totais["A Pagar"] += v.total
            qtd["A Pagar"] += 1
            continue

        try:
            partes = json.loads(v.forma_pagamento)
            if isinstance(partes, list):
                for p in partes:
                    f = p.get("forma", "Dinheiro")
                    val = float(p.get("valor", 0))
                    if f in totais:
                        totais[f] += val
                        qtd[f] += 1
                continue
        except Exception:
            pass

        f = v.forma_pagamento or "Dinheiro"
        if f in totais:
            totais[f] += v.total
            qtd[f] += 1

    return totais, qtd

def venda_to_dict(v):
    return {
        "id": v.id,
        "data": v.data.strftime("%d/%m/%Y %H:%M"),
        "data_quitacao": v.data_quitacao.strftime("%d/%m/%Y %H:%M") if v.data_quitacao else None,
        "total": v.total,
        "forma_pagamento": v.forma_pagamento,
        "forma_display": forma_display(v.forma_pagamento),
        "pago": v.pago,
        "pessoa_id": v.pessoa_id,
        "pessoa_nome": v.pessoa.nome if v.pessoa else "",
        "itens": [{"nome": i.produto_nome, "qtd": i.qtd,
                   "preco_unit": i.preco_unit, "subtotal": i.subtotal} for i in v.itens]
    }

# ══════════════════════════════════════════════════════════════════════════════
# ROTAS PRINCIPAIS
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/cardapio")
def cardapio():
    return render_template("cardapio.html")

# ─── PRODUTOS ─────────────────────────────────────────────────────────────────

@app.route("/api/produtos")
def api_produtos():
    cat   = request.args.get("categoria", "Todos")
    busca = request.args.get("busca", "").lower()
    q = Produto.query.filter_by(ativo=True)
    if cat != "Todos":
        q = q.filter_by(categoria=cat)
    prods = q.all()
    if busca:
        prods = [p for p in prods if busca in p.nome.lower()]
    return jsonify([{
        "id": p.id, "nome": p.nome, "categoria": p.categoria,
        "preco": p.preco, "estoque": p.estoque, "foto_b64": p.foto_b64
    } for p in prods])

@app.route("/api/produtos/todos")
def api_produtos_todos():
    prods = Produto.query.filter_by(ativo=True).order_by(Produto.categoria, Produto.nome).all()
    return jsonify([{
        "id": p.id, "nome": p.nome, "categoria": p.categoria,
        "preco": p.preco, "estoque": p.estoque, "foto_b64": p.foto_b64
    } for p in prods])

@app.route("/api/produtos/salvar", methods=["POST"])
def salvar_produto():
    d = request.json
    if d.get("id"):
        p = Produto.query.get(d["id"])
        if not p: return jsonify({"erro": "Produto não encontrado"}), 404
    else:
        p = Produto()
        db.session.add(p)
    p.nome      = d["nome"]
    p.categoria = d["categoria"]
    p.preco     = float(d["preco"])
    p.estoque   = int(d["estoque"])
    if d.get("foto_b64"):
        p.foto_b64 = d["foto_b64"]
    db.session.commit()
    return jsonify({"ok": True, "id": p.id})

@app.route("/api/produtos/excluir/<int:pid>", methods=["DELETE"])
def excluir_produto(pid):
    p = Produto.query.get(pid)
    if p:
        p.ativo = False
        db.session.commit()
    return jsonify({"ok": True})

@app.route("/api/produtos/estoque/<int:pid>", methods=["POST"])
def atualizar_estoque(pid):
    p = Produto.query.get(pid)
    if not p: return jsonify({"erro": "Não encontrado"}), 404
    p.estoque = int(request.json["estoque"])
    db.session.commit()
    return jsonify({"ok": True})

# ─── VENDAS ───────────────────────────────────────────────────────────────────

@app.route("/api/vendas/finalizar", methods=["POST"])
def finalizar_venda():
    d = request.json
    carrinho      = d["carrinho"]       # [{id, qtd}, ...]
    forma         = d["forma_pagamento"]  # string ou lista [{forma, valor}, ...]
    pessoa_id     = d.get("pessoa_id")

    # Valida "A Pagar"
    # Se forma for lista, verifica se alguma parte é "A Pagar"
    tem_a_pagar = False
    if isinstance(forma, list):
        tem_a_pagar = any(p.get("forma") == "A Pagar" for p in forma)
        forma_str = json.dumps(forma, ensure_ascii=False)
    else:
        tem_a_pagar = (forma == "A Pagar")
        forma_str = forma

    if tem_a_pagar and not pessoa_id:
        return jsonify({"erro": "Conta obrigatória para 'A Pagar'"}), 400

    total = 0.0
    itens_obj = []
    for item in carrinho:
        prod = Produto.query.get(item["id"])
        if not prod or prod.estoque < item["qtd"]:
            return jsonify({"erro": f"Estoque insuficiente: {prod.nome if prod else item['id']}"}), 400
        sub = prod.preco * item["qtd"]
        total += sub
        prod.estoque -= item["qtd"]
        itens_obj.append(ItemVenda(
            produto_nome=prod.nome, qtd=item["qtd"],
            preco_unit=prod.preco, subtotal=sub))

    # Venda é "paga" se nenhuma parte for "A Pagar"
    pago = not tem_a_pagar

    venda = Venda(
        total=total, forma_pagamento=forma_str,
        pago=pago,
        pessoa_id=pessoa_id if pessoa_id else None)
    db.session.add(venda)
    db.session.flush()
    for i in itens_obj:
        i.venda_id = venda.id
        db.session.add(i)
    db.session.commit()
    return jsonify({"ok": True, "total": total, "venda_id": venda.id})

@app.route("/api/vendas/historico")
def historico_vendas():
    ini = request.args.get("ini")
    fim = request.args.get("fim")
    q = Venda.query
    if ini:
        try:
            q = q.filter(Venda.data >= datetime.strptime(ini, "%Y-%m-%d"))
        except ValueError:
            pass
    if fim:
        try:
            from datetime import timedelta
            fim_dt = datetime.strptime(fim, "%Y-%m-%d") + timedelta(days=1)
            q = q.filter(Venda.data < fim_dt)
        except ValueError:
            pass
    vendas = q.order_by(Venda.data.desc()).limit(300).all()
    return jsonify([venda_to_dict(v) for v in vendas])

@app.route("/api/vendas/<int:vid>/mudar_pagamento", methods=["POST"])
def mudar_pagamento(vid):
    v = Venda.query.get(vid)
    if not v: return jsonify({"erro": "Venda não encontrada"}), 404
    nova_forma = request.json.get("forma", "").strip()
    formas_validas = ["Dinheiro", "Pix", "Cartão", "A Pagar", "Saldo"]
    if nova_forma not in formas_validas:
        return jsonify({"erro": f"Forma inválida. Use: {', '.join(formas_validas)}"}), 400
    v.forma_pagamento = nova_forma
    v.pago = (nova_forma != "A Pagar")
    db.session.commit()
    return jsonify({"ok": True})

@app.route("/api/vendas/<int:vid>/excluir", methods=["DELETE"])
def excluir_venda(vid):
    v = Venda.query.get(vid)
    if not v: return jsonify({"erro": "Venda não encontrada"}), 404
    for item in v.itens:
        prod = Produto.query.filter_by(nome=item.produto_nome, ativo=True).first()
        if prod:
            prod.estoque += item.qtd
    if v.forma_pagamento == "Saldo" and v.pessoa_id:
        s = SaldoAluno.query.filter_by(pessoa_id=v.pessoa_id).first()
        if s:
            s.saldo += v.total
    db.session.delete(v)
    db.session.commit()
    return jsonify({"ok": True})

@app.route("/api/vendas/<int:vid>/detalhes")
def detalhes_venda(vid):
    v = Venda.query.get(vid)
    if not v: return jsonify({"erro": "Venda não encontrada"}), 404
    return jsonify(venda_to_dict(v))

@app.route("/api/vendas/<int:vid>/corrigir", methods=["POST"])
def corrigir_venda(vid):
    v = Venda.query.get(vid)
    if not v:
        return jsonify({"erro": "Venda não encontrada"}), 404
    novos_itens = request.json.get("itens", [])
    if not novos_itens:
        return jsonify({"erro": "Nenhum item informado"}), 400
    for item_antigo in v.itens:
        prod = Produto.query.filter_by(nome=item_antigo.produto_nome, ativo=True).first()
        if prod:
            prod.estoque += item_antigo.qtd
    for item_antigo in list(v.itens):
        db.session.delete(item_antigo)
    db.session.flush()
    total = 0.0
    for ni in novos_itens:
        prod = Produto.query.get(ni["id"])
        if not prod or not prod.ativo:
            db.session.rollback()
            return jsonify({"erro": f"Produto não encontrado: {ni['id']}"}), 400
        if prod.estoque < ni["qtd"]:
            db.session.rollback()
            return jsonify({"erro": f"Estoque insuficiente para: {prod.nome} (disponível: {prod.estoque})"}), 400
        sub = prod.preco * ni["qtd"]
        total += sub
        prod.estoque -= ni["qtd"]
        db.session.add(ItemVenda(
            venda_id=v.id, produto_nome=prod.nome,
            qtd=ni["qtd"], preco_unit=prod.preco, subtotal=sub))
    v.total = total
    db.session.commit()
    return jsonify({"ok": True, "total": total})

@app.route("/api/vendas/trocar_item", methods=["POST"])
def trocar_item():
    d = request.json
    prod_novo = Produto.query.get(d["produto_novo_id"])
    if not prod_novo:
        return jsonify({"erro": "Produto não encontrado"}), 404
    if prod_novo.estoque < d["qtd"]:
        return jsonify({"erro": f"Estoque insuficiente. Disponível: {prod_novo.estoque}"}), 400
    return jsonify({"ok": True, "preco": prod_novo.preco, "nome": prod_novo.nome})

# ─── PESSOAS / CONTAS ─────────────────────────────────────────────────────────

@app.route("/api/pessoas")
def api_pessoas():
    busca = request.args.get("busca","").lower()
    pessoas = Pessoa.query.order_by(Pessoa.nome).all()
    result = []
    for p in pessoas:
        if busca and busca not in p.nome.lower() and busca not in (p.turma_cargo or "").lower():
            continue
        devedor = db.session.query(db.func.sum(Venda.total)).filter(
            Venda.pessoa_id==p.id, Venda.pago==False).scalar() or 0
        result.append({
            "id": p.id, "nome": p.nome, "tipo": p.tipo,
            "turma_cargo": p.turma_cargo or "", "contato": p.contato or "",
            "obs": p.obs or "", "saldo_devedor": devedor,
            "matricula": p.matricula or ""
        })
    return jsonify(result)

@app.route("/api/pessoas/salvar", methods=["POST"])
def salvar_pessoa():
    d = request.json
    if d.get("id"):
        p = Pessoa.query.get(d["id"])
        if not p: return jsonify({"erro": "Não encontrado"}), 404
    else:
        p = Pessoa(); db.session.add(p)
    p.nome        = d["nome"]
    p.tipo        = d["tipo"]
    p.turma_cargo = d.get("turma_cargo","")
    p.contato     = d.get("contato","")
    p.obs         = d.get("obs","")
    p.matricula   = d.get("matricula") or None
    db.session.commit()
    return jsonify({"ok": True, "id": p.id})

@app.route("/api/pessoas/importar", methods=["POST"])
def importar_pessoas():
    if "arquivo" not in request.files:
        return jsonify({"erro": "Nenhum arquivo enviado"}), 400
    arquivo = request.files["arquivo"]
    try:
        wb = openpyxl.load_workbook(arquivo, data_only=True)
    except Exception:
        return jsonify({"erro": "Arquivo inválido. Envie um .xlsx"}), 400
    if "MATRICULAS" in wb.sheetnames:
        ws = wb["MATRICULAS"]
        def extrair(row):
            nome  = row[3]; turma = row[7]; turno = row[8]; tel = row[19]
            if not nome or not str(nome).strip(): return None
            tc = f"{turma} - {turno}" if turma and turno else (str(turma) if turma else "")
            return {"nome": str(nome).strip(), "tipo": "Aluno",
                    "turma_cargo": tc.strip(), "contato": str(tel).strip() if tel else "", "obs": ""}
        linhas = list(ws.iter_rows(min_row=3, max_row=ws.max_row, values_only=True))
    else:
        ws = wb.active
        def extrair(row):
            if not row[0] or not str(row[0]).strip(): return None
            return {"nome": str(row[0]).strip(),
                    "tipo": str(row[1]).strip() if row[1] else "Aluno",
                    "turma_cargo": str(row[2]).strip() if row[2] else "",
                    "contato": str(row[3]).strip() if row[3] else "", "obs": ""}
        linhas = list(ws.iter_rows(min_row=2, max_row=ws.max_row, values_only=True))
    inseridos = 0; ignorados = 0
    nomes_existentes = {p.nome.lower() for p in Pessoa.query.all()}
    for row in linhas:
        dados = extrair(row)
        if not dados: continue
        if dados["nome"].lower() in nomes_existentes: ignorados += 1; continue
        p = Pessoa(nome=dados["nome"], tipo=dados["tipo"],
                   turma_cargo=dados["turma_cargo"], contato=dados["contato"], obs=dados["obs"])
        db.session.add(p)
        nomes_existentes.add(dados["nome"].lower()); inseridos += 1
    db.session.commit()
    return jsonify({"ok": True, "inseridos": inseridos, "ignorados": ignorados})

@app.route("/api/pessoas/modelo_excel")
def modelo_excel():
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Alunos"
    RX = "7C4DFF"
    cabecalhos = ["Nome Completo", "Tipo (Aluno/Funcionario)", "Turma / Cargo", "Contato (Telefone)"]
    for c, h in enumerate(cabecalhos, 1):
        cel = ws.cell(row=1, column=c, value=h)
        cel.font = Font(bold=True, color="FFFFFF", name="Calibri")
        cel.fill = PatternFill("solid", fgColor=RX)
        cel.alignment = Alignment(horizontal="center")
    exemplos = [
        ["João da Silva", "Aluno", "3º ANO - MANHÃ", "21 99999-9999"],
        ["Maria Souza",   "Aluno", "2º ANO - TARDE", "21 98888-8888"],
        ["Ana Lima",      "Funcionario", "Coordenação", "21 97777-7777"],
    ]
    for i, ex in enumerate(exemplos, 2):
        for c, v in enumerate(ex, 1):
            ws.cell(row=i, column=c, value=v).font = Font(name="Calibri")
    for i, w in enumerate([30, 22, 22, 20], 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="modelo_importacao_alunos.xlsx")

@app.route("/api/pessoas/excluir/<int:pid>", methods=["DELETE"])
def excluir_pessoa(pid):
    p = Pessoa.query.get(pid)
    if p: db.session.delete(p)
    db.session.commit()
    return jsonify({"ok": True})

@app.route("/api/pessoas/<int:pid>/extrato")
def extrato_pessoa(pid):
    p = Pessoa.query.get(pid)
    if not p: return jsonify({"erro": "Não encontrado"}), 404
    vendas = Venda.query.filter_by(pessoa_id=pid).order_by(Venda.data.desc()).all()
    return jsonify({
        "pessoa": {"id": p.id, "nome": p.nome, "tipo": p.tipo,
                   "turma_cargo": p.turma_cargo or "", "contato": p.contato or ""},
        "vendas": [venda_to_dict(v) for v in vendas]
    })

@app.route("/api/pessoas/<int:pid>/marcar_pago/<int:vid>", methods=["POST"])
def marcar_pago(pid, vid):
    v = Venda.query.get(vid)
    if not v: return jsonify({"erro": "Venda não encontrada"}), 404

    # Suporte a pagamento parcial: pode receber lista de formas
    forma_data = request.json.get("forma", "Dinheiro")
    if isinstance(forma_data, list):
        v.forma_pagamento = json.dumps(forma_data, ensure_ascii=False)
    else:
        v.forma_pagamento = forma_data

    v.pago = True
    v.data_quitacao = datetime.now()  # registra quando foi quitado
    db.session.commit()
    return jsonify({"ok": True})

@app.route("/api/pessoas/<int:pid>/quitar_tudo", methods=["POST"])
def quitar_tudo(pid):
    # Suporte a forma simples ou lista de formas (pagamento parcial)
    forma_data = request.json.get("forma", "Dinheiro")
    vendas = Venda.query.filter_by(pessoa_id=pid, pago=False).all()
    agora = datetime.now()
    for v in vendas:
        if isinstance(forma_data, list):
            v.forma_pagamento = json.dumps(forma_data, ensure_ascii=False)
        else:
            v.forma_pagamento = forma_data
        v.pago = True
        v.data_quitacao = agora
    db.session.commit()
    return jsonify({"ok": True, "qtd": len(vendas)})

# ─── FECHAMENTO DE CAIXA ──────────────────────────────────────────────────────

@app.route("/api/caixa/hoje")
def caixa_hoje():
    hoje = date.today()
    inicio = datetime(hoje.year, hoje.month, hoje.day, 0, 0, 0)
    fim    = datetime(hoje.year, hoje.month, hoje.day, 23, 59, 59)

    # Vendas criadas hoje
    vendas_hoje = Venda.query.filter(Venda.data >= inicio, Venda.data <= fim).all()

    # Vendas de dias anteriores quitadas hoje (A Pagar → Pago)
    vendas_quitadas_hoje = Venda.query.filter(
        Venda.data_quitacao >= inicio,
        Venda.data_quitacao <= fim,
        Venda.pago == True,
        Venda.data < inicio  # criada antes de hoje
    ).all()

    # Todas as vendas relevantes para o caixa de hoje
    todas = vendas_hoje + vendas_quitadas_hoje

    totais, qtd = forma_totais_do_dia(todas)
    total_recebido = totais["Dinheiro"] + totais["Pix"] + totais["Cartão"]

    ja_fechado = FechamentoCaixa.query.filter_by(data=hoje).first() is not None

    return jsonify({
        "data": hoje.strftime("%d/%m/%Y"),
        "totais": totais, "qtd": qtd,
        "total_dia": sum(v.total for v in todas),
        "total_recebido": total_recebido,
        "total_apagar": totais["A Pagar"],
        "qtd_vendas": len(todas),
        "ja_fechado": ja_fechado,
        "vendas": [venda_to_dict(v) for v in vendas_hoje],
        "vendas_quitadas_hoje": [venda_to_dict(v) for v in vendas_quitadas_hoje]
    })

@app.route("/api/caixa/fechar", methods=["POST"])
def fechar_caixa():
    d = request.json
    hoje = date.today()
    f = FechamentoCaixa(
        data=hoje,
        hora_fechamento=datetime.now().strftime("%H:%M:%S"),
        total_dia=d["total_dia"],
        total_dinheiro=d["totais"]["Dinheiro"],
        total_pix=d["totais"]["Pix"],
        total_cartao=d["totais"]["Cartão"],
        total_apagar=d["totais"]["A Pagar"],
        total_recebido=d["total_recebido"],
        qtd_vendas=d["qtd_vendas"],
        observacoes=d.get("observacoes","")
    )
    db.session.add(f)
    db.session.commit()
    return jsonify({"ok": True})

@app.route("/api/caixa/historico")
def historico_caixa():
    mes = request.args.get("mes", 0, type=int)
    ano = request.args.get("ano", 0, type=int)
    q = FechamentoCaixa.query
    if mes > 0: q = q.filter(db.extract("month", FechamentoCaixa.data) == mes)
    if ano > 0: q = q.filter(db.extract("year",  FechamentoCaixa.data) == ano)
    fechamentos = q.order_by(FechamentoCaixa.data.desc()).all()
    return jsonify([{
        "id": f.id, "data": f.data.strftime("%d/%m/%Y"),
        "hora_fechamento": f.hora_fechamento,
        "total_dia": f.total_dia, "total_dinheiro": f.total_dinheiro,
        "total_pix": f.total_pix, "total_cartao": f.total_cartao,
        "total_apagar": f.total_apagar, "total_recebido": f.total_recebido,
        "qtd_vendas": f.qtd_vendas, "observacoes": f.observacoes or ""
    } for f in fechamentos])

@app.route("/api/caixa/anos")
def anos_caixa():
    anos = db.session.query(db.func.extract("year", FechamentoCaixa.data)).distinct().all()
    return jsonify(sorted([int(a[0]) for a in anos], reverse=True) or [date.today().year])

# ─── EXPORTAÇÕES EXCEL ────────────────────────────────────────────────────────

@app.route("/api/export/estoque")
def export_estoque():
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Estoque"
    LA="F47920"; MA="8B4513"; bd=borda_cel()
    ws.merge_cells("A1:F1"); ws["A1"]="Colégio Curso Raiz - Relatório de Estoque"
    ws["A1"].font=Font(bold=True,size=16,color="FFFFFF",name="Calibri")
    ws["A1"].fill=PatternFill("solid",fgColor=LA)
    ws["A1"].alignment=Alignment(horizontal="center"); ws.row_dimensions[1].height=32
    ws.merge_cells("A2:F2")
    ws["A2"]="Gerado em: {}".format(datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    ws["A2"].font=Font(italic=True,size=10,name="Calibri"); ws["A2"].alignment=Alignment(horizontal="center")
    for c,h in enumerate(["Produto","Categoria","Preço (R$)","Estoque","Valor Total (R$)","Situação"],1):
        cel=ws.cell(row=4,column=c,value=h)
        cel.font=Font(bold=True,color="FFFFFF",name="Calibri",size=11)
        cel.fill=PatternFill("solid",fgColor=MA); cel.alignment=Alignment(horizontal="center")
    tg=0.0; linha=5
    for p in Produto.query.filter_by(ativo=True).order_by(Produto.categoria,Produto.nome).all():
        vt=p.preco*p.estoque; tg+=vt
        if p.estoque==0: sit,fc="Esgotado","FFEBEE"
        elif p.estoque<=5: sit,fc="Baixo","FFF9C4"
        else: sit,fc="OK","E8F5E9"
        for c,v in enumerate([p.nome,p.categoria,p.preco,p.estoque,vt,sit],1):
            cel=ws.cell(row=linha,column=c,value=v)
            cel.fill=PatternFill("solid",fgColor=fc); cel.border=bd
            cel.font=Font(name="Calibri",size=10); cel.alignment=Alignment(horizontal="center")
            if c in (3,5): cel.number_format='R$ #,##0.00'
        linha+=1
    ws.cell(row=linha+1,column=4,value="TOTAL:").font=Font(bold=True,name="Calibri")
    ct=ws.cell(row=linha+1,column=5,value=tg)
    ct.font=Font(bold=True,color=LA,size=12,name="Calibri"); ct.number_format='R$ #,##0.00'
    for i,l in enumerate([25,14,14,10,18,12],1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width=l
    buf=io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="estoque_raiz.xlsx")

@app.route("/api/export/extrato/<int:pid>")
def export_extrato(pid):
    p = Pessoa.query.get(pid)
    if not p: return "Não encontrado", 404
    vendas_p = Venda.query.filter_by(pessoa_id=pid).order_by(Venda.data).all()
    wb=openpyxl.Workbook(); ws=wb.active; ws.title="Extrato"
    LA="F47920"; RX="7C4DFF"; VD="5BAD6F"; bd=borda_cel()
    ws.merge_cells("A1:G1"); ws["A1"]="Colégio Curso Raiz - Extrato de Conta"
    ws["A1"].font=Font(bold=True,size=16,color="FFFFFF",name="Calibri")
    ws["A1"].fill=PatternFill("solid",fgColor=LA)
    ws["A1"].alignment=Alignment(horizontal="center"); ws.row_dimensions[1].height=32
    for i,(lbl,val) in enumerate([("Nome:",p.nome),("Tipo:",p.tipo),
        ("Turma/Cargo:",p.turma_cargo or "---"),("Contato:",p.contato or "---"),
        ("Gerado em:",datetime.now().strftime("%d/%m/%Y %H:%M"))],2):
        ws.cell(row=i,column=1,value=lbl).font=Font(bold=True,name="Calibri",color=RX)
        ws.cell(row=i,column=2,value=val).font=Font(name="Calibri")
    for c,h in enumerate(["Data/Hora","Item","Qtd","Preço Unit.","Subtotal","Forma Pag.","Status"],1):
        cel=ws.cell(row=8,column=c,value=h)
        cel.font=Font(bold=True,color="FFFFFF",name="Calibri",size=11)
        cel.fill=PatternFill("solid",fgColor=RX); cel.alignment=Alignment(horizontal="center")
    linha=9; tg=tp=td=0.0
    for v in vendas_p:
        pago=v.pago; fc="E8F5E9" if pago else "FFF3CD"
        st="Pago" if pago else "Pendente"; forma=forma_display(v.forma_pagamento)
        for item in v.itens:
            sub=item.subtotal; tg+=sub
            if pago: tp+=sub
            else: td+=sub
            for c,val in enumerate([v.data.strftime("%d/%m/%Y %H:%M"),item.produto_nome,
                item.qtd,item.preco_unit,sub,forma,st],1):
                cel=ws.cell(row=linha,column=c,value=val)
                cel.fill=PatternFill("solid",fgColor=fc); cel.border=bd
                cel.font=Font(name="Calibri",size=10); cel.alignment=Alignment(horizontal="center")
                if c in (4,5): cel.number_format='R$ #,##0.00'
            linha+=1
    for lbl,val,cor in [("Total Geral:",tg,LA),("Total Pago:",tp,VD),("Saldo Devedor:",td,"CC3300")]:
        ws.cell(row=linha+1,column=5,value=lbl).font=Font(bold=True,name="Calibri")
        c2=ws.cell(row=linha+1,column=6,value=val)
        c2.font=Font(bold=True,color=cor,size=12,name="Calibri"); c2.number_format='R$ #,##0.00'
        linha+=1
    for i,l in enumerate([22,20,6,12,12,14,12],1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width=l
    buf=io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name=f"extrato_{p.nome}.xlsx")

@app.route("/api/export/fechamento/<int:fid>")
def export_fechamento(fid):
    f = FechamentoCaixa.query.get(fid)
    if not f: return "Não encontrado", 404
    hoje_str = f.data.strftime("%d/%m/%Y")
    inicio = datetime(f.data.year, f.data.month, f.data.day)
    fim    = datetime(f.data.year, f.data.month, f.data.day, 23, 59, 59)
    vendas = Venda.query.filter(Venda.data >= inicio, Venda.data <= fim).all()
    wb=openpyxl.Workbook(); ws=wb.active; ws.title="Fechamento"
    LA="F47920"; VD="2E7D32"; VM="CC0000"; PI="32BCAD"; bd=borda_cel()
    ws.merge_cells("A1:F1"); ws["A1"]="COLÉGIO CURSO RAIZ - FECHAMENTO DE CAIXA"
    ws["A1"].font=Font(bold=True,size=16,color="FFFFFF",name="Calibri")
    ws["A1"].fill=PatternFill("solid",fgColor=LA)
    ws["A1"].alignment=Alignment(horizontal="center",vertical="center"); ws.row_dimensions[1].height=36
    ws.merge_cells("A2:F2")
    ws["A2"]="Data: {}  |  Fechado às: {}".format(hoje_str, f.hora_fechamento)
    ws["A2"].font=Font(italic=True,size=10,name="Calibri",color="888888")
    ws["A2"].alignment=Alignment(horizontal="center")
    cores_f={"Dinheiro":VD,"Pix":PI,"Cartão":"1565C0","A Pagar":"7C4DFF"}
    for c,h in enumerate(["Forma","Qtd Vendas","Total (R$)"],1):
        cel=ws.cell(row=4,column=c,value=h)
        cel.font=Font(bold=True,color="FFFFFF",name="Calibri")
        cel.fill=PatternFill("solid",fgColor="666666"); cel.alignment=Alignment(horizontal="center")
    for i,(forma,val,qtd) in enumerate([
        ("Dinheiro",f.total_dinheiro,0),("Pix",f.total_pix,0),
        ("Cartão",f.total_cartao,0),("A Pagar",f.total_apagar,0)],5):
        cor=cores_f.get(forma,"888888")
        ws.cell(row=i,column=1,value=forma).font=Font(bold=True,name="Calibri",color=cor)
        ws.cell(row=i,column=2,value=qtd).alignment=Alignment(horizontal="center")
        c3=ws.cell(row=i,column=3,value=val)
        c3.number_format='R$ #,##0.00'; c3.font=Font(bold=True,name="Calibri",color=cor)
        for c in range(1,4): ws.cell(row=i,column=c).border=bd
    for c,h in enumerate(["Horário","Itens","Total","Forma","Conta","Status"],1):
        cel=ws.cell(row=11,column=c,value=h)
        cel.font=Font(bold=True,color="FFFFFF",name="Calibri")
        cel.fill=PatternFill("solid",fgColor=LA); cel.alignment=Alignment(horizontal="center")
    linha=12
    for v in vendas:
        itens_s=", ".join("{} x{}".format(i.produto_nome,i.qtd) for i in v.itens)
        forma=forma_display(v.forma_pagamento); status="Pago" if v.pago else "Pendente"
        conta=v.pessoa.nome if v.pessoa else "À vista"
        fc="E8F5E9" if v.pago else "FFF3CD"
        for c,val in enumerate([v.data.strftime("%H:%M"),itens_s,v.total,forma,conta,status],1):
            cel=ws.cell(row=linha,column=c,value=val)
            cel.fill=PatternFill("solid",fgColor=fc); cel.border=bd
            cel.font=Font(name="Calibri",size=10); cel.alignment=Alignment(horizontal="center")
            if c==3: cel.number_format='R$ #,##0.00'
        linha+=1
    for i,l in enumerate([10,40,14,14,20,10],1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width=l
    buf=io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name=f"fechamento_{hoje_str.replace('/','_')}.xlsx")

@app.route("/api/export/mensal")
def export_mensal():
    mes = request.args.get("mes", 0, type=int)
    ano = request.args.get("ano", date.today().year, type=int)
    q = FechamentoCaixa.query.filter(db.extract("year", FechamentoCaixa.data)==ano)
    if mes > 0:
        q = q.filter(db.extract("month", FechamentoCaixa.data)==mes)
    fechamentos = q.order_by(FechamentoCaixa.data).all()
    if not fechamentos:
        return "Sem dados", 404
    wb=openpyxl.Workbook(); ws=wb.active; ws.title="Relatório Mensal"
    LA="F47920"; PI="32BCAD"; bd=borda_cel()
    ws.merge_cells("A1:G1"); ws["A1"]="COLÉGIO CURSO RAIZ - RELATÓRIO MENSAL DE CAIXA"
    ws["A1"].font=Font(bold=True,size=16,color="FFFFFF",name="Calibri")
    ws["A1"].fill=PatternFill("solid",fgColor=LA)
    ws["A1"].alignment=Alignment(horizontal="center",vertical="center"); ws.row_dimensions[1].height=36
    ws.merge_cells("A2:G2")
    ws["A2"]="Período: {}/{}  |  Gerado em: {}".format(
        mes if mes else "Todos", ano, datetime.now().strftime("%d/%m/%Y %H:%M"))
    ws["A2"].font=Font(italic=True,size=10,name="Calibri",color="888888")
    ws["A2"].alignment=Alignment(horizontal="center")
    for c,h in enumerate(["Data","Dinheiro","Pix","Cartão","A Pagar","Total Recebido","Total Dia"],1):
        cel=ws.cell(row=4,column=c,value=h)
        cel.font=Font(bold=True,color="FFFFFF",name="Calibri",size=11)
        cel.fill=PatternFill("solid",fgColor=PI); cel.alignment=Alignment(horizontal="center")
    t_d=t_p=t_c=t_a=t_r=t_t=0.0
    for i,f in enumerate(fechamentos,5):
        fc="E8F5E9" if i%2==0 else "FFFFFF"
        t_d+=f.total_dinheiro; t_p+=f.total_pix; t_c+=f.total_cartao
        t_a+=f.total_apagar; t_r+=f.total_recebido; t_t+=f.total_dia
        for c,v in enumerate([f.data.strftime("%d/%m/%Y"),f.total_dinheiro,f.total_pix,
            f.total_cartao,f.total_apagar,f.total_recebido,f.total_dia],1):
            cel=ws.cell(row=i,column=c,value=v)
            cel.fill=PatternFill("solid",fgColor=fc); cel.border=bd
            cel.font=Font(name="Calibri",size=10); cel.alignment=Alignment(horizontal="center")
            if c>1: cel.number_format='R$ #,##0.00'
    lt=len(fechamentos)+5+1
    for c,v in enumerate(["TOTAL",t_d,t_p,t_c,t_a,t_r,t_t],1):
        cel=ws.cell(row=lt,column=c,value=v)
        cel.font=Font(bold=True,color="FFFFFF",size=12,name="Calibri")
        cel.fill=PatternFill("solid",fgColor=LA); cel.border=bd
        cel.alignment=Alignment(horizontal="center")
        if c>1: cel.number_format='R$ #,##0.00'
    for i,l in enumerate([12,14,14,14,14,18,14],1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width=l
    buf=io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name=f"relatorio_mensal_{ano}.xlsx")


# ══════════════════════════════════════════════════════════════════════════════
# SISTEMA DE SALDO / QR CODE
# ══════════════════════════════════════════════════════════════════════════════

LOGO_B64_GLOBAL = ""  # coloque o base64 da logo aqui se necessário

def get_ou_criar_saldo(pessoa_id):
    s = SaldoAluno.query.filter_by(pessoa_id=pessoa_id).first()
    if not s:
        s = SaldoAluno(pessoa_id=pessoa_id, saldo=0.0)
        db.session.add(s)
        db.session.commit()
    return s

def buscar_pessoa_por_matricula(matricula):
    mat = matricula.strip().upper()
    return Pessoa.query.filter(db.func.upper(Pessoa.matricula) == mat).first()

@app.route("/aluno/<matricula>")
def pagina_aluno(matricula):
    p = buscar_pessoa_por_matricula(matricula)
    if not p:
        return "<h2 style='font-family:sans-serif;color:#c00;padding:40px'>Matrícula não encontrada.</h2>", 404
    s = get_ou_criar_saldo(p.id)
    return render_template("aluno.html", pessoa=p, saldo=s,
                           pix_chave=PIX_CHAVE, pix_nome=PIX_NOME,
                           matricula=matricula, logo_b64=LOGO_B64_GLOBAL)

@app.route("/tablet")
def pagina_tablet():
    return render_template("tablet.html")

@app.route("/api/saldo/aluno/<matricula>")
def api_aluno_por_matricula(matricula):
    p = buscar_pessoa_por_matricula(matricula)
    if not p:
        return jsonify({"erro": "Matrícula não encontrada"}), 404
    s = get_ou_criar_saldo(p.id)
    recargas = RecargaSaldo.query.filter_by(pessoa_id=p.id, confirmado=True)\
                                 .order_by(RecargaSaldo.data.desc()).limit(10).all()
    vendas   = Venda.query.filter_by(pessoa_id=p.id)\
                          .order_by(Venda.data.desc()).limit(10).all()
    pedidos  = PedidoTablet.query.filter_by(pessoa_id=p.id)\
                                 .order_by(PedidoTablet.data.desc()).limit(10).all()
    historico = []
    for r in recargas:
        historico.append({"tipo":"recarga","data":r.data.strftime("%d/%m/%Y %H:%M"),
                          "valor":r.valor,"obs":r.obs or ""})
    for v in vendas:
        historico.append({"tipo":"compra","data":v.data.strftime("%d/%m/%Y %H:%M"),
                          "valor":-v.total,
                          "obs":", ".join(f"{i.produto_nome} x{i.qtd}" for i in v.itens)})
    for pd in pedidos:
        itens_p = json.loads(pd.itens_json or "[]")
        historico.append({"tipo":"pedido_tablet","data":pd.data.strftime("%d/%m/%Y %H:%M"),
                          "valor":-pd.total,
                          "obs":", ".join(f"{i['nome']} x{i['qtd']}" for i in itens_p)})
    historico.sort(key=lambda x: x["data"], reverse=True)
    return jsonify({"pessoa_id":p.id,"nome":p.nome,"turma":p.turma_cargo or "",
                    "matricula":p.matricula or "","saldo":s.saldo,
                    "historico":historico[:20]})

@app.route("/api/saldo/<int:pid>/info")
def api_saldo_info(pid):
    p = Pessoa.query.get(pid)
    if not p: return jsonify({"erro":"Não encontrado"}), 404
    s = get_ou_criar_saldo(pid)
    url = (request.host_url.rstrip("/") + f"/aluno/{p.matricula}") if p.matricula else None
    return jsonify({"saldo":s.saldo,"matricula":p.matricula or "","url":url})

@app.route("/api/saldo/recargas/pendentes")
def recargas_pendentes():
    recargas = RecargaSaldo.query.filter_by(confirmado=False)\
                                 .order_by(RecargaSaldo.data.desc()).all()
    return jsonify([{"id":r.id,"pessoa_id":r.pessoa_id,"nome":r.pessoa.nome,
                     "turma":r.pessoa.turma_cargo or "","valor":r.valor,
                     "data":r.data.strftime("%d/%m/%Y %H:%M"),"obs":r.obs or ""}
                    for r in recargas])

@app.route("/api/saldo/recarga/solicitar", methods=["POST"])
def solicitar_recarga():
    d = request.json
    valor = float(d.get("valor", 0))
    if valor <= 0: return jsonify({"erro":"Valor inválido"}), 400
    r = RecargaSaldo(pessoa_id=d.get("pessoa_id"), valor=valor,
                     confirmado=False, obs=d.get("obs",""))
    db.session.add(r)
    db.session.commit()
    return jsonify({"ok":True,"id":r.id})

@app.route("/api/saldo/recarga/<int:rid>/confirmar", methods=["POST"])
def confirmar_recarga(rid):
    r = RecargaSaldo.query.get(rid)
    if not r: return jsonify({"erro":"Não encontrado"}), 404
    if r.confirmado: return jsonify({"erro":"Já confirmado"}), 400
    r.confirmado = True
    s = get_ou_criar_saldo(r.pessoa_id)
    s.saldo += r.valor
    db.session.commit()
    return jsonify({"ok":True,"novo_saldo":s.saldo})

@app.route("/api/saldo/recarga/<int:rid>/rejeitar", methods=["POST"])
def rejeitar_recarga(rid):
    r = RecargaSaldo.query.get(rid)
    if not r: return jsonify({"erro":"Não encontrado"}), 404
    db.session.delete(r)
    db.session.commit()
    return jsonify({"ok":True})

@app.route("/api/saldo/<int:pid>/adicionar", methods=["POST"])
def adicionar_saldo(pid):
    valor = float(request.json.get("valor",0))
    obs   = request.json.get("obs","Adicionado manualmente")
    if valor <= 0: return jsonify({"erro":"Valor inválido"}), 400
    s = get_ou_criar_saldo(pid)
    s.saldo += valor
    r = RecargaSaldo(pessoa_id=pid, valor=valor, confirmado=True, obs=obs)
    db.session.add(r)
    db.session.commit()
    return jsonify({"ok":True,"novo_saldo":s.saldo})

@app.route("/api/tablet/pedido", methods=["POST"])
def pedido_tablet():
    d = request.json
    matricula = d.get("matricula","").strip()
    carrinho  = d.get("carrinho",[])
    if not matricula or not carrinho:
        return jsonify({"erro":"Dados incompletos"}), 400
    p = buscar_pessoa_por_matricula(matricula)
    if not p: return jsonify({"erro":"Matrícula não encontrada"}), 404
    s = get_ou_criar_saldo(p.id)
    total = 0.0; itens_ok = []
    for item in carrinho:
        prod = Produto.query.get(item["id"])
        if not prod or prod.estoque < item["qtd"]:
            return jsonify({"erro":f"Estoque insuficiente: {item['nome']}"}), 400
        sub = prod.preco * item["qtd"]; total += sub
        itens_ok.append({"id":prod.id,"nome":prod.nome,"preco":prod.preco,
                          "qtd":item["qtd"],"sub":sub})
    if s.saldo < total:
        return jsonify({"erro":f"Saldo insuficiente. Disponível: R$ {s.saldo:.2f}"}), 400
    for item in itens_ok:
        Produto.query.get(item["id"]).estoque -= item["qtd"]
    s.saldo -= total
    pedido = PedidoTablet(pessoa_id=p.id, total=total, status="aguardando",
                          itens_json=json.dumps(itens_ok, ensure_ascii=False))
    db.session.add(pedido)
    venda = Venda(total=total, forma_pagamento="Saldo", pago=True, pessoa_id=p.id)
    db.session.add(venda)
    db.session.flush()
    for item in itens_ok:
        db.session.add(ItemVenda(venda_id=venda.id, produto_nome=item["nome"],
                                  qtd=item["qtd"], preco_unit=item["preco"],
                                  subtotal=item["sub"]))
    db.session.commit()
    return jsonify({"ok":True,"total":total,"novo_saldo":s.saldo,
                    "pedido_id":pedido.id,"nome":p.nome,"itens":itens_ok})

@app.route("/api/tablet/pedidos")
def listar_pedidos_tablet():
    status = request.args.get("status","aguardando")
    pedidos = PedidoTablet.query.filter_by(status=status)\
                                 .order_by(PedidoTablet.data.desc()).limit(50).all()
    return jsonify([{"id":p.id,"nome":p.pessoa.nome,"turma":p.pessoa.turma_cargo or "",
                     "data":p.data.strftime("%H:%M"),"total":p.total,"status":p.status,
                     "itens":json.loads(p.itens_json or "[]")} for p in pedidos])

@app.route("/api/tablet/pedidos/<int:pid>/entregar", methods=["POST"])
def entregar_pedido(pid):
    p = PedidoTablet.query.get(pid)
    if not p: return jsonify({"erro":"Não encontrado"}), 404
    p.status = "entregue"
    db.session.commit()
    return jsonify({"ok":True})


if __name__ == "__main__":
    app.run(debug=True)
