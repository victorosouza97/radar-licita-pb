"""Radar Licita PB — Fase 1.

Para abrir: dê dois cliques em "Iniciar Radar.bat" (ou rode: python app.py).
O programa abre no navegador em http://127.0.0.1:8765
"""
import sys

import truststore

truststore.inject_into_ssl()  # usa os certificados do Windows (necessário com o Norton)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import threading
import uuid
import webbrowser
from datetime import date, datetime
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

from radar import alertas, banco, ia, pncp, servico

PORTA = 8765
app = Flask(__name__, static_folder="static", static_url_path="/static")
app.json.ensure_ascii = False

_avaliar_todas = servico.avaliar_todas
_plataforma = servico.plataforma
_docs = servico.docs
_doc_do_cofre = servico.doc_do_cofre


# ---------------- Páginas e API ----------------

@app.get("/")
def inicio():
    return send_from_directory("static", "index.html")


@app.get("/api/status")
def status():
    with banco.conectar() as con:
        ult = con.execute("SELECT * FROM coletas WHERE erro IS NULL ORDER BY id DESC LIMIT 1").fetchone()
    return jsonify({**pncp.status, "ultima_ok": dict(ult) if ult else None})


@app.post("/api/coletar")
def coletar():
    pncp.coletar_em_segundo_plano()
    return jsonify(ok=True)


@app.get("/api/oportunidades")
def oportunidades():
    a = request.args
    lista = _avaliar_todas()
    q = a.get("q", "").strip().lower()
    nota_min = float(a.get("nota_min", 0.1))
    vmax = float(a.get("vmax") or 0)
    res = []
    for o in lista:
        if a.get("ver") == "favoritas":
            if not o["favorito"]:
                continue
        elif a.get("ver") == "descartadas":
            if not o["descartado"]:
                continue
        elif o["descartado"] or o["nota"] < nota_min:
            continue
        if q and q not in (o["objeto"] + " " + o["orgao"]).lower():
            continue
        if a.get("municipio") and o["municipio"] != a["municipio"]:
            continue
        if a.get("modalidade") and o["modalidade"] != a["modalidade"]:
            continue
        if vmax and (o["valor"] or 0) > vmax:
            continue
        kmax = float(a.get("kmax") or 0)
        if kmax and (o["km"] is None or o["km"] > kmax):
            continue
        if a.get("sem_raio_fora") == "1" and o["raio"] and o["km"] and o["km"] > o["raio"]:
            continue
        if a.get("me") == "1" and not (o["me_exclusivo"] or o["me_cota"]):
            continue
        res.append(o)
    ordem = a.get("ordem", "nota")
    chaves = {"nota": lambda o: (-o["nota"], o["encerramento"]),
              "prazo": lambda o: o["encerramento"],
              "valor": lambda o: -(o["valor"] or 0),
              "distancia": lambda o: o["km"] if o["km"] is not None else 9999}
    res.sort(key=chaves.get(ordem, chaves["nota"]))
    return jsonify({
        "total_abertas": len(lista),
        "relevantes": sum(1 for o in lista if o["nota"] >= 0.1 and not o["descartado"]),
        "municipios": sorted({o["municipio"] for o in lista if o["municipio"]}),
        "modalidades": sorted({o["modalidade"] for o in lista if o["modalidade"]}),
        "itens": res[:400],
    })


@app.get("/api/oportunidades/<path:id_>")
def detalhe(id_):
    with banco.conectar() as con:
        c = con.execute("SELECT * FROM contratacoes WHERE id=?", (id_,)).fetchone()
        if not c:
            abort(404)
        itens = con.execute("SELECT * FROM itens WHERE contratacao_id=? ORDER BY numero", (id_,)).fetchall()
    resumo = next((o for o in _avaliar_todas() if o["id"] == id_), {})
    batem = set(resumo.get("itens_batem", []))
    try:
        arquivos = pncp.buscar_arquivos(c["cnpj"], c["ano"], c["seq"])
    except Exception:
        arquivos = None
    analise = ia.ler(id_)
    docs = _docs()
    exigidos = []
    if analise and analise["dados"]:
        for nome in analise["dados"].get("documentos_exigidos", []):
            exigidos.append({"nome": nome, **_doc_do_cofre(nome, docs)})
    return jsonify({
        **dict(c), **resumo, "plataforma": _plataforma(c),
        "analise": analise, "analisando": id_ in ia.em_andamento, "exigidos": exigidos,
        "ia_configurada": bool(ia.chave()),
        "link_pncp": f"https://pncp.gov.br/app/editais/{c['cnpj']}/{c['ano']}/{c['seq']}",
        "itens": [{"numero": i["numero"], "descricao": i["descricao"], "qtd": i["qtd"],
                   "unidade": i["unidade"], "valor_unit": i["valor_unit"], "valor_total": i["valor_total"],
                   "beneficio": i["beneficio"], "bate": i["numero"] in batem} for i in itens],
        "arquivos": arquivos,
        "documentos": [{"nome": d["nome"], "status": d["status"], "status_txt": d["status_txt"]} for d in docs],
    })


@app.post("/api/oportunidades/<path:id_>/analisar")
def analisar(id_):
    ia.analisar_em_segundo_plano(id_)
    return jsonify(ok=True)


@app.post("/api/oportunidades/<path:id_>/marcar")
def marcar(id_):
    d = request.get_json(force=True)
    campo = d.get("campo")
    if campo not in ("favorito", "descartado"):
        abort(400)
    with banco.conectar() as con:
        con.execute(f"UPDATE contratacoes SET {campo}=? WHERE id=?", (1 if d.get("valor") else 0, id_))
    return jsonify(ok=True)


@app.get("/api/painel")
def painel():
    lista = [o for o in _avaliar_todas() if not o["descartado"]]
    boas = [o for o in lista if o["nota"] >= 7]
    semana = [o for o in lista if o["nota"] >= 0.1 and o["encerramento"][:10] <= _em_dias(7)]
    docs = _docs()
    return jsonify({
        "abertas": len(lista), "boas": len(boas),
        "novas": sum(1 for o in lista if o["nova"] and o["nota"] >= 0.1),
        "semana": sorted(semana, key=lambda o: o["encerramento"])[:12],
        "docs_alerta": [d for d in docs if d["status"] in ("bad", "warn")],
        "docs_pendentes": sum(1 for d in docs if d["status"] == "plain"),
        "melhores": sorted(boas, key=lambda o: -o["nota"])[:6],
    })


def _em_dias(n):
    from datetime import timedelta
    return (date.today() + timedelta(days=n)).isoformat()


def _config_publica():
    cfg = banco.ler_config()
    cfg["smtp_senha_definida"] = bool(cfg.pop("smtp_senha", ""))
    cfg["ia_configurada"] = bool(ia.chave())
    cfg["alertas_status"] = alertas.status
    return cfg


@app.get("/api/config")
def get_config():
    return jsonify(_config_publica())


@app.put("/api/config")
def put_config():
    dados = request.get_json(force=True)
    banco.salvar_config(dados)
    alertas.salvar(dados)
    return jsonify(_config_publica())


@app.post("/api/alertas/teste")
def alerta_teste():
    try:
        alertas.resumo_diario(_avaliar_todas(), _docs(), forcar=True)
    except Exception as e:
        return jsonify(erro=str(e)), 400
    return jsonify(ok=True)


@app.get("/api/documentos")
def listar_docs():
    return jsonify(_docs())


def _salvar_arquivo(f):
    ext = Path(f.filename).suffix.lower()[:8]
    nome = f"{uuid.uuid4().hex}{ext}"
    f.save(banco.PASTA_DOCS / nome)
    return nome


@app.post("/api/documentos")
@app.post("/api/documentos/<int:doc_id>")
def salvar_doc(doc_id=None):
    form = request.form
    campos = {
        "nome": form.get("nome", "").strip(), "emissor": form.get("emissor", "").strip(),
        "validade": form.get("validade") or None, "sem_validade": 1 if form.get("sem_validade") == "1" else 0,
        "obs": form.get("obs", "").strip(), "link_emissao": form.get("link_emissao", "").strip(),
        "atualizado": datetime.now().isoformat(timespec="seconds"),
    }
    if not campos["nome"]:
        return jsonify(erro="Dê um nome ao documento."), 400
    f = request.files.get("arquivo")
    with banco.conectar() as con:
        if f and f.filename:
            if doc_id:
                antigo = con.execute("SELECT arquivo FROM documentos WHERE id=?", (doc_id,)).fetchone()
                if antigo and antigo["arquivo"]:
                    (banco.PASTA_DOCS / antigo["arquivo"]).unlink(missing_ok=True)
            campos["arquivo"] = _salvar_arquivo(f)
            campos["arquivo_nome"] = f.filename
        if doc_id:
            sets = ",".join(f"{k}=?" for k in campos)
            con.execute(f"UPDATE documentos SET {sets} WHERE id=?", [*campos.values(), doc_id])
        else:
            cols = ",".join(campos)
            con.execute(f"INSERT INTO documentos ({cols}) VALUES ({','.join('?' * len(campos))})",
                        list(campos.values()))
    return jsonify(ok=True)


@app.delete("/api/documentos/<int:doc_id>")
def apagar_doc(doc_id):
    with banco.conectar() as con:
        d = con.execute("SELECT arquivo FROM documentos WHERE id=?", (doc_id,)).fetchone()
        if d and d["arquivo"]:
            (banco.PASTA_DOCS / d["arquivo"]).unlink(missing_ok=True)
        con.execute("DELETE FROM documentos WHERE id=?", (doc_id,))
    return jsonify(ok=True)


@app.get("/api/documentos/<int:doc_id>/arquivo")
def baixar_doc(doc_id):
    with banco.conectar() as con:
        d = con.execute("SELECT arquivo, arquivo_nome FROM documentos WHERE id=?", (doc_id,)).fetchone()
    if not d or not d["arquivo"]:
        abort(404)
    return send_file(banco.PASTA_DOCS / d["arquivo"], download_name=d["arquivo_nome"])


if __name__ == "__main__":
    banco.iniciar()
    ia.iniciar()
    alertas.iniciar()
    pncp.depois_da_coleta += [lambda: alertas.alerta_novas(_avaliar_todas()),
                              lambda: ia.analisar_melhores(_avaliar_todas())]
    alertas.agendar(_avaliar_todas, _docs)
    pncp.agendar(horas=6)
    if "--sem-navegador" not in sys.argv:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{PORTA}")).start()
    print(f"Radar Licita PB rodando em http://127.0.0.1:{PORTA}  (feche esta janela para desligar)")
    app.run(host="127.0.0.1", port=PORTA, debug=False, threaded=True)
