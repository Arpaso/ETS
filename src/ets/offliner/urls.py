
from django.conf import settings
from django.conf.urls.defaults import patterns, include, handler404, handler500
from django.contrib import databrowse
from django.contrib.auth.decorators import login_required
from django.views.generic.simple import direct_to_template
from django.views.generic.list_detail import object_detail, object_list
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.utils.translation import ugettext as _

from django.contrib import admin #@Reimport
admin.autodiscover()

from .views import ExportWaybillData

urlpatterns = patterns("ets.offliner.views",
    #( r'^synchronization/$', "synchronization", {}, "synchronization"),
    ( r'^synchronize/$', "request_update", {}, "synchronize" ),
    
    ( r'^export/waybills/$', ExportWaybillData.as_view(), {}, "export_waybills" ),
)
