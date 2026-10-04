(function () {
  'use strict';
  const root = document.querySelector('[data-content-page]');
  if (!root) return;
  const locale = ['en', 'pl', 'nl'].includes(document.documentElement.lang) ? document.documentElement.lang : 'en';
  const messages = {
    en: {all: 'All work', finishing: 'Finishing & renovation', facades: 'Facades', electrical: 'Electrical', loading: 'Loading…', unavailable: 'The portfolio is temporarily unavailable. Please contact us for project references.', empty: 'Project photographs will appear here after publication.', emptyRates: 'Contact us for current opportunities and cooperation terms.', more: 'Show more', photos: 'View photographs', close: 'Close', previous: 'Previous photograph', next: 'Next photograph', of: 'of', employee: 'Employee', independent: 'Independent specialist', crew: 'Independent crew', ownVehicle: 'Own vehicle', ownTools: 'Own tools', payroll_gross: 'Salary before deductions', invoice_ex_vat: 'Invoice, excluding VAT', hour_person: 'hour / person', day_person: 'day / person', hour_crew: 'hour / crew', m2: 'm²', m: 'metre', unit: 'unit', fixed: 'agreed scope', from: 'from'},
    pl: {all: 'Wszystkie prace', finishing: 'Wykończenia i renowacje', facades: 'Elewacje', electrical: 'Elektryka', loading: 'Ładowanie…', unavailable: 'Portfolio jest chwilowo niedostępne. Skontaktuj się z nami w sprawie realizacji.', empty: 'Zdjęcia realizacji pojawią się tutaj po publikacji.', emptyRates: 'Skontaktuj się z nami, aby poznać aktualne możliwości i warunki współpracy.', more: 'Pokaż więcej', photos: 'Zobacz zdjęcia', close: 'Zamknij', previous: 'Poprzednie zdjęcie', next: 'Następne zdjęcie', of: 'z', employee: 'Pracownik etatowy', independent: 'Samodzielny specjalista', crew: 'Samodzielna brygada', ownVehicle: 'Własny samochód', ownTools: 'Własne narzędzia', payroll_gross: 'Wynagrodzenie brutto', invoice_ex_vat: 'Faktura, bez VAT', hour_person: 'godzina / osoba', day_person: 'dzień / osoba', hour_crew: 'godzina / brygada', m2: 'm²', m: 'metr', unit: 'jednostka', fixed: 'uzgodniony zakres', from: 'od'},
    nl: {all: 'Alle werken', finishing: 'Afwerking & renovatie', facades: 'Gevels', electrical: 'Elektriciteit', loading: 'Laden…', unavailable: 'Het portfolio is tijdelijk niet beschikbaar. Neem contact op voor projectreferenties.', empty: 'Projectfoto’s verschijnen hier na publicatie.', emptyRates: 'Neem contact op voor actuele mogelijkheden en samenwerkingsvoorwaarden.', more: 'Meer tonen', photos: 'Foto’s bekijken', close: 'Sluiten', previous: 'Vorige foto', next: 'Volgende foto', of: 'van', employee: 'Werknemer', independent: 'Zelfstandig specialist', crew: 'Zelfstandige ploeg', ownVehicle: 'Eigen voertuig', ownTools: 'Eigen gereedschap', payroll_gross: 'Brutoloon', invoice_ex_vat: 'Factuur, exclusief btw', hour_person: 'uur / persoon', day_person: 'dag / persoon', hour_crew: 'uur / ploeg', m2: 'm²', m: 'meter', unit: 'eenheid', fixed: 'afgesproken omvang', from: 'vanaf'},
  };
  const t = messages[locale];
  Object.assign(t, {
    en: {subcontractors: 'Subcontractor crews', viewPDF: 'View PDF', downloadPDF: 'Download PDF', pages: 'pages', effective: 'Effective from', documentsUnavailable: 'Rate documents are temporarily unavailable. Please contact Arcadian.'},
    pl: {subcontractors: 'Brygady podwykonawcze', viewPDF: 'Przeglądaj PDF', downloadPDF: 'Pobierz PDF', pages: 'str.', effective: 'Obowiązuje od', documentsUnavailable: 'Dokumenty z cennikami są chwilowo niedostępne. Skontaktuj się z Arcadian.'},
    nl: {subcontractors: 'Onderaannemersploegen', viewPDF: 'Bekijk PDF', downloadPDF: 'Download PDF', pages: 'pagina’s', effective: 'Geldig vanaf', documentsUnavailable: 'Tariefdocumenten zijn tijdelijk niet beschikbaar. Neem contact op met Arcadian.'},
  }[locale]);
  const plural = new Intl.PluralRules(locale);
  const photoWords = {en: {one: 'photo', other: 'photos'}, pl: {one: 'zdjęcie', few: 'zdjęcia', many: 'zdjęć', other: 'zdjęcia'}, nl: {one: 'foto', other: 'foto’s'}}[locale];
  const status = root.querySelector('[data-content-status]');
  const list = root.querySelector('[data-content-list]');
  const more = root.querySelector('[data-content-more]');
  const type = root.dataset.contentPage;
  const isDocument = type === 'documents';
  const isRate = type === 'rates' || isDocument;
  let cms;
  try {
    cms = new URL(window.ARCADIAN_CMS_URL);
    if (cms.protocol !== 'https:' && !(cms.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(cms.hostname))) throw new Error('Invalid CMS endpoint.');
    if (cms.username || cms.password || cms.search || cms.hash) throw new Error('Invalid CMS endpoint.');
  } catch (_) {
    status.textContent = isRate ? t.emptyRates : t.empty;
    return;
  }
  const text = (row, field) => String((locale !== 'en' && row[`${field}_${locale}`]) || row[field] || '');
  const element = (tag, className, value) => {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (value !== undefined) item.textContent = value;
    return item;
  };
  const fileId = (id) => typeof id === 'string' && /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(id);
  const asset = (id, size) => new URL(`api/images/${id}/?size=${size}`, cms.href.replace(/\/?$/, '/')).href;
  const message = (value) => {status.textContent = value; status.hidden = !value;};
  let controller;
  let page = 1;
  let sector = root.dataset.contentSector || new URLSearchParams(location.search).get('sector') || '';
  if (!['finishing', 'facades', 'electrical', ...(isDocument ? ['subcontractors'] : [])].includes(sector)) sector = '';

  function projectCard(project) {
    const card = element('article', 'work-card');
    const photographs = (project.photos || []).filter((file) => file && fileId(file.id));
    if (photographs.length) {
      const open = element('button', 'work-photo');
      open.type = 'button';
      open.setAttribute('aria-label', `${t.photos}: ${text(project, 'title')}`);
      const image = element('img');
      image.src = asset(photographs[0].id, 'card');
      image.srcset = `${asset(photographs[0].id, 'small')} 480w, ${asset(photographs[0].id, 'card')} 960w`;
      image.sizes = '(max-width: 620px) 100vw, (max-width: 960px) 50vw, 33vw';
      image.alt = photographs[0].description || text(project, 'title');
      image.width = 960; image.height = 720;
      image.loading = 'lazy'; image.decoding = 'async';
      open.append(image, element('span', 'work-count', `${photographs.length} ${photoWords[plural.select(photographs.length)] || photoWords.other}`));
      open.addEventListener('click', () => openPhotos(project, photographs));
      card.append(open);
    }
    const body = element('div', 'work-body');
    body.append(element('span', 'eyebrow', t[project.category] || ''), element('h2', '', text(project, 'title')));
    const meta = [project.location, project.completed_year].filter(Boolean).join(' · ');
    if (meta) body.append(element('p', 'work-meta', meta));
    body.append(element('p', 'work-description', text(project, 'description')));
    card.append(body);
    return card;
  }

  function openPhotos(project, photographs) {
    const dialog = root.querySelector('[data-photo-dialog]');
    if (!dialog || typeof dialog.showModal !== 'function') return;
    const image = dialog.querySelector('img');
    const caption = dialog.querySelector('[data-photo-caption]');
    const position = dialog.querySelector('[data-photo-position]');
    const previous = dialog.querySelector('[data-photo-previous]');
    const next = dialog.querySelector('[data-photo-next]');
    let selected = 0;
    function show() {
      image.src = asset(photographs[selected].id, 'large');
      image.alt = photographs[selected].description || text(project, 'title');
      caption.textContent = photographs[selected].description || text(project, 'title');
      position.textContent = `${selected + 1} ${t.of} ${photographs.length}`;
      previous.disabled = selected === 0;
      next.disabled = selected === photographs.length - 1;
    }
    previous.onclick = () => {if (selected > 0) {selected--; show();}};
    next.onclick = () => {if (selected < photographs.length - 1) {selected++; show();}};
    dialog.onkeydown = (event) => {
      if (event.key === 'ArrowLeft') {event.preventDefault(); previous.onclick();}
      if (event.key === 'ArrowRight') {event.preventDefault(); next.onclick();}
    };
    dialog.querySelector('[data-photo-close]').onclick = () => dialog.close();
    dialog.onclose = () => {image.removeAttribute('src');};
    show(); dialog.showModal();
  }

  function rateCard(rate) {
    const card = element('article', 'rate-card');
    card.append(element('span', 'eyebrow', t[rate.worker_type] || ''), element('h2', '', text(rate, 'title')));
    const low = Number(rate.amount_from);
    const high = rate.amount_to == null ? null : Number(rate.amount_to);
    const number = new Intl.NumberFormat(locale, {minimumFractionDigits: 0, maximumFractionDigits: 2});
    let amount = `${number.format(low)} EUR`;
    if (high !== null && high !== low) amount = `${number.format(low)}–${number.format(high)} EUR`;
    card.append(element('p', 'rate-amount', amount), element('p', 'rate-basis', `${t[rate.unit] || ''} · ${t[rate.basis] || ''}`));
    const tags = element('div', 'rate-tags');
    tags.append(element('span', '', t[rate.category] || ''));
    if (rate.own_vehicle) tags.append(element('span', '', t.ownVehicle));
    if (rate.own_tools) tags.append(element('span', '', t.ownTools));
    card.append(tags, element('p', 'work-description', text(rate, 'description')));
    return card;
  }

  function documentCard(row) {
    if (!fileId(row.id)) throw new Error('Invalid document identifier.');
    const card = element('article', 'document-card');
    card.append(element('span', 'eyebrow', `PDF · ${t[row.category] || ''}`), element('h2', '', text(row, 'title')));
    if (text(row, 'description')) card.append(element('p', 'work-description', text(row, 'description')));
    const meta = `${Number(row.page_count)} ${t.pages} · ${(Number(row.file_bytes) / (1024 * 1024)).toLocaleString(locale, {maximumFractionDigits: 1})} MB`;
    card.append(element('p', 'document-meta', meta));
    if (/^\d{4}-\d{2}-\d{2}$/.test(row.effective_date || '')) {
      const date = new Date(`${row.effective_date}T12:00:00Z`);
      if (!Number.isNaN(date.getTime())) card.append(element('p', 'document-meta', `${t.effective}: ${new Intl.DateTimeFormat(locale).format(date)}`));
    }
    const actions = element('div', 'document-actions');
    const view = element('a', 'btn btn-copper', t.viewPDF);
    view.href = new URL(`api/documents/${row.id}/`, cms.href.replace(/\/?$/, '/')).href;
    view.target = '_blank'; view.rel = 'noopener noreferrer';
    const download = element('a', 'btn btn-outline', t.downloadPDF);
    download.href = `${view.href}?download=1`;
    actions.append(view, download); card.append(actions);
    return card;
  }

  async function load(reset) {
    if (controller) controller.abort();
    controller = new AbortController();
    const active = controller;
    if (reset) {page = 1; list.replaceChildren();}
    more.hidden = true;
    message(t.loading);
    const route = isDocument ? 'documents' : type === 'rates' ? 'rates' : 'projects';
    const endpoint = new URL(`api/${route}/`, cms.href.replace(/\/?$/, '/'));
    endpoint.searchParams.set('page', page);
    if (sector) endpoint.searchParams.set('category', sector);
    try {
      const response = await fetch(endpoint, {signal: active.signal, credentials: 'omit', cache: 'no-store'});
      if (!response.ok) throw new Error('Content unavailable.');
      const result = await response.json();
      if (!Array.isArray(result.data)) throw new Error('Invalid content response.');
      for (const row of result.data) list.append(isDocument ? documentCard(row) : type === 'rates' ? rateCard(row) : projectCard(row));
      message(list.childElementCount ? '' : isRate ? t.emptyRates : t.empty);
      more.hidden = result.has_more !== true;
    } catch (error) {
      if (error.name !== 'AbortError') {
        message(isRate ? t.documentsUnavailable : t.unavailable);
        more.hidden = true;
      }
    }
  }
  for (const button of root.querySelectorAll('[data-sector]')) {
    button.setAttribute('aria-pressed', String(button.dataset.sector === sector));
    button.addEventListener('click', () => {
      sector = button.dataset.sector;
      for (const item of root.querySelectorAll('[data-sector]')) item.setAttribute('aria-pressed', String(item === button));
      const url = new URL(location.href);
      if (sector) url.searchParams.set('sector', sector); else url.searchParams.delete('sector');
      history.replaceState(null, '', url);
      load(true);
    });
  }
  more.addEventListener('click', () => {page++; load(false);});
  load(true);
})();
