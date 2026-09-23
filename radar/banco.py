"""Banco de dados local (um arquivo SQLite em dados/radar.db)."""
import json
import sqlite3
import threading
from pathlib import Path

PASTA_DADOS = Path(__file__).resolve().parent.parent / "dados"
PASTA_DOCS = PASTA_DADOS / "documentos"
ARQUIVO_BANCO = PASTA_DADOS / "radar.db"

_lock = threading.Lock()

ESQUEMA = """
CREATE TABLE IF NOT EXISTS contratacoes (
    id TEXT PRIMARY KEY,            -- numeroControlePNCP
    cnpj TEXT, ano INTEGER, seq INTEGER,
    orgao TEXT, unidade TEXT, municipio TEXT, uf TEXT,
    objeto TEXT, objeto_norm TEXT, info TEXT,
    modalidade TEXT, modalidade_id INTEGER, srp INTEGER,
    valor REAL, abertura TEXT, encerramento TEXT,
    situacao TEXT, plataforma TEXT, link_origem TEXT,
    atualizado TEXT, itens_ok INTEGER DEFAULT 0,
    beneficios TEXT DEFAULT '',
    favorito INTEGER DEFAULT 0, descartado INTEGER DEFAULT 0,
    primeira_vez TEXT, coletado_em TEXT
);
CREATE TABLE IF NOT EXISTS itens (
    contratacao_id TEXT, numero INTEGER,
    descricao TEXT, descricao_norm TEXT,
    qtd REAL, unidade TEXT, valor_unit REAL, valor_total REAL,
    beneficio_id INTEGER, beneficio TEXT,
    PRIMARY KEY (contratacao_id, numero)
);
CREATE TABLE IF NOT EXISTS documentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL, emissor TEXT DEFAULT '',
    validade TEXT, sem_validade INTEGER DEFAULT 0,
    arquivo TEXT, arquivo_nome TEXT, obs TEXT DEFAULT '',
    link_emissao TEXT DEFAULT '', atualizado TEXT
);
CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS coletas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inicio TEXT, fim TEXT, total INTEGER, novas INTEGER, erro TEXT
);
"""

CONFIG_PADRAO = {
    "palavras": [
        "lubrificante",
        "óleo",
        "graxa",
        "fluido de freio",
        "fluido para freio",
        "aditivo de radiador",
        "aditivo para radiador",
        "líquido de arrefecimento",
        "arla 32",
        "arla-32",
        "desengripante",
        "filtro",
        "pastilha de freio",
        "disco de freio",
        "lona de freio",
        "amortecedor",
        "correia dentada",
        "vela de ignição",
        "kit embreagem",
        "palheta",
        "rolamento de roda",
        "terminal de direção",
        "pivô de suspensão", "bomba d'água", "bomba dagua",
        "junta homocinética",
        "autopeça",
        "peças automotivas",
        "peças para veículos",
        "peças e acessórios",
        "peças de reposição",
        "pneu",
        "câmara de ar",
        "bateria automotiva",
        "bateria para veículo",
        "bateria 45",
        "bateria 50",
        "bateria 60",
        "bateria 70",
        "bateria 90",
        "bateria 100",
        "bateria 150",
        "alinhamento",
        "balanceamento",
        "borracharia",
        "shampoo automotivo",
        "cera automotiva",
        "pretinho",
        "revitalizador de pneu",
        "silicone automotivo",
        "lavagem de veículos",
        "lavagem automotiva",
        "lava jato",
        "lava-jato",
        "higienização de veículos",
        "higienização veicular",
        "estética automotiva",
        "polimento automotivo",
        "manutenção de veículos",
        "manutenção veicular",
        "manutenção da frota",
        "manutenção de frota",
        "manutenção preventiva e corretiva de veículos",
        "manutenção corretiva e preventiva de veículos",
        "manutenção preventiva e corretiva da frota",
        "manutenção corretiva e preventiva da frota",
        "oficina mecânica",
        "serviços mecânicos",
        "serviços de mecânica",
        "troca de óleo",
        "revisão de veículos",
    ],
    "negativas": [
        "óleo diesel",
        "óleo combustível",
        "óleo de soja",
        "óleo vegetal",
        "óleo de cozinha",
        "óleo de girassol",
        "óleo de coco",
        "óleo de amêndoa",
        "óleos essenciais",
        "óleo essencial",
        "óleo mineral",
        "óleo de milho",
        "óleo corporal",
        "filtro solar",
        "filtro de linha",
        "filtro de barro",
        "filtro de água",
        "filtro para bebedouro",
        "filtro hepa",
        "filtro bacteriano",
        "filtro de café",
        "filtro para café",
        "filtro de papel",
        "filtro para aspirador",
        "filtro de ar condicionado",
        "filtro para ar condicionado",
        "refil",
        "óleo de silicone",
        "óleo da retina",
        "óleo na retina",
        "óleo de imersão",
        "oleoso",
        "filtro do receptor",
        "filtro bacteriológico",
        "pneumo",
    ],
    "cidades_proximas": [
        "Campina Grande", "Queimadas", "Lagoa Seca", "Puxinanã", "Massaranduba",
        "Boa Vista", "Esperança", "Fagundes", "Pocinhos", "Serra Redonda", "Ingá",
        "Alagoa Nova", "Montadas", "São Sebastião de Lagoa de Roça", "Areial",
        "Caturité", "Riachão do Bacamarte", "Barra de Santana", "Boqueirão",
    ],
    "uf": "PB",
}

DOCS_PADRAO = [
    ("Contrato social consolidado", "Junta Comercial (JUCEP)", 1, ""),
    ("Cartão CNPJ", "Receita Federal", 0, "https://solucoes.receita.fazenda.gov.br/servicos/cnpjreva/cnpjreva_solicitacao.asp"),
    ("CND Federal (Receita/PGFN)", "Receita Federal", 0, "https://servicos.receitafederal.gov.br/servico/certidoes/#/home"),
    ("CRF – Regularidade do FGTS", "Caixa", 0, "https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf"),
    ("CNDT – Débitos Trabalhistas", "TST", 0, "https://cndt-certidao.tst.jus.br/inicio.faces"),
    ("CND Estadual", "SEFAZ-PB", 0, "https://www.sefaz.pb.gov.br"),
    ("CND Municipal", "Prefeitura de Campina Grande", 0, ""),
    ("Certidão negativa de falência", "TJPB", 0, ""),
    ("Balanço patrimonial", "Contador", 0, ""),
    ("Atestado de capacidade técnica", "Órgãos atendidos", 1, ""),
    ("Alvará de funcionamento", "Prefeitura de Campina Grande", 0, ""),
]


def conectar():
    PASTA_DOCS.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ARQUIVO_BANCO, check_same_thread=False, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def iniciar():
    with _lock, conectar() as con:
        con.executescript(ESQUEMA)
        colunas = {r[1] for r in con.execute("PRAGMA table_info(documentos)")}
        if "link_arquivo" not in colunas:  # link do arquivo no Google Drive (versão online)
            con.execute("ALTER TABLE documentos ADD COLUMN link_arquivo TEXT DEFAULT ''")
        for chave, valor in CONFIG_PADRAO.items():
            con.execute("INSERT OR IGNORE INTO config VALUES (?, ?)",
                        (chave, json.dumps(valor, ensure_ascii=False)))
        if not con.execute("SELECT 1 FROM documentos LIMIT 1").fetchone():
            con.executemany(
                "INSERT INTO documentos (nome, emissor, sem_validade, link_emissao) VALUES (?,?,?,?)",
                DOCS_PADRAO)


def ler_config():
    with conectar() as con:
        return {r["chave"]: json.loads(r["valor"]) for r in con.execute("SELECT * FROM config")}


def salvar_config(dados):
    with _lock, conectar() as con:
        for chave in ("palavras", "negativas", "cidades_proximas"):
            if chave in dados:
                lista = [s.strip() for s in dados[chave] if s and s.strip()]
                con.execute("REPLACE INTO config VALUES (?, ?)",
                            (chave, json.dumps(lista, ensure_ascii=False)))
