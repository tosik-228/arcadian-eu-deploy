import {chromium} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {readFile, mkdir, writeFile, unlink} from 'node:fs/promises';
import {createHmac} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

const root = fileURLToPath(new URL('../', import.meta.url));
const droplet = process.env.LOCAL_DROPLET_ACCEPTANCE === '1';
const state = fileURLToPath(new URL('.state/browser-fixture.json', import.meta.url));
const shots = fileURLToPath(new URL(droplet ? '.state/droplet-screenshots/' : '.state/screenshots/', import.meta.url));
const acceptance = `${root}cms/.state/droplet-acceptance`;
const compose = ['--project-name', 'arcadian-content-acceptance', '--env-file', `${acceptance}/.env`,
  '-f', `${acceptance}/compose.yml`, '-f', `${acceptance}/compose.acceptance.yml`,
  'run', '--rm', '--no-deps', '-e', 'DJANGO_ENV=local', 'migrate'];
const dockerRun = (args) => execFileSync('docker-compose', [...compose, ...args],
  {cwd: root, env: {...process.env, DOCKER_CONTEXT: 'colima-arcadian-cms'}, stdio: 'pipe'});
const manage = (action) => droplet ? dockerRun(['python', 'manage.py', 'browser_fixture', action,
  '--state', '/data/acceptance/browser-fixture.json']) :
  execFileSync(`${root}cms/.venv/bin/python`, [`${root}cms/manage.py`, 'browser_fixture', action, '--state', state], {cwd: root, stdio: 'pipe'});
const cms = droplet ? 'https://localhost:8059' : 'http://127.0.0.1:8057';
const site = droplet ? 'http://127.0.0.1:8175' : 'http://127.0.0.1:8173';
const upload = `${root}cms/.state/droplet-browser-upload.jpg`;
let browser;
let created = false;
const evidence = [];
const mark = (name) => {evidence.push({name, result: 'PASS'}); console.log(`PASS: ${name}`);};
function code(key) {
  const count = Buffer.alloc(8);
  count.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const hash = createHmac('sha1', Buffer.from(key, 'hex')).update(count).digest();
  const offset = hash.at(-1) & 15;
  return String((hash.readUInt32BE(offset) & 0x7fffffff) % 1000000).padStart(6, '0');
}
try {
  await mkdir(shots, {recursive: true, mode: 0o700});
  manage('create'); created = true;
  const fixture = JSON.parse(droplet ? dockerRun(['cat', '/data/acceptance/browser-fixture.json']).toString() : await readFile(state, 'utf8'));
  if (droplet) {
    await writeFile(upload, dockerRun(['cat', fixture.upload]), {mode: 0o600});
    fixture.upload = upload;
  }
  browser = await chromium.launch({headless: true});
  const context = await browser.newContext({ignoreHTTPSErrors: droplet}); // Local Caddy development CA only.
  const admin = await context.newPage();
  await admin.setViewportSize({width: 1280, height: 900});
  const failures = [];
  admin.on('pageerror', (error) => failures.push(error.message));
  await admin.goto(`${cms}/admin/`);
  await admin.locator('#id_username').fill(fixture.username);
  await admin.locator('#id_password').fill(fixture.password);
  await admin.locator('#id_otp_token').fill(code(fixture.otp_key));
  await admin.locator('input[type=submit]').click();
  await admin.waitForURL(`${cms}/admin/`);
  assert.equal(await admin.locator('table caption').count(), 1);
  assert.equal(await admin.locator('tbody tr.model-project, tbody tr.model-rate').count(), 2);
  await admin.screenshot({path: `${shots}/admin-home.png`, fullPage: true});
  mark('Mandatory 2FA login and two editor sections');

  await admin.goto(`${cms}/admin/content/project/add/`);
  await admin.locator('#id_title').fill('Browser upload acceptance');
  await admin.locator('#id_description').fill('Uploaded through the real browser form.');
  await admin.locator('#id_category').selectOption('finishing');
  await admin.locator('#id_status').selectOption('published');
  await admin.locator('#id_photographs').setInputFiles(fixture.upload);
  await admin.locator('input[name=_save]').click();
  await admin.waitForURL(`${cms}/admin/content/project/`);
  mark('Browser photo upload and immediate publication');

  const projectData = await (await fetch(`${cms}/api/projects/`)).json();
  const uploaded = projectData.data.find((row) => row.title === 'Browser upload acceptance');
  assert.ok(uploaded && uploaded.photos.length === 1);
  await admin.goto(`${cms}/admin/content/project/${uploaded.id}/change/`);
  await admin.locator('#id_description').fill('Updated description <script>alert("xss")</script>');
  await admin.locator('input[name=_save]').click();
  await admin.waitForURL(`${cms}/admin/content/project/`);
  mark('Description edit through admin');

  await admin.goto(`${cms}/admin/content/rate/${fixture.rates[1]}/change/`);
  await admin.locator('#id_amount_from').fill('28.50');
  await admin.locator('input[name=_save]').click();
  await admin.waitForURL(`${cms}/admin/content/rate/`);
  const rates = await (await fetch(`${cms}/api/rates/`)).json();
  assert.equal(rates.data.find((row) => row.id === fixture.rates[1]).amount_from, '28.50');
  assert.equal(rates.data.length, 3);
  assert.ok(!JSON.stringify(rates).includes('PRIVATE ACCEPTANCE RATE'));
  mark('Rates edit; private rate excluded');

  const page = await context.newPage();
  await page.setViewportSize({width: 1440, height: 1000});
  page.on('pageerror', (error) => failures.push(error.message));
  for (const locale of ['', 'pl/', 'nl/']) {
    await page.goto(`${site}/${locale}gallery/`);
    await page.waitForFunction(() => document.querySelectorAll('.work-card').length === 4);
    assert.ok(await page.locator('.work-description').filter({hasText: '<script>alert("xss")</script>'}).count());
    assert.equal(await page.locator('[data-content-list] script').count(), 0);
    await page.locator('[data-sector=electrical]').click();
    await page.waitForFunction(() => document.querySelectorAll('.work-card').length === 1);
    await page.goto(`${site}/${locale}electrical/`);
    await page.waitForFunction(() => document.querySelectorAll('.work-card').length === 1);
    await page.goto(`${site}/${locale}rates/`);
    await page.waitForFunction(() => document.querySelectorAll('.rate-card').length === 3);
  }
  mark('EN / PL / NL gallery, electrical filter and rates');
  await page.goto(`${site}/gallery/`);
  await page.waitForFunction(() => document.querySelectorAll('.work-card').length === 4);
  await page.locator('.work-card').filter({hasText: 'Acceptance finishing'}).locator('button.work-photo').click();
  assert.equal(await page.locator('dialog[open]').count(), 1);
  await page.locator('[data-photo-next]').click();
  assert.equal(await page.locator('[data-photo-position]').textContent(), '2 of 2');
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('dialog[open]').count(), 0);
  mark('Photo viewer, next photo and Escape');
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({path: `${shots}/gallery-desktop.png`, fullPage: true});
  await page.setViewportSize({width: 390, height: 844});
  for (const path of ['gallery/', 'electrical/', 'rates/']) {
    await page.goto(`${site}/${path}`);
    await page.waitForSelector('.work-card, .rate-card');
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  }
  await page.screenshot({path: `${shots}/rates-mobile.png`, fullPage: true});
  await admin.setViewportSize({width: 390, height: 844});
  await admin.goto(`${cms}/admin/content/project/${uploaded.id}/change/`);
  assert.ok(await admin.locator('#id_photographs').isVisible());
  await admin.screenshot({path: `${shots}/admin-mobile.png`, fullPage: true});
  mark('390px public pages and admin');
  assert.deepEqual(failures, []);
  mark('No browser JavaScript errors');
} finally {
  if (browser) await browser.close();
  if (created) manage('cleanup');
  if (droplet) await unlink(upload).catch(() => {});
  await writeFile(`${shots}../browser-acceptance.json`, JSON.stringify({checked_at: new Date().toISOString(), checks: evidence}, null, 2));
}
