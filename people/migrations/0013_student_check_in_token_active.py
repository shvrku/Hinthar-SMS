from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0012_remove_payroll_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='check_in_token_active',
            field=models.BooleanField(default=True),
        ),
    ]
