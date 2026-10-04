import { randomBytes } from 'node:crypto';
import { mkdir, writeFile, access } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const folder = fileURLToPath(new URL('.', import.meta.url));
try {
  await access(`${folder}.env`);
  console.log('Local configuration already exists. Secrets and data were preserved.');
} catch {
  const password = () => randomBytes(24).toString('base64url');
  const values = {
    DB_PASSWORD: password(),
    CMS_SECRET: randomBytes(48).toString('hex'),
    DJANGO_ENV: 'local',
    CMS_ALLOWED_HOSTS: '127.0.0.1,localhost',
    DB_NAME: 'arcadian_content',
    DB_USER: 'arcadian',
    DB_HOST: '127.0.0.1',
    DB_PORT: '8058',
    CMS_URL: 'http://127.0.0.1:8057',
    CMS_PORT: '8057',
    SITE_ORIGINS: 'http://127.0.0.1:8173,http://localhost:8173',
    EDITOR_USERNAME: 'editor',
    EDITOR_EMAIL: 'editor@example.com',
    EDITOR_PASSWORD: password(),
    RUNTIME_DB_USER: 'arcadian_runtime',
    RUNTIME_DB_PASSWORD: password(),
    BACKUP_DB_USER: 'arcadian_backup',
    BACKUP_DB_PASSWORD: password(),
  };
  await writeFile(`${folder}.env`, Object.entries(values).map(([key, value]) => `${key}=${value}`).join('\n') + '\n', {mode: 0o600, flag: 'wx'});
  await mkdir(`${folder}.state`, {recursive: true, mode: 0o700});
  console.log('Created private local configuration. Run the bootstrap_editor command after migrations.');
}
