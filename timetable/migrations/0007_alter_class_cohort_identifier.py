from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("timetable", "0006_alter_class_cohort_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="class",
            name="cohort_identifier",
            field=models.CharField(max_length=1),
        ),
        migrations.AlterField(
            model_name="class",
            name="cohort_sub_category",
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
    ]
