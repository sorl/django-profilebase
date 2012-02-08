from .models import _profiles


def profile(request):
    context = {}
    for model in _profiles:
        profile = getattr(request, model.__namelow__, None)
        if profile is not None:
            context[model.__namelow__] = profile
    return context

