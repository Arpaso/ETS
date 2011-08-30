### -*- coding: utf-8 -*- ####################################################
from django.test import TestCase
from django.core.management import call_command
from django.core.urlresolvers import reverse

import ets.models
from .utils import TestCaseMixin

class WarehouseTestCase(TestCaseMixin, TestCase):
    
    def setUp(self):
        "Hook method for setting up the test fixture before exercising it."
        
        super(WarehouseTestCase, self).setUp()
        
        self.client.login(username='admin', password='admin')
        self.user = ets.models.User.objects.get(username="admin")
        self.waybill = ets.models.Waybill.objects.get(pk="ISBX00211A")
        self.order = ets.models.Order.objects.get(pk='OURLITORDER')
        self.warehouse = ets.models.Warehouse.objects.get(pk="ISBX002")
    
    def test_get_warehouses(self):
        """Check method get_warehouses for model Warehouse"""
        # Synchronizes data with compas database
        call_command('sync_compas', nodelete=True)
        # Get warehouses without organization, only location 
        location = ets.models.Location.objects.get(pk="OE7X")
        warehouses = ets.models.Warehouse.get_warehouses(location=location)
        self.assertEqual(warehouses.count(),1)
        self.assertEqual(warehouses[0].name, "EDO OFFICE MEHTI")
        # Get warehouses with organization and location
        location = ets.models.Location.objects.get(code="ISBX")
        ogranization = ets.models.Consignee.objects.get(code="DOEAF")
        warehouses = ets.models.Warehouse.get_warehouses(location=location, organization=ogranization)
        self.assertEqual(warehouses.count(),2)
    
    def test_get_view_stock(self):
        response = self.client.get(reverse('view_stock', kwargs={'warehouse_pk': self.warehouse.pk}))
        self.assertEqual(response.status_code, 200)  