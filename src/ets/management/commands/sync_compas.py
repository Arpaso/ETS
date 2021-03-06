### -*- coding: utf-8 -*- ####################################################

from optparse import make_option

from django.core.management.base import BaseCommand
from django.conf import settings

LOG_DIRECTORY = settings.LOG_DIRECTORY


class Command(BaseCommand):
    """
    Import stock items and orders from COMPAS stations. 
    Accepts following arguments:
        
        --compas -- COMPAS station identifier (i.e. ISBX002 for example)
        
    """
    option_list = BaseCommand.option_list + ( 
        make_option('--compas', dest='compas', default='',
            help='Tells the system to synchronize only this one compas station'),
    )

    help = 'Import orders plus stocks from COMPAS stations'
    
    def synchronize(self, compas):
        """Exact method to proceed synchronization"""
        compas.update(base=False)

    def handle(self, compas='', *args, **options):
        from ets.models import Compas
        
        stations = Compas.objects.all()
        if compas:
            stations = stations.filter(pk=compas)
            
        for compas in stations:
            self.synchronize(compas=compas)
