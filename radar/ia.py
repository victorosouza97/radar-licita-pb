"""IA (Google Gemini) lendo o edital em PDF e resumindo em português simples.

A chave fica no arquivo .env da pasta do programa: GEMINI_API_KEY=...
"""
import json
import os
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from . import banco, pncp

# Se o primeiro estiver sobrecarregado, tenta o próximo.
MODELOS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-3.5-flash"]
LIMITE_BYTES = 18 * 1024 * 1024
LIMITE_TEXTO = 160_000  # caracteres por documento (~40 mil tokens)
ARQUIVO_ENV = Path(__file__).resolve().parent.parent / ".env"

PERFIL = ("uma pequena empresa (ME) de Campina Grande-PB, oficina mecânica e troca de óleo, "
          "que vende lubrificantes, filtros e autopeças e presta serviços de manutenção de veículos")

PROMPT = f"""Você é consultor de licitações de {PERFIL}.
Leia os documentos da licitação e responda em português simples, sem juridiquês, para um leigo.
Seja fiel ao documento. Se algo não constar, use null (ou lista vazia). Não invente.

Atenção especial:
- Exigência de distância/raio máximo entre a empresa (oficina, depósito, sede) e o órgão: informe em raio_km e cite o trecho.
- Documentos de habilitação: liste cada um com nome curto (ex.: "CND Federal", "CRF do FGTS", "Balanço patrimonial", "Atestado de capacidade técnica").
- Pontos de atenção: multas, prazos curtos de entrega, amostra, visita técnica, garantia, exigências incomuns, marca exigida."""

SCHEMA = {
    "type": "object",
    "properties": {
        "resumo": {"type": "string", "description": "3 a 5 frases: o que compram, por quanto tempo, onde entregar, como é a disputa"},
        "data_sessao": {"type": "string", "nullable": True, "description": "data e hora da sessão, AAAA-MM-DD HH:MM"},
        "prazo_impugnacao": {"type": "string", "nullable": True},
        "plataforma": {"type": "string", "nullable": True, "description": "site onde ocorre a disputa"},
        "criterio": {"type": "string", "nullable": True, "description": "ex.: menor preço por item, por lote, maior desconto"},
        "participacao_me": {"type": "string", "nullable": True, "description": "exclusiva ME/EPP, cota reservada ou ampla"},
        "prazo_entrega": {"type": "string", "nullable": True},
        "local_entrega": {"type": "string", "nullable": True},
        "raio_km": {"type": "number", "nullable": True, "description": "raio máximo exigido em km, se houver"},
        "raio_trecho": {"type": "string", "nullable": True, "description": "trecho do edital que fala do raio"},
        "documentos_exigidos": {"type": "array", "items": {"type": "string"}},
        "exige_amostra": {"type": "boolean"},
        "exige_visita_tecnica": {"type": "boolean"},
        "garantia": {"type": "string", "nullable": True},
        "pontos_atencao": {"type": "array", "items": {"type": "string"}},
        "vale_a_pena": {"type": "string", "description": "recomendação curta para esta empresa, com o motivo"},
    },
    "required": ["resumo", "documentos_exigidos", "pontos_atencao", "vale_a_pena",
                 "exige_amostra", "exige_visita_tecnica"],
}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS analises (
    contratacao_id TEXT PRIMARY KEY, criado TEXT, modelo TEXT,
    arquivos TEXT, dados TEXT, erro TEXT
);
"""

em_andamento = set()
_fila_trava = threading.Lock()


def _limpar_chave(valor):
    """Tira restos comuns de copiar e colar: espaços, aspas e o próprio nome 'GEMINI_API_KEY='."""
    v = (valor or "").strip().strip('"').strip("'").strip()
    if v.upper().startswith("GEMINI_API_KEY="):
        v = v.split("=", 1)[1].strip().strip('"').strip("'")
    return "".join(v.split())


def chave():
    if os.getenv("GEMINI_API_KEY"):
        return _limpar_chave(os.getenv("GEMINI_API_KEY"))
    if ARQUIVO_ENV.exists():
        for linha in ARQUIVO_ENV.read_text(encoding="utf-8").splitlines():
            if linha.strip().startswith("GEMINI_API_KEY="):
                return linha.split("=", 1)[1].strip().strip('"')
    return ""


def iniciar():
    with banco.conectar() as con:
        con.executescript(ESQUEMA)


def _baixar(url):
    for n in range(8):  # o PNCP às vezes responde 422/503 e depois funciona
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RadarLicitaPB/1.0"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read(LIMITE_BYTES + 1)
        except Exception as e:
            erro = e
            time.sleep(3 * (n + 1))
    raise erro


PASTA_EDITAIS = banco.PASTA_DADOS / "editais"


def _baixar_com_cache(url):
    """Guarda cada arquivo baixado: o PNCP oscila e o mesmo edital não precisa vir duas vezes."""
    import hashlib
    PASTA_EDITAIS.mkdir(parents=True, exist_ok=True)
    local = PASTA_EDITAIS / (hashlib.sha1(url.encode()).hexdigest() + ".bin")
    if local.exists():
        return local.read_bytes()
    dados = _baixar(url)
    local.write_bytes(dados)
    return dados


class FalhaDownload(Exception):
    pass


def _escolher_pdfs(arquivos):
    """Edital primeiro, depois termo de referência e anexos; só PDFs, até o limite de tamanho."""
    def ordem(a):
        t = (a.get("tipo") or "").lower() + " " + (a.get("titulo") or "").lower()
        if "edital" in t:
            return 0
        if "termo de refer" in t or "tr " in t:
            return 1
        return 2
    escolhidos, total, falhas = [], 0, 0
    for a in sorted(arquivos, key=ordem):
        if ordem(a) == 2 and escolhidos:
            continue
        try:
            dados = _baixar_com_cache(a["url"])
        except Exception:
            falhas += 1
            continue
        if not dados.startswith(b"%PDF") or total + len(dados) > LIMITE_BYTES:
            continue
        escolhidos.append((a["titulo"], dados))
        total += len(dados)
        if len(escolhidos) >= 2:
            break
    if not escolhidos and falhas:
        raise FalhaDownload("O PNCP não entregou o arquivo do edital agora (o site oscila). Tente de novo em alguns minutos.")
    return escolhidos


def _texto_do_pdf(dados):
    """Extrai o texto do PDF aqui mesmo (mais leve para a IA). Vazio se for digitalizado."""
    import io

    from pypdf import PdfReader
    try:
        leitor = PdfReader(io.BytesIO(dados))
        paginas = [(p.extract_text() or "") for p in leitor.pages]
    except Exception:
        return ""
    # Tira cabeçalhos e rodapés que se repetem em todas as páginas.
    from collections import Counter
    linhas = [l.strip() for p in paginas for l in p.splitlines()]
    repetidas = {l for l, n in Counter(linhas).items() if n >= max(3, len(paginas) // 2) and len(l) < 200}
    texto = "\n".join(l for l in linhas if l and l not in repetidas)
    # PDF digitalizado (foto do papel) quase não tem texto por página
    return texto if len(texto) > 400 * max(1, len(paginas)) * 0.5 else ""


def _perguntar(pdfs):
    from google import genai
    from google.genai import types

    # Sem repetição automática do pacote: quem decide tentar outro modelo somos nós.
    cliente = genai.Client(api_key=chave(), http_options=types.HttpOptions(
        timeout=240_000, retry_options=types.HttpRetryOptions(attempts=1)))
    partes = []
    for titulo, dados in pdfs:
        texto = _texto_do_pdf(dados)
        if texto:
            partes.append(f"=== DOCUMENTO: {titulo} ===\n{texto[:LIMITE_TEXTO]}")
        else:
            partes.append(types.Part.from_bytes(data=dados, mime_type="application/pdf"))
    partes.append(PROMPT)
    config = types.GenerateContentConfig(response_mime_type="application/json",
                                         response_schema=SCHEMA, temperature=0.2)
    ultimo = None
    for rodada in range(2):
        for modelo in MODELOS:
            try:
                r = cliente.models.generate_content(model=modelo, contents=partes, config=config)
                return modelo, json.loads(r.text)
            except Exception as e:
                ultimo = e
                msg = str(e)
                if not any(x in msg for x in ("503", "429", "499", "504", "500", "404", "UNAVAILABLE", "RESOURCE_EXHAUSTED",
                                                "CANCELLED", "DEADLINE", "timed out", "Timeout")):
                    raise
        time.sleep(20 * (rodada + 1))
    raise RuntimeError(f"O Gemini está sobrecarregado agora. Tente de novo mais tarde. ({str(ultimo)[:120]})")


def analisar(contratacao_id):
    """Baixa o edital, manda para a IA e guarda o resultado. Roda em segundo plano."""
    with _fila_trava:
        if contratacao_id in em_andamento:
            return
        em_andamento.add(contratacao_id)
    modelo = arquivos = dados = erro = None
    try:
        if not chave():
            raise RuntimeError("Falta a chave do Gemini (GEMINI_API_KEY) no arquivo .env")
        with banco.conectar() as con:
            c = con.execute("SELECT cnpj, ano, seq FROM contratacoes WHERE id=?", (contratacao_id,)).fetchone()
        lista = pncp.buscar_arquivos(c["cnpj"], c["ano"], c["seq"])
        pdfs = _escolher_pdfs(lista)
        if not pdfs:
            raise RuntimeError("Nenhum edital em PDF disponível para leitura (pode estar em .zip ou .docx).")
        arquivos = [t for t, _ in pdfs]
        modelo, dados = _perguntar(pdfs)
    except Exception as e:
        erro = str(e)[:400]
    finally:
        with banco.conectar() as con:
            con.execute("REPLACE INTO analises VALUES (?,?,?,?,?,?)",
                        (contratacao_id, datetime.now().isoformat(timespec="seconds"), modelo,
                         json.dumps(arquivos, ensure_ascii=False) if arquivos else None,
                         json.dumps(dados, ensure_ascii=False) if dados else None, erro))
        em_andamento.discard(contratacao_id)


def analisar_em_segundo_plano(contratacao_id):
    threading.Thread(target=analisar, args=(contratacao_id,), daemon=True).start()


def ler(contratacao_id):
    with banco.conectar() as con:
        a = con.execute("SELECT * FROM analises WHERE contratacao_id=?", (contratacao_id,)).fetchone()
    if not a:
        return None
    return {"criado": a["criado"], "modelo": a["modelo"], "erro": a["erro"],
            "arquivos": json.loads(a["arquivos"]) if a["arquivos"] else [],
            "dados": json.loads(a["dados"]) if a["dados"] else None}


def raios():
    """Raio exigido encontrado pela IA, por licitação (para a nota)."""
    with banco.conectar() as con:
        linhas = con.execute("SELECT contratacao_id, dados FROM analises WHERE dados IS NOT NULL").fetchall()
    saida = {}
    for l in linhas:
        r = json.loads(l["dados"]).get("raio_km")
        if isinstance(r, (int, float)) and r > 0:
            saida[l["contratacao_id"]] = float(r)
    return saida


def analisar_melhores(lista, nota_min=7, maximo=15):
    """Depois de cada coleta: lê sozinho os editais das melhores licitações ainda não lidas."""
    with banco.conectar() as con:
        feitas = {r[0] for r in con.execute("SELECT contratacao_id FROM analises WHERE erro IS NULL")}
    alvo = [o["id"] for o in sorted(lista, key=lambda o: -o["nota"])
            if o["nota"] >= nota_min and o["id"] not in feitas and not o["descartado"]][:maximo]
    for cid in alvo:
        analisar(cid)


# Liga os documentos pedidos no edital aos documentos do cofre.
MAPA_DOCS = [
    (("fgts", "crf"), "fgts"), (("trabalhist", "cndt"), "trabalhist"),
    (("federal", "nacional", "uniao", "receita", "pgfn"), "federal"), (("estadual", "estado"), "estadual"),
    (("municipal", "municipio"), "municipal"), (("falencia", "recuperacao judicial"), "falencia"),
    (("balanco", "demonstracoes contabeis", "demonstracao contabil"), "balanco"),
    (("atestado", "capacidade tecnica"), "atestado"), (("contrato social", "ato constitutivo", "estatuto"), "contrato social"),
    (("cnpj",), "cnpj"), (("alvara",), "alvara"),
]


def alvo_do_documento(nome_exigido):
    """Trecho do nome do documento do cofre que corresponde ao que o edital pede (ou None)."""
    from .texto import normalizar
    n = normalizar(nome_exigido)
    for gatilhos, alvo in MAPA_DOCS:
        if any(g in n for g in gatilhos):
            return alvo
    return None
