
  /* ── Restaurar posição de scroll ── */
  window.addEventListener("beforeunload", () =>
    sessionStorage.setItem("scrollY", window.scrollY));
  window.addEventListener("DOMContentLoaded", () => {
    const y = sessionStorage.getItem("scrollY");
    if (y) { window.scrollTo(0, +y); sessionStorage.removeItem("scrollY"); }
  });

  /* ── Tema claro/escuro ── */
  function aplicarTema() {
    document.body.classList.toggle('dark-theme', localStorage.getItem('tema') === 'escuro');
  }
  function toggleTema() {
    localStorage.setItem('tema', document.body.classList.contains('dark-theme') ? 'claro' : 'escuro');
    aplicarTema();
  }
  aplicarTema();

  /* ── Toast de feedback ao salvar ── */
  function mostrarToast() {
    const t = document.getElementById('toast');
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2500);
  }

  /* ── Ordenação da tabela ── */
  const direcoesSort = {};
  function ordenarTabela(col) {
    const tbody = document.querySelector("#tabelaAtividades tbody");
    if (!tbody) return;
    const linhas = [...tbody.querySelectorAll(".linha-dado")];
    const asc = direcoesSort[col] !== "asc";
    direcoesSort[col] = asc ? "asc" : "desc";
    linhas.sort((a, b) => {
      const tA = a.querySelectorAll("td"), tB = b.querySelectorAll("td");
      const vA = col === 0
        ? (tA[0].querySelector("input")?.value  || "")
        : (tA[1].querySelector("select")?.value || "");
      const vB = col === 0
        ? (tB[0].querySelector("input")?.value  || "")
        : (tB[1].querySelector("select")?.value || "");
      return asc ? vA.localeCompare(vB) : vB.localeCompare(vA);
    });
    linhas.forEach(l => tbody.appendChild(l));
  }

  /* ── Editores rich text (formulário) ── */
  function execFormCmd(cmd, id) {
    const ed = document.getElementById(id);
    ed.focus();
    document.execCommand(cmd, false, null);
    ed.parentElement.querySelector('input[type="hidden"]').value = ed.innerHTML;
  }
  function inserirLinkForm(id) {
    const url = prompt("URL do link:");
    if (!url) return;
    const ed = document.getElementById(id);
    ed.focus();
    document.execCommand("createLink", false, url);
    ed.parentElement.querySelector('input[type="hidden"]').value = ed.innerHTML;
  }

  /* ── Editores rich text (tabela) ── */
  function execTableCmd(btn, cmd) {
    const td = btn.closest("td");
    const ed = td.querySelector(".editor-box-table");
    ed.focus();
    document.execCommand(cmd, false, null);
    td.querySelector('input[type="hidden"]').value = ed.innerHTML;
  }
  function inserirLinkTable(btn) {
    const url = prompt("URL do link:");
    if (!url) return;
    const td = btn.closest("td");
    const ed = td.querySelector(".editor-box-table");
    ed.focus();
    document.execCommand("createLink", false, url);
    td.querySelector('input[type="hidden"]').value = ed.innerHTML;
  }

  /* ── Sincronização de campos hidden ── */
  function prepararEnvioNovaAtividade() {
    const desc = document.getElementById('editor-nova-desc');
    const obs  = document.getElementById('editor-nova-obs');
    if (desc) document.getElementById('input-nova-desc').value = desc.innerHTML;
    if (obs)  document.getElementById('input-nova-obs').value  = obs.innerHTML;
  }
  function prepararEnvioProcedimento() {
    const ed = document.getElementById('editor-proc-conteudo');
    if (ed) document.getElementById('input-proc-conteudo').value = ed.innerHTML;
  }
  function inserirBlocoCodigo(id) {
    const codigo = prompt("Insira o código aqui:");
    if (!codigo) return;
    const ed = document.getElementById(id);
    ed.focus();
    // Escapa HTML básico para evitar quebras
    const codigoEscapado = codigo.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const html = `<pre><code>${codigoEscapado}</code></pre><p><br></p>`;
    document.execCommand("insertHTML", false, html);
    ed.parentElement.querySelector('input[type="hidden"]').value = ed.innerHTML;
  }
  function filtrarProcedimentos() {
    const val = document.getElementById('filtroProcedimentos').value.toLowerCase();
    document.querySelectorAll('.proc-item').forEach(item => {
      const titulo = item.querySelector('.proc-title').innerText.toLowerCase();
      item.style.display = titulo.includes(val) ? "" : "none";
    });
  }
  function sincronizarInputTabela(ed) {
    ed.closest("td").querySelector('input[type="hidden"]').value = ed.innerHTML;
  }

  /* ── Cores de selects ── */
  function ajustarCorSelect(el) {
    el.style.backgroundColor = el.selectedOptions[0]?.dataset.color || '#475569';
  }
  function ajustarCorPrio(el) {
    el.style.backgroundColor = el.selectedOptions[0]?.dataset.color || '#22c55e';
  }

  /* ── Foto do responsável ── */
  function ajustarFotoResp(el, containerId) {
    const foto = el.selectedOptions[0]?.dataset.foto || '';
    const c = document.getElementById(containerId);
    if (!c) return;
    c.innerHTML = foto
      ? `<img src="${foto}" style="width:26px;height:26px;border-radius:50%;object-fit:cover;border:1px solid var(--border-color);">`
      : `<div style="width:26px;height:26px;border-radius:50%;background:var(--table-even);display:flex;align-items:center;justify-content:center;font-size:13px;border:1px solid var(--border-color);">👤</div>`;
  }

  /* ── Filtros da tabela ── */
    function filtrarTabelaAvancado() {
    const fArea = document.getElementById("filtro-area") ? document.getElementById("filtro-area").value.toLowerCase() : "";
    const fResp = document.getElementById("filtro-responsavel") ? document.getElementById("filtro-responsavel").value.toLowerCase() : "";
    const fStatus = document.getElementById("filtro-status") ? document.getElementById("filtro-status").value.toLowerCase() : "";
    const fPrio = document.getElementById("filtro-prioridade") ? document.getElementById("filtro-prioridade").value.toLowerCase() : "";

    let selector = abaAtivaGlobal === 'arquivados' ? '#tabelaArquivadasOculta .linha-dado' : '#tabelaAtividades .linha-dado';
    const linhas = [...document.querySelectorAll(selector)];
    let pendente = 0, andamento = 0, feito = 0;

    linhas.forEach(tr => {
      // Data reading from normal table or hidden table
      const vArea = (tr.querySelector('select[data-campo="area"]')?.value || tr.querySelector('.w-area')?.innerText || tr.querySelector('td:nth-child(2)')?.innerText || "").toLowerCase().trim();
      const vResp = (tr.querySelector('select[data-campo="responsavel"]')?.value || tr.querySelector('.w-resp')?.innerText || "").toLowerCase().trim();
      const vStatus = (tr.querySelector('select[data-campo="status"]')?.value || tr.querySelector('.w-status')?.innerText || "").toLowerCase().trim();
      const vPrio = (tr.querySelector('select[data-campo="prioridade"]')?.value || tr.querySelector('.w-prio')?.innerText || "").toLowerCase().trim();

      const show = 
        (!fArea || vArea === fArea) &&
        (!fResp || vResp === fResp) &&
        (!fStatus || vStatus === fStatus) &&
        (!fPrio || vPrio === fPrio);

      tr.style.display = show ? "" : "none";

      if (show) {
          if (vStatus === 'pendente') pendente++;
          else if (vStatus === 'em andamento') andamento++;
          else if (vStatus === 'feito') feito++;
      }
    });

    if (abaAtivaGlobal === 'ativos') {
        const bPendente = document.getElementById("metric-pendente");
        const bAndamento = document.getElementById("metric-emandamento");
        const bFeito = document.getElementById("metric-feito");
        const bTotal = document.getElementById("metric-total");
        if (bPendente) bPendente.innerText = pendente;
        if (bAndamento) bAndamento.innerText = andamento;
        if (bFeito) bFeito.innerText = feito;
        if (bTotal) bTotal.innerText = pendente + andamento + feito;

        if (window.chartDashboardInstance) {
            window.chartDashboardInstance.data.datasets[0].data = [pendente, andamento, feito];
            window.chartDashboardInstance.update();
        }
    } else {
        const bPendente = document.getElementById("metric-pendente-arq");
        const bAndamento = document.getElementById("metric-emandamento-arq");
        const bFeito = document.getElementById("metric-feito-arq");
        const bTotal = document.getElementById("metric-total-arq");
        if (bPendente) bPendente.innerText = pendente;
        if (bAndamento) bAndamento.innerText = andamento;
        if (bFeito) bFeito.innerText = feito;
        if (bTotal) bTotal.innerText = pendente + andamento + feito;

        if (window.chartArquivadosDashInstance) {
            window.chartArquivadosDashInstance.data.datasets[0].data = [pendente, andamento, feito];
            window.chartArquivadosDashInstance.update();
        }
    }
  }

  window.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('select.tag-select').forEach(ajustarCorSelect);
    document.querySelectorAll('select.prio-select').forEach(ajustarCorPrio);

    // Clique em links dentro dos editores abre em nova aba
    document.querySelectorAll('.editor-box, .editor-box-table').forEach(ed => {
      ed.addEventListener('click', e => {
        if (e.target.tagName === 'A') { e.preventDefault(); window.open(e.target.href, '_blank'); }
      });
    });

    if (document.getElementById('chartGeralDashboard')) {
      criarGraficoDashboardGlobal();
    }
  });

        const barValuePluginGlobal = {
    id: 'barValuePluginGlobal',
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      chart.data.datasets.forEach((dataset, datasetIndex) => {
        const meta = chart.getDatasetMeta(datasetIndex);
        if (meta.hidden) return;
        meta.data.forEach((datapoint, index) => {
          const value = dataset.data[index];
          if (value > 0) {
              const { x, y } = datapoint.tooltipPosition();
              ctx.font = 'bold 15px "Poppins", sans-serif';
              
              if (chart.options.indexAxis === 'y') {
                  ctx.fillStyle = dataset.backgroundColor;
                  ctx.textAlign = 'left';
                  ctx.textBaseline = 'middle';
                  ctx.fillText(` ${value}`, x + 5, y);
              } else {
                  ctx.fillStyle = Array.isArray(dataset.backgroundColor) ? dataset.backgroundColor[index] : dataset.backgroundColor;
                  ctx.textAlign = 'center';
                  ctx.textBaseline = 'bottom';
                  ctx.fillText(value, x, y - 5);
              }
          }
        });
      });
    }
  };
  function criarGraficoArquivadosDashboard() {
    const canvas = document.getElementById('chartArquivadosDashboard');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const pendente = parseInt(document.getElementById("metric-pendente-arq")?.innerText || canvas.dataset.pendentearq) || 0;
    const emAndamento = parseInt(document.getElementById("metric-emandamento-arq")?.innerText || canvas.dataset.emandamentoarq) || 0;
    const feito = parseInt(document.getElementById("metric-feito-arq")?.innerText || canvas.dataset.feitoarq) || 0;

    if (window.chartArquivadosDashInstance) window.chartArquivadosDashInstance.destroy();

    window.chartArquivadosDashInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: ['Pendentes', ['Em', 'andamento'], 'Concluídas'],
        datasets: [{
          label: 'Arquivadas',
          data: [pendente, emAndamento, feito],
          backgroundColor: ['#ff4757', '#1e90ff', '#2ed573'],
          borderWidth: 0, borderRadius: 8, barPercentage: 0.6, categoryPercentage: 0.7
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
            x: { ticks: { maxRotation: 0, minRotation: 0, font: { family: 'Poppins', size: 12, weight: 'bold' } }, grid: { display: false } },
            y: { beginAtZero: true, ticks: { display: true, precision: 0, font: { family: 'Poppins', size: 11 } }, grid: { display: true, color: 'rgba(150, 150, 150, 0.15)', drawBorder: false } }
        },
        layout: { padding: { top: 25, bottom: 10 } }
      },
      plugins: [barValuePluginGlobal]
    });
  }

  function criarGraficoDashboardGlobal() {
    const canvas = document.getElementById('chartGeralDashboard');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const pendente = parseInt(document.getElementById("metric-pendente")?.innerText || canvas.dataset.pendente) || 0;
    const emAndamento = parseInt(document.getElementById("metric-emandamento")?.innerText || canvas.dataset.emandamento) || 0;
    const feito = parseInt(document.getElementById("metric-feito")?.innerText || canvas.dataset.feito) || 0;

    if (window.chartDashboardInstance) window.chartDashboardInstance.destroy();

    window.chartDashboardInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: ['Pendentes', ['Em', 'andamento'], 'Concluídas'],
        datasets: [{
          label: 'Atividades',
          data: [pendente, emAndamento, feito],
          backgroundColor: ['#ff4757', '#1e90ff', '#2ed573'],
          borderWidth: 0,
          borderRadius: 8,
          barPercentage: 0.6, categoryPercentage: 0.7
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { display: false }
        },
        scales: {
            x: {
                ticks: { maxRotation: 0, minRotation: 0, font: { family: 'Poppins', size: 12, weight: 'bold' } },
                grid: { display: true, color: 'rgba(150, 150, 150, 0.15)', drawBorder: false }
            },
            y: {
                beginAtZero: true,
                ticks: { display: true, precision: 0, font: { family: 'Poppins', size: 11 } },
                grid: { display: true, color: 'rgba(150, 150, 150, 0.15)', drawBorder: false }
            }
        },
        layout: { padding: { top: 25, bottom: 10 } }
      },
      plugins: [{
        id: 'barValuePlugin',
        afterDatasetsDraw(chart) {
          const { ctx } = chart;
          chart.data.datasets.forEach((dataset, datasetIndex) => {
            const meta = chart.getDatasetMeta(datasetIndex);
            if (meta.hidden) return;
            meta.data.forEach((datapoint, index) => {
              const value = dataset.data[index];
              if (value > 0) {
                  const { x, y } = datapoint.tooltipPosition();
                  ctx.font = 'bold 16px "Poppins", sans-serif';
                  ctx.fillStyle = dataset.backgroundColor[index] || '#1e293b';
                  ctx.textAlign = 'center';
                  ctx.textBaseline = 'bottom';
                  ctx.fillText(value, x, y - 5);
              }
            });
          });
        }
      }]
    });
  }

  /* ── Dashboard — Abas e Gráficos ── */

  // Helper para ler as cores ativas do CSS (Claro ou Escuro)
  function getCoresTema() {
    const estilo = getComputedStyle(document.body);
    return {
      texto: estilo.getPropertyValue('--text-main').trim() || '#0f172a',
      mutado: estilo.getPropertyValue('--text-muted').trim() || '#64748b',
      grade: estilo.getPropertyValue('--border-color').trim() || '#e2e8f0'
    };
  }

  let abaAtivaGlobal = 'ativos';
  function mudarAbaDashboard(aba) {
    abaAtivaGlobal = aba;
    const dash_ativos = document.getElementById('dash-ativos');
    const dash_arquivados = document.getElementById('dash-arquivados');

    if (dash_ativos) dash_ativos.style.display = 'none';
    if (dash_arquivados) dash_arquivados.style.display = 'none';

    const aba_ativos = document.getElementById('aba-ativos');
    const aba_arquivados = document.getElementById('aba-arquivados');

    if (aba_ativos) aba_ativos.style.borderBottomColor = 'transparent';
    if (aba_arquivados) aba_arquivados.style.borderBottomColor = 'transparent';

    if (aba === 'ativos' && dash_ativos) {
      dash_ativos.style.display = 'block';
      if (aba_ativos) aba_ativos.style.borderBottomColor = 'var(--accent)';
      setTimeout(criarGraficoDashboardGlobal, 50);
    } else if (aba === 'arquivados' && dash_arquivados) {
      dash_arquivados.style.display = 'block';
      if (aba_arquivados) aba_arquivados.style.borderBottomColor = 'var(--accent)';
      setTimeout(criarGraficoArquivadosDashboard, 50);
    }
    
    // Call filter to recalculate counts for the active tab
    filtrarTabelaAvancado();
  }


  function criarGraficoAtivos() {
    const canvas = document.getElementById('chartAtivos');
    if (!canvas) return;
    if (chartAtivos) chartAtivos.destroy();

    const ctx = canvas.getContext('2d');
    const pendente = parseInt(canvas.dataset.pendente) || 0;
    const emAndamento = parseInt(canvas.dataset.emandamento) || 0;
    const feito = parseInt(canvas.dataset.feito) || 0;

    chartAtivos = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: ['Pendentes', ['Em', 'andamento'], 'Concluídas'],
        datasets: [{
          data: [pendente, emAndamento, feito],
          backgroundColor: ['#ff4757', '#1e90ff', '#2ed573'],
          borderRadius: 8, barPercentage: 0.6, categoryPercentage: 0.7
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { 
            x: { ticks: { maxRotation: 0, minRotation: 0, font: { family: 'Poppins', size: 12, weight: 'bold' } }, grid: { display: true, color: 'rgba(150, 150, 150, 0.15)', drawBorder: false } },
            y: { beginAtZero: true, ticks: { display: true, precision: 0, font: { family: 'Poppins', size: 11 } }, grid: { display: true, color: 'rgba(150, 150, 150, 0.15)', drawBorder: false } }
        },
        layout: { padding: { top: 25, bottom: 10 } }
      },
      plugins: [barValuePluginGlobal]
    });
  }

  function criarGraficoArquivados() {
    const canvas = document.getElementById('chartArquivados');
    if (!canvas) return;
    if (chartArquivados) chartArquivados.destroy();

    const ctx = canvas.getContext('2d');
    const pendente = parseInt(canvas.dataset.pendentearq) || 0;
    const emAndamento = parseInt(canvas.dataset.emandamentoarq) || 0;
    const feito = parseInt(canvas.dataset.feitoarq) || 0;

    chartArquivados = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: ['Pendentes', ['Em', 'andamento'], 'Concluídas'],
        datasets: [{
          data: [pendente, emAndamento, feito],
          backgroundColor: ['#ff4757', '#1e90ff', '#2ed573'],
          borderRadius: 8, barPercentage: 0.6, categoryPercentage: 0.7
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { 
            x: { ticks: { maxRotation: 0, minRotation: 0, font: { family: 'Poppins', size: 12, weight: 'bold' } }, grid: { display: true, color: 'rgba(150, 150, 150, 0.15)', drawBorder: false } },
            y: { beginAtZero: true, ticks: { display: true, precision: 0, font: { family: 'Poppins', size: 11 } }, grid: { display: true, color: 'rgba(150, 150, 150, 0.15)', drawBorder: false } }
        },
        layout: { padding: { top: 25, bottom: 10 } }
      },
      plugins: [barValuePluginGlobal]
    });
  }

  function criarGraficoGeral() {
    const canvas = document.getElementById('chartGeral');
    if (!canvas) return;
    if (chartGeral) chartGeral.destroy();

    const ctx = canvas.getContext('2d');
    const pendenteAtivos = parseInt(canvas.dataset.pendenteativos) || 0;
    const emAndamentoAtivos = parseInt(canvas.dataset.emandamentoativos) || 0;
    const feitoAtivos = parseInt(canvas.dataset.feitoativos) || 0;
    const pendenteArquivados = parseInt(canvas.dataset.pendentearquivados) || 0;
    const emAndamentoArquivados = parseInt(canvas.dataset.emandamentoarquivados) || 0;
    const feitoArquivados = parseInt(canvas.dataset.feitoarquivados) || 0;

    const dadosAtivos = [pendenteAtivos, emAndamentoAtivos, feitoAtivos];
    const dadosArquivados = [pendenteArquivados, emAndamentoArquivados, feitoArquivados];

    chartGeral = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: ['Pendentes', ['Em', 'andamento'], 'Concluídas'],
        datasets: [
          {
            label: 'Ativas',
            data: dadosAtivos,
            backgroundColor: '#1e90ff',
            borderRadius: 6,
            maxBarThickness: 45, barPercentage: 0.7, categoryPercentage: 0.8
          },
          {
            label: 'Arquivadas',
            data: dadosArquivados,
            backgroundColor: '#ff4757',
            borderRadius: 6,
            maxBarThickness: 45, barPercentage: 0.7, categoryPercentage: 0.8
          }
        ]
      },
      options: {
        indexAxis: 'x',
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { font: { family: 'Poppins' }, usePointStyle: true } } },
        scales: { 
            x: { ticks: { maxRotation: 0, minRotation: 0, font: { family: 'Poppins', size: 12, weight: 'bold' } }, grid: { display: true, color: 'rgba(150, 150, 150, 0.15)', drawBorder: false } },
            y: { beginAtZero: true, ticks: { display: true, precision: 0, font: { family: 'Poppins', size: 11 } }, grid: { display: true, color: 'rgba(150, 150, 150, 0.15)', drawBorder: false } }
        },
        layout: { padding: { top: 25, bottom: 10 } }
      },
      plugins: [barValuePluginGlobal]
    });
  }

  /* ── Sidebar Toggle ── */
  function toggleSidebar() {
    document.getElementById("sidebar").classList.toggle("fechada");
    document.getElementById("main-content").classList.toggle("expandido");
  }



  let atividadeAtualId = null;

  function adicionarCampoPasso() {
      const container = document.getElementById('lista-passos-form');
      const div = document.createElement('div');
      div.style.cssText = "display:flex; gap:5px; margin-bottom:5px;";
      div.innerHTML = `
        <input type="text" name="passos_desc[]" placeholder="Descrição do passo..." style="flex:2">
        <input type="date" name="passos_prazo[]" style="flex:1">
        <button type="button" onclick="this.parentElement.remove()" style="background:transparent; border:none; color:#ef4444; font-weight:bold; cursor:pointer;">X</button>
      `;
      container.appendChild(div);
  }

  function abrirModalPassos(id) {
      atividadeAtualId = id;
      document.getElementById('modalPassos').style.display = 'flex';
      carregarPassos();
  }

  function fecharModalPassos() {
      document.getElementById('modalPassos').style.display = 'none';
  }

  async function carregarPassos() {
      const resp = await fetch(`/api/atividades/${atividadeAtualId}/passos`);
      const passos = await resp.json();
      const container = document.getElementById('listaPassos');
      container.innerHTML = '';
      
      if (passos.length === 0) {
          container.innerHTML = '<p style="color:var(--text-muted); font-size:13px;">Nenhum passo cadastrado.</p>';
          return;
      }
      
      passos.forEach(p => {
          container.innerHTML += `
            <div style="display:flex; gap:10px; align-items:center; background:var(--table-even); padding:10px; border-radius:var(--radius-sm); border:1px solid var(--border-color);">
              <input type="checkbox" ${p.concluido ? 'checked' : ''} onchange="togglePasso(${p.id}, this.checked)" style="width:18px; height:18px; cursor:pointer;">
              <input type="text" value="${p.descricao}" onchange="atualizarPasso(${p.id}, 'descricao', this.value)" style="flex:2; border:none; background:transparent; ${p.concluido ? 'text-decoration:line-through; color:var(--text-muted);' : ''}">
              <input type="date" value="${p.prazo || ''}" onchange="atualizarPasso(${p.id}, 'prazo', this.value)" style="flex:1; border:none; background:transparent; font-size:12px;">
              <button onclick="excluirPasso(${p.id})" style="background:transparent; border:none; color:#ef4444; font-weight:bold; cursor:pointer;" title="Excluir">X</button>
            </div>
          `;
      });
  }

  async function togglePasso(id, checked) {
      const data = new FormData();
      data.append('concluido', checked);
      const resp = await fetch(`/api/passos/${id}/toggle`, { method: 'POST', body: data });
      const res = await resp.json();
      carregarPassos(); 
      
      if (res.novo_status_atividade) {
          const sel = document.querySelector(`select[data-campo="status"][data-id="${atividadeAtualId}"]`);
          if (sel) {
              sel.value = res.novo_status_atividade;
          }
      }
  }

  async function atualizarPasso(id, campo, valor) {
      const data = new FormData();
      data.append('campo', campo);
      data.append('valor', valor);
      await fetch(`/api/passos/${id}/atualizar`, { method: 'POST', body: data });
  }

  async function salvarNovoPasso() {
      const desc = document.getElementById('novoPassoDesc').value;
      const prazo = document.getElementById('novoPassoPrazo').value;
      if (!desc.trim()) return;
      
      const data = new FormData();
      data.append('atividade_id', atividadeAtualId);
      data.append('descricao', desc);
      data.append('prazo', prazo);
      
      await fetch('/api/passos/adicionar', { method: 'POST', body: data });
      document.getElementById('novoPassoDesc').value = '';
      document.getElementById('novoPassoPrazo').value = '';
      carregarPassos();
      
      // Se estava feito, volta pra andamento
      const sel = document.querySelector(`select[data-campo="status"][data-id="${atividadeAtualId}"]`);
      if (sel && sel.value === "Feito") {
          sel.value = "Em andamento";
          ajustarCorSelect(sel);
      }
  }

  async function excluirPasso(id) {
      if (!confirm("Excluir este passo?")) return;
      await fetch(`/api/passos/${id}/excluir`, { method: 'POST' });
      carregarPassos();
  }

  // AUTO-SAVE nas tabelas
  window.addEventListener('DOMContentLoaded', () => {
      document.querySelectorAll('.auto-save').forEach(el => {
          el.addEventListener('change', async function() {
              const id = this.getAttribute('data-id');
              const campo = this.getAttribute('data-campo');
              const valor = this.value;
              
              const data = new FormData();
              data.append('campo', campo);
              data.append('valor', valor);
              
              await fetch(`/api/atividades/${id}/atualizar`, { method: 'POST', body: data });
              
              // Se for o select de status ou prioridade, ajusta a cor
              if (this.tagName === 'SELECT' && this.classList.contains('tag-select')) ajustarCorSelect(this);
              if (this.tagName === 'SELECT' && this.classList.contains('prio-select')) ajustarCorPrio(this);
          });
      });
  });


  // --- PROCEDIMENTOS QUILL EDITOR ---
  let quill;
  
  window.addEventListener('DOMContentLoaded', () => {
    // Inicializa o Quill apenas se estiver na aba de procedimentos
    if (document.getElementById('quill-editor')) {
      quill = new Quill('#quill-editor', {
        theme: 'snow',
        placeholder: 'Escreva o conteúdo do procedimento aqui...',
        modules: {
          toolbar: [
            [{ 'header': [1, 2, 3, false] }],
            ['bold', 'italic', 'underline', 'strike'],
            [{ 'color': [] }, { 'background': [] }],
            [{ 'list': 'ordered'}, { 'list': 'bullet' }],
            [{ 'indent': '-1'}, { 'indent': '+1' }],
            [{ 'align': [] }],
            ['link', 'image', 'video'],
            ['clean']
          ]
        }
      });

      // Interceptar o submit do form para jogar o HTML do Quill no input escondido
      const formProc = document.getElementById('form-procedimento');
      if (formProc) {
        formProc.addEventListener('submit', function(e) {
          const htmlContent = quill.root.innerHTML;
          document.getElementById('proc-conteudo-input').value = htmlContent;
        });
      }
    }
  });

  function abrirModalProcedimento(id = null) {
    const modal = document.getElementById('modal-procedimento');
    const form = document.getElementById('form-procedimento');
    const titleText = document.getElementById('modal-proc-title-text');
    
    if (id) {
      // Editar existente
      titleText.innerText = "Editar Procedimento";
      form.action = `/procedimentos/editar/${id}`;
      
      document.getElementById('proc-titulo-input').value = document.getElementById(`proc-titulo-${id}`).value;
      document.getElementById('proc-categoria-input').value = document.getElementById(`proc-cat-${id}`).value;
      
      // Carregar HTML no Quill
      const htmlContent = document.getElementById(`proc-conteudo-${id}`).innerHTML;
      quill.clipboard.dangerouslyPasteHTML(0, htmlContent);
    } else {
      // Criar novo
      titleText.innerText = "Novo Procedimento";
      form.action = `/procedimentos/adicionar`;
      
      document.getElementById('proc-titulo-input').value = "";
      document.getElementById('proc-categoria-input').value = "Geral";
      quill.setContents([{ insert: '\n' }]); // Limpa o editor
    }
    
    modal.style.display = 'flex';
  }

  function fecharModalProcedimento() {
    document.getElementById('modal-procedimento').style.display = 'none';
  }

