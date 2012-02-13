import datetime
import hashlib
import random
import uuid
from .utils import uncamel
from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.core.urlresolvers import reverse, NoReverseMatch
from django.db import models
from django.db.models.base import ModelBase
from django.db.models.fields import Field
from django.http import HttpResponseRedirect
from django.template.loader import render_to_string
from django.utils.encoding import smart_str
from django.utils.http import urlquote
from django.utils.translation import ugettext_lazy as _
from functools import wraps
from stringfield import StringField, EmailField


RESET_TIMEOUT = 3600 * 24
CACHE_KEY = 'password.reset.%s.%s'
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
        if model not in _profiles:
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

    def send_password_reset(self, timeout=RESET_TIMEOUT):
        hash_ = uuid.uuid1().hex
        cache.set(self.get_reset_key(hash_), self.pk, timeout)
        body = render_to_string('profilebase/password_reset_email.txt', {
            'profile': self,
            'hash': hash_,
            'domain': getattr(settings, 'SITE_DOMAIN', '')
        })
        msg = EmailMessage(_('Password reset'), body,
            settings.DEFAULT_FROM_EMAIL, [self.email]
            )
        msg.send()

    @classmethod
    def login_url(cls, next_=''):
        try:
            url = reverse('login')
        except NoReverseMatch:
            url = '/login'
        return '%s?next=%s' % (url, next_)

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
    def profile_required(cls, f):
        """
        Check that a profile for this class is authenticated
        """
        @wraps(f)
        def wrapper(request, *args, **kwargs):
            profile = getattr(request, cls.__namelow__)
            if not (profile.is_authenticated() and profile.is_active):
                path = urlquote(request.get_full_path())
                return HttpResponseRedirect(cls.login_url(path))
            return f(request, *args, **kwargs)
        return wrapper

    @classmethod
    def authenticate(cls, login, password):
        for profile in cls.get_profiles(login):
            if profile.check_password(password):
                return profile

    @classmethod
    def get_profiles(cls, login):
        """
        Mostly a helper method for :meth:authenticate
        """
        return cls._default_manager.filter(email__iexact=login.strip())

    @classmethod
    def get_reset_key(cls, hash_):
        return 'password.reset.%s.%s' % (cls.__namelow__, hash_)

    @classmethod
    def get_profile_by_hash(cls, hash_):
        pk = cache.get(cls.get_reset_key(hash_))
        if pk is not None:
            try:
                return cls.get_profiles().get(pk=pk)
            except cls.DoesNotExist:
                pass

    @classmethod
    def login_form(cls, **kwargs):
        from .forms import LoginForm
        return LoginForm(cls.authenticate, **kwargs)

    @classmethod
    def password_reset_form(cls, **kwargs):
        from .forms import PasswordResetForm
        return PasswordResetForm(cls.get_profiles, **kwargs)

    def new_password_form(self, **kwargs):
        from .forms import NewPasswordForm
        return NewPasswordForm(self, **kwargs)

    class Meta:
        abstract = True
        ordering = ('created',)

