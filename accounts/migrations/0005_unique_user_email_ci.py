from django.db import migrations

# Django's User model does not enforce unique emails. Employees are identified by email
# (ELM-003) and "Forgot password" looks accounts up by it, so enforce it in PostgreSQL:
# case-insensitive, ignoring accounts without an email. The API also checks this first
# to give a friendly message; the index closes the race between two concurrent requests.


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_profile_department_employee_code"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE UNIQUE INDEX accounts_user_email_ci_uniq "
                "ON auth_user (LOWER(email)) WHERE email <> '';"
            ),
            reverse_sql="DROP INDEX IF EXISTS accounts_user_email_ci_uniq;",
        ),
    ]
