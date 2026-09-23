"""Leitura do Firebase (Firestore), onde o site guarda o que você muda nele.

Usa a API pública do Firestore, sem senha: as regras do banco (firestore.rules) liberam
o acesso, do mesmo jeito que no Placar 7 Wonders.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

PROJETO = os.getenv("FIREBASE_PROJECT", "")


def configurado():
    return bool(PROJETO)


def _base():
    return f"https://firestore.googleapis.com/v1/projects/{PROJETO}/databases/(default)/documents"


def _valor(v):
    if "stringValue" in v:
        return v["stringValue"]
    if "booleanValue" in v:
        return v["booleanValue"]
    if "integerValue" in v:
        return int(v["integerValue"])
    if "doubleValue" in v:
        return v["doubleValue"]
    if "timestampValue" in v:
        return v["timestampValue"]
    if "arrayValue" in v:
        return [_valor(x) for x in v["arrayValue"].get("values", [])]
    if "mapValue" in v:
        return {k: _valor(x) for k, x in v["mapValue"].get("fields", {}).items()}
    return None


def listar(colecao):
    """Devolve {id_do_documento: {campos}} de uma coleção inteira."""
    docs, token = {}, None
    while True:
        q = {"pageSize": 300}
        if token:
            q["pageToken"] = token
        url = f"{_base()}/{colecao}?{urllib.parse.urlencode(q)}"
        with urllib.request.urlopen(url, timeout=60) as r:
            dados = json.load(r)
        for d in dados.get("documents", []):
            doc_id = d["name"].rsplit("/", 1)[-1]
            docs[doc_id] = {k: _valor(v) for k, v in d.get("fields", {}).items()}
        token = dados.get("nextPageToken")
        if not token:
            return docs


def apagar(colecao, doc_id):
    req = urllib.request.Request(f"{_base()}/{colecao}/{urllib.parse.quote(doc_id)}", method="DELETE")
    try:
        urllib.request.urlopen(req, timeout=60).close()
    except urllib.error.HTTPError:
        pass


def id_seguro(contratacao_id):
    """O número do PNCP tem '/', que o Firestore não aceita em nome de documento."""
    return contratacao_id.replace("/", "_")


def id_original(doc_id):
    return doc_id[::-1].replace("_", "/", 1)[::-1]
