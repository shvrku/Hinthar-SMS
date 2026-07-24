import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0007_alter_staff_contact_alter_student_contact_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='teacher',
            name='join_date',
            field=models.DateField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name='teacher',
            name='school_code',
            field=models.CharField(blank=True, default='HIS', max_length=10),
        ),
        migrations.AddField(
            model_name='teacher',
            name='unique_code',
            field=models.CharField(blank=True, db_index=True, editable=False, max_length=50, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='student',
            name='school_code',
            field=models.CharField(blank=True, default='HIS', max_length=10),
        ),
        migrations.AddField(
            model_name='student',
            name='unique_code',
            field=models.CharField(blank=True, db_index=True, editable=False, max_length=50, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='student',
            name='exam_candidate_number',
            field=models.CharField(blank=True, db_index=True, max_length=50, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='staff',
            name='join_date',
            field=models.DateField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name='staff',
            name='school_code',
            field=models.CharField(blank=True, default='HIS', max_length=10),
        ),
        migrations.AddField(
            model_name='staff',
            name='unique_code',
            field=models.CharField(blank=True, db_index=True, editable=False, max_length=50, null=True, unique=True),
        ),
    ]
