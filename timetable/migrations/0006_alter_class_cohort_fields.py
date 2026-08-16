from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("timetable", "0005_classstudent_idx_class_student_rel"),
    ]

    operations = [
        migrations.AlterField(
            model_name="class",
            name="cohort_sub_category",
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
    ]
