/* ==========================================================================
   POSTMORTEM 2.0 ENTERPRISE FRONTEND CLIENT
   Interactive Controller for Overview, Investigations, Memory, Analytics, Reports
   ========================================================================== */

(function () {
  'use strict';

  // --- Global State ---
  const state = {
    currentIncident: null,
    currentPlan: null,
    incidents: [],
    outcomes: {}, // map of action_id -> { result, notes }
    services: [],
    analytics: null,
  };

  // --- DOM Elements ---
  const el = {
    sidebar: document.getElementById('sidebar'),
    collapseToggle: document.getElementById('collapse-toggle'),
    navItems: document.querySelectorAll('.nav-item'),
    viewPanels: document.querySelectorAll('.view-panel'),
    pageHeading: document.getElementById('page-heading'),
    themeBtn: document.getElementById('theme-btn'),
    toast: document.getElementById('toast-notification'),
    healthIndicator: document.getElementById('health-indicator'),
    
    // Overview
    kpiTotal: document.getElementById('kpi-total'),
    kpiOpen: document.getElementById('kpi-open'),
    kpiResolved: document.getElementById('kpi-resolved'),
    kpiMemory: document.getElementById('kpi-memory'),
    overviewRecentBody: document.getElementById('overview-recent-body'),
    btnQuickNew: document.getElementById('btn-quick-new'),

    // Investigation
    investigationForm: document.getElementById('investigation-form'),
    sampleSelect: document.getElementById('sample-select'),
    investigationPlaceholder: document.getElementById('investigation-placeholder'),
    investigationResultPanel: document.getElementById('investigation-result-panel'),
    resIncidentId: document.getElementById('res-incident-id'),
    resMemoryBadge: document.getElementById('res-memory-badge'),
    resRcaHypo: document.getElementById('res-rca-hypo'),
    resRcaExplanation: document.getElementById('res-rca-explanation'),
    resRcaConfidence: document.getElementById('res-rca-confidence'),
    resCat: document.getElementById('res-cat'),
    resAffectedSvcs: document.getElementById('res-affected-svcs'),
    resTimelineContainer: document.getElementById('res-timeline-container'),
    resActionsList: document.getElementById('res-actions-list'),
    resMemoriesCited: document.getElementById('res-memories-cited'),
    btnSaveOutcomes: document.getElementById('btn-save-outcomes'),
    outcomeSaveStatus: document.getElementById('outcome-save-status'),
    investigationSpinner: document.getElementById('investigation-spinner'),

    // Hub & Views
    incidentsHubBody: document.getElementById('incidents-hub-body'),
    incidentsSearch: document.getElementById('incidents-search'),
    memSearchInput: document.getElementById('mem-search-input'),
    btnMemSearch: document.getElementById('btn-mem-search'),
    btnMemSeed: document.getElementById('btn-mem-seed'),
    btnMemReset: document.getElementById('btn-mem-reset'),
    memCardsContainer: document.getElementById('mem-cards-container'),
    memStatusLine: document.getElementById('mem-status-line'),
    patternsList: document.getElementById('patterns-list'),
    serviceGraphContainer: document.getElementById('service-graph-container'),
    analyticsKpis: document.getElementById('analytics-kpis'),
    analyticsSeverityList: document.getElementById('analytics-severity-list'),
    analyticsCategoryList: document.getElementById('analytics-category-list'),
    reportsTableBody: document.getElementById('reports-table-body'),
  };

  // --- Utilities ---
  function showToast(message, type = 'info') {
    el.toast.textContent = message;
    el.toast.className = 'toast show';
    setTimeout(() => {
      el.toast.className = 'toast';
    }, 3500);
  }

  async function api(path, options = {}) {
    try {
      const res = await fetch(path, {
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        ...options,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || `Request failed with status ${res.status}`);
      }
      return data;
    } catch (err) {
      console.error(`API Error on ${path}:`, err);
      throw err;
    }
  }

  // --- Navigation & Routing ---
  function switchView(viewName) {
    const panels = document.querySelectorAll('.view-panel');
    const navItems = document.querySelectorAll('.nav-item');

    navItems.forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.view === viewName);
    });

    panels.forEach((panel) => {
      panel.classList.toggle('hidden', panel.id !== `view-${viewName}`);
    });

    const titles = {
      overview: 'Executive Incident Overview',
      investigation: 'New AI Incident Investigation',
      incidents: 'Incidents Management Hub',
      memory: 'Hindsight Long-Term Memory Bank',
      patterns: 'Recurring Pattern Intelligence',
      services: 'Service Topology & Blast Radius',
      analytics: 'Incident Resolution Analytics',
      reports: 'Postmortem Incident Reports',
    };
    el.pageHeading.textContent = titles[viewName] || 'Incident Intelligence';

    // Lazy load content
    if (viewName === 'overview') loadOverview();
    if (viewName === 'incidents') loadIncidentsHub();
    if (viewName === 'memory') loadMemories();
    if (viewName === 'patterns') loadPatterns();
    if (viewName === 'services') loadServices();
    if (viewName === 'analytics') loadAnalytics();
    if (viewName === 'reports') loadReports();
  }

  // --- Initialization ---
  async function init() {
    // Check Health
    try {
      const health = await api('/api/health');
      if (health.hindsight && health.hindsight.ok) {
        el.healthIndicator.innerHTML = `<span class="dot"></span> Online (v${health.hindsight.version || '1.0'})`;
      } else {
        el.healthIndicator.innerHTML = `<span class="dot warn"></span> Memory Degraded`;
      }
    } catch {
      el.healthIndicator.innerHTML = `<span class="dot err"></span> Offline`;
    }

    // Load Samples
    try {
      const samples = await api('/api/samples');
      samples.forEach((sample, index) => {
        const opt = document.createElement('option');
        opt.value = index;
        opt.textContent = `${sample.service}: ${sample.title}`;
        opt.dataset.sample = JSON.stringify(sample);
        el.sampleSelect.appendChild(opt);
      });
    } catch (err) {
      console.warn('Could not load samples', err);
    }

    // Custom Dropdown Transformer: enhances all native selects with the Logo Palette
    initCustomDropdowns();
    initSplitResizer();
    initSidebarResizer();
  }

  // --- Draggable Main Navigation Sidebar ---
  function initSidebarResizer() {
    const sResizer = document.getElementById('sidebar-resizer');
    const sidebar = el.sidebar;
    if (!sResizer || !sidebar) return;

    let isSidebarDragging = false;

    sResizer.addEventListener('mousedown', (e) => {
      isSidebarDragging = true;
      sResizer.classList.add('dragging');
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', (e) => {
      if (!isSidebarDragging) return;
      let newWidth = e.clientX;
      if (newWidth < 70) newWidth = 70;
      if (newWidth > 450) newWidth = 450;
      sidebar.style.width = `${newWidth}px`;
      sidebar.classList.toggle('collapsed', newWidth <= 90);
    });

    document.addEventListener('mouseup', () => {
      if (isSidebarDragging) {
        isSidebarDragging = false;
        sResizer.classList.remove('dragging');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    });
  }

  // --- Draggable Adjustable Workspace Splitter ---
  function initSplitResizer() {
    const resizer = document.getElementById('copilot-resizer');
    const leftPane = document.getElementById('copilot-left-pane');
    if (!resizer || !leftPane) return;

    let isDragging = false;

    resizer.addEventListener('mousedown', (e) => {
      isDragging = true;
      resizer.classList.add('dragging');
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      const sidebarWidth = el.sidebar && !el.sidebar.classList.contains('collapsed') ? 230 : 66;
      let newWidth = e.clientX - sidebarWidth;
      if (newWidth < 300) newWidth = 300;
      if (newWidth > window.innerWidth * 0.7) newWidth = window.innerWidth * 0.7;
      leftPane.style.width = `${newWidth}px`;
    });

    document.addEventListener('mouseup', () => {
      if (isDragging) {
        isDragging = false;
        resizer.classList.remove('dragging');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    });
  }

  function initCustomDropdowns() {
    document.querySelectorAll('select').forEach((nativeSelect) => {
      if (nativeSelect.dataset.customized === 'true') return;
      nativeSelect.dataset.customized = 'true';
      nativeSelect.style.display = 'none';

      const wrapper = document.createElement('div');
      wrapper.className = 'custom-select-wrapper';
      if (nativeSelect.style.width) {
        wrapper.style.width = nativeSelect.style.width;
      }
      if (nativeSelect.style.maxWidth) {
        wrapper.style.maxWidth = nativeSelect.style.maxWidth;
      }

      const trigger = document.createElement('div');
      trigger.className = 'custom-select-trigger';
      const selectedOption = nativeSelect.selectedOptions[0] || nativeSelect.options[0];
      trigger.innerHTML = `<span>${selectedOption ? selectedOption.text : 'Select'}</span><span class="custom-select-arrow"></span>`;

      const optionsContainer = document.createElement('div');
      optionsContainer.className = 'custom-select-options';

      function syncOptions() {
        optionsContainer.innerHTML = '';
        Array.from(nativeSelect.options).forEach((opt) => {
          const optDiv = document.createElement('div');
          optDiv.className = `custom-option ${opt.selected ? 'selected' : ''}`;
          optDiv.textContent = opt.text;
          optDiv.dataset.value = opt.value;

          optDiv.addEventListener('click', (e) => {
            e.stopPropagation();
            nativeSelect.value = opt.value;
            trigger.querySelector('span').textContent = opt.text;
            optionsContainer.querySelectorAll('.custom-option').forEach(o => o.classList.remove('selected'));
            optDiv.classList.add('selected');
            wrapper.classList.remove('open');
            nativeSelect.dispatchEvent(new Event('change', { bubbles: true }));
          });

          optionsContainer.appendChild(optDiv);
        });
      }

      syncOptions();

      // Observer to re-sync when options are dynamically added (e.g., sample incidents)
      const observer = new MutationObserver(() => {
        syncOptions();
        const cur = nativeSelect.selectedOptions[0] || nativeSelect.options[0];
        if (cur) trigger.querySelector('span').textContent = cur.text;
      });
      observer.observe(nativeSelect, { childList: true, subtree: true });

      trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = wrapper.classList.contains('open');
        document.querySelectorAll('.custom-select-wrapper').forEach(w => w.classList.remove('open'));
        if (!isOpen) wrapper.classList.add('open');
      });

      wrapper.appendChild(trigger);
      wrapper.appendChild(optionsContainer);
      nativeSelect.parentNode.insertBefore(wrapper, nativeSelect.nextSibling);
    });

    document.addEventListener('click', () => {
      document.querySelectorAll('.custom-select-wrapper').forEach(w => w.classList.remove('open'));
    });
    el.collapseToggle.addEventListener('click', () => {
      el.sidebar.classList.toggle('collapsed');
    });

    el.navItems.forEach((btn) => {
      btn.addEventListener('click', () => switchView(btn.dataset.view));
    });

    // Subtab Navigation inside Results Pane
    document.querySelectorAll('.subtab-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.subtab-btn').forEach((b) => b.classList.remove('active'));
        document.querySelectorAll('.subtab-content').forEach((c) => c.classList.add('hidden'));
        btn.classList.add('active');
        const target = document.getElementById(`subtab-content-${btn.dataset.subtab}`);
        if (target) target.classList.remove('hidden');
      });
    });

    el.btnQuickNew.addEventListener('click', () => {
      clearInvestigationForm();
      switchView('investigation');
    });

    const btnTopbarNew = document.getElementById('btn-topbar-new');
    if (btnTopbarNew) {
      btnTopbarNew.addEventListener('click', () => {
        clearInvestigationForm();
        switchView('investigation');
      });
    }

    const btnClearForm = document.getElementById('btn-clear-form');
    if (btnClearForm) {
      btnClearForm.addEventListener('click', clearInvestigationForm);
    }

    el.themeBtn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme');
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      el.themeBtn.textContent = next === 'dark' ? '🌙 Dark' : '☀️ Light';
    });

    el.sampleSelect.addEventListener('change', (e) => {
      const opt = e.target.selectedOptions[0];
      if (!opt || !opt.dataset.sample) return;
      const s = JSON.parse(opt.dataset.sample);
      document.getElementById('inp-title').value = s.title || '';
      document.getElementById('inp-service').value = s.service || '';
      document.getElementById('inp-desc').value = s.description || '';
      document.getElementById('inp-symptoms').value = s.symptoms || '';
      document.getElementById('inp-logs').value = s.logs || '';
    });

    el.investigationForm.addEventListener('submit', runInvestigation);
    el.btnSaveOutcomes.addEventListener('click', saveOutcomes);

    el.btnMemSearch.addEventListener('click', () => loadMemories(el.memSearchInput.value));
    el.btnMemSeed.addEventListener('click', seedMemories);
    el.btnMemReset.addEventListener('click', resetMemories);

    // Incidents Hub Sorting & Filtering
    document.querySelectorAll('#incidents-table th.sortable').forEach((th) => {
      th.addEventListener('click', () => {
        const field = th.dataset.sort;
        if (incidentsSort.field === field) {
          incidentsSort.dir = incidentsSort.dir === 'asc' ? 'desc' : 'asc';
        } else {
          incidentsSort.field = field;
          incidentsSort.dir = field === 'created' ? 'desc' : 'asc';
        }
        applyIncidentsFilterAndSort();
      });
    });

    const sInput = document.getElementById('incidents-search-input');
    if (sInput) sInput.addEventListener('input', applyIncidentsFilterAndSort);
    const sevFilter = document.getElementById('incidents-severity-filter');
    if (sevFilter) sevFilter.addEventListener('change', applyIncidentsFilterAndSort);
    const statFilter = document.getElementById('incidents-status-filter');
    if (statFilter) statFilter.addEventListener('change', applyIncidentsFilterAndSort);

    // Initial View
    loadOverview();
  }

  function clearInvestigationForm() {
    document.getElementById('inp-title').value = '';
    document.getElementById('inp-service').value = '';
    document.getElementById('inp-desc').value = '';
    document.getElementById('inp-symptoms').value = '';
    document.getElementById('inp-logs').value = '';
    el.sampleSelect.value = '';
    el.investigationPlaceholder.classList.remove('hidden');
    el.investigationResultPanel.classList.add('hidden');
    document.getElementById('inp-title').focus();
  }

  window.switchToNewProblem = function() {
    clearInvestigationForm();
    switchView('investigation');
  };
  async function loadOverview() {
    try {
      const [analytics, incidents] = await Promise.all([
        api('/api/analytics'),
        api('/api/incidents?limit=5'),
      ]);

      el.kpiTotal.textContent = analytics.total_incidents;
      el.kpiOpen.textContent = analytics.open_incidents;
      el.kpiResolved.textContent = analytics.resolved_incidents;
      el.kpiMemory.textContent = analytics.memory_assisted_count;

      if (!incidents.length) {
        el.overviewRecentBody.innerHTML = `<tr><td colspan="7" class="text-muted" style="text-align:center;">No incidents recorded yet.</td></tr>`;
        return;
      }

      el.overviewRecentBody.innerHTML = incidents
        .map(
          (inc) => `
        <tr>
          <td class="cell-nowrap"><strong>${inc.id}</strong></td>
          <td>${escapeHtml(inc.title)}</td>
          <td class="cell-nowrap"><code>${escapeHtml(inc.service)}</code></td>
          <td class="cell-nowrap"><span class="badge badge-${(inc.severity || 'high').toLowerCase()}">${inc.severity || 'high'}</span></td>
          <td class="cell-nowrap"><span class="badge ${inc.status === 'Resolved' ? 'badge-success' : 'badge-warning'}">${inc.status}</span></td>
          <td class="cell-date">${(inc.created_at || '').slice(0, 16).replace('T', ' ')}</td>
          <td class="cell-nowrap"><button class="btn btn-secondary btn-sm" onclick="window.viewIncidentDetail('${inc.id}')">Inspect</button></td>
        </tr>
      `
        )
        .join('');
    } catch (err) {
      showToast('Failed to load overview data', 'error');
    }
  }

  // --- View: Run Investigation ---
  async function runInvestigation(e) {
    e.preventDefault();
    el.investigationSpinner.classList.remove('hidden');

    const payload = {
      title: document.getElementById('inp-title').value.trim(),
      service: document.getElementById('inp-service').value.trim(),
      environment: document.getElementById('inp-env').value,
      severity: document.getElementById('inp-severity').value,
      category: document.getElementById('inp-category').value || null,
      description: document.getElementById('inp-desc').value.trim(),
      symptoms: document.getElementById('inp-symptoms').value.trim(),
      logs: document.getElementById('inp-logs').value.trim(),
      use_memory: document.getElementById('inp-use-memory').checked,
    };

    try {
      const res = await api('/api/incidents', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      state.currentIncident = res.incident_id;
      state.currentPlan = res.plan;
      state.outcomes = {};

      renderInvestigationResult(res.incident_id, res.plan);
      showToast(`Investigation ${res.incident_id} generated!`);
    } catch (err) {
      showToast(`Investigation failed: ${err.message}`, 'error');
    } finally {
      el.investigationSpinner.classList.add('hidden');
    }
  }

  function renderInvestigationResult(incidentId, plan) {
    el.investigationPlaceholder.classList.add('hidden');
    el.investigationResultPanel.classList.remove('hidden');

    el.resIncidentId.textContent = incidentId;
    
    // Status Badge
    const badgeMap = {
      used: { label: 'Memory Used', cls: 'badge-success' },
      empty: { label: 'Cold Start (No Memory)', cls: 'badge-medium' },
      disabled: { label: 'Memory Disabled', cls: 'badge-warning' },
      unavailable: { label: 'Memory Offline', cls: 'badge-danger' },
    };
    const b = badgeMap[plan.memory_status] || { label: plan.memory_status, cls: 'badge-medium' };
    el.resMemoryBadge.textContent = b.label;
    el.resMemoryBadge.className = `badge ${b.cls}`;

    // RCA
    if (plan.rca) {
      el.resRcaHypo.textContent = plan.rca.primary_hypothesis;
      el.resRcaExplanation.textContent = plan.rca.confidence_explanation;
      el.resRcaConfidence.textContent = plan.rca.confidence.toUpperCase();
      el.resRcaConfidence.className = `badge ${plan.rca.confidence === 'confirmed' ? 'badge-success' : 'badge-high'}`;
    } else {
      el.resRcaHypo.textContent = plan.summary;
      el.resRcaExplanation.textContent = 'Standard heuristic plan.';
      el.resRcaConfidence.textContent = 'UNVERIFIED';
    }

    el.resCat.textContent = (plan.incident_category || 'Application').toUpperCase();
    el.resAffectedSvcs.textContent = (plan.affected_services || []).join(', ') || 'None reported';

    // Update Memory Count Pill
    const memCountEl = document.getElementById('res-mem-count');
    if (memCountEl) {
      memCountEl.textContent = (plan.memories || []).length;
    }

    // RCA Contributing Factors
    const factorsEl = document.getElementById('res-rca-factors');
    if (factorsEl && plan.rca) {
      const factors = (plan.rca.contributing_factors || []).map(f => `<li>${escapeHtml(f)}</li>`).join('');
      factorsEl.innerHTML = factors ? `<ul style="padding-left: 18px; margin-top: 6px;">${factors}</ul>` : 'No distinct secondary factors noted.';
    }

    // Default to Actions subtab
    const defaultSubtab = document.querySelector('.subtab-btn[data-subtab="actions"]');
    if (defaultSubtab) defaultSubtab.click();

    // Timeline
    el.resTimelineContainer.innerHTML = (plan.timeline || [])
      .map(
        (t) => `
      <div class="timeline-item">
        <div class="timeline-dot"></div>
        <div class="timeline-time">${t.timestamp} [${t.phase.toUpperCase()}]</div>
        <div class="timeline-content"><strong>${escapeHtml(t.title)}:</strong> ${escapeHtml(t.details)}</div>
      </div>
    `
      )
      .join('');

    // Actions
    el.resActionsList.innerHTML = (plan.actions || [])
      .map(
        (a) => `
      <div class="action-item" id="action-box-${a.id}">
        <div class="action-header">
          <div>
            <span class="badge badge-${a.risk}">${a.risk} Risk</span>
            <span class="action-title" style="margin-left: 8px;">${a.priority}. ${escapeHtml(a.title)}</span>
          </div>
          <span style="font-size: 0.78rem; color: var(--text-muted);">Est. ${a.estimated_minutes}m</span>
        </div>

        <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 6px;">${escapeHtml(a.explanation || a.rationale)}</p>

        ${
          a.rank_reason
            ? `<div style="font-size: 0.8rem; color: var(--success); margin-bottom: 6px;"><strong>⚡ Memory Effect:</strong> ${escapeHtml(a.rank_reason)}</div>`
            : ''
        }

        ${
          a.warning
            ? `<div style="font-size: 0.8rem; color: var(--danger); margin-bottom: 6px;"><strong>⚠️ Warning:</strong> ${escapeHtml(a.warning)}</div>`
            : ''
        }

        ${
          a.suggested_command
            ? `<div class="action-command"><code>${escapeHtml(a.suggested_command)}</code></div>`
            : ''
        }

        <div class="outcome-selector">
          <button type="button" class="outcome-btn" data-act="${a.id}" data-res="worked" onclick="window.setOutcome('${a.id}', 'worked')">Worked</button>
          <button type="button" class="outcome-btn" data-act="${a.id}" data-res="failed" onclick="window.setOutcome('${a.id}', 'failed')">Failed</button>
          <button type="button" class="outcome-btn" data-act="${a.id}" data-res="blocked" onclick="window.setOutcome('${a.id}', 'blocked')">Blocked</button>
          <button type="button" class="outcome-btn selected-not_tried" data-act="${a.id}" data-res="not_tried" onclick="window.setOutcome('${a.id}', 'not_tried')">Not Tried</button>
          <input type="text" id="notes-${a.id}" placeholder="Engineer resolution notes (optional)..." style="flex: 1; padding: 4px 10px; font-size: 0.8rem;" oninput="window.setNotes('${a.id}', this.value)">
        </div>
      </div>
    `
      )
      .join('');

    // Memories Cited
    if (!plan.memories || !plan.memories.length) {
      el.resMemoriesCited.innerHTML = `<p class="text-muted" style="font-size: 0.85rem;">No historical memories cited for this investigation (cold start).</p>`;
    } else {
      el.resMemoriesCited.innerHTML = plan.memories
        .map(
          (m) => `
        <div style="background: var(--bg-card); border: 1px solid var(--border); border-left: 3px solid var(--ice-cyan); border-radius: 6px; padding: 12px; margin-bottom: 10px;">
          <div style="display: flex; justify-content: space-between; font-size: 0.82rem; margin-bottom: 6px;">
            <strong style="color: var(--ice-cyan); font-family: var(--font-mono);">${m.ref}</strong>
            <span class="badge ${m.outcome === 'worked' ? 'badge-success' : 'badge-danger'}">${m.outcome ? m.outcome.toUpperCase() : 'RECALLED'}</span>
          </div>
          <p style="font-size: 0.86rem; color: var(--text-ivory); line-height: 1.5;">${escapeHtml(m.text)}</p>
        </div>
      `
        )
        .join('');
    }
  }

  window.setOutcome = function (actionId, result) {
    state.outcomes[actionId] = state.outcomes[actionId] || { action_id: actionId, result: 'not_tried', notes: '' };
    state.outcomes[actionId].result = result;

    const box = document.getElementById(`action-box-${actionId}`);
    if (box) {
      box.querySelectorAll('.outcome-btn').forEach((b) => {
        b.className = 'outcome-btn';
        if (b.dataset.res === result) {
          b.classList.add(`selected-${result}`);
        }
      });
    }
  };

  window.setNotes = function (actionId, notes) {
    state.outcomes[actionId] = state.outcomes[actionId] || { action_id: actionId, result: 'not_tried', notes: '' };
    state.outcomes[actionId].notes = notes.trim();
  };

  async function saveOutcomes() {
    if (!state.currentIncident) return;
    const list = Object.values(state.outcomes);
    if (!list.length) {
      showToast('Select an outcome for at least one action before saving.', 'warning');
      return;
    }

    try {
      el.outcomeSaveStatus.textContent = 'Retaining outcomes in Hindsight…';
      const res = await api(`/api/incidents/${state.currentIncident}/outcomes`, {
        method: 'POST',
        body: JSON.stringify({ outcomes: list }),
      });

      el.outcomeSaveStatus.textContent = `Saved ${res.saved}. Retained ${res.retained_in_hindsight} in Hindsight.`;
      showToast('Outcomes committed to long-term memory!');
    } catch (err) {
      el.outcomeSaveStatus.textContent = `Error: ${err.message}`;
      showToast(`Save error: ${err.message}`, 'error');
    }
  }

  // --- View: Incidents Hub ---
  let incidentsSort = { field: 'created', dir: 'desc' };

  async function loadIncidentsHub() {
    try {
      const incidents = await api('/api/incidents?limit=100');
      state.incidents = incidents;
      applyIncidentsFilterAndSort();
    } catch (err) {
      showToast('Failed to load incidents', 'error');
    }
  }

  function applyIncidentsFilterAndSort() {
    if (!state.incidents) return;
    const searchVal = (document.getElementById('incidents-search-input')?.value || '').trim().toLowerCase();
    const severityVal = (document.getElementById('incidents-severity-filter')?.value || 'ALL').toUpperCase();
    const statusVal = (document.getElementById('incidents-status-filter')?.value || 'ALL').toUpperCase();

    let filtered = state.incidents.filter((inc) => {
      if (severityVal !== 'ALL' && (inc.severity || '').toUpperCase() !== severityVal) return false;
      if (statusVal !== 'ALL' && (inc.status || '').toUpperCase() !== statusVal) return false;
      if (searchVal) {
        const hay = `${inc.id || ''} ${inc.title || ''} ${inc.service || ''} ${inc.category || ''}`.toLowerCase();
        if (!hay.includes(searchVal)) return false;
      }
      return true;
    });

    const sevRank = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 };
    filtered.sort((a, b) => {
      let vA, vB;
      if (incidentsSort.field === 'id') {
        const numA = parseInt((a.id || '').replace(/\D/g, ''), 10) || 0;
        const numB = parseInt((b.id || '').replace(/\D/g, ''), 10) || 0;
        vA = numA; vB = numB;
      } else if (incidentsSort.field === 'severity') {
        vA = sevRank[(a.severity || '').toUpperCase()] || 0;
        vB = sevRank[(b.severity || '').toUpperCase()] || 0;
      } else if (incidentsSort.field === 'created') {
        vA = new Date(a.created_at || 0).getTime();
        vB = new Date(b.created_at || 0).getTime();
      } else if (incidentsSort.field === 'status') {
        vA = (a.status || '').toLowerCase();
        vB = (b.status || '').toLowerCase();
      } else if (incidentsSort.field === 'service') {
        vA = (a.service || '').toLowerCase();
        vB = (b.service || '').toLowerCase();
      } else if (incidentsSort.field === 'category') {
        vA = (a.category || '').toLowerCase();
        vB = (b.category || '').toLowerCase();
      } else {
        vA = (a.title || '').toLowerCase();
        vB = (b.title || '').toLowerCase();
      }

      if (vA < vB) return incidentsSort.dir === 'asc' ? -1 : 1;
      if (vA > vB) return incidentsSort.dir === 'asc' ? 1 : -1;
      return 0;
    });

    // Update sort header icons
    document.querySelectorAll('#incidents-table th.sortable').forEach((th) => {
      const field = th.dataset.sort;
      const icon = th.querySelector('.sort-icon');
      th.classList.remove('sorted-asc', 'sorted-desc');
      if (field === incidentsSort.field) {
        th.classList.add(incidentsSort.dir === 'asc' ? 'sorted-asc' : 'sorted-desc');
        if (icon) icon.textContent = incidentsSort.dir === 'asc' ? '▲' : '▼';
      } else {
        if (icon) icon.textContent = '↕';
      }
    });

    const badge = document.getElementById('incidents-count-badge');
    if (badge) {
      badge.textContent = `${filtered.length} of ${state.incidents.length} incidents`;
    }

    renderIncidentsTable(filtered);
  }

  function renderIncidentsTable(list) {
    if (!list.length) {
      el.incidentsHubBody.innerHTML = `<tr><td colspan="8" class="text-muted" style="text-align: center; padding: 24px;">No matching incidents found.</td></tr>`;
      return;
    }
    el.incidentsHubBody.innerHTML = list
      .map(
        (i) => `
      <tr>
        <td class="cell-nowrap"><strong>${i.id}</strong></td>
        <td>${escapeHtml(i.title)}</td>
        <td class="cell-nowrap"><code>${escapeHtml(i.service)}</code></td>
        <td class="cell-nowrap"><span class="badge badge-${(i.severity || 'high').toLowerCase()}">${i.severity}</span></td>
        <td class="cell-nowrap"><span class="badge">${i.category}</span></td>
        <td class="cell-nowrap"><span class="badge ${i.status === 'Resolved' ? 'badge-success' : 'badge-warning'}">${i.status}</span></td>
        <td class="cell-date">${(i.created_at || '').slice(0, 16).replace('T', ' ')}</td>
        <td class="cell-nowrap" style="text-align: right;">
          <button class="btn btn-secondary btn-sm" onclick="window.viewIncidentDetail('${i.id}')">Inspect</button>
        </td>
      </tr>
    `
      )
      .join('');
  }

  window.viewIncidentDetail = async function (incidentId) {
    try {
      const inc = await api(`/api/incidents/${incidentId}`);
      state.currentIncident = inc.id;
      state.currentPlan = inc.plan;
      switchView('investigation');
      renderInvestigationResult(inc.id, inc.plan);
    } catch (err) {
      showToast(`Could not load incident ${incidentId}`, 'error');
    }
  };

  // --- View: Memory Inspector ---
  async function loadMemories(query = '') {
    try {
      const qParam = query ? `?q=${encodeURIComponent(query)}` : '';
      const res = await api(`/api/memories${qParam}`);
      el.memStatusLine.textContent = `Total memories in bank: ${res.total || 0}`;

      if (!res.items || !res.items.length) {
        el.memCardsContainer.innerHTML = `<div class="card" style="text-align:center; color: var(--text-muted);">No memories found matching query.</div>`;
        return;
      }

      el.memCardsContainer.innerHTML = res.items
        .map((m) => {
          const outcomeTag = (m.tags || []).find((t) => t.startsWith('result:'));
          const outcome = outcomeTag ? outcomeTag.split(':')[1] : null;
          return `
          <div class="card" style="margin-bottom: 0; padding: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <code style="color: var(--accent);">${m.id}</code>
              <div style="display: flex; gap: 6px;">
                ${outcome ? `<span class="badge ${outcome === 'worked' ? 'badge-success' : 'badge-danger'}">${outcome.toUpperCase()}</span>` : ''}
                <span class="badge">${m.fact_type || 'memory'}</span>
              </div>
            </div>
            <p style="font-size: 0.9rem; line-height: 1.5;">${escapeHtml(m.text)}</p>
            <div style="margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap;">
              ${(m.tags || []).map((t) => `<span class="badge" style="font-size: 0.7rem; background: var(--border);">${escapeHtml(t)}</span>`).join('')}
            </div>
          </div>
        `;
        })
        .join('');
    } catch (err) {
      showToast('Failed to load memory bank', 'error');
    }
  }

  async function seedMemories() {
    try {
      const res = await api('/api/memory/seed', { method: 'POST' });
      showToast(`Seeded ${res.retained_items} historical items into Hindsight!`);
      loadMemories();
    } catch (err) {
      showToast(`Seed failed: ${err.message}`, 'error');
    }
  }

  async function resetMemories() {
    const ok = confirm('Type RESET to confirm deleting the memory bank?');
    if (!ok) return;
    try {
      await api('/api/memory/reset', { method: 'POST', body: JSON.stringify({ confirm: 'RESET' }) });
      showToast('Memory bank reset completely.');
      loadMemories();
    } catch (err) {
      showToast(`Reset error: ${err.message}`, 'error');
    }
  }

  // --- View: Recurring Patterns ---
  async function loadPatterns() {
    try {
      const patterns = await api('/api/patterns');
      if (!patterns.length) {
        el.patternsList.innerHTML = `<div class="card" style="text-align: center; color: var(--text-muted);">No recurring patterns detected yet. Correlates automatically across multiple incidents.</div>`;
        return;
      }
      el.patternsList.innerHTML = patterns
        .map(
          (p) => `
        <div class="card" style="margin-bottom: 0;">
          <div class="card-header">
            <h4 class="card-title" style="color: var(--warning);">${p.title}</h4>
            <span class="badge badge-high">${p.occurrences_count} Occurrences</span>
          </div>
          <p style="font-size: 0.88rem; margin-bottom: 8px;"><strong>Pattern Summary:</strong> ${escapeHtml(p.underlying_pattern)}</p>
          <div style="font-size: 0.82rem; color: var(--text-secondary); margin-bottom: 6px;">
            <strong>Most Proven Resolution:</strong> <span style="color: var(--success); font-weight: 600;">${escapeHtml(p.most_successful_resolution)}</span>
          </div>
          <div style="font-size: 0.78rem; color: var(--text-muted);">
            Observed across services: <code>${p.affected_services.join(', ')}</code> (From ${p.first_seen.slice(0, 10)} to ${p.last_seen.slice(0, 10)})
          </div>
        </div>
      `
        )
        .join('');
    } catch (err) {
      showToast('Failed to load patterns', 'error');
    }
  }

  // --- View: Service Topology ---
  async function loadServices() {
    try {
      const res = await api('/api/services');
      el.serviceGraphContainer.innerHTML = (res.services || [])
        .map(
          (s) => `
        <div class="service-card ${s.health}">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <strong>${s.name}</strong>
            <span class="badge ${s.health === 'healthy' ? 'badge-success' : 'badge-danger'}">${s.health.toUpperCase()}</span>
          </div>
          <span style="font-size: 0.75rem; color: var(--text-muted);">Tier ${s.tier} • ${s.category}</span>
          <div style="font-size: 0.75rem; margin-top: 4px;">
            ${s.dependencies.length ? `Depends on: <code>${s.dependencies.join(', ')}</code>` : '<span class="text-muted">Root entity</span>'}
          </div>
        </div>
      `
        )
        .join('');
    } catch (err) {
      showToast('Failed to load topology', 'error');
    }
  }

  // --- View: Analytics ---
  async function loadAnalytics() {
    try {
      const data = await api('/api/analytics');
      el.analyticsKpis.innerHTML = `
        <div class="kpi-card">
          <span class="kpi-label">Total Incidents</span>
          <span class="kpi-value">${data.total_incidents}</span>
          <span class="kpi-meta">All tracked services</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Avg Resolution</span>
          <span class="kpi-value">${data.average_resolution_minutes}m</span>
          <span class="kpi-meta">Mean time to resolve</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Successful Fixes</span>
          <span class="kpi-value" style="color: var(--success);">${data.successful_resolutions_count}</span>
          <span class="kpi-meta">Permanent fixes applied</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Failed Attempts</span>
          <span class="kpi-value" style="color: var(--danger);">${data.failed_attempts_count}</span>
          <span class="kpi-meta">Learned negative paths</span>
        </div>
      `;

      el.analyticsSeverityList.innerHTML = Object.entries(data.severity_distribution || {})
        .map(
          ([k, v]) => `
        <div style="display:flex; justify-content:space-between; align-items:center; padding: 12px 0; border-bottom: 1px solid var(--border);">
          <span class="badge badge-${k}">${k.toUpperCase()}</span>
          <strong style="font-family: var(--font-mono); font-size: 1.1rem; color: var(--text-primary);">${v}</strong>
        </div>
      `
        )
        .join('');

      el.analyticsCategoryList.innerHTML = Object.entries(data.category_distribution || {})
        .map(
          ([k, v]) => `
        <div style="display:flex; justify-content:space-between; align-items:center; padding: 12px 0; border-bottom: 1px solid var(--border);">
          <span style="font-weight: 600; color: var(--text-secondary);">${k.toUpperCase()}</span>
          <strong style="font-family: var(--font-mono); font-size: 1.1rem; color: var(--text-primary);">${v}</strong>
        </div>
      `
        )
        .join('');
    } catch (err) {
      showToast('Failed to load analytics', 'error');
    }
  }

  // --- View: Reports ---
  async function loadReports() {
    try {
      const incidents = await api('/api/incidents?limit=50');
      if (!incidents.length) {
        el.reportsTableBody.innerHTML = `<tr><td colspan="4" class="text-muted" style="text-align:center;">No incidents to generate reports for.</td></tr>`;
        return;
      }
      el.reportsTableBody.innerHTML = incidents
        .map(
          (i) => `
        <tr>
          <td class="cell-nowrap"><strong>${i.id}</strong></td>
          <td>${escapeHtml(i.title)}</td>
          <td class="cell-nowrap"><code>${escapeHtml(i.service)}</code></td>
          <td class="cell-nowrap" style="text-align: right;">
            <a class="btn btn-primary btn-sm" href="/api/incidents/${i.id}/report?format=pdf" download="${i.id}-postmortem.pdf">📥 Download PDF</a>
            <a class="btn btn-secondary btn-sm" href="/api/incidents/${i.id}/report?format=html" target="_blank">📄 Printable Web</a>
            <a class="btn btn-secondary btn-sm" href="/api/incidents/${i.id}/report?format=markdown" download="${i.id}-postmortem.md">📥 Markdown</a>
          </td>
        </tr>
      `
        )
        .join('');
    } catch (err) {
      showToast('Failed to load reports table', 'error');
    }
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/[&<>"']/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
  }

  // Boot
  document.addEventListener('DOMContentLoaded', init);
})();
