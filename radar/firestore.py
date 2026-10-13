"""Leitura do Firebase (Firestore), onde o site guarda o que você muda nele.

Com o segredo FIREBASE_SA (chave da conta de serviço do projeto, em JSON), o robô entra com
acesso próprio, que não depende das regras do banco — assim as regras podem exigir login
com Google para todo o resto. Sem o segredo, usa a API pública (só funciona com regras abertas).
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

PROJETO = os.getenv("FIREBASE_PROJECT", "")
_credencial = None


def configurado():
    return bool(PROJETO)


def _base():
    return f"https://firestore.googleapis.com/v1/projects/{PROJETO}/databases/(default)/documents"


def _cabecalhos():
    global _credencial
    chave = os.getenv("FIREBASE_SA", "").strip()
    if not chave:
        return {}
    if _credencial is None or not _credencial.valid:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account

        primeira = _credencial is None
        _credencial = service_account.Credentials.from_service_account_info(
            json.loads(chave), scopes=["https://www.googleapis.com/auth/datastore"])
        _credencial.refresh(Request())
        if primeira:
            print("Firebase: acesso com a conta de serviço (FIREBASE_SA).")
    return {"Authorization": f"Bearer {_credencial.token}"}


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
        with urllib.request.urlopen(urllib.request.Request(url, headers=_cabecalhos()), timeout=60) as r:
            dados = json.load(r)
        for d in dados.get("documents", []):
            doc_id = d["name"].rsplit("/", 1)[-1]
            docs[doc_id] = {k: _valor(v) for k, v in d.get("fields", {}).items()}
        token = dados.get("nextPageToken")
        if not token:
            return docs


def apagar(colecao, doc_id):
    req = urllib.request.Request(f"{_base()}/{colecao}/{urllib.parse.quote(doc_id)}", method="DELETE",
                                 headers=_cabecalhos())
    try:
        urllib.request.urlopen(req, timeout=60).close()
    except urllib.error.HTTPError:
        pass


def id_seguro(contratacao_id):
    """O número do PNCP tem '/', que o Firestore não aceita em nome de documento."""
    return contratacao_id.replace("/", "_")


def id_original(doc_id):
    return doc_id[::-1].replace("_", "/", 1)[::-1]
