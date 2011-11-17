import datetime
import hashlib
import random
from django.db import models
from django.db.models import Q
from django.db.models.base import ModelBase
from django.db.models.fields import Field
from django.utils.encoding import smart_str
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

    username = StringField(_('username'), unique=True, null=True)
    email = EmailField(_('email'))
    password = StringField(editable=False)
    is_active = models.BooleanField(_('active'), default=True)

    last_login = models.DateTimeField(_('last login'), null=True, editable=False)
    created = models.DateTimeField(_('created'), auto_now_add=True, editable=False)
    updated = models.DateTimeField(_('updated'), auto_now=True, editable=False)

    def __unicode__(self):
        return self.username or self.email

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
        name = self.__class__.__name__.lower()
        session_key = '_%s_id' % name
        request.session.pop(session_key, None)
        request.session.cycle_key()
        request.session[session_key] = self.pk
        self.last_login = datetime.datetime.now()
        ProfileBase.save(self)
        setattr(request, name, self)

    def logout(self, request):
        """
        Removes the authenticated profile's id from the request and deletes key
        from their session data.
        """
        name = self.__class__.__name__.lower()
        session_key = '_%s_id' % name
        request.session.pop(session_key, None)
        setattr(request, name, EmptyProfile())

    @classmethod
    def authenticate(cls, login, password):
        profiles = cls._default_manager.filter(
            Q(is_active=True) &
            (Q(email__iexact=login) | Q(username__iexact=login))
            )
        for profile in profiles:
            if profile.check_password(password):
                return profile

    @classmethod
    def login_form(cls, **kwargs):
        from .forms import LoginForm
        return LoginForm(cls.authenticate, **kwargs)

    class Meta:
        abstract = True
        ordering = ('created',)

