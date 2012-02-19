
import datetime
from itertools import chain

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.generic.simple import direct_to_template
from django.views.decorators.http import require_POST, require_GET
from django.http import HttpResponse
from django.views.generic.edit import FormView
from django.core import serializers

from ets.models import Warehouse, Waybill, LoadingDetail
from ets.compress import compress_json, decompress_json
from ets.utils import data_to_file_response
from ets.forms import DateRangeForm

from .models import UpdateLog

@login_required
def request_update(request):
    """requests data at server and import them localy"""
    last = None
    if UpdateLog.objects.count():
        last = UpdateLog.objects.latest("date")
    UpdateLog.request_data(last)

    return redirect('synchronization')

#===============================================================================
# @login_required
# def synchronization(request, template="synchronization.html", export_form=ExportDataForm, import_form=ImportDataForm):
#    """
#    Page for synchronization
#    """
#    export_form.base_fields['warehouse'].queryset = Warehouse.objects.filter(persons__pk=request.user.pk)
#        
#    return direct_to_template(request, template, {
#        'form_import': import_form,
#        'form_export': export_form,
#    })
#===============================================================================

class ExportWaybillData(FormView):
    
    template_name = 'offliner/export_waybills.html'
    form_class = DateRangeForm
    file_name = 'waybills-%(start_date)s-%(end_date)s'
    
    def get_initial(self):
        end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=7)
        return {'start_date': start_date, 'end_date': end_date}
    
    def construct_data(self, start_date, end_date):
        #Append log entry 
        return chain(
            Waybill.objects.filter(date_modified__range=(start_date, end_date+datetime.timedelta(1))),
            LoadingDetail.objects.filter(waybill__date_modified__range=(start_date, end_date+datetime.timedelta(1)),
                                                    waybill__date_removed__isnull=True)
        )
    
    def form_valid(self, form):
        start_date = form.cleaned_data['start_date'] 
        end_date = form.cleaned_data['end_date']
        
        data = compress_json( serializers.serialize('json', self.construct_data(start_date, end_date), use_decimal=False) )
        
        return data_to_file_response(data, self.file_name % {
            'start_date': start_date, 
            'end_date': end_date,
        })
    