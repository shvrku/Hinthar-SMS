# Generated manually for communications app

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Tag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80, unique=True)),
                ('slug', models.SlugField(blank=True, max_length=100, unique=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Announcement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('slug', models.SlugField(blank=True, max_length=280, unique=True)),
                ('body', models.TextField()),
                ('status', models.CharField(choices=[('published', 'Published'), ('archived', 'Archived')], default='published', max_length=20)),
                ('is_featured', models.BooleanField(default=False)),
                ('is_pinned', models.BooleanField(default=False)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('author', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='announcements', to=settings.AUTH_USER_MODEL)),
                ('tags', models.ManyToManyField(blank=True, related_name='announcements', to='communications.tag')),
            ],
            options={
                'ordering': ['-is_featured', '-is_pinned', '-published_at', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('slug', models.SlugField(blank=True, max_length=280, unique=True)),
                ('summary', models.CharField(blank=True, max_length=500)),
                ('body', models.TextField(blank=True)),
                ('audience', models.CharField(choices=[('internal', 'Internal'), ('external', 'External')], default='internal', max_length=20)),
                ('registration_mode', models.CharField(choices=[('instant_waitlist', 'Instant with waitlist'), ('approval_required', 'Approval required')], default='instant_waitlist', max_length=30)),
                ('status', models.CharField(choices=[('published', 'Published'), ('closed', 'Closed'), ('cancelled', 'Cancelled')], default='published', max_length=20)),
                ('starts_at', models.DateTimeField()),
                ('ends_at', models.DateTimeField(blank=True, null=True)),
                ('location', models.CharField(blank=True, max_length=255)),
                ('registration_opens_at', models.DateTimeField(blank=True, null=True)),
                ('registration_closes_at', models.DateTimeField(blank=True, null=True)),
                ('capacity', models.PositiveIntegerField(blank=True, null=True)),
                ('cover_image_url', models.URLField(blank=True, max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='events_created', to=settings.AUTH_USER_MODEL)),
                ('tags', models.ManyToManyField(blank=True, related_name='events', to='communications.tag')),
            ],
            options={
                'ordering': ['-starts_at'],
            },
        ),
        migrations.CreateModel(
            name='EventRegistration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('confirmed', 'Confirmed'), ('waitlisted', 'Waitlisted'), ('pending', 'Pending'), ('cancelled', 'Cancelled')], max_length=20)),
                ('staff_note', models.TextField(blank=True)),
                ('registered_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='registrations', to='communications.event')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='event_registrations_reviewed', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='event_registrations', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['registered_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='eventregistration',
            constraint=models.UniqueConstraint(fields=('event', 'user'), name='unique_event_registration_per_user'),
        ),
    ]
