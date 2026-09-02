from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('communications', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='tag',
            name='scope',
            field=models.CharField(
                choices=[('announcement', 'Announcement'), ('event', 'Event')],
                default='announcement',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='tag',
            name='name',
            field=models.CharField(max_length=80),
        ),
        migrations.AlterField(
            model_name='tag',
            name='slug',
            field=models.SlugField(blank=True, max_length=100),
        ),
        migrations.AddConstraint(
            model_name='tag',
            constraint=models.UniqueConstraint(fields=('name', 'scope'), name='unique_tag_name_per_scope'),
        ),
        migrations.AddConstraint(
            model_name='tag',
            constraint=models.UniqueConstraint(fields=('slug', 'scope'), name='unique_tag_slug_per_scope'),
        ),
    ]
