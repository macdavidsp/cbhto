import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from datetime import datetime
import pytz

# Carregar as senhas do ficheiro .env
load_dotenv()

# ==========================================
# 1. CONFIGURAÇÃO DO BANCO DE DADOS
# ==========================================
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Carrega as variáveis do arquivo .env
load_dotenv()

# Pega a URL do arquivo .env
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

# Se a URL não for encontrada, ele avisa no terminal em vez de dar um erro feio
if not SQLALCHEMY_DATABASE_URL:
    print("⚠️ ERRO: DATABASE_URL não encontrada no arquivo .env!")

# Conecta no banco de dados na nuvem
engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==========================================
# 2. MODELOS (Tabelas do Banco de Dados)
# ==========================================
class ReuniaoDB(Base):
    __tablename__ = "reunioes"
    id = Column(Integer, primary_key=True, index=True)
    comite = Column(String, index=True)
    titulo = Column(String)
    data_reuniao = Column(String)
    ativa = Column(Boolean, default=True)

class PresencaDB(Base):
    __tablename__ = "presencas"
    id = Column(Integer, primary_key=True, index=True)
    reuniao_id = Column(Integer, ForeignKey("reunioes.id"))
    comite = Column(String)
    nome = Column(String)
    cpf = Column(String)
    instituicao = Column(String)
    setor = Column(String)
    representacao = Column(String)
    codigo_validacao = Column(String, unique=True, index=True)
    registado_em = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# ==========================================
# 3. SCHEMAS (Validação do que entra na API)
# ==========================================
class SenhaAdmin(BaseModel):
    senha: str

class NovaReuniao(BaseModel):
    comite: str
    titulo: str
    data_reuniao: str

class NovaPresenca(BaseModel):
    comite: str
    nome: str
    cpf: str
    instituicao: str
    setor: str
    representacao: str
    reuniao_id: int
    codigo_validacao: str

# ==========================================
# 4. CONFIGURAÇÃO DO SERVIDOR FASTAPI
# ==========================================
app = FastAPI(title="API Comitês")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 5. ROTAS (A comunicação com o index.html)
# ==========================================
@app.post("/admin/login")
def login_admin(dados: SenhaAdmin):
    # 1. Verifica a senha mestre
    senha_mestre = os.getenv("SENHA_MESTRE")
    if senha_mestre and dados.senha == senha_mestre:
        return {"comite": "TODOS"}
    
    # 2. Verifica as senhas individuais de cada comitê
    comites = ["CBHRCC", "CBHLP", "CBHSAST", "CBHLC", "CBHF", "CBHMA", "CBHRP"]
    for comite in comites:
        senha_comite = os.getenv(f"SENHA_{comite}")
        if senha_comite and dados.senha == senha_comite:
            return {"comite": comite}

    # Se não acertou nenhuma, recusa o acesso
    raise HTTPException(status_code=401, detail="Senha incorreta")

@app.post("/reunioes/")
def criar_reuniao(reuniao: NovaReuniao, db: Session = Depends(get_db)):
    db.query(ReuniaoDB).filter(ReuniaoDB.comite == reuniao.comite, ReuniaoDB.ativa == True).update({"ativa": False})
    nova = ReuniaoDB(**reuniao.dict(), ativa=True)
    db.add(nova)
    db.commit()
    db.refresh(nova)
    return nova

@app.get("/reunioes/ativa/{comite}")
def get_reuniao_ativa(comite: str, db: Session = Depends(get_db)):
    reuniao = db.query(ReuniaoDB).filter(ReuniaoDB.comite == comite, ReuniaoDB.ativa == True).first()
    if not reuniao:
        raise HTTPException(status_code=404, detail="Nenhuma reunião ativa")
    return reuniao

@app.get("/reunioes/{comite}")
def get_historico_reunioes(comite: str, db: Session = Depends(get_db)):
    return db.query(ReuniaoDB).filter(ReuniaoDB.comite == comite).order_by(ReuniaoDB.id.desc()).all()

@app.put("/reunioes/{reuniao_id}/finalizar")
def finalizar_reuniao(reuniao_id: int, db: Session = Depends(get_db)):
    reuniao = db.query(ReuniaoDB).filter(ReuniaoDB.id == reuniao_id).first()
    if reuniao:
        reuniao.ativa = False
        db.commit()
    return {"status": "sucesso"}

@app.post("/presencas/")
def registrar_presenca(presenca: NovaPresenca, db: Session = Depends(get_db)):
    existente = db.query(PresencaDB).filter(PresencaDB.reuniao_id == presenca.reuniao_id, PresencaDB.cpf == presenca.cpf).first()
    if existente:
        raise HTTPException(status_code=400, detail="CPF já registado nesta reunião.")
    fuso_br = pytz.timezone('America/Sao_Paulo')
    nova_presenca = PresencaDB(**presenca.dict(), registado_em=datetime.now(fuso_br))
    db.add(nova_presenca)
    db.commit()
    return {"status": "sucesso", "codigo": presenca.codigo_validacao}

@app.get("/presencas/reuniao/{reuniao_id}")
def get_presencas(reuniao_id: int, db: Session = Depends(get_db)):
    return db.query(PresencaDB).filter(PresencaDB.reuniao_id == reuniao_id).all()

@app.delete("/presencas/reuniao/{reuniao_id}")
def resetar_quorum(reuniao_id: int, db: Session = Depends(get_db)):
    db.query(PresencaDB).filter(PresencaDB.reuniao_id == reuniao_id).delete()
    db.commit()
    return {"status": "apagado"}

@app.get("/presencas/validar/{codigo}")
def validar_codigo(codigo: str, db: Session = Depends(get_db)):
    presenca = db.query(PresencaDB).filter(PresencaDB.codigo_validacao == codigo).first()
    if not presenca:
        raise HTTPException(status_code=404, detail="Código inválido")
    return presenca

# Rota nova: Apagar uma presença específica (Exclusão Individual)
@app.delete("/presencas/{presenca_id}")
def apagar_presenca_individual(presenca_id: int, db: Session = Depends(get_db)):
    presenca = db.query(PresencaDB).filter(PresencaDB.id == presenca_id).first()
    if not presenca:
        raise HTTPException(status_code=404, detail="Presença não encontrada")
    db.delete(presenca)
    db.commit()
    return {"status": "apagado"}