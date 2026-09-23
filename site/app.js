/* Radar Licita PB — versão online (GitHub Pages + Firebase).
   Os dados das licitações vêm de dados/oportunidades.json, gerado todo dia às 7h pelo GitHub.
   O que você muda aqui (favoritos, palavras, documentos) fica salvo no Firebase. */
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const brl = v => (v ?? 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const brl0 = v => (v ?? 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
const dataBR = s => s ? new Date(s).toLocaleDateString('pt-BR') : '—';
const dataHoraBR = s => s ? new Date(s).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
const diasAte = s => Math.ceil((new Date(s) - new Date()) / 86400000);
const scoreCls = n => n >= 7 ? 'good' : n >= 5 ? 'warn' : 'bad';
const notaTxt = n => (n || 0).toFixed(1).replace('.', ',');
const normalizar = s => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const idSeguro = id => id.replace(/\//g, '_');
const limpar = s => (s || '').replace(/^\s*\[[^\]]*\]\s*-?\s*/, '').replace(/\s+/g, ' ').trim();
const resumir = (s, n) => { s = limpar(s); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
const foraRaio = o => o.raio && o.km != null && o.km > o.raio;
const NOTA_MINIMA = 5; // abaixo disso a licitação só aparece em "Todas abertas" (decisão do usuário)

function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => t.hidden = true, 4000);
}

const DOCS_PADRAO = [
  ['Contrato social consolidado', 'Junta Comercial (JUCEP)', true, ''],
  ['Cartão CNPJ', 'Receita Federal', false, 'https://solucoes.receita.fazenda.gov.br/servicos/cnpjreva/cnpjreva_solicitacao.asp'],
  ['CND Federal (Receita/PGFN)', 'Receita Federal', false, 'https://servicos.receitafederal.gov.br/servico/certidoes/#/home'],
  ['CRF – Regularidade do FGTS', 'Caixa', false, 'https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf'],
  ['CNDT – Débitos Trabalhistas', 'TST', false, 'https://cndt-certidao.tst.jus.br/inicio.faces'],
  ['CND Estadual', 'SEFAZ-PB', false, 'https://www.sefaz.pb.gov.br'],
  ['CND Municipal', 'Prefeitura de Campina Grande', false, ''],
  ['Certidão negativa de falência', 'TJPB', false, ''],
  ['Balanço patrimonial', 'Contador', false, ''],
  ['Atestado de capacidade técnica', 'Órgãos atendidos', true, ''],
  ['Alvará de funcionamento', 'Prefeitura de Campina Grande', false, ''],
];

/* ---------------- Estado ---------------- */
const state = {
  view: 'painel', dados: null, marcas: {}, docs: [], pedidos: {}, cfg: null,
  f: { ver: 'relevantes', q: '', municipio: '', modalidade: '', vmax: '', kmax: '', me: false, semRaioFora: true, ordem: 'nota' },
  sel: null,
};
try { const v = localStorage.getItem('rl-view'); if (v) state.view = v; } catch (e) {}

let db = null;
function iniciarFirebase() {
  if (!window.FIREBASE_CONFIG || !window.firebase) return;
  firebase.initializeApp(window.FIREBASE_CONFIG);
  db = firebase.firestore();
  db.collection('marcas').onSnapshot(s => { state.marcas = {}; s.forEach(d => state.marcas[d.id] = d.data()); aoMudar(); });
  db.collection('pedidos_ia').onSnapshot(s => { state.pedidos = {}; s.forEach(d => state.pedidos[d.id] = d.data()); aoMudar(); });
  db.collection('config').doc('palavras').onSnapshot(d => { state.cfg = d.exists ? d.data() : null; if (state.view === 'ajustes') render(); });
  let semeado = false;
  db.collection('documentos').onSnapshot(s => {
    state.docs = []; s.forEach(d => state.docs.push({ id: d.id, ...d.data() }));
    if (!state.docs.length && !semeado) { semeado = true; semearDocs(); }
    aoMudar();
  });
}
async function semearDocs() {
  const lote = db.batch();
  DOCS_PADRAO.forEach(([nome, emissor, semValidade, link], i) =>
    lote.set(db.collection('documentos').doc(), { nome, emissor, sem_validade: semValidade, link_emissao: link, validade: '', link_arquivo: '', obs: '', ordem: i }));
  await lote.commit();
}
const semFirebase = () => { toast('O Firebase ainda não foi configurado: por enquanto o site só mostra.'); return !db; };
let tMudar;
function aoMudar() { clearTimeout(tMudar); tMudar = setTimeout(() => { if (state.view !== 'oport') render(); else carregarLista(); }, 150); }

/* Aplica favoritos/descartes salvos no Firebase por cima dos dados do dia. */
function oportunidades() {
  return (state.dados?.oportunidades || []).map(o => {
    const m = state.marcas[idSeguro(o.id)] || {};
    return { ...o, favorito: !!m.favorito, descartado: !!m.descartado };
  });
}

/* ---------------- Documentos: situação ---------------- */
function statusDoc(d) {
  if (d.sem_validade) return d.link_arquivo ? ['good', 'Sem vencimento'] : ['plain', 'Falta o link do arquivo'];
  if (!d.validade) return ['plain', 'Não cadastrado'];
  const dias = Math.round((new Date(d.validade + 'T12:00') - new Date(new Date().toDateString() + ' 12:00')) / 86400000);
  if (dias < 0) return ['bad', `Vencido há ${-dias} dia(s)`];
  if (dias <= 15) return ['warn', `Vence em ${dias} dia(s)`];
  return ['good', 'Válido'];
}
const docsComStatus = () => [...state.docs].sort((a, b) => (a.ordem ?? 99) - (b.ordem ?? 99))
  .map(d => { const [status, status_txt] = statusDoc(d); return { ...d, status, status_txt }; });

/* ---------------- Navegação ---------------- */
function go(v) {
  state.view = v;
  try { localStorage.setItem('rl-view', v); } catch (e) {}
  render();
  window.scrollTo(0, 0);
}
function render() {
  document.querySelectorAll('#nav button').forEach(b => b.dataset.go === state.view ? b.setAttribute('aria-current', 'page') : b.removeAttribute('aria-current'));
  if (!state.dados) return;
  ({ painel: vPainel, oport: vOport, docs: vDocs, ajustes: vAjustes }[state.view] || vPainel)();
}
function caixaAtualizacao() {
  const d = state.dados;
  $('#coleta-box').innerHTML = `<span>Dados do PNCP de<br><b>${dataHoraBR(d.atualizado)}</b></span>
    ${d.erro ? `<span class="pill bad">${esc(d.erro)}</span>` : ''}
    <span class="small">O Radar busca sozinho todo dia às 7h e manda o resumo por e-mail.</span>
    ${db ? '' : '<span class="pill warn">Firebase ainda não configurado</span>'}`;
}

/* ---------------- Painel ---------------- */
function vPainel() {
  const lista = oportunidades().filter(o => !o.descartado);
  const boas = lista.filter(o => o.nota >= 7).sort((a, b) => b.nota - a.nota);
  const limite = new Date(Date.now() + 7 * 86400000).toISOString();
  const semana = lista.filter(o => o.nota >= NOTA_MINIMA && o.encerramento <= limite).sort((a, b) => a.encerramento.localeCompare(b.encerramento));
  const novas = lista.filter(o => o.nova && o.nota >= NOTA_MINIMA).length;
  const docs = docsComStatus();
  const alerta = docs.filter(d => d.status === 'bad' || d.status === 'warn');
  const pend = docs.filter(d => d.status === 'plain').length;
  const hoje = new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' });
  $('#view').innerHTML = `
  <div class="view-head"><div><h2>Hoje é ${hoje}.</h2><p class="muted">Licitações abertas na Paraíba, lidas do PNCP (portal oficial do governo).</p></div></div>
  <div class="grid kpis">
    <button class="kpi" data-go="oport"><span class="label">Boas oportunidades</span><span class="big num">${boas.length}</span><span class="small muted">nota 7 ou mais, de ${lista.length} abertas na PB</span></button>
    <button class="kpi" data-go="oport"><span class="label">Novas hoje</span><span class="big num">${novas}</span><span class="small muted">com nota 5 ou mais</span></button>
    <button class="kpi warn" data-go="oport"><span class="label">Prazos em 7 dias</span><span class="big num">${semana.length}</span><span class="small muted">propostas com nota 5 ou mais fecham nesta semana</span></button>
    <button class="kpi ${alerta.length ? 'bad' : ''}" data-go="docs"><span class="label">Documentos</span><span class="big num">${alerta.length + pend}</span><span class="small muted">${alerta.length ? `${alerta.filter(d => d.status === 'bad').length} vencido(s), ${alerta.filter(d => d.status === 'warn').length} vencendo` : pend ? `${pend} ainda não cadastrados` : 'tudo em dia'}</span></button>
  </div>
  <div class="grid dash">
    <section class="panel"><div class="row" style="justify-content:space-between;margin-bottom:6px"><h3>Melhores oportunidades</h3><button class="btn small" data-go="oport">Ver todas</button></div>
      ${boas.length ? `<ul class="lista-simples">${boas.slice(0, 8).map(itemSimples).join('')}</ul>` : '<p class="vazio">Nenhuma com nota 7 ou mais agora.</p>'}</section>
    <section class="panel"><h3 style="margin-bottom:6px">Propostas que fecham em 7 dias</h3>
      ${semana.length ? `<ul class="lista-simples">${semana.slice(0, 12).map(itemSimples).join('')}</ul>` : '<p class="vazio">Nada fechando nesta semana.</p>'}</section>
  </div>`;
}
function itemSimples(o) {
  const d = new Date(o.encerramento);
  return `<li data-abrir="${esc(o.id)}"><div class="date-chip"><b>${String(d.getDate()).padStart(2, '0')}</b>${d.toLocaleDateString('pt-BR', { month: 'short' }).replace('.', '')}${d.getFullYear() !== new Date().getFullYear() ? `<br>${d.getFullYear()}` : ''}</div>
    <div><div style="font-weight:600">${esc(resumir(o.objeto, 110))}</div><div class="small muted">${esc(o.municipio)}${o.km != null ? ` (~${o.km} km)` : ''} · ${brl0(o.valor)}</div></div>
    <span class="pill ${scoreCls(o.nota)}">${notaTxt(o.nota)}</span></li>`;
}

/* ---------------- Oportunidades ---------------- */
function vOport() {
  const f = state.f, todas = oportunidades();
  const municipios = [...new Set(todas.map(o => o.municipio).filter(Boolean))].sort();
  const modalidades = [...new Set(todas.map(o => o.modalidade).filter(Boolean))].sort();
  $('#view').innerHTML = `
  <div class="view-head"><div><h2>Oportunidades</h2><p class="muted">Licitações com propostas abertas na Paraíba. A nota (0 a 10) mostra o quanto cada uma combina com suas palavras-chave, a distância de Campina Grande e os benefícios para ME/EPP.</p></div></div>
  <div class="tabs" role="group">
    ${[['relevantes', 'Combinam com você'], ['todas', 'Todas abertas'], ['favoritas', 'Favoritas'], ['descartadas', 'Descartadas']].map(([k, t]) => `<button class="tab" data-ver="${k}" aria-pressed="${f.ver === k}">${t}</button>`).join('')}
  </div>
  <div class="panel" style="margin-bottom:14px"><div class="filters">
    <label class="field"><span class="label">Buscar no texto</span><input type="text" id="f-q" value="${esc(f.q)}" placeholder="ex.: ambulância, trator"></label>
    <label class="field"><span class="label">Cidade</span><select id="f-municipio"><option value="">Toda a Paraíba</option>${municipios.map(m => `<option ${m === f.municipio ? 'selected' : ''}>${esc(m)}</option>`).join('')}</select></label>
    <label class="field"><span class="label">Modalidade</span><select id="f-modalidade"><option value="">Todas</option>${modalidades.map(m => `<option ${m === f.modalidade ? 'selected' : ''}>${esc(m)}</option>`).join('')}</select></label>
    <label class="field"><span class="label">Valor máximo (R$)</span><input type="number" id="f-vmax" min="0" step="1000" value="${esc(f.vmax)}" placeholder="sem limite"></label>
    <label class="field"><span class="label">Distância máxima (km)</span><input type="number" id="f-kmax" min="0" step="10" value="${esc(f.kmax)}" placeholder="qualquer distância"></label>
    <label class="field"><span class="label">Ordenar por</span><select id="f-ordem">${[['nota', 'Melhor nota'], ['prazo', 'Prazo mais próximo'], ['valor', 'Maior valor'], ['distancia', 'Mais perto']].map(([v, t]) => `<option value="${v}" ${v === f.ordem ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
    <label class="field" style="justify-content:flex-end"><span class="row"><input type="checkbox" id="f-me" ${f.me ? 'checked' : ''}> Só com vantagem ME/EPP</span></label>
    <label class="field" style="justify-content:flex-end"><span class="row"><input type="checkbox" id="f-raio" ${f.semRaioFora ? 'checked' : ''}> Esconder as que exigem raio menor que a minha distância</span></label>
  </div></div>
  <div class="opp-layout"><div><p class="small muted" id="count" style="margin-bottom:8px"></p><div class="opp-list" id="opp-list"></div></div>
  <aside class="panel detail" id="detail"><p class="muted">Clique numa licitação para ver os detalhes.</p></aside></div>`;
  carregarLista();
  if (state.sel) abrirDetalhe(state.sel, true);
}
function filtrar() {
  const f = state.f, q = f.q.trim().toLowerCase(), vmax = +f.vmax || 0, kmax = +f.kmax || 0;
  const res = oportunidades().filter(o => {
    if (f.ver === 'favoritas') { if (!o.favorito) return false; }
    else if (f.ver === 'descartadas') { if (!o.descartado) return false; }
    else if (o.descartado || (f.ver === 'relevantes' && o.nota < NOTA_MINIMA)) return false;
    if (q && !(o.objeto + ' ' + o.orgao).toLowerCase().includes(q)) return false;
    if (f.municipio && o.municipio !== f.municipio) return false;
    if (f.modalidade && o.modalidade !== f.modalidade) return false;
    if (vmax && (o.valor || 0) > vmax) return false;
    if (kmax && (o.km == null || o.km > kmax)) return false;
    if (f.semRaioFora && foraRaio(o)) return false;
    if (f.me && !(o.me_exclusivo || o.me_cota)) return false;
    return true;
  });
  const ord = { nota: (a, b) => b.nota - a.nota || a.encerramento.localeCompare(b.encerramento), prazo: (a, b) => a.encerramento.localeCompare(b.encerramento), valor: (a, b) => (b.valor || 0) - (a.valor || 0), distancia: (a, b) => (a.km ?? 9999) - (b.km ?? 9999) };
  return res.sort(ord[f.ordem] || ord.nota);
}
function carregarLista() {
  const lista = filtrar(), todas = oportunidades();
  const rel = todas.filter(o => o.nota >= NOTA_MINIMA && !o.descartado).length;
  const cont = $('#count'); if (!cont) return;
  cont.textContent = `${lista.length} licitação(ões) nesta lista · ${rel} de ${todas.length} abertas na PB têm nota 5 ou mais`;
  $('#opp-list').innerHTML = lista.length ? lista.slice(0, 400).map(o => `
    <button class="opp" data-sel="${esc(o.id)}" aria-selected="${o.id === state.sel}">
      <div class="score ${o.nota > 0 ? scoreCls(o.nota) : 'bad'}">${notaTxt(o.nota)}<small>nota</small></div>
      <div><h3>${esc(resumir(o.objeto, 180))}</h3>
      <div class="meta"><span>${esc(o.municipio)}${o.km != null ? ` (~${o.km} km)` : ''} · ${esc(resumir(o.unidade || o.orgao, 50))}</span><span class="num">${brl0(o.valor)}</span>
      <span>Fecha ${dataBR(o.encerramento)} (${diasAte(o.encerramento)} dias)</span>
      ${o.nova ? '<span class="pill info">Nova</span>' : ''}${o.me_exclusivo ? '<span class="pill good">Exclusiva ME/EPP</span>' : o.me_cota ? '<span class="pill good">Cota ME/EPP</span>' : ''}${o.favorito ? '<span class="pill warn">Favorita</span>' : ''}${o.lida_ia ? '<span class="pill info">Lida pela IA</span>' : ''}${foraRaio(o) ? `<span class="pill bad">Exige raio de ${o.raio} km</span>` : ''}</div></div>
    </button>`).join('') : '<div class="panel vazio">Nenhuma licitação com esses filtros.</div>';
}
async function abrirDetalhe(id, silencioso) {
  state.sel = id;
  try { history.replaceState(null, '', '#' + idSeguro(id)); } catch (e) {}
  document.querySelectorAll('.opp').forEach(b => b.setAttribute('aria-selected', b.dataset.sel === id));
  const o = oportunidades().find(x => x.id === id);
  const el = $('#detail');
  if (!o || !el) return;
  el.innerHTML = '<p class="muted">Carregando…</p>';
  let d = null;
  try { const r = await fetch(`dados/detalhe/${idSeguro(id)}.json`); if (r.ok) d = await r.json(); } catch (e) {}
  const [cnpj, resto] = [id.split('-')[0], id.split('-').pop()];
  const linkPncp = d?.link_pncp || `https://pncp.gov.br/app/editais/${cnpj}/${resto.split('/')[1]}/${+resto.split('/')[0]}`;
  const dias = diasAte(o.encerramento);
  const itens = d?.itens || [];
  const batem = itens.filter(i => i.bate);
  el.innerHTML = `
    <div class="row" style="justify-content:space-between;margin-bottom:6px"><span class="label">${esc(o.modalidade)}${o.srp ? ' · Registro de preços' : ''}</span><span class="pill ${o.nota > 0 ? scoreCls(o.nota) : 'plain'}">Nota ${notaTxt(o.nota)}</span></div>
    <h3 style="font-size:1.08rem;margin-bottom:4px;font-family:var(--f-body)">${esc(limpar(o.objeto))}</h3>
    <p class="muted" style="margin-bottom:12px">${esc(o.orgao)} · ${esc(o.unidade)} · ${esc(o.municipio)}</p>
    <div class="kv" style="margin-bottom:14px">
      <div><span class="label">Valor estimado</span><b class="num">${o.valor ? brl(o.valor) : 'Sigiloso / não informado'}</b></div>
      <div><span class="label">Propostas até</span><b>${dataHoraBR(o.encerramento)}</b><span class="small muted">${dias} dia(s)</span></div>
      <div><span class="label">Plataforma</span><b>${esc(o.plataforma || '—')}</b></div>
      <div><span class="label">Distância de Campina Grande</span><b>${o.km != null ? `~${o.km} km por estrada` : '—'}</b><span class="small muted">estimativa</span></div>
      <div><span class="label">Raio exigido</span><b style="color:${foraRaio(o) ? 'var(--bad)' : 'inherit'}">${o.raio ? `${o.raio} km${foraRaio(o) ? ' (você está fora)' : ' (você está dentro)'}` : 'Não encontrado'}</b></div>
      <div><span class="label">Nº no PNCP</span><b class="mono small">${esc(o.id)}</b></div>
    </div>
    <div class="row">
      <a class="btn primary" href="${esc(linkPncp)}" target="_blank" rel="noopener">Abrir no PNCP</a>
      ${d?.link_origem ? `<a class="btn" href="${esc(d.link_origem)}" target="_blank" rel="noopener">Abrir na plataforma</a>` : ''}
      <button class="btn" data-marcar="favorito" data-valor="${o.favorito ? 0 : 1}">${o.favorito ? 'Tirar das favoritas' : 'Favoritar'}</button>
      <button class="btn" data-marcar="descartado" data-valor="${o.descartado ? 0 : 1}">${o.descartado ? 'Restaurar' : 'Descartar'}</button>
    </div>
    ${(o.motivos?.length || o.alertas?.length) ? `<div class="detail-sec" style="margin-top:14px"><span class="label">Por que essa nota</span>
      <div class="row">${(o.motivos || []).map(m => `<span class="pill good">${esc(m)}</span>`).join('')}${(o.alertas || []).map(m => `<span class="pill warn">${esc(m)}</span>`).join('')}</div></div>` : ''}
    ${blocoIA(o, d)}
    ${d?.info ? `<div class="detail-sec"><span class="label">Informação complementar</span><p class="small">${esc(d.info)}</p></div>` : ''}
    <div class="detail-sec"><span class="label">Arquivos (edital, termo de referência…)</span>
      ${!d || d.arquivos == null ? '<p class="small muted">Use o botão “Abrir no PNCP” para ver os arquivos.</p>' :
        d.arquivos.length ? `<ul class="checklist">${d.arquivos.map(a => `<li><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.titulo)}</a><span class="pill plain">${esc(a.tipo || '')}</span></li>`).join('')}</ul>` : '<p class="small muted">Nenhum arquivo publicado.</p>'}</div>
    ${d ? `<div class="detail-sec"><div class="row" style="justify-content:space-between"><span class="label">Itens (${d.total_itens})</span>${batem.length ? `<span class="pill good">${batem.length} combinam com você</span>` : ''}</div>
      ${itens.length ? `<div class="table-wrap"><table><thead><tr><th>#</th><th>Descrição</th><th class="r">Qtd</th><th class="r">Unit. estimado</th></tr></thead><tbody>
        ${[...batem, ...itens.filter(i => !i.bate)].slice(0, 200).map(i => `<tr class="${i.bate ? 'bate' : ''}"><td class="mono">${i.numero}</td><td>${esc(i.descricao)}${i.beneficio && /ME\/EPP/i.test(i.beneficio) ? `<br><span class="pill good">${esc(i.beneficio)}</span>` : ''}</td>
          <td class="r num">${(i.qtd ?? '').toLocaleString('pt-BR')} ${esc((i.unidade || '').toLowerCase())}</td><td class="r mono">${i.valor_unit ? brl(i.valor_unit) : '—'}</td></tr>`).join('')}
      </tbody></table></div>` : ''}${d.total_itens > 200 ? '<p class="small muted">Mostrando 200 itens. Veja todos no PNCP.</p>' : ''}</div>` :
      '<div class="detail-sec"><p class="small muted">Esta licitação não combina com suas palavras, então os itens não foram guardados. Veja no PNCP.</p></div>'}`;
  if (window.innerWidth <= 1100 && !silencioso) el.scrollIntoView({ behavior: 'smooth' });
}
function blocoIA(o, d) {
  const a = d?.analise, x = a?.dados, pedido = state.pedidos[idSeguro(o.id)];
  if (!x) return `<div class="detail-sec"><span class="label">Leitura do edital pela IA</span>
    ${pedido ? '<p class="small"><span class="pill info">Pedido registrado</span> A IA lê este edital na próxima busca, amanhã às 7h.</p>'
      : `<p class="small muted">A IA lê sozinha os editais com nota acima de 6. Para esta, peça abaixo: ela é lida na próxima busca (amanhã às 7h).</p>
         <div><button class="btn primary" data-pedir="${esc(o.id)}">Pedir leitura pela IA</button></div>`}</div>`;
  const lin = (rot, v) => v ? `<div><span class="label">${rot}</span><b>${esc(v)}</b></div>` : '';
  const exig = (d.exigidos || []).map(e => {
    const doc = e.alvo ? docsComStatus().find(k => normalizar(k.nome).includes(e.alvo)) : null;
    return `<li><span>${esc(e.nome)}</span><span class="pill ${doc ? doc.status : 'plain'}">${esc(doc ? doc.status_txt : 'Conferir')}</span></li>`;
  }).join('');
  return `<div class="detail-sec ia-box">
    <div class="row" style="justify-content:space-between"><span class="label">Leitura do edital pela IA</span><span class="small muted">${esc((a.arquivos || []).join(', '))}</span></div>
    <p>${esc(x.resumo)}</p>
    <p><b>Vale a pena?</b> ${esc(x.vale_a_pena)}</p>
    <div class="kv">${lin('Sessão', x.data_sessao)}${lin('Impugnar até', x.prazo_impugnacao)}${lin('Critério', x.criterio)}${lin('Participação', x.participacao_me)}${lin('Prazo de entrega', x.prazo_entrega)}${lin('Local de entrega', x.local_entrega)}${lin('Garantia', x.garantia)}${lin('Raio exigido', x.raio_km ? x.raio_km + ' km' : null)}</div>
    ${x.raio_trecho ? `<p class="small"><b>Trecho sobre o raio:</b> “${esc(x.raio_trecho)}”</p>` : ''}
    <div class="row">${x.exige_amostra ? '<span class="pill warn">Exige amostra</span>' : ''}${x.exige_visita_tecnica ? '<span class="pill warn">Exige visita técnica</span>' : ''}</div>
    ${x.pontos_atencao?.length ? `<div><span class="label">Pontos de atenção</span><ul style="margin:4px 0 0;padding-left:18px">${x.pontos_atencao.map(p => `<li>${esc(p)}</li>`).join('')}</ul></div>` : ''}
    ${exig ? `<div><span class="label">Documentos exigidos × seu cofre</span><ul class="checklist" style="margin-top:4px">${exig}</ul></div>` : ''}
    <p class="small muted">Resumo feito por IA: confira no edital antes de decidir.</p></div>`;
}

/* ---------------- Documentos ---------------- */
function vDocs() {
  const ord = { bad: 0, warn: 1, plain: 2, good: 3 };
  const lista = docsComStatus().sort((a, b) => ord[a.status] - ord[b.status]);
  $('#view').innerHTML = `
  <div class="view-head"><div><h2>Cofre de documentos</h2><p class="muted">A validade de cada certidão fica aqui, e o e-mail diário avisa quando algo estiver para vencer. Os arquivos (PDFs) ficam na <b>sua pasta do Google Drive</b>: cole aqui o link de cada um.</p></div>
  <button class="btn primary" data-doc="novo">Adicionar documento</button></div>
  ${db ? '' : '<p class="pill warn" style="margin-bottom:12px">O Firebase ainda não foi configurado: a lista aparece depois dessa etapa.</p>'}
  <div class="panel table-wrap"><table>
    <thead><tr><th>Documento</th><th>Emissor</th><th>Validade</th><th>Situação</th><th>Arquivo</th><th></th></tr></thead>
    <tbody>${lista.map(d => `<tr>
      <td style="font-weight:600">${esc(d.nome)}${d.obs ? `<div class="small muted">${esc(d.obs)}</div>` : ''}</td>
      <td class="muted">${esc(d.emissor)}</td>
      <td class="mono">${d.sem_validade ? '—' : d.validade ? dataBR(d.validade + 'T12:00') : '—'}</td>
      <td><span class="pill ${d.status}">${esc(d.status_txt)}</span></td>
      <td>${d.link_arquivo ? `<a href="${esc(d.link_arquivo)}" target="_blank" rel="noopener">Abrir no Drive</a>` : '<span class="muted small">—</span>'}</td>
      <td><div class="row" style="flex-wrap:nowrap">
        ${d.link_emissao ? `<a class="btn small" href="${esc(d.link_emissao)}" target="_blank" rel="noopener">Emitir</a>` : ''}
        <button class="btn small" data-doc="${esc(d.id)}">Atualizar</button></div></td></tr>`).join('')}</tbody>
  </table></div>
  <p class="small muted" style="margin-top:10px">Como atualizar uma certidão: clique em “Emitir” (abre o site oficial), baixe o PDF, envie para a sua pasta do Google Drive, copie o link do arquivo (botão “Compartilhar” → “Copiar link”) e cole em “Atualizar”, junto com a nova validade.</p>`;
}
function abrirDoc(id) {
  if (!db) return semFirebase();
  const d = id === 'novo' ? { nome: '', emissor: '', validade: '', sem_validade: false, obs: '', link_emissao: '', link_arquivo: '' } : state.docs.find(x => x.id === id);
  const dlg = $('#dlg-doc');
  dlg.innerHTML = `<form id="form-doc">
    <h3>${id === 'novo' ? 'Novo documento' : 'Atualizar documento'}</h3>
    <label class="field"><span class="label">Nome</span><input type="text" id="doc-nome" required value="${esc(d.nome)}"></label>
    <label class="field"><span class="label">Emissor</span><input type="text" id="doc-emissor" value="${esc(d.emissor)}"></label>
    <div class="row" style="align-items:flex-end">
      <label class="field" style="flex:1"><span class="label">Válido até</span><input type="date" id="doc-validade" value="${esc(d.validade || '')}" ${d.sem_validade ? 'disabled' : ''}></label>
      <label class="row" style="padding-bottom:8px"><input type="checkbox" id="doc-sem" ${d.sem_validade ? 'checked' : ''}> Não vence</label>
    </div>
    <label class="field"><span class="label">Link do arquivo no Google Drive</span><input type="text" id="doc-arquivo" value="${esc(d.link_arquivo)}" placeholder="https://drive.google.com/…"></label>
    <label class="field"><span class="label">Site para emitir (opcional)</span><input type="text" id="doc-link" value="${esc(d.link_emissao)}"></label>
    <label class="field"><span class="label">Observação</span><input type="text" id="doc-obs" value="${esc(d.obs)}"></label>
    <div class="row" style="justify-content:space-between;margin-top:6px">
      ${id !== 'novo' ? '<button type="button" class="btn danger" id="doc-apagar">Excluir…</button>' : '<span></span>'}
      <div class="row"><button type="button" class="btn" id="doc-cancelar">Cancelar</button><button class="btn primary">Salvar</button></div>
    </div>
    <p class="small" id="doc-confirma" hidden style="color:var(--bad)">Clique em “Excluir” de novo para confirmar.</p>
  </form>`;
  dlg.showModal();
  $('#doc-sem').onchange = e => { $('#doc-validade').disabled = e.target.checked; };
  $('#doc-cancelar').onclick = () => dlg.close();
  const apagar = $('#doc-apagar');
  if (apagar) apagar.onclick = async () => {
    if ($('#doc-confirma').hidden) { $('#doc-confirma').hidden = false; apagar.textContent = 'Excluir'; return; }
    await db.collection('documentos').doc(id).delete();
    dlg.close(); toast('Documento excluído.');
  };
  $('#form-doc').onsubmit = async e => {
    e.preventDefault();
    const dados = {
      nome: $('#doc-nome').value.trim(), emissor: $('#doc-emissor').value.trim(),
      sem_validade: $('#doc-sem').checked, validade: $('#doc-sem').checked ? '' : $('#doc-validade').value,
      link_arquivo: $('#doc-arquivo').value.trim(), link_emissao: $('#doc-link').value.trim(), obs: $('#doc-obs').value.trim(),
    };
    if (!dados.nome) return toast('Dê um nome ao documento.');
    const ref = id === 'novo' ? db.collection('documentos').doc() : db.collection('documentos').doc(id);
    await ref.set(id === 'novo' ? { ...dados, ordem: 99 } : dados, { merge: true });
    dlg.close(); toast('Documento salvo.');
  };
}

/* ---------------- Ajustes ---------------- */
const listaCfg = k => state.cfg?.[k] || state.dados[k] || [];
function vAjustes() {
  const bloco = (chave, titulo, texto, exemplo) => `
    <section class="panel"><h3>${titulo}</h3><p class="small muted" style="margin:4px 0 12px">${texto}</p>
      <div class="chips">${listaCfg(chave).map((p, i) => `<span class="chip">${esc(p)}<button title="Remover" aria-label="Remover ${esc(p)}" data-rm="${chave}" data-i="${i}">×</button></span>`).join('')}</div>
      <form class="add-row" data-add="${chave}"><input type="text" id="add-${chave}" placeholder="${exemplo}"><button class="btn">Adicionar</button></form></section>`;
  const d = state.dados;
  $('#view').innerHTML = `
  <div class="view-head"><div><h2>Ajustes</h2><p class="muted">As palavras definem a nota de cada licitação. Mudanças feitas aqui valem a partir da próxima busca (todo dia às 7h).</p></div></div>
  <div class="grid">
    <section class="panel"><h3>Como o Radar trabalha</h3>
      <ul class="small" style="margin:6px 0 0;padding-left:18px;display:flex;flex-direction:column;gap:4px">
        <li>Todo dia às 7h, o GitHub busca as licitações abertas da PB no PNCP, calcula as notas e atualiza este site.</li>
        <li>A IA (Gemini) lê sozinha os editais com nota acima de 6 (inclusive PDFs dentro de .zip e arquivos do Word): ${d.lidas_ia} lido(s) na última busca.</li>
        <li>Em seguida chega o e-mail do dia, com as novidades, os prazos dos próximos 3 dias e os documentos vencendo.</li>
        <li>A aba “Combinam com você” e o painel mostram só as licitações com nota 5 ou mais; as demais ficam em “Todas abertas”.</li>
        <li>A distância é calculada de Campina Grande. Se o edital exigir um raio menor que a sua distância, a licitação perde 4 pontos e fica escondida.</li>
      </ul></section>
    ${bloco('palavras', 'Palavras que interessam', 'Procuradas no objeto e em cada item da licitação. Acentos e maiúsculas não importam.', 'ex.: amortecedor')}
    ${bloco('negativas', 'Palavras que excluem', 'Trechos com estas palavras são ignorados (ex.: “óleo diesel” não conta como “óleo”).', 'ex.: óleo de coco')}
  </div>`;
}
async function salvarCfg(chave, lista) {
  if (!db) return semFirebase();
  await db.collection('config').doc('palavras').set({ palavras: listaCfg('palavras'), negativas: listaCfg('negativas'), [chave]: lista });
  toast('Salvo. As notas são recalculadas na próxima busca (amanhã às 7h).');
}

/* ---------------- Eventos ---------------- */
document.addEventListener('click', async e => {
  const t = e.target.closest('[data-go],[data-sel],[data-abrir],[data-ver],[data-marcar],[data-doc],[data-rm],[data-pedir]');
  if (!t) return;
  if (t.dataset.go) return go(t.dataset.go);
  if (t.dataset.abrir) { state.f.ver = 'todas'; state.sel = t.dataset.abrir; return go('oport'); }
  if (t.dataset.sel) return abrirDetalhe(t.dataset.sel);
  if (t.dataset.ver) { state.f.ver = t.dataset.ver; document.querySelectorAll('[data-ver]').forEach(b => b.setAttribute('aria-pressed', b === t)); return carregarLista(); }
  if (t.dataset.marcar) {
    if (!db) return semFirebase();
    const valor = t.dataset.valor === '1';
    await db.collection('marcas').doc(idSeguro(state.sel)).set({ [t.dataset.marcar]: valor }, { merge: true });
    toast({ favorito: valor ? 'Adicionada às favoritas.' : 'Removida das favoritas.', descartado: valor ? 'Descartada.' : 'Restaurada.' }[t.dataset.marcar]);
    setTimeout(() => abrirDetalhe(state.sel, true), 300);
    return;
  }
  if (t.dataset.pedir) {
    if (!db) return semFirebase();
    await db.collection('pedidos_ia').doc(idSeguro(t.dataset.pedir)).set({ pedido_em: new Date().toISOString() });
    toast('Pedido registrado: a IA lê este edital amanhã às 7h.');
    setTimeout(() => abrirDetalhe(t.dataset.pedir, true), 300);
    return;
  }
  if (t.dataset.doc) return abrirDoc(t.dataset.doc);
  if (t.dataset.rm) { const k = t.dataset.rm; return salvarCfg(k, listaCfg(k).filter((_, i) => i !== +t.dataset.i)); }
});
document.addEventListener('submit', e => {
  const chave = e.target.dataset.add;
  if (!chave) return;
  e.preventDefault();
  const v = $('#add-' + chave).value.trim();
  if (v && !listaCfg(chave).some(x => x.toLowerCase() === v.toLowerCase())) salvarCfg(chave, [...listaCfg(chave), v]);
});
let tBusca;
document.addEventListener('input', e => {
  if (['f-q', 'f-vmax', 'f-kmax'].includes(e.target.id)) {
    state.f[e.target.id.slice(2)] = e.target.value;
    clearTimeout(tBusca); tBusca = setTimeout(carregarLista, 250);
  }
});
document.addEventListener('change', e => {
  const id = e.target.id;
  if (['f-municipio', 'f-modalidade', 'f-ordem'].includes(id)) { state.f[id.slice(2)] = e.target.value; carregarLista(); }
  if (id === 'f-me') { state.f.me = e.target.checked; carregarLista(); }
  if (id === 'f-raio') { state.f.semRaioFora = e.target.checked; carregarLista(); }
});

/* ---------------- Início ---------------- */
(async function iniciar() {
  for (let tentativa = 0; tentativa < 3 && !state.dados; tentativa++) {
    try {
      const r = await fetch('dados/oportunidades.json', { cache: 'no-store' });
      if (r.ok) state.dados = await r.json();
    } catch (e) { await new Promise(ok => setTimeout(ok, 1000)); }
  }
  if (!state.dados) {
    $('#view').innerHTML = '<p class="vazio">Os dados ainda não foram gerados. A primeira busca acontece logo depois da instalação.</p>';
    return;
  }
  try { iniciarFirebase(); } catch (e) { console.error(e); }
  caixaAtualizacao();
  const hash = location.hash.slice(1);
  if (hash) {
    const o = state.dados.oportunidades.find(x => idSeguro(x.id) === hash);
    if (o) { state.f.ver = 'todas'; state.sel = o.id; state.view = 'oport'; }
  }
  render();
})();
