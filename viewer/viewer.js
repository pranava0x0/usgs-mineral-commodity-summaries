/* Critical Minerals viewer — vanilla JS, no build step.
 *
 * Reads viewer/data.json (mirrored from data/processed/elements.json), renders
 * the latest-year summary table, and lets the user drill into a single
 * element to see the full salient stats table, import sources, world
 * production rows, narrative prose, and source PDF screenshots.
 */

const DATA_PATH = './data.json';
const AUDIT_BASE = '../data/audit';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function fmt(value, { suffix = '', muted = 'N/A' } = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return `<span class="muted-cell">${muted}</span>`;
  }
  if (typeof value === 'number') {
    const rounded = Number.isInteger(value) ? value : Number(value.toFixed(2));
    return rounded.toLocaleString('en-US') + suffix;
  }
  return String(value);
}

function fmtNum(value, raw, suffix = '') {
  // When the PDF wrote a sentinel like "W", "E", or ">95", show that verbatim;
  // otherwise format the numeric value.
  if (raw && (raw === 'W' || raw === 'E' || /^[<>]/.test(raw))) {
    return `<span title="raw value from PDF" class="sentinel">${raw}</span>`;
  }
  return fmt(value, { suffix });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

function setupTheme() {
  const btn = $('#theme-toggle');
  const stored = localStorage.getItem('cmie-theme');
  if (stored === 'dark') document.documentElement.dataset.theme = 'dark';
  btn.addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('cmie-theme', next);
    btn.textContent = next === 'dark' ? '☾' : '☼';
  });
  btn.textContent = document.documentElement.dataset.theme === 'dark' ? '☾' : '☼';
}

function renderOverview(bundle) {
  $('#generated-at').textContent = bundle.generated_at;
  if (bundle.elements[0]) {
    $('#primary-source').href = 'https://pubs.usgs.gov/periodicals/mcs2026/';
    $('#primary-source').textContent = 'USGS MCS 2026 index';
    $('#units-note').textContent =
      'Units differ per sheet — see each row’s detail panel for the verbatim units note. Open a row to see the full table and source-page screenshots.';
  }

  const body = $('#overview-body');
  body.innerHTML = '';
  bundle.elements.forEach((el, idx) => {
    const tr = document.createElement('tr');
    tr.dataset.slug = el.slug;
    tr.tabIndex = 0;
    tr.setAttribute('role', 'button');
    tr.setAttribute('aria-label', `Open detail for ${el.name}`);
    const sentinels = el.latest_year_sentinels || {};
    tr.innerHTML = `
      <td class="element-cell">${escapeHtml(el.name)}<span class="element-symbol">${escapeHtml(el.symbol ?? '')}</span></td>
      <td class="num">${fmtNum(el.mined_production_latest, sentinels.mined_production)}</td>
      <td class="num">${fmtNum(el.primary_smelting_latest, sentinels.primary_smelting)}</td>
      <td class="num">${fmtNum(el.secondary_smelting_latest, sentinels.secondary_smelting)}</td>
      <td class="num">${fmtNum(el.imports_total_latest)}</td>
      <td class="num">${fmtNum(el.exports_total_latest)}</td>
      <td class="num">${fmtNum(el.apparent_consumption_latest, sentinels.apparent_consumption)}</td>
      <td class="num">${fmtNum(el.price_usd_per_pound_latest)}</td>
      <td class="num">${fmtNum(el.net_import_reliance_pct_latest, sentinels.net_import_reliance, '%')}</td>
      <td><a class="source-link" href="${el.source_url}" target="_blank" rel="noopener">USGS MCS ↗</a></td>
    `;
    tr.addEventListener('click', () => showDetail(el));
    tr.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        showDetail(el);
      }
    });
    body.appendChild(tr);
    if (idx === 0) showDetail(el);
  });

  // Footnote line explaining latest-year framing
  const first = bundle.elements[0];
  if (first) {
    $('#overview-footnote').innerHTML =
      `Showing <strong>${first.latest_year}</strong> values; ` +
      `<code>W</code> = withheld, <code>E</code> = net exporter, <code>&gt;95</code> = "more than 95%". ` +
      `Missing values render as <em class="muted-cell">N/A</em>.`;
  }
}

function showDetail(el) {
  $$('#overview-body tr').forEach(tr => {
    tr.setAttribute('aria-selected', tr.dataset.slug === el.slug ? 'true' : 'false');
  });

  const card = document.createElement('div');
  card.className = 'detail-card';
  card.innerHTML = `
    <h3>${escapeHtml(el.name)} <span class="element-symbol">${escapeHtml(el.symbol ?? '')}</span></h3>
    <p class="source-row">
      <a href="${escapeHtml(el.source_url)}" target="_blank" rel="noopener">${escapeHtml(el.source_url)}</a>
      · captured ${escapeHtml(el.captured_at)}
      · ${escapeHtml(el.edition)} (${escapeHtml(el.edition_date)})
      · PDF SHA-256 <code>${escapeHtml(el.pdf_sha256.slice(0, 12))}…</code>
    </p>
    <p class="prose"><strong>Units:</strong> ${escapeHtml(el.units_note)}</p>
    ${el.price_unit_note
      ? `<p class="prose"><strong>Price basis:</strong> ${escapeHtml(el.price_unit_note)}${
          el.price_footnote_text ? ` — <em>${escapeHtml(el.price_footnote_text)}</em>` : ''
        }</p>`
      : ''}
    <div class="detail-grid">
      ${salientBlock(el)}
      ${importSourcesBlock(el)}
      ${worldProductionBlock(el)}
    </div>
    ${proseBlock(el)}
    ${footnotesBlock(el)}
    ${screenshotsBlock(el)}
  `;

  const host = $('#detail-body');
  host.innerHTML = '';
  host.appendChild(card);
  $('#detail').hidden = false;
}

const YEARS = ['2021', '2022', '2023', '2024', '2025e'];

function salientBlock(el) {
  // Group rows by their `section` so the table reads "Production / Imports /
  // Exports / Consumption / Price / NIR" rather than as one flat blob.
  const groups = {};
  const order = [];
  for (const r of el.salient_stats) {
    const sec = r.section || '(uncategorized)';
    if (!(sec in groups)) {
      groups[sec] = [];
      order.push(sec);
    }
    groups[sec].push(r);
  }
  const fmtCell = (r, y) => {
    const v = r.values[y];
    const raw = (r.raw_values || {})[y];
    if (raw && (raw === 'W' || raw === 'E' || /^[<>]/.test(raw))) {
      return `<span title="raw value from PDF" class="sentinel">${escapeHtml(raw)}</span>`;
    }
    if (raw && /[–-]/.test(raw) && /\d.+\d/.test(raw)) {
      // range value (e.g. "890–1,000")
      return `<span title="midpoint shown; raw=${escapeHtml(raw)}">${escapeHtml(raw)}</span>`;
    }
    return fmt(v);
  };
  const tables = order.map(sec => {
    const rows = groups[sec].map(r => `
      <tr>
        <td class="row-label">${escapeHtml(r.label)}${r.footnote ? `<sup>${r.footnote}</sup>` : ''}</td>
        ${YEARS.map(y => `<td class="num">${fmtCell(r, y)}</td>`).join('')}
      </tr>
    `).join('');
    return `
      <h5 class="cat-heading">${escapeHtml(sec)}</h5>
      <table class="mini-table">
        <thead>
          <tr>
            <th>Row</th>
            ${YEARS.map(y => `<th class="num">${y}</th>`).join('')}
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }).join('');
  return `
    <div style="grid-column: 1 / -1">
      <h4 class="eyebrow">Salient Statistics — United States</h4>
      ${tables}
    </div>
  `;
}

function importSourcesBlock(el) {
  const cats = el.import_sources_by_category || [];
  if (!cats.length) {
    return `<div><h4 class="eyebrow">Import Sources</h4><p class="muted-cell">Not reported.</p></div>`;
  }
  const tables = cats.map(cat => {
    const rows = cat.countries.map(cs => `
      <tr>
        <td>${escapeHtml(cs.country)}</td>
        <td class="num">${fmt(cs.share_pct, { suffix: '%' })}</td>
      </tr>
    `).join('');
    const heading = cat.category ? `<h5 class="cat-heading">${escapeHtml(cat.category)}</h5>` : '';
    return `${heading}<table class="mini-table"><thead>
      <tr><th>Country</th><th class="num">Share</th></tr>
    </thead><tbody>${rows}</tbody></table>`;
  }).join('');
  return `
    <div>
      <h4 class="eyebrow">Import Sources (${escapeHtml(el.import_sources_range || 'range unspecified')})</h4>
      ${tables}
    </div>
  `;
}

function worldProductionBlock(el) {
  if (!el.world_production?.length) {
    return `<div style="grid-column: 1 / -1"><h4 class="eyebrow">World production</h4><p class="muted-cell">Not reported in this MCS sheet.</p></div>`;
  }
  const headerLabel = el.world_production_label || 'World production';
  const cellFor = (val, raw) => {
    if (raw && (raw === 'W' || raw === 'E' || /^[<>]/.test(raw))) {
      return `<span class="sentinel">${escapeHtml(raw)}</span>`;
    }
    return fmt(val);
  };
  const rows = el.world_production.map(r => `
    <tr>
      <td>${escapeHtml(r.country)}${r.note ? ` <small class="muted-cell">(${escapeHtml(r.note)})</small>` : ''}</td>
      <td class="num">${cellFor(r.production_prev_year, r.production_prev_raw)}</td>
      <td class="num">${cellFor(r.production_latest_year, r.production_latest_raw)}</td>
      <td class="num">${fmt(r.capacity)}</td>
      <td class="num">${cellFor(r.reserves, r.reserves_raw)}</td>
    </tr>
  `).join('');
  // Year labels come straight from the PDF's world-production sub-header band
  // (captured into `world_production_year_{prev,latest}` by the parser). Fall
  // back to generic labels for the rare sheet where they couldn't be parsed.
  const prevLabel = el.world_production_year_prev || 'Prev year';
  const latestLabel = el.world_production_year_latest || 'Latest year';
  return `
    <div style="grid-column: 1 / -1">
      <h4 class="eyebrow">${escapeHtml(headerLabel)}</h4>
      <table class="mini-table">
        <thead>
          <tr>
            <th>Country</th>
            <th class="num">${escapeHtml(prevLabel)}</th>
            <th class="num">${escapeHtml(latestLabel)}</th>
            <th class="num">Capacity</th>
            <th class="num">Reserves</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function proseBlock(el) {
  const parts = [];
  if (el.domestic_use_summary)
    parts.push(`<h4 class="eyebrow">Domestic production &amp; use</h4><p class="prose">${el.domestic_use_summary}</p>`);
  if (el.events_trends_summary)
    parts.push(`<h4 class="eyebrow">Events, trends, &amp; issues</h4><p class="prose">${el.events_trends_summary}</p>`);
  if (el.world_resources_summary)
    parts.push(`<h4 class="eyebrow">World resources</h4><p class="prose">${el.world_resources_summary}</p>`);
  if (el.substitutes_summary)
    parts.push(`<h4 class="eyebrow">Substitutes</h4><p class="prose">${el.substitutes_summary}</p>`);
  if (el.recycling_summary)
    parts.push(`<h4 class="eyebrow">Recycling</h4><p class="prose">${el.recycling_summary}</p>`);
  return parts.join('');
}

function footnotesBlock(el) {
  const entries = Object.entries(el.footnotes || {});
  if (!entries.length) return '';
  entries.sort(([a], [b]) => {
    const na = Number(a), nb = Number(b);
    if (Number.isNaN(na) && Number.isNaN(nb)) return a.localeCompare(b);
    if (Number.isNaN(na)) return 1;
    if (Number.isNaN(nb)) return -1;
    return na - nb;
  });
  return `
    <h4 class="eyebrow">Footnotes</h4>
    <ul class="footnotes">
      ${entries.map(([k, v]) => `<li><span class="marker">${k}</span>${v}</li>`).join('')}
    </ul>
  `;
}

function screenshotsBlock(el) {
  const figs = [];
  for (let p = 1; p <= el.pdf_page_count; p++) {
    const src = `${AUDIT_BASE}/${el.slug}/page-${String(p).padStart(2, '0')}.png`;
    figs.push(`
      <figure>
        <figcaption>${el.name} — MCS page ${p} (rendered from source PDF)</figcaption>
        <img loading="lazy" src="${src}" alt="${el.name} MCS sheet page ${p} (verbatim from USGS source PDF)" />
      </figure>
    `);
  }
  return `<div class="screenshots">${figs.join('')}</div>`;
}

/* ---------- Exports ----------
 * CSV is a plain <a download> — no JS needed.
 * XLS builds an Office XML "Spreadsheet ML" file inline from the CSV. Excel,
 * Numbers, and LibreOffice all open the .xls extension. No library.
 * PDF triggers window.print(); a print stylesheet hides the page chrome so
 * the resulting PDF is the data + currently-open detail panel.
 */

function setupExports() {
  $('#export-xls').addEventListener('click', exportXls);
  $('#export-pdf').addEventListener('click', () => window.print());
}

async function exportXls() {
  // Read the same CSV the user can already download, then wrap each row in
  // Office-XML cells. This guarantees byte-identical numbers across formats.
  let csvText;
  try {
    const res = await fetch('data.csv');
    csvText = await res.text();
  } catch (err) {
    alert('Failed to load data.csv for XLS export: ' + String(err));
    return;
  }

  const rows = parseCsv(csvText);
  if (!rows.length) return;

  const xmlRows = rows.map(cells => {
    const xmlCells = cells.map(cell => {
      // Numbers (including signed/decimal); leave "N/A" and "W"/"E" as String.
      if (/^-?\d+(?:\.\d+)?$/.test(cell)) {
        return `<Cell><Data ss:Type="Number">${cell}</Data></Cell>`;
      }
      return `<Cell><Data ss:Type="String">${escapeXml(cell)}</Data></Cell>`;
    }).join('');
    return `<Row>${xmlCells}</Row>`;
  }).join('');

  const xml =
    '<?xml version="1.0"?>\n' +
    '<?mso-application progid="Excel.Sheet"?>\n' +
    '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"\n' +
    ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">\n' +
    '<Worksheet ss:Name="Critical Minerals">\n' +
    `<Table>${xmlRows}</Table>\n` +
    '</Worksheet>\n</Workbook>';

  const blob = new Blob([xml], { type: 'application/vnd.ms-excel' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'critical-minerals-mcs2026.xls';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Revoke after the download has had a beat to start.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function parseCsv(text) {
  // Minimal RFC-4180 parser: handles quoted cells, escaped quotes, and CRLF.
  const rows = [];
  let row = [];
  let cell = '';
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') { cell += '"'; i++; }
        else { inQuotes = false; }
      } else {
        cell += c;
      }
    } else {
      if (c === '"') { inQuotes = true; }
      else if (c === ',') { row.push(cell); cell = ''; }
      else if (c === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
      else if (c === '\r') { /* swallow */ }
      else { cell += c; }
    }
  }
  if (cell.length > 0 || row.length > 0) { row.push(cell); rows.push(row); }
  // Drop a trailing empty row if the file ended with a newline.
  if (rows.length && rows[rows.length - 1].length === 1 && rows[rows.length - 1][0] === '') {
    rows.pop();
  }
  return rows;
}

function escapeXml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;'
  }[c]));
}

async function main() {
  setupTheme();
  setupExports();
  let bundle;
  try {
    const res = await fetch(DATA_PATH);
    bundle = await res.json();
  } catch (err) {
    $('#overview-body').innerHTML = `<tr><td colspan="10" class="muted-cell">
      Failed to load <code>data.json</code>: ${String(err)} —
      run <code>python -m src.pipeline --audit</code> first.
    </td></tr>`;
    return;
  }
  renderOverview(bundle);
}

main();
