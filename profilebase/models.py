import datetime
import hashlib
import random
from .utils import uncamel
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import models
from django.db.models.base import ModelBase
from django.db.models.fields import Field
from django.http import HttpResponseRedirect
from django.template.loader import render_to_string
from django.utils.encoding import smart_str
from django.utils.http import urlquote
from django.utils.translation import ugettext_lazy as _
from stringfield import StringField, EmailField


_profiles = []


class ProfileBaseMeta(ModelBase):
    """
    Meta class for abstract class ``ProfileBase``. This class hides the model
    fields on allocation so that you can pick them up or not in a meta class
    that inherits this.
    """
    base_fields = {}

    def __new__(cls, name, bases, attrs):
        for k, v in attrs.items():
            if isinstance(v, Field):
                cls.base_fields[k] = attrs.pop(k)
        return ModelBase.__new__(cls, name, bases, attrs)


class ProfileMeta(ProfileBaseMeta):
    """
    This is what implementing User class need to use
    """
    def __new__(cls, name, bases, attrs):
        # inject Profile fields
        for k, v in cls.base_fields.items():
            if k not in attrs:
                attrs[k] = cls.base_fields[k]
        model = ModelBase.__new__(cls, name, bases, attrs)
        model.__namelow__ = uncamel(model.__name__)
        _profiles.append(model)
        return model


class EmptyProfile(object):
    def is_authenticated(self):
        return False

    def __nonzero__(self):
        return False

    def __getattr__(self, name):
        return ''


class ProfileBase(models.Model):
    __metaclass__ = ProfileBaseMeta

    email = EmailField(_('email'), unique=True)
    password = StringField(editable=False)
    is_active = models.BooleanField(_('active'), default=True)

    last_login = models.DateTimeField(_('last login'), null=True, editable=False)
    created = models.DateTimeField(_('created'), auto_now_add=True, editable=False)
    updated = models.DateTimeField(_('updated'), auto_now=True, editable=False)

    def login_url(self, next_=''):
        return '/login/?next=%s' % next_

    def __unicode__(self):
        return self.email

    def is_authenticated(self):
        return True

    def set_password(self, raw_password):
        if not raw_password:
            self.password = '!'
        else:
            raw_password = smart_str(raw_password)
            salt = str(random.getrandbits(128))[:10]
            hash_ = hashlib.sha1(salt + raw_password).hexdigest()
            self.password = '%s$%s' % (salt, hash_)

    def check_password(self, raw_password):
        if '$' not in self.password:
            return False
        raw_password = smart_str(raw_password)
        salt, hash_ = map(smart_str, self.password.split('$'))
        return hashlib.sha1(salt + raw_password).hexdigest() == hash_

    def login(self, request):
        """
        Persist a profile id in the request. This way a profile doesn't have to
        reauthenticate on every request.
        """
        session_key = '_%s_id' % self.__namelow__
        request.session.pop(session_key, None)
        request.session.cycle_key()
        request.session[session_key] = self.pk
        self.last_login = datetime.datetime.now()
        ProfileBase.save(self)
        setattr(request, self.__namelow__, self)

    @classmethod
    def logout(cls, request):
        """
        Removes the authenticated profile's id from the request and deletes key
        from their session data.
        """
        session_key = '_%s_id' % cls.__namelow__
        request.session.pop(session_key, None)
        setattr(request, cls.__namelow__, EmptyProfile())

    @classmethod
    def profile_required(cls, view):
        """
        Check that a profile for this class is authenticated
        """
        def wrapped(request, *args, **kwargs):
            profile = getattr(request, cls.__namelow__, None)
            if not profile.is_authenticated():
                path = urlquote(request.get_full_path())
                return HttpResponseRedirect(cls.login_url(path))
            return view(request, *args, **kwargs)
        return wrapped

    @classmethod
    def authenticate(cls, login, password):
        profiles = cls.get_profiles(login)
        for profile in profiles:
            if profile.check_password(password):
                return profile

    @classmethod
    def get_profiles(cls, login):
        profiles = cls._default_manager.filter(
            is_active=True, email__iexact=login
            )
        return profiles

    @classmethod
    def make_password_reset_key(cls, code):
        return 'profilebase.reset.%s.%s' % (cls.__namelow__, code)

    @classmethod
    def get_profile_by_code(cls, code):
        cache_key = cls.make_password_reset_key(code)
        profile_id = cache.get(cache_key)
        try:
            return cls._default_manager.get(pk=profile_id)
        except cls.DoesNotExist:
            return None

    def send_password_reset(self, timeout=3600):
        import uuid
        code = uuid.uuid4().hex
        cache_key = self.make_password_reset_key(code)
        cache.set(cache_key, self.pk, timeout)
        ctx = { 'code': code, 'profile': self }
        text = render_to_string('profilebase/password_reset_email.txt', ctx)
        send_mail('Reset password', text, settings.DEFAULT_FROM_EMAIL,
            [self.email], fail_silently=False)

    @classmethod
    def login_form(cls, **kwargs):
        from .forms import LoginForm
        return LoginForm(cls.authenticate, **kwargs)

    @classmethod
    def password_reset_form(cls, **kwargs):
        from .forms import PasswordResetForm
        return PasswordResetForm(cls, **kwargs)

    class Meta:
        abstract = True
        ordering = ('created',)

