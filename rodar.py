"""Rodada diária do Radar (executada pelo GitHub Actions todo dia às 7h).

1. Lê do Firebase o que você mudou no site (palavras, favoritos, descartes, documentos, pedidos de leitura).
2. Busca as licitações abertas da PB no PNCP.
3. A IA lê os editais com nota acima de 6 e os que você pediu.
4. Gera os arquivos do site (pasta site/dados).
5. Envia o e-mail do dia.

Para testar no computador: python rodar.py
"""
import sys

import truststore

truststore.inject_into_ssl()
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from radar import alertas, banco, firestore, ia, pncp, servico

PASTA_SITE = Path(__file__).resolve().parent / "site"
PASTA_DADOS_SITE = PASTA_SITE / "dados"
NOTA_LEITURA_AUTOMATICA = 6      # a IA lê sozinha os editais com nota ACIMA desta
MAX_LEITURAS_POR_DIA = int(os.getenv("RADAR_MAX_IA", "25"))
TEMPO_MAX_IA = 25 * 60           # segundos


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def sincronizar_firebase():
    """Traz para o banco local o que foi mudado no site. Devolve os pedidos de leitura pela IA."""
    if not firestore.configurado():
        log("Firebase não configurado: usando só o que está no banco.")
        return []
    cfg = firestore.listar("config")
    if "palavras" in cfg:
        banco.salvar_config({k: cfg["palavras"][k] for k in ("palavras", "negativas") if k in cfg["palavras"]})
    marcas = firestore.listar("marcas")
    with banco.conectar() as con:
        con.execute("UPDATE contratacoes SET favorito=0, descartado=0")
        for doc_id, m in marcas.items():
            con.execute("UPDATE contratacoes SET favorito=?, descartado=? WHERE id=?",
                        (1 if m.get("favorito") else 0, 1 if m.get("descartado") else 0,
                         firestore.id_original(doc_id)))
    docs = firestore.listar("documentos")
    if docs:
        with banco.conectar() as con:
            con.execute("DELETE FROM documentos")
            for d in docs.values():
                con.execute(
                    "INSERT INTO documentos (nome, emissor, validade, sem_validade, link_arquivo, link_emissao, obs)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (d.get("nome", ""), d.get("emissor", ""), d.get("validade") or None,
                     1 if d.get("sem_validade") else 0, d.get("link_arquivo", ""),
                     d.get("link_emissao", ""), d.get("obs", "")))
    pedidos = [firestore.id_original(i) for i in firestore.listar("pedidos_ia")]
    log(f"Firebase: {len(marcas)} marcações, {len(docs)} documentos, {len(pedidos)} pedidos de leitura.")
    return pedidos


def ler_editais(lista, pedidos):
    with banco.conectar() as con:
        feitas = {r[0] for r in con.execute("SELECT contratacao_id FROM analises WHERE dados IS NOT NULL")}
    abertas = {o["id"] for o in lista}
    fila = [p for p in pedidos if p in abertas]
    fila += [o["id"] for o in sorted(lista, key=lambda o: -o["nota"])
             if o["nota"] > NOTA_LEITURA_AUTOMATICA and not o["descartado"]
             and o["id"] not in feitas and o["id"] not in fila]
    fila = fila[:MAX_LEITURAS_POR_DIA]
    inicio, lidas = time.time(), 0
    for cid in fila:
        if time.time() - inicio > TEMPO_MAX_IA:
            log("Tempo da IA esgotado por hoje; o resto fica para amanhã.")
            break
        ia.analisar(cid)
        a = ia.ler(cid)
        if a and a["dados"]:
            lidas += 1
            if cid in pedidos and firestore.configurado():
                firestore.apagar("pedidos_ia", firestore.id_seguro(cid))
        log(f"IA: {cid} -> {'ok' if a and a['dados'] else (a or {}).get('erro')}")
    return lidas


CAMPOS_LISTA = ["id", "orgao", "unidade", "municipio", "objeto", "modalidade", "modalidade_id", "srp",
                "valor", "encerramento", "plataforma", "nova", "me_exclusivo", "me_cota", "nota",
                "palavras", "itens_batem", "motivos", "alertas", "km", "raio"]


def exportar_site(lista, info, pncp_fora=False):
    if PASTA_DADOS_SITE.exists():
        shutil.rmtree(PASTA_DADOS_SITE)
    (PASTA_DADOS_SITE / "detalhe").mkdir(parents=True)
    with banco.conectar() as con:
        analisadas = {r[0] for r in con.execute("SELECT contratacao_id FROM analises WHERE dados IS NOT NULL")}
        detalhados = 0
        for o in lista:
            if not (o["nota"] > 0 or o["favorito"] or o["id"] in analisadas):
                continue
            c = con.execute("SELECT * FROM contratacoes WHERE id=?", (o["id"],)).fetchone()
            itens = con.execute("SELECT * FROM itens WHERE contratacao_id=? ORDER BY numero", (o["id"],)).fetchall()
            arquivos = None
            if not pncp_fora:  # com o PNCP fora do ar, não perde tempo buscando a lista de arquivos
                try:
                    arquivos = pncp.buscar_arquivos(c["cnpj"], c["ano"], c["seq"], tentativas=2)
                except Exception:
                    pass
            analise = ia.ler(o["id"])
            exigidos = []
            if analise and analise["dados"]:
                for nome in analise["dados"].get("documentos_exigidos", []):
                    exigidos.append({"nome": nome, "alvo": ia.alvo_do_documento(nome)})
            batem = set(o["itens_batem"])
            detalhe = {
                "info": c["info"], "link_origem": c["link_origem"],
                "link_pncp": f"https://pncp.gov.br/app/editais/{c['cnpj']}/{c['ano']}/{c['seq']}",
                "itens": [{"numero": i["numero"], "descricao": i["descricao"], "qtd": i["qtd"],
                           "unidade": i["unidade"], "valor_unit": i["valor_unit"], "beneficio": i["beneficio"],
                           "bate": i["numero"] in batem} for i in itens[:300]],
                "total_itens": len(itens), "arquivos": arquivos,
                "analise": analise if analise and analise["dados"] else None, "exigidos": exigidos,
            }
            (PASTA_DADOS_SITE / "detalhe" / f"{firestore.id_seguro(o['id'])}.json").write_text(
                json.dumps(detalhe, ensure_ascii=False), encoding="utf-8")
            detalhados += 1
    cfg = banco.ler_config()
    saida = {
        "atualizado": datetime.now().isoformat(timespec="seconds"), **info,
        "palavras": cfg["palavras"], "negativas": cfg["negativas"],
        "firebase_projeto": firestore.PROJETO,
        "oportunidades": [{**{k: o[k] for k in CAMPOS_LISTA}, "lida_ia": o["id"] in analisadas} for o in lista],
    }
    (PASTA_DADOS_SITE / "oportunidades.json").write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")
    log(f"Site: {len(lista)} licitações, {detalhados} com detalhes.")


def main():
    banco.iniciar()
    ia.iniciar()
    alertas.iniciar()
    pedidos = sincronizar_firebase()

    log("Buscando licitações no PNCP…")
    pncp.coletar()
    erro = pncp.status["erro"]
    if erro:
        log(f"PNCP com problema ({erro}); tentando de novo em 5 minutos…")
        time.sleep(300)
        pncp.coletar()
        erro = pncp.status["erro"]
        log(f"Segunda tentativa: {'falhou: ' + erro if erro else 'ok'}")

    lista = servico.avaliar_todas()
    lidas = ler_editais(lista, pedidos) if ia.chave() else 0
    lista = servico.avaliar_todas()  # a IA pode ter achado exigência de raio
    info = {"abertas": len(lista), "combinam": sum(1 for o in lista if o["nota"] > 0),
            "lidas_ia": lidas, "erro": f"O PNCP falhou hoje; mostrando os dados de ontem. ({erro})" if erro else None}
    exportar_site(lista, info, pncp_fora=bool(erro))

    try:
        if alertas.email_diario(lista, servico.docs(), info):
            log("E-mail do dia enviado.")
        else:
            log("E-mail não configurado (faltam os segredos GMAIL_USER e GMAIL_APP_PASSWORD).")
    except Exception as e:
        log(f"Falha ao enviar o e-mail: {e}")
        raise


if __name__ == "__main__":
    main()
