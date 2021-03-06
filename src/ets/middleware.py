
from django.contrib.auth.views import login
from django.utils.translation import ugettext

from piston.authentication import NoAuthentication

class RequiredAuthenticationMiddleware(object):
    """Middleware that forces every user to be authenticated. Otherwise returns login form."""
    def process_view(self, request, view_func, view_args, view_kwargs):
        
        #DIRTY HACK. CHANGE IT LATER.
        if hasattr(view_func, 'authentication')\
        and not (isinstance(view_func.authentication, NoAuthentication) and view_func.authentication):
            return
        
        if not request.user.is_authenticated():
            return login(request, extra_context={"extra_error": ugettext("The system requires you to be authenticated.")})
        elif not request.user.is_active:
            return login(request, extra_context={"extra_error": ugettext("Your account is not active.")})
