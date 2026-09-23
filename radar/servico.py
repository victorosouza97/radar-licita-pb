"""Regras compartilhadas entre a versão online (GitHub) e a do computador."""
import json
import re
from collections import defaultdict
from datetime import date, datetime
from urllib.parse import urlparse

from . import banco, ia, nota
from .texto import Buscador, normalizar

_cache = {"chave": None, "lista": None}

PLATAFORMAS = {
    "portaldecompraspublicas": "Portal de Compras Públicas", "bll": "BLL Compras",
    "licitanet": "Licitanet", "compras.gov": "Compras.gov.br", "comprasnet": "Compras.gov.br",
    "bnc": "BNC Compras", "bbmnet": "BBMNet", "licitacoes-e": "Licitações-e (BB)",
    "centraldecompras.pb": "Central de Compras PB", "cnetmobile": "Compras.gov.br",
}


def avaliar_todas():
    """Lista todas as licitações abertas, já com nota. Guarda em memória até algo mudar."""
    cfg = banco.ler_config()
    with banco.conectar() as con:
        ultima = con.execute("SELECT MAX(id) FROM coletas").fetchone()[0]
        marcas = con.execute("SELECT SUM(favorito)*1000+SUM(descartado) FROM contratacoes").fetchone()[0]
        analises = con.execute("SELECT COUNT(*), MAX(criado) FROM analises").fetchone()
        chave = (ultima, json.dumps(cfg, sort_keys=True), marcas, tuple(analises))
        if _cache["chave"] == chave:
            return _cache["lista"]
        agora = datetime.now()
        contratacoes = con.execute(
            "SELECT * FROM contratacoes WHERE encerramento >= ?", (agora.isoformat(),)).fetchall()
        itens = defaultdict(list)
        for it in con.execute("SELECT contratacao_id, numero, descricao_norm, beneficio_id, valor_total FROM itens"):
            itens[it["contratacao_id"]].append(it)
        # Na primeira coleta tudo é "novo"; só marca como nova o que surgiu depois dela.
        primeira = con.execute("SELECT MIN(primeira_vez) FROM contratacoes").fetchone()[0]

    buscador = Buscador(cfg["palavras"], cfg["negativas"])
    raio_ia = ia.raios()
    lista = []
    for c in contratacoes:
        av = nota.calcular(c, itens.get(c["id"], []), buscador, agora, raio_ia.get(c["id"]))
        benef = set((c["beneficios"] or "").split(","))
        lista.append({
            "id": c["id"], "orgao": c["orgao"], "unidade": c["unidade"], "municipio": c["municipio"],
            "objeto": c["objeto"], "modalidade": c["modalidade"], "modalidade_id": c["modalidade_id"],
            "srp": bool(c["srp"]), "valor": c["valor"], "encerramento": c["encerramento"],
            "plataforma": plataforma(c), "favorito": bool(c["favorito"]),
            "descartado": bool(c["descartado"]),
            "nova": c["primeira_vez"] == c["coletado_em"] and c["primeira_vez"] != primeira,
            "me_exclusivo": nota.EXCLUSIVO_ME in benef, "me_cota": nota.COTA_ME in benef,
            "itens_ok": bool(c["itens_ok"]), **av,
        })
    _cache.update(chave=chave, lista=lista)
    return lista


def plataforma(c):
    """Nome da plataforma de disputa: '[Portal de Compras Públicas] - ...' no objeto, ou o site do link."""
    m = re.match(r"\s*\[([^\]]+)\]", c["objeto"] or "")
    if m:
        return _nome_conhecido(m.group(1).strip())
    if c["link_origem"]:
        return _nome_conhecido(urlparse(c["link_origem"]).netloc.lower().removeprefix("www."))
    return c["plataforma"] or ""


def _nome_conhecido(texto):
    chave = re.sub(r"[^a-z0-9.]", "", texto.lower())
    return next((nome for trecho, nome in PLATAFORMAS.items() if trecho in chave), texto)


def status_doc(d):
    tem_arquivo = d.get("arquivo") or d.get("link_arquivo")
    if d["sem_validade"]:
        return ("good", "Sem vencimento") if tem_arquivo else ("plain", "Falta enviar o arquivo")
    if not d["validade"]:
        return ("plain", "Não cadastrado")
    dias = (date.fromisoformat(d["validade"]) - date.today()).days
    if dias < 0:
        return ("bad", f"Vencido há {-dias} dia(s)")
    if dias <= 15:
        return ("warn", f"Vence em {dias} dia(s)")
    return ("good", "Válido")


def docs():
    with banco.conectar() as con:
        linhas = con.execute("SELECT * FROM documentos ORDER BY id").fetchall()
    saida = []
    for d in linhas:
        d = dict(d)
        cls, txt = status_doc(d)
        saida.append({**d, "status": cls, "status_txt": txt})
    return saida


def doc_do_cofre(nome_exigido, lista_docs):
    """Procura no cofre o documento que corresponde ao que o edital pede."""
    n = normalizar(nome_exigido)
    for gatilhos, alvo in ia.MAPA_DOCS:
        if any(g in n for g in gatilhos):
            for d in lista_docs:
                if alvo in normalizar(d["nome"]):
                    return {"cofre": d["nome"], "status": d["status"], "status_txt": d["status_txt"]}
    return {"cofre": None, "status": "plain", "status_txt": "Conferir"}
