(() => {
  'use strict';

  const vendor = new URL('../vendor/pdfjs/', document.currentScript.src);
  let rendererPromise;
  let ui;
  let source;
  let trigger;
  let loadingTask;
  let pdf;
  let renderTask;
  let textTask;
  let session = 0;
  let renderVersion = 0;
  let page = 1;
  let zoom = 100;
  let frame;
  let stageWidth = 0;
  let scrollLock;

  function controls() {
    ui.position.textContent = pdf ? `${page} / ${pdf.numPages}` : '—';
    ui.previous.disabled = !pdf || page === 1;
    ui.next.disabled = !pdf || page === pdf.numPages;
    ui.zoom.disabled = !pdf;
    ui.zoom.textContent = zoom === 100 ? 'Fit width' : '125%';
    ui.zoom.setAttribute('aria-pressed', String(zoom === 125));
  }

  function status(message, retry = false) {
    ui.status.textContent = message;
    ui.status.hidden = !message;
    ui.retry.hidden = !retry;
  }

  function stopRendering() {
    renderVersion++;
    renderTask?.cancel();
    textTask?.cancel();
    renderTask = textTask = null;
  }

  function dispose() {
    session++;
    stopRendering();
    cancelAnimationFrame(frame);
    const task = loadingTask;
    loadingTask = pdf = null;
    if (task) task.destroy().catch(() => {});
  }

  function release() {
    dispose();
    ui.paper.replaceChildren();
    if (scrollLock) {
      document.documentElement.style.overflow = scrollLock.html;
      document.body.style.overflow = scrollLock.body;
      scrollLock = null;
    }
    const previousTrigger = trigger;
    trigger = null;
    if (previousTrigger?.isConnected) previousTrigger.focus({preventScroll: true});
  }

  function close() {
    if (!ui.dialog.open) return;
    ui.dialog.close();
    release();
  }

  function setup() {
    if (ui) return;
    const dialog = document.createElement('dialog');
    dialog.className = 'pdf-dialog';
    dialog.lang = 'en';
    dialog.setAttribute('aria-labelledby', 'pdf-preview-title');
    dialog.innerHTML = '<div class="pdf-viewer-bar"><div class="pdf-viewer-heading"><strong id="pdf-preview-title"></strong><span class="pdf-viewer-meta"></span></div><div class="pdf-viewer-actions"><a class="pdf-tool pdf-download">Download PDF</a><button type="button" class="pdf-tool pdf-close" autofocus aria-label="Close PDF preview"><span class="pdf-close-label">Close</span><span aria-hidden="true">×</span></button></div></div><div class="pdf-reader-controls"><button type="button" class="pdf-tool pdf-previous" aria-label="Previous page">←</button><span class="pdf-position" role="status" aria-live="polite"></span><button type="button" class="pdf-tool pdf-next" aria-label="Next page">→</button><span class="pdf-controls-spacer"></span><button type="button" class="pdf-tool pdf-zoom" aria-label="Toggle zoom between fit width and 125 percent" aria-pressed="false">Fit width</button></div><div class="pdf-paper-stage" tabindex="0" aria-label="PDF pages"><div class="pdf-viewer-notice"><p class="pdf-status" role="status" aria-live="polite"></p><button type="button" class="pdf-tool pdf-retry" hidden>Retry</button></div><div class="pdf-paper" aria-busy="true"></div></div>';
    document.body.append(dialog);
    const find = selector => dialog.querySelector(selector);
    ui = {dialog, title: find('#pdf-preview-title'), meta: find('.pdf-viewer-meta'), download: find('.pdf-download'), close: find('.pdf-close'), previous: find('.pdf-previous'), next: find('.pdf-next'), position: find('.pdf-position'), zoom: find('.pdf-zoom'), stage: find('.pdf-paper-stage'), paper: find('.pdf-paper'), status: find('.pdf-status'), retry: find('.pdf-retry')};
    ui.close.addEventListener('click', close);
    dialog.addEventListener('cancel', event => {event.preventDefault(); close();});
    dialog.addEventListener('close', () => {if (!dialog.open && scrollLock) release();});
    dialog.addEventListener('click', event => {
      if (event.target !== dialog) return;
      const bounds = dialog.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) close();
    });
    ui.previous.addEventListener('click', () => turn(-1));
    ui.next.addEventListener('click', () => turn(1));
    ui.zoom.addEventListener('click', () => {
      if (!pdf) return;
      zoom = zoom === 100 ? 125 : 100;
      controls();
      draw();
    });
    ui.retry.addEventListener('click', load);
    new ResizeObserver(() => {
      const width = ui.stage.clientWidth;
      if (!dialog.open || !pdf || Math.abs(width - stageWidth) < 1) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(draw);
    }).observe(ui.stage);
  }

  async function renderer() {
    if (!rendererPromise) {
      rendererPromise = import(new URL('pdf.min.js', vendor).href).then(library => {
        library.GlobalWorkerOptions.workerSrc = new URL('pdf.worker.min.js', vendor).href;
        return library;
      }).catch(error => {rendererPromise = null; throw error;});
    }
    return rendererPromise;
  }

  async function load() {
    dispose();
    const active = session;
    page = 1;
    zoom = 100;
    controls();
    ui.paper.replaceChildren();
    ui.paper.removeAttribute('data-page');
    ui.paper.style.removeProperty('height');
    ui.paper.style.removeProperty('width');
    ui.paper.setAttribute('aria-busy', 'true');
    status('Loading PDF…');
    try {
      const library = await renderer();
      if (active !== session || !ui.dialog.open) return;
      loadingTask = library.getDocument({url: source.url, withCredentials: false, enableXfa: false, useWasm: false, standardFontDataUrl: new URL('standard_fonts/', vendor).href});
      const document = await loadingTask.promise;
      if (active !== session || !ui.dialog.open) return;
      pdf = document;
      controls();
      await draw();
    } catch (error) {
      if (active !== session || !ui.dialog.open) return;
      ui.paper.setAttribute('aria-busy', 'false');
      status('The PDF could not be loaded. Retry or download a copy.', true);
    }
  }

  function turn(step) {
    if (!pdf) return;
    const next = Math.max(1, Math.min(pdf.numPages, page + step));
    if (next === page) return;
    page = next;
    ui.stage.scrollTop = ui.stage.scrollLeft = 0;
    controls();
    draw();
  }

  async function draw() {
    if (!pdf || !ui.dialog.open) return;
    stopRendering();
    const active = session;
    const revision = renderVersion;
    const current = pdf;
    const pageNumber = page;
    const isCurrent = () => active === session && revision === renderVersion && ui.dialog.open;
    ui.paper.removeAttribute('data-page');
    ui.paper.setAttribute('aria-busy', 'true');
    status('Loading page…');
    try {
      const pdfPage = await current.getPage(pageNumber);
      if (!isCurrent()) return;
      const library = await renderer();
      if (!isCurrent()) return;
      stageWidth = ui.stage.clientWidth;
      const style = getComputedStyle(ui.stage);
      const innerWidth = ui.stage.getBoundingClientRect().width - (ui.stage.offsetWidth - stageWidth);
      const available = Math.floor(innerWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight));
      const width = Math.min(794, Math.max(1, available)) * zoom / 100;
      const unit = pdfPage.getViewport({scale: 1});
      const viewport = pdfPage.getViewport({scale: width / unit.width});
      const density = Math.max(1, Math.min(window.devicePixelRatio || 1, 2, Math.sqrt(6000000 / (viewport.width * viewport.height))));
      const canvas = document.createElement('canvas');
      canvas.width = Math.ceil(viewport.width * density);
      canvas.height = Math.ceil(viewport.height * density);
      canvas.setAttribute('aria-hidden', 'true');
      const text = document.createElement('div');
      text.className = 'pdf-text-layer';
      text.style.setProperty('--total-scale-factor', viewport.scale);
      ui.paper.style.width = `${viewport.width}px`;
      ui.paper.style.height = `${viewport.height}px`;
      ui.paper.replaceChildren(canvas, text);
      canvas.style.visibility = text.style.visibility = 'hidden';
      renderTask = pdfPage.render({canvasContext: canvas.getContext('2d'), viewport, transform: density === 1 ? null : [density, 0, 0, density, 0, 0]});
      textTask = new library.TextLayer({textContentSource: pdfPage.streamTextContent(), container: text, viewport});
      await Promise.all([renderTask.promise, textTask.render()]);
      if (!isCurrent()) return;
      renderTask = textTask = null;
      canvas.style.visibility = text.style.visibility = '';
      ui.paper.dataset.page = String(pageNumber);
      ui.paper.setAttribute('aria-busy', 'false');
      status('');
    } catch (error) {
      if (!isCurrent()) return;
      stopRendering();
      ui.paper.replaceChildren();
      ui.paper.setAttribute('aria-busy', 'false');
      status('This page could not be displayed. Retry or download a copy.', true);
    }
  }

  window.ARCADIAN_PDF_PREVIEW = Object.freeze({open(record, button) {
    setup();
    if (ui.dialog.open) close();
    source = record;
    trigger = button;
    ui.title.textContent = record.title;
    ui.meta.textContent = record.meta;
    const download = new URL(record.url);
    download.searchParams.set('download', '1');
    ui.download.href = download.href;
    scrollLock = {html: window.document.documentElement.style.overflow, body: window.document.body.style.overflow};
    window.document.documentElement.style.overflow = window.document.body.style.overflow = 'hidden';
    ui.dialog.showModal();
    ui.stage.scrollTop = ui.stage.scrollLeft = 0;
    ui.close.focus({preventScroll: true});
    load();
  }});
})();
