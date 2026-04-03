/* ════════════════════════════════════════
   ROYAL KEYS COST SHEET — APP.JS v2
   ════════════════════════════════════════ */

const PASSWORD = 'RoyalKeys@2026';

const RESIDENTIAL_TERMS = [
  'Above-mentioned rates are subject to change without prior notice.',
  'Booking amount: ₹2,00,000/-.',
  'Government taxes will be charged as applicable at the time of agreement.',
  'Cheques / DD to be drawn in favour of "KEYS REALITY".',
  'Agreement execution charges: ₹15,000/-, payable in cash at the time of agreement.',
  'In case of booking cancellation, cancellation charges along with cheque return charges (if applicable) will be levied.',
  'Layout plans are subject to change as per Government / PCMC norms.',
  'Maintenance charges applicable at the time of possession for 2 & 2.5 BHK: ₹3 per sq.ft. + GST.',
  'The project is approved by all major banks and financial institutions. Outside bankers are strictly not allowed.',
  'TDS (if applicable) must be paid immediately after agreement execution to avoid Government penalties (1% of the Agreement Value).',
  'PROJECT APPROVED BY LEADING BANKS : HDFC Bank, Axis Bank, PNB, ICICI Bank, SBI Bank.',
];

const COMMERCIAL_TERMS = [
  'Above-mentioned rates are subject to change without prior notice.',
  'Booking amount: ₹5,00,000/-.',
  'Government taxes will be charged as applicable at the time of agreement.',
  'Cheques / DD to be drawn in favour of "KEYS REALITY".',
  'Agreement execution charges: ₹15,000/-, payable in cash at the time of agreement.',
  'In case of booking cancellation, cancellation charges along with cheque return charges (if any) will be applicable.',
  'Layout plans are subject to change as per Government / PCMC norms.',
  'Maintenance charges will be applicable as per the society\'s decision at the time of possession.',
  'The project is approved by all major banks and financial institutions. Outside bankers are strictly not allowed.',
  'TDS (if applicable) must be paid immediately after agreement execution to avoid penalties from the Government (1% of the Agreement Value).',
  'PROJECT APPROVED BY LEADING BANKS : HDFC Bank, Axis Bank, PNB, ICICI Bank, SBI Bank.',
];

const PAYMENT_STAGES = [
  ['On or before execution of the Agreement', '10%'],
  ['Within 15 days from the date of execution of the Agreement', '20%'],
  ['On completion of the plinth of the building / wing in which the said flat is located', '15%'],
  ['On completion of the second slab of the building / wing', '5%'],
  ['On completion of the fourth slab (including podiums & stilts)', '5%'],
  ['On completion of the sixth slab (including podiums & stilts)', '5%'],
  ['On completion of the tenth slab (including podiums & stilts)', '5%'],
  ['On completion of the fourteenth slab (including podiums & stilts)', '5%'],
  ['On completion of walls, internal plaster, flooring, doors & windows of the said flat', '5%'],
  ['On completion of sanitary fittings, staircases, lift wells & lobbies up to the floor level of the said flat', '5%'],
  ['On completion of external plumbing, external plaster, elevation & terrace waterproofing', '5%'],
  ['On completion of lifts, water pumps, electrical fittings, electro-mechanical & environmental requirements, entrance lobbies, plinth protection & paving of common areas', '10%'],
  ['At the time of handing over possession of the flat to the allottee(s) on or after receipt of Occupancy Certificate', '5%'],
];

/* ── STATE ───────────────────────────── */
let currentType = 'Residential';
let selectedUnit = null;

/* ── HELPERS ─────────────────────────── */
function isSoldUnit(u) {
  const s = (u.status || '').toLowerCase().trim();
  return s.startsWith('sold') || (s.includes('sold') && !s.includes('unsold'));
}

function formatINR(n) {
  n = Math.round(n);
  if (isNaN(n) || n < 0) return '0';
  let s = String(n);
  if (s.length <= 3) return s;
  const last3 = s.slice(-3);
  const rest   = s.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ',');
  return rest + ',' + last3;
}

function amtInWords(n) {
  n = Math.round(n);
  const ones = ['','One','Two','Three','Four','Five','Six','Seven','Eight','Nine',
                 'Ten','Eleven','Twelve','Thirteen','Fourteen','Fifteen','Sixteen',
                 'Seventeen','Eighteen','Nineteen'];
  const tens = ['','','Twenty','Thirty','Forty','Fifty','Sixty','Seventy','Eighty','Ninety'];
  if (n === 0) return 'Zero';
  function below1000(x) {
    if (x < 20) return ones[x];
    if (x < 100) return tens[Math.floor(x/10)] + (x % 10 ? ' ' + ones[x % 10] : '');
    return ones[Math.floor(x/100)] + ' Hundred' + (x % 100 ? ' ' + below1000(x % 100) : '');
  }
  let result = '';
  const cr  = Math.floor(n / 10000000); n %= 10000000;
  const lac = Math.floor(n / 100000);   n %= 100000;
  const th  = Math.floor(n / 1000);     n %= 1000;
  if (cr)  result += below1000(cr)  + ' Crore ';
  if (lac) result += below1000(lac) + ' Lakh ';
  if (th)  result += below1000(th)  + ' Thousand ';
  if (n)   result += below1000(n);
  return result.trim();
}

function calcCosts(agreement, isCommercial, sdGender) {
  const sdPct  = (sdGender === 'female' || sdGender === 'both') ? 0.06 : 0.07;
  const gstPct = isCommercial ? 0.12 : 0.05;
  const sd  = Math.round(agreement * sdPct);
  const gst = Math.round(agreement * gstPct);
  const reg = 30000;
  return { agreement, sd, sdPct, gst, gstPct, reg, total: agreement + sd + gst + reg };
}

/* ── LOGIN ───────────────────────────── */
document.getElementById('login-btn').addEventListener('click', doLogin);
document.getElementById('pwd-input').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });

function doLogin() {
  const val = document.getElementById('pwd-input').value.trim();
  if (val === PASSWORD) {
    document.getElementById('login-screen').classList.remove('active');
    document.getElementById('app-screen').classList.add('active');
    initApp();
  } else {
    const err = document.getElementById('login-error');
    err.textContent = 'Incorrect access code. Please try again.';
    setTimeout(() => { err.textContent = ''; }, 3000);
  }
}

document.getElementById('logout-btn').addEventListener('click', () => {
  document.getElementById('app-screen').classList.remove('active');
  document.getElementById('login-screen').classList.add('active');
  document.getElementById('pwd-input').value = '';
  selectedUnit = null;
});

/* ── APP INIT ────────────────────────── */
function initApp() {
  document.getElementById('cs-date').value = new Date().toISOString().split('T')[0];
  populateFilters();
  renderUnitGrid();

  document.getElementById('btn-residential').addEventListener('click', () => setType('Residential'));
  document.getElementById('btn-commercial').addEventListener('click',  () => setType('Commercial'));

  ['filter-wing','filter-floor','filter-config','filter-status'].forEach(id => {
    document.getElementById(id).addEventListener('change', renderUnitGrid);
  });

  document.getElementById('back-btn').addEventListener('click', goBack);
  document.getElementById('download-btn').addEventListener('click', downloadPDF);
  document.getElementById('apply-total-btn').addEventListener('click', applyTotalEdit);
  document.getElementById('apr-input').addEventListener('input', onAPRChange);
  document.getElementById('sd-gender').addEventListener('change', recalc);

  document.getElementById('customer-name').addEventListener('input', () => {
    if (document.getElementById('customer-name').value.trim()) {
      document.getElementById('customer-name').classList.remove('field-error');
      document.getElementById('name-error').style.display = 'none';
    }
  });
}

function setType(type) {
  currentType = type;
  document.getElementById('btn-residential').classList.toggle('active', type === 'Residential');
  document.getElementById('btn-commercial').classList.toggle('active',  type === 'Commercial');
  selectedUnit = null;
  document.getElementById('step3').style.display = 'none';
  document.getElementById('step2').classList.remove('collapsed');
  ['filter-wing','filter-floor','filter-config','filter-status'].forEach(id => {
    document.getElementById(id).value = '';
  });
  populateFilters();
  renderUnitGrid();
}

function populateFilters() {
  const pool = UNITS_DATA.filter(u => u.type === currentType);

  const floors = [...new Set(pool.map(u => u.floor))].sort((a,b) => {
    if (a === 'Ground') return -1;
    if (b === 'Ground') return 1;
    return parseInt(a) - parseInt(b);
  });
  const floorSel = document.getElementById('filter-floor');
  const curFloor = floorSel.value;
  floorSel.innerHTML = '<option value="">All Floors</option>' +
    floors.map(f => `<option value="${f}" ${f===curFloor?'selected':''}>${f==='Ground'?'Ground Floor':'Floor '+f}</option>`).join('');

  const configs = [...new Set(pool.map(u => u.config))].sort();
  const configSel = document.getElementById('filter-config');
  const curConfig = configSel.value;
  configSel.innerHTML = '<option value="">All</option>' +
    configs.map(c => `<option value="${c}" ${c===curConfig?'selected':''}>${c}</option>`).join('');
}

/* ── UNIT GRID ───────────────────────── */
function renderUnitGrid() {
  const wing    = document.getElementById('filter-wing').value;
  const floor   = document.getElementById('filter-floor').value;
  const config  = document.getElementById('filter-config').value;
  const statusF = document.getElementById('filter-status').value;

  let units = UNITS_DATA.filter(u => u.type === currentType);
  if (wing)   units = units.filter(u => u.wing === wing);
  if (floor)  units = units.filter(u => u.floor === floor);
  if (config) units = units.filter(u => u.config === config);

  if (statusF === 'unsold') units = units.filter(u => !isSoldUnit(u));
  if (statusF === 'sold')   units = units.filter(u =>  isSoldUnit(u));

  const grid = document.getElementById('unit-grid');
  if (units.length === 0) {
    grid.innerHTML = '<div class="no-units">No units match the selected filters.</div>';
    return;
  }

  grid.innerHTML = units.map(u => {
    const sold       = isSoldUnit(u);
    const isSelected = selectedUnit && selectedUnit.sno === u.sno;
    return `<div class="unit-card ${sold?'sold':''} ${isSelected?'selected':''}"
         data-sno="${u.sno}" ${sold?'title="This unit is already sold"':''}>
      <div class="uc-no">Unit ${u.unit_no}</div>
      <div class="uc-wing">Wing ${u.wing} · ${u.floor==='Ground'?'GF':'Fl.'+u.floor}</div>
      <div class="uc-config">${u.config}</div>
      <div class="uc-carpet">${u.carpet_area.toFixed(2)} sq.ft.</div>
      <span class="uc-badge ${sold?'sold':'unsold'}">${sold?'SOLD':'AVAILABLE'}</span>
    </div>`;
  }).join('');

  grid.querySelectorAll('.unit-card:not(.sold)').forEach(card => {
    card.addEventListener('click', () => selectUnit(card.dataset.sno));
  });
}

function goBack() {
  document.getElementById('step3').style.display = 'none';
  document.getElementById('step2').classList.remove('collapsed');
  selectedUnit = null;
  renderUnitGrid();
  document.getElementById('step2').scrollIntoView({ behavior:'smooth' });
}

/* ── SELECT UNIT ─────────────────────── */
function selectUnit(sno) {
  const raw = UNITS_DATA.find(u => u.sno === sno);
  if (!raw) return;
  selectedUnit = Object.assign({}, raw);
  selectedUnit._apr       = selectedUnit.apr;
  selectedUnit._agreement = Math.round(selectedUnit.apr * selectedUnit.saleable_area);

  // Collapse step2, expand step3
  document.getElementById('step2').classList.add('collapsed');
  document.getElementById('step3').style.display = 'block';

  // Reset name field
  document.getElementById('customer-name').value = '';
  document.getElementById('customer-name').classList.remove('field-error');
  document.getElementById('name-error').style.display = 'none';

  const isCommercial = currentType === 'Commercial';
  document.getElementById('info-unit').textContent       = `Unit ${selectedUnit.unit_no}`;
  document.getElementById('info-wing-floor').textContent = `Wing ${selectedUnit.wing} · ${selectedUnit.floor==='Ground'?'Ground Floor':'Floor '+selectedUnit.floor}`;
  document.getElementById('info-config').textContent     = selectedUnit.config;
  document.getElementById('info-carpet').textContent     = selectedUnit.carpet_area.toFixed(2);
  document.getElementById('info-saleable').textContent   = selectedUnit.saleable_area.toFixed(2);
  document.getElementById('info-gst-rate').textContent   = isCommercial ? '12%' : '5%';
  document.getElementById('apr-input').value             = selectedUnit._apr;

  const terms = isCommercial ? COMMERCIAL_TERMS : RESIDENTIAL_TERMS;
  document.getElementById('terms-list').innerHTML =
    terms.map(t => `<li>${t}</li>`).join('');

  document.getElementById('stage-section').style.display = isCommercial ? 'none' : 'block';

  recalc();
  setTimeout(() => document.getElementById('step3').scrollIntoView({ behavior:'smooth' }), 60);
}

function onAPRChange() {
  if (!selectedUnit) return;
  const newAPR = parseFloat(document.getElementById('apr-input').value) || 0;
  selectedUnit._apr       = newAPR;
  selectedUnit._agreement = Math.round(newAPR * selectedUnit.saleable_area);
  recalc();
}

/* ── RECALC ──────────────────────────── */
function recalc() {
  if (!selectedUnit) return;
  const isCommercial = currentType === 'Commercial';
  const sdGender     = document.getElementById('sd-gender').value;
  const c = calcCosts(selectedUnit._agreement, isCommercial, sdGender);

  document.getElementById('apr-input').value           = selectedUnit._apr;
  document.getElementById('amt-agreement').textContent = '₹' + formatINR(c.agreement);
  document.getElementById('sd-label').textContent      = `Stamp Duty ${Math.round(c.sdPct*100)}%`;
  document.getElementById('amt-sd').textContent        = '₹' + formatINR(c.sd);
  document.getElementById('gst-label').textContent     = `GST @ ${Math.round(c.gstPct*100)}%`;
  document.getElementById('amt-gst').textContent       = '₹' + formatINR(c.gst);
  document.getElementById('amt-total').textContent     = '₹' + formatINR(c.total);
  document.getElementById('total-input').value         = c.total;
  document.getElementById('words-line').textContent    = `Rupees ${amtInWords(c.total)} Only`;
}

/* ── APPLY TOTAL → BACK-CALC APR ── */
function applyTotalEdit() {
  if (!selectedUnit) return;
  const isCommercial = currentType === 'Commercial';
  const sdGender     = document.getElementById('sd-gender').value;
  const desired = parseFloat(document.getElementById('total-input').value) || 0;
  if (desired <= 30000) return;
  const sdPct  = (sdGender === 'female' || sdGender === 'both') ? 0.06 : 0.07;
  const gstPct = isCommercial ? 0.12 : 0.05;
  const agr    = Math.round((desired - 30000) / (1 + sdPct + gstPct));
  const newAPR = selectedUnit.saleable_area > 0 ? Math.round(agr / selectedUnit.saleable_area) : 0;
  selectedUnit._agreement = agr;
  selectedUnit._apr       = newAPR;
  recalc();
}

/* ══════════════════════════════════════
   PDF — matches original design exactly
══════════════════════════════════════ */
async function downloadPDF() {
  // Validate customer name
  const custName = document.getElementById('customer-name').value.trim();
  if (!custName) {
    document.getElementById('customer-name').classList.add('field-error');
    document.getElementById('name-error').style.display = 'block';
    document.getElementById('customer-name').focus();
    document.getElementById('customer-name').scrollIntoView({ behavior:'smooth', block:'center' });
    return;
  }
  if (!selectedUnit) return;

  const { jsPDF } = window.jspdf;
  const doc = new jsPDF({ unit:'mm', format:'a4' });

  const isCommercial = currentType === 'Commercial';
  const sdGender     = document.getElementById('sd-gender').value;
  const c            = calcCosts(selectedUnit._agreement, isCommercial, sdGender);
  const dateVal      = document.getElementById('cs-date').value || new Date().toISOString().split('T')[0];
  const dateStr      = new Date(dateVal + 'T00:00:00').toLocaleDateString('en-IN', {day:'2-digit',month:'long',year:'numeric'});

  let logoTop = null, logoBot = null, bwLogo = null;
  try { logoTop = await loadImg('assets/logo-top.jpg');  } catch(e){}
  try { logoBot = await loadImg('assets/logo-bottom.jpg'); } catch(e){}
  try { bwLogo  = await loadImg('assets/bw_logo.png');  } catch(e){}

  const W = 210, H = 297;
  const PURPLE = [52, 4, 47];
  const GOLD   = [174, 138, 54];
  const GOLD_B = [201, 168, 76];
  const WHITE  = [255, 255, 255];

  for (let ci = 0; ci < 2; ci++) {
    if (ci > 0) doc.addPage();
    const copyLabel = ci === 0 ? "Customer's Copy" : "Sales Copy";

    /* ══ WHITE BACKGROUND ══ */
    doc.setFillColor(...WHITE);
    doc.rect(0, 0, W, H, 'F');

    /* ══ HEADER BAND ══ */
    doc.setFillColor(...PURPLE);
    doc.rect(0, 0, W, 38, 'F');

    /* Royal Keys logo */
    if (logoTop) {
      doc.addImage(logoTop, 'JPEG', 5, 3, 54, 31);
    } else {
      doc.setTextColor(...GOLD_B); doc.setFontSize(18); doc.setFont('helvetica','bold');
      doc.text('Royal Keys', 10, 22);
    }

    /* RERA badge */
    doc.setFillColor(...WHITE);
    doc.roundedRect(148, 5, 58, 20, 2, 2, 'F');
    doc.setTextColor(80,80,80); doc.setFontSize(5.5); doc.setFont('helvetica','normal');
    doc.text('MAHA-RERA Registration No.', 150, 11);
    doc.setFontSize(9); doc.setFont('helvetica','bold'); doc.setTextColor(...PURPLE);
    doc.text('P52100079364', 150, 18);
    doc.setFontSize(5); doc.setFont('helvetica','normal'); doc.setTextColor(100,100,100);
    doc.text('www.maharera.maharashstra.gov.in', 150, 23);

    /* copy label */
    doc.setFontSize(7); doc.setFont('helvetica','italic'); doc.setTextColor(210,190,140);
    doc.text(copyLabel, W - 5, 6, { align:'right' });

    /* ══ CUSTOMER / UNIT INFO ══ */
    let y = 44;
    doc.setFontSize(9.5); doc.setFont('helvetica','bold'); doc.setTextColor(20,20,20);
    doc.text(`Customer Name : ${custName}`, 12, y);
    doc.text(`Date : ${dateStr}`, W - 12, y, { align:'right' });

    y += 6;
    doc.setFontSize(8.5); doc.setFont('helvetica','normal'); doc.setTextColor(40,40,40);
    const floorLabel = selectedUnit.floor === 'Ground' ? 'Ground Floor' : 'Floor ' + selectedUnit.floor;
    doc.text(`Unit No: ${selectedUnit.unit_no}   |   Wing: ${selectedUnit.wing}   |   Floor: ${floorLabel}   |   Configuration: ${selectedUnit.config}`, 12, y);

    y += 5;
    doc.setFontSize(8);
    doc.text(`Carpet Area: ${selectedUnit.carpet_area.toFixed(2)} sq.ft.     Saleable Area: ${selectedUnit.saleable_area.toFixed(2)} sq.ft.     APR: ₹${formatINR(selectedUnit._apr)}/sq.ft.`, 12, y);

    /* gold rule */
    y += 5;
    doc.setDrawColor(...GOLD_B); doc.setLineWidth(0.7);
    doc.line(12, y, W - 12, y);
    y += 6;

    /* ══ COST TABLE ══ */
    const COL1 = 12, TW = W - 24, RH = 10;

    // Header row — gold fill, white text
    doc.setFillColor(...GOLD);
    doc.rect(COL1, y, TW, RH, 'F');
    doc.setDrawColor(...GOLD); doc.setLineWidth(0.3);
    doc.rect(COL1, y, TW, RH, 'S');
    doc.setTextColor(...WHITE); doc.setFont('helvetica','bold'); doc.setFontSize(9);
    doc.text('Description', COL1 + 5, y + 7);
    doc.text('Amount (₹)', W - 16, y + 7, { align:'right' });
    y += RH;

    // Table rows with alternating bands
    function tRow(label, value, alt) {
      if (alt) doc.setFillColor(247, 240, 222); else doc.setFillColor(...WHITE);
      doc.rect(COL1, y, TW, RH, 'F');
      doc.setDrawColor(200, 185, 150); doc.setLineWidth(0.15);
      doc.rect(COL1, y, TW, RH, 'S');
      doc.setTextColor(30,30,30); doc.setFont('helvetica','normal'); doc.setFontSize(9);
      doc.text(label, COL1 + 5, y + 7);
      doc.setFont('helvetica','bold');
      doc.text(value, W - 16, y + 7, { align:'right' });
      y += RH;
    }

    tRow('Agreement Value',                              '₹'+formatINR(c.agreement), false);
    tRow(`Stamp Duty ${Math.round(c.sdPct*100)}%`,      '₹'+formatINR(c.sd),        true);
    tRow('Registration Charges',                         '₹30,000',                  false);
    tRow(`GST @ ${Math.round(c.gstPct*100)}%`,          '₹'+formatINR(c.gst),       true);

    // Total row — purple fill
    const TRH = 12;
    doc.setFillColor(...PURPLE);
    doc.rect(COL1, y, TW, TRH, 'F');
    doc.setDrawColor(...GOLD_B); doc.setLineWidth(0.5);
    doc.rect(COL1, y, TW, TRH, 'S');
    doc.setTextColor(...WHITE); doc.setFont('helvetica','bold'); doc.setFontSize(10);
    doc.text('Total Cost', COL1 + 5, y + 8.5);
    doc.setTextColor(255, 220, 60); doc.setFontSize(11);
    doc.text('₹'+formatINR(c.total), W - 16, y + 9, { align:'right' });
    y += TRH;

    /* amount in words */
    y += 5;
    doc.setFontSize(8); doc.setFont('helvetica','bolditalic'); doc.setTextColor(60,40,15);
    const wl = doc.splitTextToSize(`Rupees ${amtInWords(c.total)} Only`, TW);
    doc.text(wl, COL1, y);
    y += wl.length * 5 + 6;

    /* gold divider */
    doc.setDrawColor(...GOLD_B); doc.setLineWidth(0.5);
    doc.line(COL1, y, W - COL1, y);
    y += 5;

    /* ══ STAGE OF PAYMENT (Residential only) ══ */
    if (!isCommercial) {
      // Section header
      doc.setFillColor(240, 232, 208);
      doc.roundedRect(COL1, y, 40, 7, 1, 1, 'F');
      doc.setDrawColor(...GOLD); doc.setLineWidth(0.3);
      doc.roundedRect(COL1, y, 40, 7, 1, 1, 'S');
      doc.setTextColor(50,30,5); doc.setFont('helvetica','bold'); doc.setFontSize(7.5);
      doc.text('Stage of Payment', COL1 + 3, y + 5);
      y += 10;

      // Stage rows
      PAYMENT_STAGES.forEach(([desc, pct], idx) => {
        const rh = 6.5;
        if (idx % 2 === 0) doc.setFillColor(...WHITE); else doc.setFillColor(247,240,222);
        doc.rect(COL1, y, TW, rh, 'F');
        doc.setDrawColor(200,185,150); doc.setLineWidth(0.1);
        doc.rect(COL1, y, TW, rh, 'S');

        const descLines = doc.splitTextToSize(desc, TW - 22);
        const rowH = Math.max(rh, descLines.length * 4);

        // re-draw with correct height
        if (idx % 2 === 0) doc.setFillColor(...WHITE); else doc.setFillColor(247,240,222);
        doc.rect(COL1, y, TW, rowH, 'F');
        doc.setDrawColor(200,185,150); doc.rect(COL1, y, TW, rowH, 'S');

        doc.setTextColor(30,30,30); doc.setFont('helvetica','normal'); doc.setFontSize(6.8);
        doc.text(descLines, COL1 + 2, y + 4.2);
        doc.setFont('helvetica','bold'); doc.setTextColor(...PURPLE);
        doc.text(pct, W - 16, y + 4.2, { align:'right' });
        y += rowH;
      });

      // Total row
      doc.setFillColor(...PURPLE);
      doc.rect(COL1, y, TW, 7, 'F');
      doc.setTextColor(...WHITE); doc.setFont('helvetica','bold'); doc.setFontSize(8);
      doc.text('TOTAL', COL1 + 3, y + 5);
      doc.setTextColor(255,220,60);
      doc.text('100%', W - 16, y + 5, { align:'right' });
      y += 9;

      /* gold divider */
      doc.setDrawColor(...GOLD_B); doc.setLineWidth(0.5);
      doc.line(COL1, y, W - COL1, y);
      y += 5;
    }

    /* ══ TERMS & CONDITIONS ══ */
    doc.setFillColor(240, 232, 208);
    doc.roundedRect(COL1, y, 48, 7, 1, 1, 'F');
    doc.setDrawColor(...GOLD); doc.setLineWidth(0.3);
    doc.roundedRect(COL1, y, 48, 7, 1, 1, 'S');
    doc.setTextColor(50,30,5); doc.setFont('helvetica','bold'); doc.setFontSize(7.5);
    doc.text('Terms and Conditions', COL1 + 3, y + 5);
    y += 10;

    const terms = isCommercial ? COMMERCIAL_TERMS : RESIDENTIAL_TERMS;
    doc.setFont('helvetica','normal'); doc.setFontSize(6.8); doc.setTextColor(35,25,15);
    for (const t of terms) {
      const lines = doc.splitTextToSize('\u25AA  ' + t, TW - 3);
      if (y + lines.length * 4 > H - 28) break;
      doc.text(lines, COL1 + 2, y);
      y += lines.length * 4 + 1.2;
    }

    /* ══ FOOTER ══ */
    const FY = H - 24;
    doc.setFillColor(...WHITE);
    doc.rect(0, FY, W, 24, 'F');
    doc.setDrawColor(...GOLD_B); doc.setLineWidth(0.5);
    doc.line(0, FY, W, FY);

    if (logoBot) {
      doc.addImage(logoBot, 'JPEG', 8, FY + 2, 28, 18);
    }
    if (bwLogo) {
      doc.setFillColor(...WHITE);
      doc.rect(38, FY+4, 26, 14, 'F');
      doc.addImage(bwLogo, 'PNG', 38, FY+4, 26, 14);
    }

    doc.setTextColor(30,30,30); doc.setFont('helvetica','bold'); doc.setFontSize(8.5);
    doc.text('Dikshita Dak \u2013 94619 30679   |   Kartik Patil \u2013 99213 84868', 105, FY + 8, { align:'center' });

    doc.setFontSize(7); doc.setFont('helvetica','normal'); doc.setTextColor(50,50,50);
    doc.text('Contact Us:', 67, FY + 16);
    doc.setFont('helvetica','bold'); doc.setFontSize(12); doc.setTextColor(...PURPLE);
    doc.text('080 6591 7414', 82, FY + 16);

    doc.setFont('helvetica','normal'); doc.setFontSize(6.5); doc.setTextColor(80,80,80);
    doc.text('Site Address: Royal Keys, Charholi Budruk \u2013 Nirgudi Rd, Wagholi, Charholi Budruk, Maharashtra 412105', 105, FY + 21, { align:'center' });

    /* Signature box */
    doc.setDrawColor(100,80,50); doc.setLineWidth(0.3);
    doc.rect(W - 50, FY - 20, 38, 14);
    doc.setFontSize(6); doc.setTextColor(80,60,30); doc.setFont('helvetica','normal');
    doc.text('Customer Signature', W - 31, FY - 4, { align:'center' });
  }

  const safe = custName.replace(/[^a-zA-Z0-9 _-]/g,'').replace(/\s+/g,'_');
  doc.save(`RoyalKeys_CostSheet_Unit${selectedUnit.unit_no}_${safe}.pdf`);
}

/* ── IMAGE LOADER ────────────────────── */
function loadImg(src) {
  return new Promise((res, rej) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      const cv = document.createElement('canvas');
      cv.width = img.naturalWidth; cv.height = img.naturalHeight;
      cv.getContext('2d').drawImage(img, 0, 0);
      res(cv.toDataURL('image/jpeg', 0.92));
    };
    img.onerror = rej;
    img.src = src + '?v=2';
  });
}
