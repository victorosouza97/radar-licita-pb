"""Coleta de licitações abertas no PNCP (Portal Nacional de Contratações Públicas).

API pública e gratuita: https://pncp.gov.br/api/consulta/swagger-ui/index.html
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from . import banco
from .texto import normalizar

URL_CONSULTA = "https://pncp.gov.br/api/consulta/v1/contratacoes/proposta"
URL_COMPRA = "https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}"

# Estado da coleta em andamento, mostrado na tela.
status = {"rodando": False, "etapa": "", "feito": 0, "total": 0, "ultima": None, "erro": None}
_trava = threading.Lock()
# Funções chamadas depois de cada coleta bem-sucedida (alertas, leitura pela IA).
depois_da_coleta = []


def _get(url, tentativas=7):
    for n in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json",
                                                       "User-Agent": "RadarLicitaPB/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                corpo = r.read()
                return json.loads(corpo) if corpo else None
        except urllib.error.HTTPError as e:
            if e.code == 204:
                return None
            if e.code < 500 and e.code != 429:
                raise
            erro = e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            erro = e
        time.sleep(min(30, 3 * (n + 1)))
    raise erro


def buscar_arquivos(cnpj, ano, seq, tentativas=7):
    """Lista os arquivos (edital, termo de referência...) de uma licitação."""
    dados = _get(URL_COMPRA.format(cnpj=cnpj, ano=ano, seq=seq) + "/arquivos", tentativas) or []
    return [{"titulo": a.get("titulo"), "tipo": a.get("tipoDocumentoNome"), "url": a.get("url")}
            for a in dados if a.get("statusAtivo", True)]


def _buscar_itens(cnpj, ano, seq):
    itens, pagina = [], 1
    while True:
        lote = _get(URL_COMPRA.format(cnpj=cnpj, ano=ano, seq=seq)
                    + f"/itens?pagina={pagina}&tamanhoPagina=500") or []
        itens.extend(lote)
        if len(lote) < 500:
            return itens
        pagina += 1


def _salvar_contratacao(con, c, agora):
    uo = c.get("unidadeOrgao") or {}
    oe = c.get("orgaoEntidade") or {}
    antigo = con.execute("SELECT atualizado FROM contratacoes WHERE id=?",
                         (c["numeroControlePNCP"],)).fetchone()
    atualizado = c.get("dataAtualizacaoGlobal") or c.get("dataAtualizacao")
    campos = dict(
        id=c["numeroControlePNCP"], cnpj=oe.get("cnpj"), ano=c.get("anoCompra"),
        seq=c.get("sequencialCompra"), orgao=oe.get("razaoSocial"), unidade=uo.get("nomeUnidade"),
        municipio=uo.get("municipioNome"), uf=uo.get("ufSigla"),
        objeto=c.get("objetoCompra") or "", objeto_norm=normalizar(c.get("objetoCompra")),
        info=c.get("informacaoComplementar") or "", modalidade=c.get("modalidadeNome"),
        modalidade_id=c.get("modalidadeId"), srp=1 if c.get("srp") else 0,
        valor=c.get("valorTotalEstimado") or 0, abertura=c.get("dataAberturaProposta"),
        encerramento=c.get("dataEncerramentoProposta"), situacao=c.get("situacaoCompraNome"),
        plataforma=c.get("usuarioNome"), link_origem=c.get("linkSistemaOrigem"),
        atualizado=atualizado, coletado_em=agora,
    )
    if antigo is None:
        campos["primeira_vez"] = agora
        cols = ",".join(campos)
        con.execute(f"INSERT INTO contratacoes ({cols}) VALUES ({','.join('?' * len(campos))})",
                    list(campos.values()))
        return True
    sets = ",".join(f"{k}=?" for k in campos if k != "id")
    valores = [v for k, v in campos.items() if k != "id"]
    if antigo["atualizado"] != atualizado:
        sets += ",itens_ok=0"
    con.execute(f"UPDATE contratacoes SET {sets} WHERE id=?", valores + [campos["id"]])
    return False


def coletar(uf="PB"):
    """Baixa todas as licitações com propostas abertas no estado e os itens de cada uma."""
    if not _trava.acquire(blocking=False):
        return
    inicio = datetime.now().isoformat(timespec="seconds")
    status.update(rodando=True, etapa="Buscando licitações abertas", feito=0, total=0, erro=None)
    novas = total = 0
    try:
        con = banco.conectar()
        limite = (datetime.now() + timedelta(days=365)).strftime("%Y%m%d")
        pagina = 1
        while True:
            q = urllib.parse.urlencode({"dataFinal": limite, "uf": uf, "pagina": pagina,
                                        "tamanhoPagina": 50})
            resp = _get(f"{URL_CONSULTA}?{q}") or {}
            if pagina == 1:
                status["total"] = resp.get("totalRegistros", 0)
            with con:
                for c in resp.get("data") or []:
                    novas += _salvar_contratacao(con, c, inicio)
                    total += 1
            status["feito"] = total
            if not resp.get("paginasRestantes"):
                break
            pagina += 1

        pendentes = con.execute(
            "SELECT id, cnpj, ano, seq FROM contratacoes WHERE itens_ok=0 AND encerramento>=?",
            (datetime.now().isoformat(),)).fetchall()
        status.update(etapa="Lendo os itens de cada licitação", feito=0, total=len(pendentes))
        for i, p in enumerate(pendentes, 1):
            try:
                itens = _buscar_itens(p["cnpj"], p["ano"], p["seq"])
            except Exception:
                continue  # tenta de novo na próxima coleta
            beneficios = sorted({str(it.get("tipoBeneficio")) for it in itens if it.get("tipoBeneficio")})
            with con:
                con.execute("DELETE FROM itens WHERE contratacao_id=?", (p["id"],))
                con.executemany(
                    "INSERT OR REPLACE INTO itens VALUES (?,?,?,?,?,?,?,?,?,?)",
                    [(p["id"], it.get("numeroItem"), it.get("descricao") or "",
                      normalizar((it.get("descricao") or "") + " " + (it.get("informacaoComplementar") or "")),
                      it.get("quantidade"), it.get("unidadeMedida"), it.get("valorUnitarioEstimado"),
                      it.get("valorTotal"), it.get("tipoBeneficio"), it.get("tipoBeneficioNome"))
                     for it in itens])
                con.execute("UPDATE contratacoes SET itens_ok=1, beneficios=? WHERE id=?",
                            (",".join(beneficios), p["id"]))
            status["feito"] = i
            time.sleep(0.05)
        con.close()
    except Exception as e:
        status["erro"] = f"{type(e).__name__}: {e}"
    finally:
        fim = datetime.now().isoformat(timespec="seconds")
        with banco.conectar() as con:
            con.execute("INSERT INTO coletas (inicio, fim, total, novas, erro) VALUES (?,?,?,?,?)",
                        (inicio, fim, total, novas, status["erro"]))
        status.update(rodando=False, etapa="", ultima=fim)
        _trava.release()
    if not status["erro"]:
        for f in depois_da_coleta:
            try:
                f()
            except Exception as e:
                print("Erro depois da coleta:", e)


def coletar_em_segundo_plano():
    threading.Thread(target=coletar, daemon=True).start()


def agendar(horas=6):
    """Repete a coleta a cada X horas enquanto o programa estiver aberto."""
    def laco():
        while True:
            coletar()
            time.sleep(horas * 3600)
    threading.Thread(target=laco, daemon=True).start()
