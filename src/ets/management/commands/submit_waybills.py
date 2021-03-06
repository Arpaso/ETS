### -*- coding: utf-8 -*- ####################################################

from datetime import datetime

from ets.management.commands.sync_compas import Command as UpdateCompas

from ets.utils import send_dispatched, send_received, import_stock
from ets.models import Waybill

class Command(UpdateCompas):
    """
    Submits waybills to COMPAS. Both dispatch and receipt. Afterwards imports stock items to update quantity. 
    Accepts following arguments:
        
        --compas -- COMPAS station identifier (i.e. ISBX002 for example)
        
    """
    
    help = 'Submits waybills and updates stocks'

    def synchronize(self, compas):
        
        total = 0
        for waybill in Waybill.objects.filter(transport_dispach_signed_date__lte=datetime.now(), 
                                              validated=True, sent_compas__isnull=True,
                                              order__warehouse__compas__pk=compas.pk,
                                              order__warehouse__compas__read_only=False):
        
            if send_dispatched(waybill, compas.pk):
                total += 1
        
        for waybill in Waybill.objects.filter(receipt_signed_date__lte=datetime.now(), 
                                              receipt_validated=True, receipt_sent_compas__isnull=True,
                                              destination__compas__pk=compas.pk,
                                              destination__compas__read_only=False):
            
            if send_received(waybill, compas.pk):
                total += 1
        
        if total:
            import_stock(compas.pk)
