"""Nota de 0 a 10: o quanto uma licitação combina com o negócio.

Por enquanto é feita por regras simples. Na próxima etapa a IA vai ler o edital e refinar a nota.

Como a nota é montada:
  2,0  base, se alguma palavra-chave aparece
 +5,0  x fatia do valor da licitação que está em itens que combinam
       (item cuja palavra aparece no nome do produto conta inteiro; se aparece só
        no meio da especificação técnica, conta 30%)
 +1,5  palavra no início do objeto (+0,5 se aparece só mais para o fim)
 +1,0  variedade: várias palavras diferentes (0,25 por palavra extra)
 +1,0  itens exclusivos ME/EPP (+0,5 se for cota reservada)
 +1,0  cidade a até 40 km (+0,5 até 100 km; -0,5 acima de 250 km, pelo frete)
 -4,0  edital exige empresa num raio menor que a sua distância
 -1,5  prazo menor que 2 dias
"""
import re
from datetime import datetime

from . import distancia
from .texto import normalizar

EXCLUSIVO_ME = "1"   # tipoBeneficio no PNCP: participação exclusiva ME/EPP
COTA_ME = "3"        # cota reservada para ME/EPP
INICIO_ITEM = 60     # caracteres onde costuma ficar o nome do produto
INICIO_OBJETO = 140

# Palavras burocráticas que costumam abrir o texto antes do que interessa.
_RODEIO = re.compile(
    r"^(?:\[[^\]]*\]\s*-?\s*|\d+(?:\.\d+)*\.?\s*|(?:o|a|os|as|de|da|do|das|dos|na|no|para|por|com|e|em|"
    r"objeto|presente|licitacao|procedimento|pregao|eletronico|eletronica|credenciamento|chamada|publica|"
    r"sistema|registro|precos?|eventual|eventuais|futura|futuras|contratacao|empresa|empresas|\(s\)|"
    r"especializadas?|pessoa|pessoas|fisica|fisicas|juridica|juridicas|ou|prestacao|servicos?|"
    r"aquisicao|aquisicoes|fornecimento|parcelada|escolha|proposta|mais|vantajosa|visando|"
    r"interessados)\b[\s,:;.\-–]*)+")


def _sem_rodeio(texto):
    return _RODEIO.sub("", texto or "", count=1)


def calcular(c, itens, buscador, agora=None, raio_ia=None):
    agora = agora or datetime.now()
    km = distancia.km_estrada(c["municipio"])
    raio = distancia.raio_exigido(c["objeto_norm"], normalizar(c["info"]),
                                  *(it["descricao_norm"] for it in itens))
    if raio_ia and (raio is None or raio_ia < raio):
        raio = raio_ia
    extra = {"km": km, "raio": raio}
    no_objeto, objeto_forte = buscador.achar(_sem_rodeio(c["objeto_norm"]), INICIO_OBJETO)

    achados, palavras = {}, set(no_objeto)
    soma_total = soma_bate = 0.0
    for it in itens:
        peso_valor = it["valor_total"] or 0
        soma_total += peso_valor
        ps, forte = buscador.achar(_sem_rodeio(it["descricao_norm"]), INICIO_ITEM)
        if ps:
            forca = 1.0 if forte else 0.3
            achados[it["numero"]] = forca
            palavras.update(ps)
            soma_bate += forca * peso_valor

    if not palavras:
        return {"nota": 0.0, "palavras": [], "itens_batem": [], "motivos": [],
                "alertas": ["Nenhuma das suas palavras-chave aparece"], **extra}

    if itens:
        if soma_total > 0:
            fatia = soma_bate / soma_total
        else:  # valores sigilosos: usa a contagem de itens
            fatia = sum(achados.values()) / len(itens)
    else:
        fatia = 1.0 if objeto_forte else 0.3

    motivos, alertas = [], []
    nota = 2 + 5 * fatia
    if itens and achados:
        fortes = sum(1 for f in achados.values() if f == 1.0)
        txt = f"{len(achados)} de {len(itens)} itens combinam"
        if soma_total > 0:
            txt += f" ({round(100 * fatia)}% do valor)"
        motivos.append(txt)
        if fortes < len(achados):
            alertas.append(f"{len(achados) - fortes} item(ns) só citam a palavra na especificação")
    if no_objeto:
        nota += 1.5 if objeto_forte else 0.5
        motivos.append("Objeto cita: " + ", ".join(no_objeto))
    nota += min(1.0, 0.25 * (len(palavras) - 1))

    benef_itens = {str(it["beneficio_id"]) for it in itens if it["numero"] in achados}
    if EXCLUSIVO_ME in benef_itens:
        nota += 1
        motivos.append("Itens exclusivos para ME/EPP")
    elif COTA_ME in benef_itens:
        nota += 0.5
        motivos.append("Cota reservada para ME/EPP")

    if km is not None:
        if km <= 40:
            nota += 1
            motivos.append(f"Perto de você (~{km} km)")
        elif km <= 100:
            nota += 0.5
            motivos.append(f"Distância razoável (~{km} km)")
        elif km > 250:
            nota -= 0.5
            alertas.append(f"Longe (~{km} km): considere o frete")
    if raio is not None:
        if km is not None and km > raio:
            nota -= 4
            alertas.append(f"Edital exige empresa num raio de {raio:g} km; você está a ~{km} km")
        elif km is not None:
            motivos.append(f"Exige raio de {raio:g} km: você está dentro (~{km} km)")
        else:
            alertas.append(f"Edital exige raio de {raio:g} km")

    try:
        dias = (datetime.fromisoformat(c["encerramento"]) - agora).total_seconds() / 86400
        if dias < 2:
            nota -= 1.5
            alertas.append("Prazo muito curto")
    except (TypeError, ValueError):
        pass
    if c["modalidade_id"] == 12:
        alertas.append("Credenciamento: não há disputa de preço")

    return {"nota": round(max(0.1, min(10, nota)), 1), "palavras": sorted(palavras),
            "itens_batem": sorted(achados), "motivos": motivos, "alertas": alertas, **extra}
