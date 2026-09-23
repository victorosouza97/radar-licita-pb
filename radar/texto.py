import re
import unicodedata


def normalizar(texto):
    """Minúsculas e sem acentos, para comparar 'Óleo' com 'oleo'."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t.lower()).strip()


class Buscador:
    """Procura palavras-chave no início de palavras ('oleo' acha 'oleos', não 'petroleo')."""

    def __init__(self, palavras, negativas=()):
        self.palavras = [(p, self._regex(p)) for p in palavras if normalizar(p)]
        self.negativas = [self._regex(n) for n in negativas if normalizar(n)]

    @staticmethod
    def _regex(p):
        return re.compile(r"(?<![a-z0-9])" + re.escape(normalizar(p)))

    def achar(self, texto_norm, inicio=None):
        """Devolve as palavras encontradas (vazio se houver palavra negativa).

        Com `inicio`, devolve também se alguma apareceu nos primeiros `inicio` caracteres,
        onde normalmente fica o nome do produto (o resto é especificação técnica).
        """
        achadas, forte = [], False
        if texto_norm:
            # Tira os trechos negativos ("óleo diesel") antes de procurar ("óleo").
            limpo = texto_norm
            for n in self.negativas:
                limpo = n.sub(lambda m: " " * len(m.group()), limpo)
            for p, rx in self.palavras:
                m = rx.search(limpo)
                if m:
                    achadas.append(p)
                    forte = forte or (inicio is not None and m.start() < inicio)
        return (achadas, forte) if inicio is not None else achadas
