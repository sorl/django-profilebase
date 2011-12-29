from .models import Profile
from django.contrib.sessions.backends.cache import SessionStore
from django.http import HttpRequest
from django.utils import unittest
from profilebase import EmptyProfile


class SimpleTestCase(unittest.TestCase):
    def setUp(self):
        self.p = Profile.objects.create(email='xxx@xxx.com')

    def tearDown(self):
        self.p.delete()

    def test_unicode(self):
        self.assertEqual(u'xxx@xxx.com', unicode(self.p))

    def test_authentication1(self):
        self.assertEqual(Profile.authenticate('xxx', 'yyy'), None)

    def test_authentication2(self):
        self.p.set_password('yyy')
        self.p.save()
        self.assertEqual(Profile.authenticate('xxx@xxx.com', 'zzz'), None)
        self.assertEqual(Profile.authenticate('xxx@xxx.com', 'yyy'), self.p)

    def test_login_logout(self):
        request = HttpRequest()
        request.session = SessionStore()
        self.p.login(request)
        self.assertEqual(request.session.get('_profile_id'), self.p.pk)
        self.assertEqual(request.profile, self.p)
        self.p.logout(request)
        self.assertEqual(request.session.get('_profile_id'), None)
        self.assertTrue(isinstance(request.profile, EmptyProfile))

