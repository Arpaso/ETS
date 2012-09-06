### -*- coding: utf-8 -*- ####################################################

from functools import wraps

from django.conf import settings
from django.core.management import call_command

from ets.models import Compas, CommodityCategory

def change_settings(func, **kwargs):
    @wraps(func)
    def wrapper(*args, **kwargs):
        old_settings = {}
        for name, value in kwargs:
            old_settings[name] = getattr(settings, name)
            setattr(settings, value)
            
        result = func(*args, **kwargs)
        
        for name, value in kwargs:
            setattr(settings, old_settings[name])
        
        return result
    
    return wrapper

class TestCaseMixin(object):
    
    #multi_db = True
    compas = 'ISBX002'
    fixtures = ('db_compas.json', 'groups.json', 'permissions.json', 'warehouse.json')
    
    def setUp(self):
        "Hook method for setting up the test fixture before exercising it."
        for cat in CommodityCategory.objects.all():
            print cat.code
        call_command('loaddata', 'compas.json', verbosity=0, commit=False, database=self.compas)
        
        station = Compas.objects.get(pk=self.compas)
        station.update(base=True)
        station.update(base=False)
        call_command('loaddata', 'development.json', verbosity=0, commit=False, database='default')


