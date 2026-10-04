import os
import re
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from psycopg import sql


class Command(BaseCommand):
    help = 'Run with migration credentials: grant a non-DDL web role and a read-only backup role.'

    def handle(self, *args, **options):
        roles = [('RUNTIME_DB_USER', 'RUNTIME_DB_PASSWORD', False), ('BACKUP_DB_USER', 'BACKUP_DB_PASSWORD', True)]
        with connection.cursor() as cursor:
            for user_key, password_key, readonly in roles:
                name, password = os.environ.get(user_key, ''), os.environ.get(password_key, '')
                if not re.fullmatch(r'arcadian_[a-z_]+', name) or len(password) < 24:
                    raise CommandError('Dedicated role names and strong passwords must be configured.')
                cursor.execute('SELECT 1 FROM pg_roles WHERE rolname = %s', [name])
                if not cursor.fetchone():
                    cursor.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(name), sql.Literal(password)))
                cursor.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(connection.settings_dict['NAME']), sql.Identifier(name)))
                cursor.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(name)))
                privileges = sql.SQL('SELECT') if readonly else sql.SQL('SELECT, INSERT, UPDATE, DELETE')
                cursor.execute(sql.SQL('GRANT {} ON ALL TABLES IN SCHEMA public TO {}').format(privileges, sql.Identifier(name)))
                if not readonly:
                    cursor.execute(sql.SQL('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}').format(sql.Identifier(name)))
                    # Editing audit history is not a web application's capability.
                    from content.models import Project, ProjectPhoto, Rate, RateDocument
                    for table in [model.history.model._meta.db_table for model in (Project, ProjectPhoto, Rate, RateDocument)]:
                        cursor.execute(sql.SQL('REVOKE UPDATE, DELETE ON {} FROM {}').format(sql.Identifier(table), sql.Identifier(name)))
                cursor.execute(sql.SQL('REVOKE CREATE ON SCHEMA public FROM {}').format(sql.Identifier(name)))
        self.stdout.write('Dedicated runtime and backup roles configured. Passwords were not changed.')
