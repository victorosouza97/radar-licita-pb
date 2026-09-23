const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const brl = v => (v ?? 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const brl0 = v => (v ?? 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
const dataBR = s => s ? new Date(s).toLocaleDateString('pt-BR') : '—';
const dataHoraBR = s => s ? new Date(s).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
const diasAte = s => Math.ceil((new Date(s) - new Date()) / 86400000);
const scoreCls = n => n >= 7 ? 'good' : n >= 5 ? 'warn' : 'bad';
const notaTxt = n => n.toFixed(1).replace('.', ',');

async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg = `Erro ${r.status}`;
    try { msg = (await r.json()).erro || msg; } catch (e) {}
    throw new Error(msg);
  }
  return r.json();
}
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => t.hidden = true, 3500);
}

const state = {
  view: 'painel',
  f: { ver: 'relevantes', q: '', municipio: '', modalidade: '', vmax: '', kmax: '', me: false, semRaioFora: true, ordem: 'nota' },
  sel: null,
};
try { const v = localStorage.getItem('rl-view'); if (v) state.view = v; } catch (e) {}

function go(v) {
  state.view = v;
  try { localStorage.setItem('rl-view', v); } catch (e) {}
  render();
}
function render() {
  document.querySelectorAll('#nav button').forEach(b => b.toggleAttribute('aria-current', b.dataset.go === state.view));
  document.querySelectorAll('#nav button[aria-current]').forEach(b => b.setAttribute('aria-current', 'page'));
  ({ painel: vPainel, oport: vOport, docs: vDocs, ajustes: vAjustes }[state.view] || vPainel)();
}

/* ---------------- Coleta (barra lateral) ---------------- */
let coletaRodando = false;
async function atualizarStatus() {
  let s;
  try { s = await api('/api/status'); } catch (e) { return; }
  const box = $('#coleta-box');
  if (s.rodando) {
    const pct = s.total ? Math.round(100 * s.feito / s.total) : 0;
    box.innerHTML = `<b>Atualizando…</b><span>${esc(s.etapa)} (${s.feito} de ${s.total || '?'})</span><div class="progress"><div style="width:${pct}%"></div></div>`;
  } else {
    const u = s.ultima_ok;
    box.innerHTML = `<span>Dados do PNCP atualizados em<br><b>${u ? dataHoraBR(u.fim) : 'ainda não atualizado'}</b></span>
      ${s.erro ? `<span class="pill bad">Última tentativa falhou</span>` : ''}
      <button class="btn small" id="btn-coletar">Atualizar agora</button>
      <span class="small">Atualiza sozinho a cada 6 horas enquanto o programa estiver aberto.</span>`;
    if (coletaRodando) { coletaRodando = false; render(); toast('Lista de licitações atualizada.'); }
  }
  coletaRodando = s.rodando;
  setTimeout(atualizarStatus, s.rodando ? 1500 : 30000);
}
document.addEventListener('click', async e => {
  if (e.target.id === 'btn-coletar') {
    await api('/api/coletar', { method: 'POST' });
    toast('Buscando licitações novas no PNCP…');
    setTimeout(atualizarStatus, 500);
  }
});

/* ---------------- Painel ---------------- */
async function vPainel() {
  const v = $('#view');
  v.innerHTML = `<p class="muted">Carregando…</p>`;
  const p = await api('/api/painel');
  const hoje = new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' });
  const docsTxt = p.docs_alerta.length ? `${p.docs_alerta.filter(d => d.status === 'bad').length} vencido(s), ${p.docs_alerta.filter(d => d.status === 'warn').length} vencendo` : (p.docs_pendentes ? `${p.docs_pendentes} ainda não cadastrados` : 'tudo em dia');
  v.innerHTML = `
  <div class="view-head"><div><h2>Hoje é ${hoje}.</h2><p class="muted">Licitações abertas na Paraíba, lidas do PNCP (portal oficial do governo).</p></div></div>
  <div class="grid kpis">
    <button class="kpi" data-go="oport"><span class="label">Boas oportunidades</span><span class="big num">${p.boas}</span><span class="small muted">nota 7 ou mais, de ${p.abertas} abertas na PB</span></button>
    <button class="kpi" data-go="oport"><span class="label">Novas na última atualização</span><span class="big num">${p.novas}</span><span class="small muted">que combinam com suas palavras</span></button>
    <button class="kpi warn" data-go="oport"><span class="label">Prazos em 7 dias</span><span class="big num">${p.semana.length}</span><span class="small muted">propostas fecham nesta semana</span></button>
    <button class="kpi ${p.docs_alerta.length ? 'bad' : ''}" data-go="docs"><span class="label">Documentos</span><span class="big num">${p.docs_alerta.length + p.docs_pendentes}</span><span class="small muted">${docsTxt}</span></button>
  </div>
  <div class="grid dash">
    <section class="panel"><div class="row" style="justify-content:space-between;margin-bottom:6px"><h3>Melhores oportunidades</h3><button class="btn small" data-go="oport">Ver todas</button></div>
      ${p.melhores.length ? `<ul class="lista-simples">${p.melhores.map(o => itemSimples(o)).join('')}</ul>` : `<p class="vazio">Nenhuma com nota 7 ou mais agora. ${p.abertas ? 'Veja a lista completa em Oportunidades.' : 'Clique em “Atualizar agora” na barra lateral.'}</p>`}
    </section>
    <section class="panel"><h3 style="margin-bottom:6px">Propostas que fecham em 7 dias</h3>
      ${p.semana.length ? `<ul class="lista-simples">${p.semana.map(o => itemSimples(o)).join('')}</ul>` : `<p class="vazio">Nada fechando nesta semana.</p>`}
    </section>
  </div>`;
}
function itemSimples(o) {
  const d = new Date(o.encerramento);
  return `<li data-abrir="${esc(o.id)}"><div class="date-chip"><b>${String(d.getDate()).padStart(2, '0')}</b>${d.toLocaleDateString('pt-BR', { month: 'short' }).replace('.', '')}${d.getFullYear() !== new Date().getFullYear() ? `<br>${d.getFullYear()}` : ''}</div>
    <div><div style="font-weight:600">${esc(resumir(o.objeto, 110))}</div><div class="small muted">${esc(o.municipio)} · ${brl0(o.valor)}</div></div>
    <span class="pill ${scoreCls(o.nota)}">${notaTxt(o.nota)}</span></li>`;
}
const limpar = s => (s || '').replace(/^\s*\[[^\]]*\]\s*-?\s*/, '').replace(/\s+/g, ' ').trim();
const resumir = (s, n) => { s = limpar(s); return s.length > n ? s.slice(0, n - 1) + '…' : s; };

/* ---------------- Oportunidades ---------------- */
let dadosOport = null;
async function vOport() {
  const f = state.f;
  $('#view').innerHTML = `
  <div class="view-head"><div><h2>Oportunidades</h2><p class="muted">Licitações com propostas abertas na Paraíba. A nota (0 a 10) mostra o quanto cada uma combina com suas palavras-chave, a distância de Campina Grande e os benefícios para ME/EPP.</p></div></div>
  <div class="tabs" role="group">
    ${[['relevantes', 'Combinam com você'], ['todas', 'Todas abertas'], ['favoritas', 'Favoritas'], ['descartadas', 'Descartadas']].map(([k, t]) => `<button class="tab" data-ver="${k}" aria-pressed="${f.ver === k}">${t}</button>`).join('')}
  </div>
  <div class="panel" style="margin-bottom:14px"><div class="filters">
    <label class="field"><span class="label">Buscar no texto</span><input type="text" id="f-q" value="${esc(f.q)}" placeholder="ex.: ambulância, trator"></label>
    <label class="field"><span class="label">Cidade</span><select id="f-municipio"><option value="">Toda a Paraíba</option></select></label>
    <label class="field"><span class="label">Modalidade</span><select id="f-modalidade"><option value="">Todas</option></select></label>
    <label class="field"><span class="label">Valor máximo (R$)</span><input type="number" id="f-vmax" min="0" step="1000" value="${esc(f.vmax)}" placeholder="sem limite"></label>
    <label class="field"><span class="label">Distância máxima (km)</span><input type="number" id="f-kmax" min="0" step="10" value="${esc(f.kmax)}" placeholder="qualquer distância"></label>
    <label class="field"><span class="label">Ordenar por</span><select id="f-ordem">${[['nota', 'Melhor nota'], ['prazo', 'Prazo mais próximo'], ['valor', 'Maior valor'], ['distancia', 'Mais perto']].map(([v, t]) => `<option value="${v}" ${v === f.ordem ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
    <label class="field" style="justify-content:flex-end"><span class="row"><input type="checkbox" id="f-me" ${f.me ? 'checked' : ''}> Só com vantagem ME/EPP</span></label>
    <label class="field" style="justify-content:flex-end"><span class="row"><input type="checkbox" id="f-raio" ${f.semRaioFora ? 'checked' : ''}> Esconder as que exigem raio menor que a minha distância</span></label>
  </div></div>
  <div class="opp-layout"><div><p class="small muted" id="count" style="margin-bottom:8px">Carregando…</p><div class="opp-list" id="opp-list"></div></div>
  <aside class="panel detail" id="detail"><p class="muted">Clique numa licitação para ver os detalhes.</p></aside></div>`;
  await carregarLista();
}
async function carregarLista() {
  const f = state.f;
  const qs = new URLSearchParams({ ver: f.ver, q: f.q, municipio: f.municipio, modalidade: f.modalidade, vmax: f.vmax, kmax: f.kmax, sem_raio_fora: f.semRaioFora ? '1' : '', me: f.me ? '1' : '', ordem: f.ordem, nota_min: f.ver === 'todas' ? '0' : '5' });
  dadosOport = await api('/api/oportunidades?' + qs);
  const d = dadosOport;
  const selM = $('#f-municipio'), selMod = $('#f-modalidade');
  if (selM && selM.options.length === 1) {
    selM.insertAdjacentHTML('beforeend', d.municipios.map(m => `<option ${m === f.municipio ? 'selected' : ''}>${esc(m)}</option>`).join(''));
    selMod.insertAdjacentHTML('beforeend', d.modalidades.map(m => `<option ${m === f.modalidade ? 'selected' : ''}>${esc(m)}</option>`).join(''));
  }
  $('#count').textContent = d.total_abertas
    ? `${d.itens.length} licitação(ões) nesta lista · ${d.relevantes} de ${d.total_abertas} abertas na PB combinam com suas palavras`
    : 'Ainda não há dados. Clique em “Atualizar agora” na barra lateral (a primeira vez leva alguns minutos).';
  $('#opp-list').innerHTML = d.itens.length ? d.itens.map(o => `
    <button class="opp" data-sel="${esc(o.id)}" aria-selected="${o.id === state.sel}">
      <div class="score ${o.nota > 0 ? scoreCls(o.nota) : 'bad'}">${notaTxt(o.nota)}<small>nota</small></div>
      <div><h3>${esc(resumir(o.objeto, 180))}</h3>
      <div class="meta"><span>${esc(o.municipio)}${o.km != null ? ` (~${o.km} km)` : ''} · ${esc(resumir(o.unidade || o.orgao, 50))}</span><span class="num">${brl0(o.valor)}</span>
      <span>Fecha ${dataBR(o.encerramento)} (${diasAte(o.encerramento)} dias)</span>
      ${o.nova ? '<span class="pill info">Nova</span>' : ''}${o.me_exclusivo ? '<span class="pill good">Exclusiva ME/EPP</span>' : o.me_cota ? '<span class="pill good">Cota ME/EPP</span>' : ''}${o.favorito ? '<span class="pill warn">Favorita</span>' : ''}${foraRaio(o) ? `<span class="pill bad">Exige raio de ${o.raio} km</span>` : o.raio ? `<span class="pill info">Raio ${o.raio} km: você está dentro</span>` : ''}</div></div>
    </button>`).join('') : (d.total_abertas ? '<div class="panel vazio">Nenhuma licitação com esses filtros.</div>' : '');
}
const foraRaio = o => o.raio && o.km != null && o.km > o.raio;
let pollIA;
async function abrirDetalhe(id) {
  clearTimeout(pollIA);
  state.sel = id;
  document.querySelectorAll('.opp').forEach(b => b.setAttribute('aria-selected', b.dataset.sel === id));
  const el = $('#detail');
  el.innerHTML = '<p class="muted">Carregando detalhes e arquivos do edital…</p>';
  let o;
  try { o = await api('/api/oportunidades/' + encodeURIComponent(id)); }
  catch (e) { el.innerHTML = `<p class="muted">Não consegui carregar: ${esc(e.message)}</p>`; return; }
  const dias = diasAte(o.encerramento);
  const itensBatem = o.itens.filter(i => i.bate);
  el.innerHTML = `
    <div class="row" style="justify-content:space-between;margin-bottom:6px"><span class="label">${esc(o.modalidade)}${o.srp ? ' · Registro de preços' : ''}</span><span class="pill ${o.nota > 0 ? scoreCls(o.nota) : 'plain'}">Nota ${notaTxt(o.nota || 0)}</span></div>
    <h3 style="font-size:1.08rem;margin-bottom:4px;font-family:var(--f-body)">${esc(limpar(o.objeto))}</h3>
    <p class="muted" style="margin-bottom:12px">${esc(o.orgao)} · ${esc(o.unidade)} · ${esc(o.municipio)}</p>
    <div class="kv" style="margin-bottom:14px">
      <div><span class="label">Valor estimado</span><b class="num">${o.valor ? brl(o.valor) : 'Sigiloso / não informado'}</b></div>
      <div><span class="label">Propostas até</span><b>${dataHoraBR(o.encerramento)}</b><span class="small ${dias <= 2 ? 'muted' : 'muted'}">${dias} dia(s)</span></div>
      <div><span class="label">Plataforma</span><b>${esc(o.plataforma || '—')}</b></div>
      <div><span class="label">Distância de Campina Grande</span><b>${o.km != null ? `~${o.km} km por estrada` : '—'}</b><span class="small muted">estimativa</span></div>
      <div><span class="label">Raio exigido</span><b style="color:${foraRaio(o) ? 'var(--bad)' : 'inherit'}">${o.raio ? `${o.raio} km${foraRaio(o) ? ' (você está fora)' : ' (você está dentro)'}` : 'Não encontrado no texto'}</b></div>
      <div><span class="label">Nº no PNCP</span><b class="mono small">${esc(o.id)}</b></div>
    </div>
    <div class="row">
      <a class="btn primary" href="${esc(o.link_pncp)}" target="_blank" rel="noopener">Abrir no PNCP</a>
      ${o.link_origem ? `<a class="btn" href="${esc(o.link_origem)}" target="_blank" rel="noopener">Abrir na plataforma</a>` : ''}
      <button class="btn" data-marcar="favorito" data-valor="${o.favorito ? 0 : 1}">${o.favorito ? 'Tirar das favoritas' : 'Favoritar'}</button>
      <button class="btn" data-marcar="descartado" data-valor="${o.descartado ? 0 : 1}">${o.descartado ? 'Restaurar' : 'Descartar'}</button>
    </div>
    ${(o.motivos?.length || o.alertas?.length) ? `<div class="detail-sec" style="margin-top:14px"><span class="label">Por que essa nota</span>
      <div class="row">${(o.motivos || []).map(m => `<span class="pill good">${esc(m)}</span>`).join('')}${(o.alertas || []).map(m => `<span class="pill warn">${esc(m)}</span>`).join('')}</div></div>` : ''}
    ${blocoIA(o)}
    ${o.info ? `<div class="detail-sec"><span class="label">Informação complementar</span><p class="small">${esc(o.info)}</p></div>` : ''}
    <div class="detail-sec"><span class="label">Arquivos (edital, termo de referência…)</span>
      ${o.arquivos === null ? '<p class="small muted">O PNCP não respondeu agora. Use o botão “Abrir no PNCP”.</p>' :
        o.arquivos.length ? `<ul class="checklist">${o.arquivos.map(a => `<li><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.titulo)}</a><span class="pill plain">${esc(a.tipo || '')}</span></li>`).join('')}</ul>` : '<p class="small muted">Nenhum arquivo publicado.</p>'}</div>
    <div class="detail-sec"><div class="row" style="justify-content:space-between"><span class="label">Itens (${o.itens.length})</span>${itensBatem.length ? `<span class="pill good">${itensBatem.length} combinam com você</span>` : ''}</div>
      ${o.itens.length ? `<div class="table-wrap"><table><thead><tr><th>#</th><th>Descrição</th><th class="r">Qtd</th><th class="r">Unit. estimado</th></tr></thead><tbody>
        ${[...itensBatem, ...o.itens.filter(i => !i.bate)].slice(0, 200).map(i => `<tr class="${i.bate ? 'bate' : ''}"><td class="mono">${i.numero}</td><td>${esc(i.descricao)}${i.beneficio && /ME\/EPP/i.test(i.beneficio) ? `<br><span class="pill good">${esc(i.beneficio)}</span>` : ''}</td>
          <td class="r num">${(i.qtd ?? '').toLocaleString('pt-BR')} ${esc((i.unidade || '').toLowerCase())}</td><td class="r mono">${i.valor_unit ? brl(i.valor_unit) : '—'}</td></tr>`).join('')}
      </tbody></table></div>${o.itens.length > 200 ? '<p class="small muted">Mostrando 200 itens. Veja todos no PNCP.</p>' : ''}` : '<p class="small muted">Itens ainda não lidos. Atualize os dados.</p>'}</div>
    <div class="detail-sec" style="padding-bottom:0"><span class="label">Seus documentos (os que quase todo edital pede)</span>
      <ul class="checklist">${o.documentos.map(d => `<li><span>${esc(d.nome)}</span><span class="pill ${d.status}">${esc(d.status_txt)}</span></li>`).join('')}</ul></div>`;
  if (window.innerWidth <= 1100 && !abrirDetalhe.silencioso) el.scrollIntoView({ behavior: 'smooth' });
  if (o.analisando) pollIA = setTimeout(() => { abrirDetalhe.silencioso = true; abrirDetalhe(id).finally(() => abrirDetalhe.silencioso = false); }, 4000);
}
function blocoIA(o) {
  const a = o.analise, d = a?.dados;
  if (o.analisando) return `<div class="detail-sec ia-box"><span class="label">Leitura do edital pela IA</span><p>Lendo o edital… isso leva de 30 segundos a 2 minutos.</p></div>`;
  if (!o.ia_configurada) return `<div class="detail-sec"><span class="label">Leitura do edital pela IA</span><p class="small muted">Falta a chave do Gemini no arquivo .env.</p></div>`;
  if (!d) return `<div class="detail-sec"><span class="label">Leitura do edital pela IA</span>
    ${a?.erro ? `<p class="small" style="color:var(--bad)">Não deu certo da última vez: ${esc(a.erro)}</p>` : '<p class="small muted">A IA lê o PDF do edital e resume o que importa: documentos, prazos, raio, multas e pontos de atenção.</p>'}
    <div><button class="btn primary" data-analisar="${esc(o.id)}">${a?.erro ? 'Tentar de novo' : 'Ler edital com IA'}</button></div></div>`;
  const lin = (rot, v) => v ? `<div><span class="label">${rot}</span><b>${esc(v)}</b></div>` : '';
  return `<div class="detail-sec ia-box">
    <div class="row" style="justify-content:space-between"><span class="label">Leitura do edital pela IA</span><span class="small muted">${esc((a.arquivos || []).join(', '))}</span></div>
    <p>${esc(d.resumo)}</p>
    <p><b>Vale a pena?</b> ${esc(d.vale_a_pena)}</p>
    <div class="kv">${lin('Sessão', d.data_sessao)}${lin('Impugnar até', d.prazo_impugnacao)}${lin('Critério', d.criterio)}${lin('Participação', d.participacao_me)}${lin('Prazo de entrega', d.prazo_entrega)}${lin('Local de entrega', d.local_entrega)}${lin('Garantia', d.garantia)}${lin('Raio exigido', d.raio_km ? d.raio_km + ' km' : null)}</div>
    ${d.raio_trecho ? `<p class="small"><b>Trecho sobre o raio:</b> “${esc(d.raio_trecho)}”</p>` : ''}
    <div class="row">${d.exige_amostra ? '<span class="pill warn">Exige amostra</span>' : ''}${d.exige_visita_tecnica ? '<span class="pill warn">Exige visita técnica</span>' : ''}</div>
    ${d.pontos_atencao?.length ? `<div><span class="label">Pontos de atenção</span><ul style="margin:4px 0 0;padding-left:18px">${d.pontos_atencao.map(p => `<li>${esc(p)}</li>`).join('')}</ul></div>` : ''}
    ${o.exigidos?.length ? `<div><span class="label">Documentos exigidos × seu cofre</span><ul class="checklist" style="margin-top:4px">${o.exigidos.map(x => `<li><span>${esc(x.nome)}</span><span class="pill ${x.status}">${esc(x.cofre ? x.status_txt : 'Conferir')}</span></li>`).join('')}</ul></div>` : ''}
    <p class="small muted">Resumo feito por IA: confira no edital antes de decidir. <button class="btn small" data-analisar="${esc(o.id)}">Ler de novo</button></p>
  </div>`;
}

/* ---------------- Documentos ---------------- */
let docsCache = [];
async function vDocs() {
  docsCache = await api('/api/documentos');
  const ord = { bad: 0, warn: 1, plain: 2, good: 3 };
  const lista = [...docsCache].sort((a, b) => ord[a.status] - ord[b.status]);
  $('#view').innerHTML = `
  <div class="view-head"><div><h2>Cofre de documentos</h2><p class="muted">Guarde aqui as certidões e documentos da empresa, com a data de validade. O painel avisa quando algo estiver para vencer. Os arquivos ficam só neste computador, na pasta <span class="mono small">dados\\documentos</span>.</p></div>
  <button class="btn primary" data-doc="novo">Adicionar documento</button></div>
  <div class="panel table-wrap"><table>
    <thead><tr><th>Documento</th><th>Emissor</th><th>Validade</th><th>Situação</th><th>Arquivo</th><th></th></tr></thead>
    <tbody>${lista.map(d => `<tr>
      <td style="font-weight:600">${esc(d.nome)}${d.obs ? `<div class="small muted">${esc(d.obs)}</div>` : ''}</td>
      <td class="muted">${esc(d.emissor)}</td>
      <td class="mono">${d.sem_validade ? '—' : d.validade ? dataBR(d.validade + 'T12:00') : '—'}</td>
      <td><span class="pill ${d.status}">${esc(d.status_txt)}</span></td>
      <td>${d.arquivo ? `<a href="/api/documentos/${d.id}/arquivo" target="_blank">${esc(resumir(d.arquivo_nome, 28))}</a>` : '<span class="muted small">—</span>'}</td>
      <td><div class="row" style="flex-wrap:nowrap">
        ${d.link_emissao ? `<a class="btn small" href="${esc(d.link_emissao)}" target="_blank" rel="noopener">Emitir</a>` : ''}
        <button class="btn small" data-doc="${d.id}">Atualizar</button></div></td></tr>`).join('')}</tbody>
  </table></div>
  <p class="small muted" style="margin-top:10px">“Emitir” abre o site oficial da certidão. Baixe o PDF, depois clique em “Atualizar”, anexe o arquivo e informe a nova validade.</p>`;
}
function abrirDoc(id) {
  const d = id === 'novo' ? { nome: '', emissor: '', validade: '', sem_validade: 0, obs: '', link_emissao: '' } : docsCache.find(x => x.id === +id);
  const dlg = $('#dlg-doc');
  dlg.innerHTML = `<form id="form-doc">
    <h3>${id === 'novo' ? 'Novo documento' : 'Atualizar documento'}</h3>
    <label class="field"><span class="label">Nome</span><input type="text" name="nome" id="doc-nome" required value="${esc(d.nome)}"></label>
    <label class="field"><span class="label">Emissor</span><input type="text" name="emissor" id="doc-emissor" value="${esc(d.emissor)}"></label>
    <div class="row" style="align-items:flex-end">
      <label class="field" style="flex:1"><span class="label">Válido até</span><input type="date" name="validade" id="doc-validade" value="${esc(d.validade || '')}" ${d.sem_validade ? 'disabled' : ''}></label>
      <label class="row" style="padding-bottom:8px"><input type="checkbox" name="sem_validade" id="doc-sem" value="1" ${d.sem_validade ? 'checked' : ''}> Não vence</label>
    </div>
    <label class="field"><span class="label">Arquivo (PDF ou imagem)${d.arquivo_nome ? ` · atual: ${esc(d.arquivo_nome)}` : ''}</span><input type="file" name="arquivo" id="doc-arquivo" accept=".pdf,.png,.jpg,.jpeg,.doc,.docx"></label>
    <label class="field"><span class="label">Site para emitir (opcional)</span><input type="text" name="link_emissao" id="doc-link" value="${esc(d.link_emissao)}"></label>
    <label class="field"><span class="label">Observação</span><input type="text" name="obs" id="doc-obs" value="${esc(d.obs)}"></label>
    <div class="row" style="justify-content:space-between;margin-top:6px">
      ${id !== 'novo' ? `<button type="button" class="btn danger" id="doc-apagar">Excluir…</button>` : '<span></span>'}
      <div class="row"><button type="button" class="btn" id="doc-cancelar">Cancelar</button><button class="btn primary">Salvar</button></div>
    </div>
    <p class="small" id="doc-confirma" hidden style="color:var(--bad)">Clique em “Excluir” de novo para confirmar. O arquivo também será apagado.</p>
  </form>`;
  dlg.showModal();
  $('#doc-sem').onchange = e => { $('#doc-validade').disabled = e.target.checked; };
  $('#doc-cancelar').onclick = () => dlg.close();
  const apagar = $('#doc-apagar');
  if (apagar) apagar.onclick = async () => {
    if ($('#doc-confirma').hidden) { $('#doc-confirma').hidden = false; apagar.textContent = 'Excluir'; return; }
    await api(`/api/documentos/${id}`, { method: 'DELETE' });
    dlg.close(); toast('Documento excluído.'); vDocs();
  };
  $('#form-doc').onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    if (!$('#doc-sem').checked && !fd.get('validade') && id !== 'novo' && !d.validade) { /* permite salvar sem validade */ }
    try {
      await api(id === 'novo' ? '/api/documentos' : `/api/documentos/${id}`, { method: 'POST', body: fd });
      dlg.close(); toast('Documento salvo.'); vDocs();
    } catch (err) { toast(err.message); }
  };
}

/* ---------------- Ajustes ---------------- */
let cfg = null;
async function vAjustes() {
  cfg = await api('/api/config');
  const bloco = (chave, titulo, texto, exemplo) => `
    <section class="panel"><h3>${titulo}</h3><p class="small muted" style="margin:4px 0 12px">${texto}</p>
      <div class="chips" id="chips-${chave}">${cfg[chave].map((p, i) => `<span class="chip">${esc(p)}<button title="Remover" aria-label="Remover ${esc(p)}" data-rm="${chave}" data-i="${i}">×</button></span>`).join('')}</div>
      <form class="add-row" data-add="${chave}"><input type="text" id="add-${chave}" placeholder="${exemplo}"><button class="btn">Adicionar</button></form></section>`;
  const st = cfg.alertas_status || {};
  $('#view').innerHTML = `
  <div class="view-head"><div><h2>Ajustes e alertas</h2><p class="muted">As palavras definem a nota de cada licitação. As mudanças valem na hora, sem precisar baixar nada de novo.</p></div></div>
  <div class="grid">
    <section class="panel" id="painel-email"><h3>Alertas por e-mail (grátis, pelo Gmail)</h3>
      <p class="small muted" style="margin:4px 0 12px">Você recebe um e-mail quando aparecer licitação com nota alta e um resumo diário com prazos fechando e documentos vencendo. O Radar precisa estar aberto no computador para enviar.</p>
      <form id="form-email" class="grid" style="gap:12px">
        <label class="row"><input type="checkbox" id="em-ativo" ${cfg.email_ativo ? 'checked' : ''}> <b>Ligar os alertas por e-mail</b></label>
        <div class="filters">
          <label class="field"><span class="label">Seu Gmail (quem envia)</span><input type="text" id="em-usuario" value="${esc(cfg.smtp_usuario)}" placeholder="seuemail@gmail.com" autocomplete="off"></label>
          <label class="field"><span class="label">Senha de app do Google</span><input type="password" id="em-senha" placeholder="${cfg.smtp_senha_definida ? 'já cadastrada (deixe em branco para manter)' : '16 letras'}" autocomplete="new-password"></label>
          <label class="field"><span class="label">Enviar para (pode ser mais de um, separados por vírgula)</span><input type="text" id="em-para" value="${esc(cfg.email_para)}" placeholder="seuemail@gmail.com"></label>
        </div>
        <div class="filters">
          <label class="field"><span class="label">Horário do resumo diário</span><input type="text" id="em-hora" value="${esc(cfg.hora_resumo)}" placeholder="07:00"></label>
          <label class="field"><span class="label">Avisar na hora quando a nota for pelo menos</span><input type="number" id="em-nota" min="1" max="10" step="0.5" value="${esc(cfg.nota_alerta)}"></label>
          <label class="field" style="justify-content:flex-end"><span class="row"><input type="checkbox" id="em-imediato" ${cfg.alerta_imediato ? 'checked' : ''}> Avisar assim que surgir licitação boa</span></label>
        </div>
        <div class="row"><button class="btn primary">Salvar</button><button type="button" class="btn" id="em-teste">Enviar e-mail de teste</button>
          ${st.ultimo_envio ? `<span class="small muted">Último envio: ${dataHoraBR(st.ultimo_envio)}</span>` : ''}${st.ultimo_erro ? `<span class="pill bad">${esc(st.ultimo_erro)}</span>` : ''}</div>
      </form>
      <details style="margin-top:14px"><summary><b>Como criar a “senha de app” do Google (5 minutos)</b></summary>
        <ol class="small" style="margin:8px 0 0;padding-left:20px;display:flex;flex-direction:column;gap:4px">
          <li>A senha de app é uma senha especial, só para este programa enviar e-mails. Ela não é a senha normal do seu Gmail e não dá acesso à sua conta pelo navegador.</li>
          <li>Ela exige a <b>verificação em duas etapas</b> ligada. Se ainda não tiver, ative em <a href="https://myaccount.google.com/signinoptions/twosv" target="_blank" rel="noopener">myaccount.google.com/signinoptions/twosv</a>.</li>
          <li>Abra <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener">myaccount.google.com/apppasswords</a> e faça login.</li>
          <li>No campo “Nome do app”, digite <b>Radar Licita</b> e clique em <b>Criar</b>.</li>
          <li>O Google mostra 16 letras num quadro amarelo. Copie e cole no campo “Senha de app” acima. Os espaços não importam.</li>
          <li>Clique em <b>Salvar</b> e depois em <b>Enviar e-mail de teste</b>.</li>
        </ol></details>
    </section>
    <section class="panel"><h3>Leitura de editais pela IA</h3>
      <p class="small muted" style="margin-top:4px">${cfg.ia_configurada ? '<span class="pill good">Chave do Gemini configurada</span> Depois de cada atualização, a IA lê sozinha os editais das licitações com nota 7 ou mais. Nas outras, use o botão “Ler edital com IA”.' : '<span class="pill bad">Falta a chave do Gemini</span> Coloque GEMINI_API_KEY no arquivo .env da pasta do programa.'}</p></section>
    ${bloco('palavras', 'Palavras que interessam', 'O sistema procura estas palavras no objeto e em cada item da licitação. Acentos e maiúsculas não importam.', 'ex.: amortecedor')}
    ${bloco('negativas', 'Palavras que excluem', 'Trechos com estas palavras são ignorados (ex.: “óleo diesel” não conta como “óleo”).', 'ex.: óleo de coco')}
    <section class="panel"><h3>Distância e raio</h3><p class="small muted" style="margin-top:4px">A distância é calculada de Campina Grande até a sede de cada cidade (estimativa por estrada). Até 40 km a licitação ganha +1 ponto, até 100 km ganha +0,5 e acima de 250 km perde 0,5. Se o texto ou o edital exigir empresa num raio menor que a sua distância, a licitação perde 4 pontos e fica escondida (dá para mostrar de novo no filtro).</p></section>
  </div>`;
}
document.addEventListener('submit', async e => {
  if (e.target.id !== 'form-email') return;
  e.preventDefault();
  const dados = {
    email_ativo: $('#em-ativo').checked, smtp_usuario: $('#em-usuario').value.trim(), smtp_senha: $('#em-senha').value,
    email_para: $('#em-para').value.trim(), hora_resumo: $('#em-hora').value.trim() || '07:00',
    nota_alerta: +$('#em-nota').value || 7, alerta_imediato: $('#em-imediato').checked,
  };
  if (!/^\d{1,2}:\d{2}$/.test(dados.hora_resumo)) return toast('Horário no formato 07:00');
  cfg = await api('/api/config', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(dados) });
  toast(dados.email_ativo ? 'Alertas por e-mail salvos e ligados.' : 'Salvo. Os alertas estão desligados.');
  vAjustes();
});
document.addEventListener('click', async e => {
  if (e.target.id !== 'em-teste') return;
  e.target.disabled = true; e.target.textContent = 'Enviando…';
  try { await api('/api/alertas/teste', { method: 'POST' }); toast('E-mail de teste enviado. Confira sua caixa de entrada (e o spam).'); }
  catch (err) { toast(err.message); }
  e.target.disabled = false; e.target.textContent = 'Enviar e-mail de teste';
});
async function salvarCfg(chave, lista) {
  cfg = await api('/api/config', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ [chave]: lista }) });
  vAjustes();
}
document.addEventListener('submit', e => {
  const chave = e.target.dataset.add;
  if (!chave) return;
  e.preventDefault();
  const v = $('#add-' + chave).value.trim();
  if (v && !cfg[chave].some(x => x.toLowerCase() === v.toLowerCase())) salvarCfg(chave, [...cfg[chave], v]).then(() => toast(`“${v}” adicionada.`));
});

/* ---------------- Eventos gerais ---------------- */
document.addEventListener('click', async e => {
  const t = e.target.closest('[data-go],[data-sel],[data-abrir],[data-ver],[data-marcar],[data-doc],[data-rm],[data-analisar]');
  if (!t) return;
  if (t.dataset.go) return go(t.dataset.go);
  if (t.dataset.abrir) {
    state.f.ver = 'todas';
    state.view = 'oport';
    render();
    await new Promise(r => setTimeout(r, 0));
    return abrirDetalhe(t.dataset.abrir);
  }
  if (t.dataset.sel) return abrirDetalhe(t.dataset.sel);
  if (t.dataset.ver) { state.f.ver = t.dataset.ver; document.querySelectorAll('[data-ver]').forEach(b => b.setAttribute('aria-pressed', b === t)); return carregarLista(); }
  if (t.dataset.marcar) {
    await api(`/api/oportunidades/${encodeURIComponent(state.sel)}/marcar`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ campo: t.dataset.marcar, valor: t.dataset.valor === '1' }) });
    toast({ favorito: t.dataset.valor === '1' ? 'Adicionada às favoritas.' : 'Removida das favoritas.', descartado: t.dataset.valor === '1' ? 'Descartada. Ela não aparece mais na lista principal.' : 'Restaurada.' }[t.dataset.marcar]);
    await carregarLista(); return abrirDetalhe(state.sel);
  }
  if (t.dataset.doc) return abrirDoc(t.dataset.doc);
  if (t.dataset.analisar) {
    await api(`/api/oportunidades/${encodeURIComponent(t.dataset.analisar)}/analisar`, { method: 'POST' });
    toast('A IA está lendo o edital…');
    setTimeout(() => abrirDetalhe(t.dataset.analisar), 800);
    return;
  }
  if (t.dataset.rm) { const k = t.dataset.rm; return salvarCfg(k, cfg[k].filter((_, i) => i !== +t.dataset.i)); }
});
let tBusca;
document.addEventListener('input', e => {
  if (e.target.id === 'f-q' || e.target.id === 'f-vmax' || e.target.id === 'f-kmax') {
    state.f[e.target.id.slice(2)] = e.target.value;
    clearTimeout(tBusca); tBusca = setTimeout(carregarLista, 300);
  }
});
document.addEventListener('change', e => {
  const id = e.target.id;
  if (id === 'f-municipio' || id === 'f-modalidade' || id === 'f-ordem') { state.f[id.slice(2)] = e.target.value; carregarLista(); }
  if (id === 'f-me') { state.f.me = e.target.checked; carregarLista(); }
  if (id === 'f-raio') { state.f.semRaioFora = e.target.checked; carregarLista(); }
});

render();
atualizarStatus();
