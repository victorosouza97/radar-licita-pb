"""Alertas por e-mail (Gmail, gratuito).

Usa uma "senha de app" do Google: uma senha especial só para programas enviarem e-mail,
diferente da senha normal da conta. Criada em https://myaccount.google.com/apppasswords
"""
import html
import json
import os
import smtplib
import ssl
import threading
import time
from datetime import date, datetime, timedelta
from email.message import EmailMessage

from . import banco

ESQUEMA = """
CREATE TABLE IF NOT EXISTS alertas_enviados (
    tipo TEXT, ref TEXT, enviado_em TEXT, PRIMARY KEY (tipo, ref)
);
"""
PADRAO = {"email_ativo": False, "smtp_usuario": "", "smtp_senha": "", "email_para": "",
          "hora_resumo": "07:00", "nota_alerta": 7, "alerta_imediato": True}
URL_APP = os.getenv("SITE_URL", "http://127.0.0.1:8765")

status = {"ultimo_envio": None, "ultimo_erro": None}


def iniciar():
    with banco.conectar() as con:
        con.executescript(ESQUEMA)
        for k, v in PADRAO.items():
            con.execute("INSERT OR IGNORE INTO config VALUES (?, ?)", (k, json.dumps(v)))


def salvar(dados):
    with banco.conectar() as con:
        for k in PADRAO:
            if k in dados:
                if k == "smtp_senha" and not dados[k]:
                    continue  # campo vazio = manter a senha atual
                v = dados[k]
                if k == "smtp_senha":
                    v = v.replace(" ", "")  # o Google mostra a senha de app em blocos com espaço
                con.execute("REPLACE INTO config VALUES (?, ?)", (k, json.dumps(v)))


def _cfg():
    cfg = banco.ler_config()
    if os.getenv("GMAIL_USER"):  # versão online: dados vêm dos "segredos" do GitHub
        cfg.update(email_ativo=True, smtp_usuario=os.getenv("GMAIL_USER"),
                   smtp_senha=os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", ""),
                   email_para=os.getenv("EMAIL_TO") or os.getenv("GMAIL_USER"))
    return cfg


def enviar(assunto, corpo_html, cfg=None):
    cfg = cfg or _cfg()
    para = [e.strip() for e in cfg.get("email_para", "").replace(";", ",").split(",") if e.strip()]
    if not (cfg.get("smtp_usuario") and cfg.get("smtp_senha") and para):
        raise RuntimeError("Preencha o seu Gmail, a senha de app e para quem enviar.")
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = f"Radar Licita PB <{cfg['smtp_usuario']}>"
    msg["To"] = ", ".join(para)
    msg.set_content("Abra este e-mail num programa que mostre HTML.")
    msg.add_alternative(corpo_html, subtype="html")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=60) as s:
            s.login(cfg["smtp_usuario"], cfg["smtp_senha"])
            s.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError("O Gmail recusou o login. Confira o e-mail e a senha de app (não é a senha normal).")
    status.update(ultimo_envio=datetime.now().isoformat(timespec="seconds"), ultimo_erro=None)


# ---------------- montagem dos e-mails ----------------

def _moeda(v):
    return f"R$ {v or 0:,.0f}".replace(",", ".")


def _linha(o):
    d = datetime.fromisoformat(o["encerramento"])
    link = f"https://pncp.gov.br/app/editais/{o['id'].split('-')[0]}/{o['id'].split('/')[-1]}/{int(o['id'].split('-')[-1].split('/')[0])}"
    avisos = "".join(f'<div style="color:#9A5B00;font-size:13px">⚠ {html.escape(a)}</div>'
                     for a in o.get("alertas", []) if "raio" in a or "Prazo" in a)
    return f"""<tr><td style="padding:10px 8px;border-bottom:1px solid #ddd;vertical-align:top">
      <b style="background:#DCF0E3;color:#1B7648;padding:2px 8px;border-radius:10px">{o['nota']:.1f}</b></td>
      <td style="padding:10px 8px;border-bottom:1px solid #ddd">
      <a href="{_link_site(o) or link}" style="color:#0B6A7F;font-weight:bold;text-decoration:none">{html.escape(_limpo(o['objeto'])[:160])}</a>
      <div style="color:#555;font-size:13px">{html.escape(o['municipio'] or '')}{f" (~{o['km']} km)" if o.get('km') is not None else ''} · {_moeda(o['valor'])} ·
      propostas até {d:%d/%m %H:%M} · {html.escape(o.get('plataforma') or '')}</div>{avisos}</td></tr>"""


def _limpo(t):
    import re
    return re.sub(r"^\s*\[[^\]]*\]\s*-?\s*", "", t or "").strip()


def _pagina(titulo, blocos):
    return f"""<div style="font-family:Segoe UI,Arial,sans-serif;max-width:680px;color:#132429">
      <h2 style="margin:0 0 4px">{titulo}</h2>
      <p style="color:#555;margin:0 0 18px">Radar Licita PB · {datetime.now():%d/%m/%Y %H:%M}</p>
      {''.join(blocos)}
      <p style="margin-top:22px"><a href="{URL_APP}" style="background:#0B6A7F;color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none;font-weight:bold">Abrir o Radar</a></p>
      <p style="color:#777;font-size:12px;margin-top:18px">Radar Licita PB · busca diária no PNCP (portal oficial do governo).</p></div>"""


def _tabela(titulo, lista):
    if not lista:
        return ""
    return (f'<h3 style="margin:18px 0 6px">{titulo}</h3><table style="border-collapse:collapse;width:100%">'
            + "".join(_linha(o) for o in lista) + "</table>")


def _ja_enviados(tipo):
    with banco.conectar() as con:
        return {r[0] for r in con.execute("SELECT ref FROM alertas_enviados WHERE tipo=?", (tipo,))}


def _marcar(tipo, refs):
    agora = datetime.now().isoformat(timespec="seconds")
    with banco.conectar() as con:
        con.executemany("INSERT OR IGNORE INTO alertas_enviados VALUES (?,?,?)",
                        [(tipo, r, agora) for r in refs])


def alerta_novas(lista):
    """Logo depois de cada atualização: avisa das licitações boas que ainda não foram avisadas."""
    cfg = _cfg()
    if not (cfg.get("email_ativo") and cfg.get("alerta_imediato")):
        return
    enviados = _ja_enviados("oport")
    novas = [o for o in lista if o["nota"] >= float(cfg.get("nota_alerta", 7))
             and not o["descartado"] and o["id"] not in enviados and not _fora_do_raio(o)]
    if not novas:
        return
    novas.sort(key=lambda o: -o["nota"])
    n = len(novas)
    assunto = f"{n} licitação boa encontrada na PB" if n == 1 else f"{n} licitações boas encontradas na PB"
    try:
        enviar(assunto, _pagina(assunto, [_tabela("Novas oportunidades", novas[:30])]), cfg)
        _marcar("oport", [o["id"] for o in novas])
    except Exception as e:
        status["ultimo_erro"] = str(e)


def _fora_do_raio(o):
    return o.get("raio") and o.get("km") is not None and o["km"] > o["raio"]


def resumo_diario(lista, docs, forcar=False):
    """Um e-mail por dia: prazos que estão fechando e documentos vencendo."""
    cfg = _cfg()
    if not cfg.get("email_ativo") and not forcar:
        return
    hoje = date.today().isoformat()
    if not forcar and hoje in _ja_enviados("resumo"):
        return
    limite = (datetime.now() + timedelta(days=3)).isoformat()
    nota_min = float(cfg.get("nota_alerta", 7))
    fechando = sorted([o for o in lista if not o["descartado"] and o["encerramento"] <= limite
                       and (o["favorito"] or o["nota"] >= nota_min)], key=lambda o: o["encerramento"])
    docs_alerta = [d for d in docs if d["status"] in ("bad", "warn")]
    if not (fechando or docs_alerta or forcar):
        _marcar("resumo", [hoje])
        return
    blocos = [_tabela("Propostas que fecham nos próximos 3 dias", fechando)]
    if docs_alerta:
        blocos.append('<h3 style="margin:18px 0 6px">Documentos para resolver</h3><ul>' + "".join(
            f'<li><b>{html.escape(d["nome"])}</b>: <span style="color:{"#B42318" if d["status"] == "bad" else "#9A5B00"}">'
            f'{html.escape(d["status_txt"])}</span></li>' for d in docs_alerta) + "</ul>")
    if forcar and not (fechando or docs_alerta):
        blocos.append("<p>Nada urgente hoje. Este é um e-mail de teste: os alertas estão funcionando.</p>")
    assunto = "Radar: resumo do dia" + (f" · {len(fechando)} prazo(s) fechando" if fechando else "")
    enviar(assunto, _pagina("Resumo do dia", blocos), cfg)
    if not forcar:
        _marcar("resumo", [hoje])


def agendar(obter_lista, obter_docs):
    """Confere a cada 5 minutos se já passou da hora do resumo diário."""
    def laco():
        while True:
            try:
                cfg = _cfg()
                h, m = (int(x) for x in str(cfg.get("hora_resumo", "07:00")).split(":"))
                agora = datetime.now()
                if cfg.get("email_ativo") and (agora.hour, agora.minute) >= (h, m):
                    resumo_diario(obter_lista(), obter_docs())
            except Exception as e:
                status["ultimo_erro"] = str(e)
            time.sleep(300)
    threading.Thread(target=laco, daemon=True).start()


def email_diario(lista, docs, info):
    """Versão online: um e-mail por dia com tudo junto. Sempre chega, para você saber que o Radar está vivo."""
    cfg = _cfg()
    if not cfg.get("email_ativo"):
        return False
    nota_min = float(cfg.get("nota_alerta", 7))
    enviados = _ja_enviados("oport")
    novas = sorted([o for o in lista if o["nota"] >= nota_min and not o["descartado"]
                    and o["id"] not in enviados and not _fora_do_raio(o)], key=lambda o: -o["nota"])
    limite = (datetime.now() + timedelta(days=3)).isoformat()
    fechando = sorted([o for o in lista if not o["descartado"] and o["encerramento"] <= limite
                       and (o["favorito"] or o["nota"] >= nota_min)], key=lambda o: o["encerramento"])
    docs_alerta = [d for d in docs if d["status"] in ("bad", "warn")]

    resumo = (f"{info['abertas']} licitações abertas na PB · {info['combinam']} combinam com você · "
              f"{info['lidas_ia']} editais lidos pela IA hoje")
    blocos = [f'<p style="color:#333">{html.escape(resumo)}</p>']
    if info.get("erro"):
        blocos.append(f'<p style="color:#B42318"><b>Atenção:</b> {html.escape(info["erro"])}</p>')
    blocos.append(_tabela("Novas oportunidades boas", novas[:30]))
    blocos.append(_tabela("Propostas que fecham nos próximos 3 dias", fechando))
    if docs_alerta:
        blocos.append('<h3 style="margin:18px 0 6px">Documentos para resolver</h3><ul>' + "".join(
            f'<li><b>{html.escape(d["nome"])}</b>: <span style="color:{"#B42318" if d["status"] == "bad" else "#9A5B00"}">'
            f'{html.escape(d["status_txt"])}</span></li>' for d in docs_alerta) + "</ul>")
    if not (novas or fechando or docs_alerta):
        blocos.append("<p>Nada novo que combine com você hoje. O Radar está funcionando normalmente.</p>")

    partes = []
    if novas:
        partes.append(f"{len(novas)} nova(s) boa(s)")
    if fechando:
        partes.append(f"{len(fechando)} prazo(s) fechando")
    if docs_alerta:
        partes.append(f"{len(docs_alerta)} documento(s)")
    assunto = "Radar Licita PB: " + (", ".join(partes) if partes else "nada novo hoje")
    enviar(assunto, _pagina("Resumo do dia", blocos), cfg)
    _marcar("oport", [o["id"] for o in novas])
    return True


def _link_site(o):
    """Na versão online, o link do e-mail abre a licitação direto no site do Radar."""
    if not os.getenv("SITE_URL"):
        return None
    return URL_APP + "#" + o["id"].replace("/", "_")
