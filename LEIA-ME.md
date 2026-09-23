# Radar Licita PB

## Versão online (principal)

Roda sozinha no GitHub, de graça, sem precisar deixar computador ligado:

- **Todo dia às 7h** o GitHub busca as licitações abertas da PB no PNCP, calcula as notas,
  a IA lê os editais com nota 5 ou mais e o site é atualizado.
- Logo depois chega o **e-mail do dia**: novidades boas, prazos dos próximos 3 dias e
  documentos vencendo. Ele chega todo dia, mesmo sem novidade, para você saber que está funcionando.
- **O site** (link do GitHub Pages) mostra tudo, no computador e no celular. O que você muda
  nele (favoritos, descartes, palavras, validade dos documentos) fica salvo no Firebase.
- **Certidões:** os PDFs ficam na sua pasta do Google Drive; no site vai só o link e a validade.
- **Rodar na hora:** no GitHub, aba "Actions" → "Radar diário" → "Run workflow".

Peças: `rodar.py` (rodada diária), `site/` (o site), `.github/workflows/radar.yml` (agendamento),
`firestore.rules` (regras do Firebase). Segredos no GitHub: `GEMINI_API_KEY`, `GMAIL_USER`,
`GMAIL_APP_PASSWORD`, `EMAIL_TO`; variável: `FIREBASE_PROJECT`.

---

## Versão do computador (opcional)

Programa que busca todas as licitações abertas na Paraíba no **PNCP** (portal oficial do governo),
dá uma nota de 0 a 10 para cada uma conforme o seu ramo e guarda os documentos da empresa
com aviso de vencimento.

## Como abrir

1. Dê **dois cliques** em `Iniciar Radar.bat`.
2. Uma janela preta abre (é o programa rodando) e, em seguida, o navegador abre sozinho no Radar.
3. Para desligar, feche a janela preta.

> Enquanto a janela preta estiver aberta, a lista se atualiza sozinha a cada 6 horas.
> Também há o botão **Atualizar agora** na barra lateral.

A primeira atualização leva uns 5 minutos (lê cerca de 550 licitações e 10 mil itens).
As seguintes são bem mais rápidas, porque só buscam o que mudou.

## As telas

- **Painel**: boas oportunidades, prazos da semana e documentos vencendo.
- **Oportunidades**: a lista com filtros (texto, cidade, modalidade, valor, ME/EPP).
  Clique numa licitação para ver os itens, os arquivos do edital e os links para o PNCP e para a plataforma.
  Dá para **favoritar** ou **descartar**.
- **Documentos**: o cofre de certidões. "Emitir" abre o site oficial; depois clique em
  "Atualizar", anexe o PDF e informe a validade.
- **Ajustes e alertas**: palavras que definem a nota, alertas por e-mail e situação da IA.

## Distância e raio

Cada licitação mostra a distância aproximada **por estrada** de Campina Grande até a cidade
(linha reta x 1,15). Há o filtro "Distância máxima". Quando o texto ou o edital exige a empresa
num **raio** menor que a sua distância, a licitação perde 4 pontos e fica escondida
(desmarque "Esconder as que exigem raio…" para ver).

A exigência de raio quase sempre está dentro do PDF do edital, por isso quem a encontra é a IA.

## IA lendo o edital (Gemini)

No detalhe de uma licitação, clique em **Ler edital com IA**. Em até 2 minutos aparecem: resumo,
se vale a pena, datas, critério, entrega, raio exigido (com o trecho do edital), amostra,
visita técnica, pontos de atenção e os documentos exigidos comparados com o seu cofre.
Depois de cada atualização, a IA lê sozinha as licitações com nota 7 ou mais.
A chave fica no arquivo `.env` (GEMINI_API_KEY). O custo é de poucos centavos por edital.
Às vezes o Google fica sobrecarregado: o programa tenta outros modelos e, se não der, é só
clicar em "Tentar de novo" mais tarde.

## Alertas por e-mail (grátis)

Em **Ajustes e alertas**, preencha o seu Gmail, a **senha de app** (o passo a passo está na própria
tela) e para quem enviar. Você recebe:
- um e-mail assim que surgir licitação com nota alta;
- um resumo diário (no horário que escolher) com propostas que fecham em 3 dias e documentos vencendo.

O Radar precisa estar aberto no computador para enviar.

## Como a nota é calculada

A nota é maior quando:
- suas palavras aparecem no **nome do produto** dos itens (não só no meio da especificação técnica);
- esses itens representam uma **parte grande do valor** da licitação;
- o objeto da licitação cita suas palavras;
- há itens **exclusivos ou com cota para ME/EPP**;
- a cidade é **perto de Campina Grande**.

Perde pontos quando o prazo é menor que 2 dias. Palavras de exclusão (ex.: "óleo diesel",
"filtro solar") evitam falsos resultados.

## Onde ficam os dados

Tudo fica neste computador, na pasta `dados` (banco `radar.db` e os PDFs em `dados\documentos`).
**Faça cópia dessa pasta de vez em quando** (pendrive ou Google Drive).

## Próximos passos (ainda não feitos)

- Incluir o Mural de Licitações do TCE-PB e a Central de Compras PB.
- Deixar rodando na nuvem, para funcionar com o computador desligado e abrir pelo celular.
