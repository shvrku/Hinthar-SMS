from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from svix.webhooks import WebhookVerificationError

from people.clerk_users import upsert_from_clerk
from people.models import Student

User = get_user_model()


def _clerk_user(clerk_id, *, email='a@example.com', username='alice'):
    return {
        'id': clerk_id,
        'username': username,
        'primary_email_address_id': 'idn_1',
        'email_addresses': [{'id': 'idn_1', 'email_address': email}],
    }


@override_settings(CLERK_WEBHOOK_SECRET='whsec_test', CLERK_SECRET_KEY='sk_test')
class ClerkWebhookTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = '/api/v1/webhooks/clerk/'

    def _post(self, payload, *, verify_side_effect=None, verify_return=None):
        target = 'people.webhooks.Webhook.verify'
        if verify_side_effect is not None:
            ctx = patch(target, side_effect=verify_side_effect)
        else:
            ctx = patch(target, return_value=verify_return if verify_return is not None else payload)
        with ctx:
            return self.client.post(
                self.url,
                payload,
                format='json',
                HTTP_SVIX_ID='msg_1',
                HTTP_SVIX_TIMESTAMP='1',
                HTTP_SVIX_SIGNATURE='v1,sig',
            )

    def test_missing_secret_is_401(self):
        with override_settings(CLERK_WEBHOOK_SECRET=''):
            res = self.client.post(self.url, {'type': 'user.created'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_bad_signature_is_401(self):
        res = self._post(
            {'type': 'user.created', 'data': _clerk_user('user_new')},
            verify_side_effect=WebhookVerificationError('bad'),
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(User.objects.filter(clerk_id='user_new').exists())

    def test_created_inserts_pending(self):
        payload = {'type': 'user.created', 'data': _clerk_user('user_new', email='n@example.com', username='newbie')}
        res = self._post(payload)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        user = User.objects.get(clerk_id='user_new')
        self.assertEqual(user.role, 'pending')
        self.assertEqual(user.email, 'n@example.com')
        self.assertTrue(user.is_active)

    def test_updated_syncs_email(self):
        existing, _ = upsert_from_clerk('user_old', email='old@example.com', username='oldie')
        existing.role = 'staff'
        existing.save(update_fields=['role'])
        payload = {
            'type': 'user.updated',
            'data': _clerk_user('user_old', email='new@example.com', username='oldie'),
        }
        res = self._post(payload)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        existing.refresh_from_db()
        self.assertEqual(existing.email, 'new@example.com')
        self.assertEqual(existing.role, 'staff')

    def test_deleted_deactivates(self):
        user, _ = upsert_from_clerk('user_gone', email='g@example.com', username='gone')
        payload = {'type': 'user.deleted', 'data': {'id': 'user_gone'}}
        res = self._post(payload)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertTrue(User.objects.filter(pk=user.pk).exists())

    def test_unknown_event_is_ok(self):
        res = self._post({'type': 'session.created', 'data': {}})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data.get('ignored'), 'session.created')


@override_settings(CLERK_SECRET_KEY='sk_test')
class ClerkSyncApiTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='sync_admin', role='admin', clerk_id='user_admin_live', email='admin@example.com'
        )
        self.staff = User.objects.create_user(
            username='sync_staff', role='staff', clerk_id='user_staff_live'
        )
        self.stale = User.objects.create_user(
            username='sync_stale', role='teacher', clerk_id='user_dev_old', email='stale@example.com'
        )
        self.student = Student.objects.create(name='Linked Teacher', user=self.stale)

    def test_sync_admin_only(self):
        self.client.force_authenticate(user=self.staff)
        res = self.client.get('/api/v1/users/clerk_sync/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    @patch('people.views.list_clerk_users')
    def test_sync_report_splits_unlinked(self, list_users):
        list_users.return_value = [
            _clerk_user('user_admin_live', email='admin@example.com', username='sync_admin'),
            _clerk_user('user_staff_live', email='staff@example.com', username='sync_staff'),
            _clerk_user('user_new_clerk', email='fresh@example.com', username='fresh'),
        ]
        self.client.force_authenticate(user=self.admin)
        res = self.client.get('/api/v1/users/clerk_sync/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        clerk_ids = {item['clerk_id'] for item in res.data['clerk_unlinked']}
        django_ids = {item['id'] for item in res.data['django_unlinked']}
        self.assertEqual(clerk_ids, {'user_new_clerk'})
        self.assertIn(self.stale.id, django_ids)
        self.assertNotIn(self.admin.id, django_ids)

    @patch('people.views.get_clerk_user')
    @patch('people.views.list_clerk_users')
    def test_import_creates_only_clerk_unlinked(self, list_users, get_user):
        list_users.return_value = [
            _clerk_user('user_admin_live'),
            _clerk_user('user_new_clerk', email='fresh@example.com', username='fresh'),
        ]
        get_user.return_value = _clerk_user('user_new_clerk', email='fresh@example.com', username='fresh')
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            '/api/v1/users/clerk_import/',
            {'clerk_ids': ['user_new_clerk']},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        created = User.objects.get(clerk_id='user_new_clerk')
        self.assertEqual(created.role, 'pending')
        self.assertEqual(created.email, 'fresh@example.com')

    @patch('people.views.get_clerk_user')
    def test_import_rejects_existing_django_id(self, get_user):
        get_user.return_value = _clerk_user('user_admin_live')
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            '/api/v1/users/clerk_import/',
            {'clerk_ids': ['user_admin_live']},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_import_staff_forbidden(self):
        self.client.force_authenticate(user=self.staff)
        res = self.client.post('/api/v1/users/clerk_import/', {}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    @patch('people.views.get_clerk_user')
    def test_link_replaces_stale_id(self, get_user):
        def fake_get(clerk_id):
            if clerk_id == 'user_dev_old':
                return None
            if clerk_id == 'user_prod_new':
                return _clerk_user('user_prod_new', email='prod@example.com', username='stale')
            return None

        get_user.side_effect = fake_get
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            f'/api/v1/users/{self.stale.id}/clerk_link/',
            {'clerk_id': 'user_prod_new'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.stale.refresh_from_db()
        self.assertEqual(self.stale.clerk_id, 'user_prod_new')
        self.assertEqual(self.stale.role, 'teacher')
        self.assertEqual(self.stale.email, 'prod@example.com')
        self.student.refresh_from_db()
        self.assertEqual(self.student.user_id, self.stale.id)

    @patch('people.views.get_clerk_user')
    def test_link_400_if_current_id_in_clerk(self, get_user):
        get_user.return_value = _clerk_user('user_admin_live')
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            f'/api/v1/users/{self.admin.id}/clerk_link/',
            {'clerk_id': 'user_prod_new'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('people.views.get_clerk_user')
    def test_link_400_if_new_id_already_used(self, get_user):
        def fake_get(clerk_id):
            if clerk_id == 'user_dev_old':
                return None
            if clerk_id == 'user_admin_live':
                return _clerk_user('user_admin_live')
            return None

        get_user.side_effect = fake_get
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            f'/api/v1/users/{self.stale.id}/clerk_link/',
            {'clerk_id': 'user_admin_live'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('people.views.get_clerk_user')
    def test_link_404_if_new_clerk_missing(self, get_user):
        def fake_get(clerk_id):
            return None

        get_user.side_effect = fake_get
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            f'/api/v1/users/{self.stale.id}/clerk_link/',
            {'clerk_id': 'user_missing'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_link_staff_forbidden(self):
        self.client.force_authenticate(user=self.staff)
        res = self.client.post(
            f'/api/v1/users/{self.stale.id}/clerk_link/',
            {'clerk_id': 'user_prod_new'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
