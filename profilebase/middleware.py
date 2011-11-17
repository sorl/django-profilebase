from .models import EmptyProfile, _profiles


class ProfileMiddleware(object):
    def process_request(self, request):
        assert hasattr(request, 'session'), "Edit your MIDDLEWARE_CLASSES setting to insert 'django.contrib.sessions.middleware.SessionMiddleware'."
        for model in _profiles:
            name = model.__name__.lower()
            session_key = '_%s_id' % name
            pk = request.session.get(session_key)
            if pk is not None:
                try:
                    setattr(request, name, model.objects.get(is_active=True, pk=pk))
                    return
                except model.DoesNotExist:
                    request.session.pop(session_key)
            setattr(request, name, EmptyProfile())

