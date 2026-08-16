from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from people.models import AuditLog, Student, Teacher, Subject
from timetable.models import Class, TimetableSlot

User = get_user_model()


class AuditLogApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='audit_admin', role='admin', clerk_id='audit_admin'
        )
        self.staff = User.objects.create_user(
            username='audit_staff', role='staff', clerk_id='audit_staff'
        )
        self.teacher_user = User.objects.create_user(
            username='audit_teacher', role='teacher', clerk_id='audit_teacher'
        )

    def test_creating_student_writes_readable_log(self):
        self.client.force_authenticate(user=self.staff)
        res = self.client.post(
            '/api/v1/students/',
            {'name': 'Ada Lovelace', 'school_code': 'HIS'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        log = AuditLog.objects.get(category='student', action='create')
        self.assertEqual(log.summary, 'Created student Ada Lovelace')
        self.assertEqual(log.user_id, self.staff.id)

    def test_staff_can_list_audit_logs(self):
        AuditLog.objects.create(
            category='student',
            summary='Created student Ada Lovelace',
            model_name='Student',
            record_id='1',
            action='create',
        )
        self.client.force_authenticate(user=self.staff)
        res = self.client.get('/api/v1/audit-logs/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        rows = res.data['results'] if isinstance(res.data, dict) else res.data
        self.assertTrue(any(row['summary'] == 'Created student Ada Lovelace' for row in rows))

    def test_teacher_cannot_list_audit_logs(self):
        self.client.force_authenticate(user=self.teacher_user)
        res = self.client.get('/api/v1/audit-logs/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_generate_sessions_writes_one_summary_not_per_row(self):
        class_obj = Class.objects.create(education_level='IG', cohort_identifier='A')
        teacher = Teacher.objects.create(name='Ms. Khan')
        subject = Subject.objects.create(name='Physics')
        TimetableSlot.objects.create(
            class_obj=class_obj,
            subject=subject,
            teacher=teacher,
            day_of_week=0,
            start_time='09:00',
            end_time='10:00',
        )
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            f'/api/v1/sessions/generate/{class_obj.id}/',
            {'start_date': '2026-08-17', 'end_date': '2026-08-31'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res.data['total_created'], 2)
        creates = AuditLog.objects.filter(category='session', action='create')
        self.assertEqual(creates.count(), 1)
        self.assertIn('Generated', creates.get().summary)

    def test_qr_checkin_writes_check_in_log(self):
        terminal = User.objects.create_user(
            username='audit_terminal', role='terminal', clerk_id='audit_term'
        )
        student = Student.objects.create(
            name='Checked Student',
            check_in_token='audit_qr_token',
        )
        self.client.force_authenticate(user=terminal)
        res = self.client.post(
            '/api/v1/check-ins/qr/',
            {'check_in_token': 'audit_qr_token'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        log = AuditLog.objects.get(category='check_in', action='create')
        self.assertIn('Checked Student', log.summary)

    def test_stats_includes_trends_series_and_recent_activity(self):
        older = timezone.localdate() - timedelta(days=40)
        Student.objects.create(name='Old Student')
        Student.objects.filter(name='Old Student').update(enrollment_date=older)
        Student.objects.create(name='New Student')
        AuditLog.objects.create(
            category='student',
            summary='Created student New Student',
            model_name='Student',
            record_id='2',
            action='create',
        )
        self.client.force_authenticate(user=self.staff)
        res = self.client.get('/api/v1/stats/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('trends', res.data)
        self.assertEqual(res.data['trends']['students']['direction'], 'up')
        self.assertGreaterEqual(len(res.data['student_series']), 2)
        self.assertLessEqual(len(res.data['student_series']), 12)
        self.assertGreaterEqual(res.data['student_series'][-1]['count'], 2)
        self.assertTrue(res.data['recent_activity'])
        self.assertEqual(res.data['recent_activity'][0]['summary'], 'Created student New Student')

    def test_stats_recent_activity_skips_per_session_creates(self):
        AuditLog.objects.create(
            category='session',
            summary='Created Session #1080',
            model_name='Session',
            record_id='1080',
            action='create',
        )
        AuditLog.objects.create(
            category='session',
            summary='Generated 12 sessions for IG A',
            model_name='Session',
            record_id='',
            action='create',
        )
        AuditLog.objects.create(
            category='student',
            summary='Created student Ada',
            model_name='Student',
            record_id='1',
            action='create',
        )
        self.client.force_authenticate(user=self.staff)
        res = self.client.get('/api/v1/stats/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        summaries = [row['summary'] for row in res.data['recent_activity']]
        self.assertIn('Created student Ada', summaries)
        self.assertIn('Generated 12 sessions for IG A', summaries)
        self.assertNotIn('Created Session #1080', summaries)

    def test_role_change_writes_user_log(self):
        pending = User.objects.create_user(
            username='to_promote',
            email='promote@example.com',
            role='pending',
            clerk_id='to_promote',
        )
        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(
            f'/api/v1/users/{pending.id}/',
            {'role': 'staff'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        log = AuditLog.objects.get(category='user', action='update')
        self.assertEqual(log.user_id, self.admin.id)
        self.assertIn('pending', log.summary)
        self.assertIn('staff', log.summary)
