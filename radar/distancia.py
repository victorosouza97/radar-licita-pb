"""Distância até a cidade da licitação e exigência de raio máximo no edital.

Coordenadas das sedes municipais da PB (IBGE, via github.com/kelvins/municipios-brasileiros).
A distância por estrada é estimada: linha reta x 1,15 (conferido com CG-JP, CG-Patos e CG-Cajazeiras).
"""
import json
import math
import re
from pathlib import Path

from .texto import normalizar

FATOR_ESTRADA = 1.15
ORIGEM = {"nome": "Campina Grande", "lat": -7.22196, "lon": -35.8731}

_MUNICIPIOS = {normalizar(m["nome"]): m for m in
               json.loads((Path(__file__).parent / "municipios_pb.json").read_text(encoding="utf-8"))}


def _linha_reta(lat1, lon1, lat2, lon2):
    p = math.radians
    a = (math.sin(p(lat2 - lat1) / 2) ** 2
         + math.cos(p(lat1)) * math.cos(p(lat2)) * math.sin(p(lon2 - lon1) / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(a))


def km_estrada(municipio):
    """Distância aproximada por estrada, em km, da sua sede até a cidade. None se não achar."""
    m = _MUNICIPIOS.get(normalizar(municipio))
    if not m:
        return None
    return round(_linha_reta(ORIGEM["lat"], ORIGEM["lon"], m["lat"], m["lon"]) * FATOR_ESTRADA)


# "raio de 50 km", "raio máximo de até 30 (trinta) quilômetros", "distância máxima de 40km da sede"
_RAIO = re.compile(
    r"(?:raio|distancia maxima|distancia nao superior|distancia de ate|distancia inferior)"
    r"[^0-9]{0,40}?(\d{1,3}(?:[.,]\d)?)\s*(?:\([a-z ]+\)\s*)?(?:km|quilometro)")


def raio_exigido(*textos_norm):
    """Menor raio (km) citado nos textos, ou None."""
    achados = []
    for t in textos_norm:
        for m in _RAIO.finditer(t or ""):
            km = float(m.group(1).replace(",", "."))
            if 1 <= km <= 800:
                achados.append(km)
    return min(achados) if achados else None
