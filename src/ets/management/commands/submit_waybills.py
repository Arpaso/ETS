### -*- coding: utf-8 -*- ####################################################

from datetime import datetime

from .sync_compas import Command as UpdateCompas

from ets.utils import send_dispatched, send_received, import_stock
from ets.models import Waybill

class Command(UpdateCompas):

    help = 'Submits waybills and updates stocks'
    lock_file_name = 'submit_waybills'
    log_name = 'submit_waybills.log'

    def synchronize(self, compas):
        
        for waybill in Waybill.objects.filter(transport_dispach_signed_date__lte=datetime.now(), 
                                              validated=True, sent_compas__isnull=True,
                                              order__warehouse__compas__pk=compas,
                                              order__warehouse__compas__read_only=False):
        
            send_dispatched(waybill, compas)
        
        for waybill in Waybill.objects.filter(receipt_signed_date__lte=datetime.now(), 
                                              receipt_validated=True, receipt_sent_compas__isnull=True,
                                              destination__compas__pk=compas,
                                              destination__compas__read_only=False):
            send_received(waybill, compas)
            
        import_stock(compas)
