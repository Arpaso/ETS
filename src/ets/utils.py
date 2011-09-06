from datetime import datetime

from django.db import connections, transaction
from django.db.utils import DatabaseError
from django.conf import settings
from django.contrib.auth.models import User, UNUSABLE_PASSWORD

import compas.models as compas_models
import models as ets_models

TOTAL_WEIGHT_METRIC = 1000


def update_compas(using):
    
    send_dispatched(using)
    
    send_received(using)
    
    #Update places
    import_places(using)
    
    #Update persons
    import_persons(using)
    
    #Update stocks
    import_stock(using)
    
    #Update loss/damage types
    ets_models.LossDamageType.update(using)
    
    #Update orders
    import_order(using)


def import_places(compas):
    for place in compas_models.Place.objects.using(compas).filter(country_code__in = settings.COUNTRIES,
                                                               reporting_code=compas):
            
        #Create location
        location = ets_models.Location.objects.get_or_create(code=place.geo_point_code, defaults={
            'name': place.geo_name,
            'country': place.country_code,
        })[0]
        
        #Create consignee organization
        organization = ets_models.Organization.objects.get_or_create(code=place.organization_id)[0]\
                        if place.organization_id else None
        
        #Update warehouse
        defaults = {
            'name': place.name,
            'location': location,
            'organization': organization,
            'compas': ets_models.Compas.objects.get(pk=place.reporting_code),
        }
        
        rows = ets_models.Warehouse.objects.filter(code=place.org_code).update(**defaults)
        if not rows:
            ets_models.Warehouse.objects.create(code=place.org_code, **defaults)


def import_persons(compas):
    for person in compas_models.CompasPerson.objects.using(compas).filter(org_unit_code=compas):
        try:
            person = ets_models.Person.objects.get(pk=person.person_pk)
        except ets_models.Person.DoesNotExist:
            user = User.objects.create(username=person.person_pk, password=UNUSABLE_PASSWORD,
                                       email=person.email,
                                       first_name = person.first_name, last_name = person.last_name, 
                                       is_staff=False, is_active=False, is_superuser=False)
            person = ets_models.Person.objects.create(user=user, person_pk=person.person_pk, title=person.title,
                                           code=person.code, compas_id=person.org_unit_code, 
                                           organization_id=person.organization_id, 
                                           location_id=person.location_code)


def import_stock(compas):
    """Executes Imports of Stock"""
    
    now = datetime.now()
    
    for stock in compas_models.EpicStock.objects.using(compas):
        
        #Create commodity's category
        category = ets_models.CommodityCategory.objects.get_or_create(pk=stock.comm_category_code)[0]
        
        #Create commodity
        commodity = ets_models.Commodity.objects.get_or_create(pk=stock.commodity_code, defaults={
            'name': stock.cmmname,
            'category': category, 
        })[0]
        
        #Create package
        package = ets_models.Package.objects.get_or_create(pk=stock.package_code, 
                                                           defaults={'name': stock.packagename})[0]
        
        #Check package type. If 'BULK' then modify number and weight
        number_of_units, quantity_net = (stock.quantity_net, stock.number_of_units) if stock.is_bulk() \
                                        else (stock.number_of_units, stock.quantity_net)
        
        defaults = {
            'warehouse': ets_models.Warehouse.objects.get(pk=stock.wh_code),
            'project_number': stock.project_wbs_element,
            'si_code': stock.si_code,
            'commodity': commodity,
            'package': package,
            'number_of_units': number_of_units,
            'quality_code': stock.qualitycode,
            'quality_description': stock.qualitydescr,
            'unit_weight_net': number_of_units and TOTAL_WEIGHT_METRIC*quantity_net/number_of_units,
            'unit_weight_gross': number_of_units and TOTAL_WEIGHT_METRIC*stock.quantity_gross/number_of_units,
            
            'allocation_code': stock.allocation_code,
            'is_bulk': stock.is_bulk(),
            
            'updated': now,
        }
        
        rows = ets_models.StockItem.objects.filter(origin_id=stock.origin_id).update(**defaults)
        if not rows:
            ets_models.StockItem.objects.create(origin_id=stock.origin_id, **defaults)
    
    #Flush empty stocks
    ets_models.StockItem.objects.filter(number_of_units__gt=0).exclude(updated=now).update(number_of_units=0)


def import_order(compas):
    """Imports all LTIs from COMPAS"""
    now = datetime.now()

    original = compas_models.LtiOriginal.objects.using(compas).filter(requested_dispatch_date__gt = settings.MAX_DATE)
    if not settings.DISABLE_EXPIERED_LTI:
        original = original.filter( expiry_date__gt = now )
    
    for lti in original:
        
        #Update Consignee
        # TODO: correct epic_geo view. It should contain organization name field. Then we will be able to delete this
        consignee = ets_models.Organization.objects.get(pk=lti.consegnee_code)
        
        if not consignee.name:
            consignee.name = lti.consegnee_name
            consignee.save()
        
        #Create Order
        defaults = {
            'created': lti.lti_date,
            'expiry': lti.expiry_date,
            'dispatch_date': lti.requested_dispatch_date,
            'transport_code': lti.transport_code,
            'transport_ouc': lti.transport_ouc,
            'transport_name': lti.transport_name,
            'origin_type': lti.origin_type,
            'project_number': lti.project_wbs_element,
            'warehouse': ets_models.Warehouse.objects.get(code=lti.origin_wh_code),
            'consignee': consignee,
            'location': ets_models.Location.objects.get(pk=lti.destination_location_code),
            'updated': now,
        }
        
        order = ets_models.Order.objects.get_or_create(code=lti.code, defaults=defaults)[0]
        
        #Create order item
        defaults = {
            'order': order,
            'si_code': lti.si_code,
            'commodity': ets_models.Commodity.objects.get(pk=lti.commodity_code),
            'number_of_units': lti.number_of_units,
        }
        
        rows = ets_models.OrderItem.objects.filter(lti_pk=lti.lti_pk).update(**defaults)
        if not rows:
            ets_models.OrderItem.objects.create(lti_pk=lti.lti_pk, **defaults)


def send_dispatched(using):
    for waybill in ets_models.Waybill.objects.filter(transport_dispach_signed_date__lte=datetime.now(), 
                                                     validated=True, sent_compas=False,
                                                     order__warehouse__compas__pk=using):
        with transaction.commit_on_success(using=using) as tr:
            
            CURR_CODE = u"%s%s" % (datetime.now().strftime( '%y' ), waybill.pk)
            
            CONTAINER_NUMBER = waybill.container_one_number
    
            special_case = waybill.loading_details.count() == 2 and waybill.container_two_number
            code_letter = u'A'
    
            for index, loading in enumerate( waybill.loading_details.all() ):
                
                if special_case:
                    CURR_CODE = u"%s%s%s" % (datetime.now().strftime( '%y' ), code_letter, waybill.pk)
                    code_letter = u'B'
                    if index == 1:
                        CONTAINER_NUMBER = waybill.container_two_number
            
                is_bulk = loading.stock_item.is_bulk
                
                call_db_procedure('write_waybill.dispatch', (
                    CURR_CODE, 
                    waybill.dispatch_date.strftime( "%Y%m%d" ), 
                    waybill.order.origin_type, 
                    waybill.order.warehouse.location.pk, 
                    waybill.order.warehouse.pk,
                    '', 
                    waybill.order.location.pk, 
                    waybill.order.consignee.pk, 
                    waybill.order.pk, 
                    waybill.loading_date.strftime( "%Y%m%d" ),
                    waybill.order.consignee.pk, 
                    waybill.transaction_type, 
                    waybill.transport_vehicle_registration, 
                    waybill.transport_type,
                    waybill.dispatch_remarks, 
                    waybill.dispatcher_person.code, 
                    waybill.dispatcher_person.compas, 
                    waybill.dispatcher_person.title, 
                    waybill.order.transport_code, 
                    waybill.order.transport_ouc,
                    waybill.transport_driver_name, 
                    waybill.transport_driver_licence, 
                    CONTAINER_NUMBER, 
                    using,
                    loading.stock_item.pk, 
                    loading.stock_item.commodity.category.pk, 
                    loading.stock_item.commodity.pk, 
                    loading.stock_item.package.pk, 
                    loading.stock_item.allocation_code, 
                    loading.stock_item.quality_code,
                    
                    u'%.3f' % loading.calculate_total_net(), 
                    u'%.3f' % loading.calculate_total_gross(), 
                    u'%.3f' % (1 if is_bulk else loading.number_of_units), 
                    u'' if is_bulk else u'%.3f' % loading.stock_item.unit_weight_net, 
                    u'' if is_bulk else u'%.3f' % loading.stock_item.unit_weight_gross, 
                    
                    '', '', '' 
                ), using)
            
            waybill.sent_compas = True
            waybill.save()

def send_received(using):
    for reception in ets_models.ReceiptWaybill.objects.filter(signed_date__lte=datetime.now(), 
                                                              validated=True, sent_compas=False,
                                                              waybill__destination__compas__pk=using):
        waybill = reception.waybill
        with transaction.commit_on_success(using=using) as tr:
            
            CURR_CODE = u"%s%s" % (datetime.now().strftime( '%y' ), waybill.pk)

            ## check if containers = 2 & lines = 2
            special_case = waybill.loading_details.count() == 2 and waybill.container_two_number
            code_letter = u'A'
            
            for loading in waybill.loading_details.all():
                
                if special_case:
                    CURR_CODE = u"%s%s%s" % (datetime.now().strftime( '%y' ), code_letter, waybill.pk)
                    code_letter = u'B'
                
                call_db_procedure('write_waybill.receipt', (
                    CURR_CODE, 
                    reception.person.compas.pk, 
                    reception.person.code, 
                    reception.arrival_date.strftime("%Y%m%d"),
                    loading.number_units_good, 
                    loading.units_damaged_reason and loading.units_damaged_reason.cause or '', 
                    loading.number_units_damaged or '', 
                    loading.units_lost_reason and loading.units_lost_reason.cause or '', 
                    loading.number_units_lost or '', 
                    loading.stock_item.pk, 
                    loading.stock_item.commodity.category.pk,
                    loading.stock_item.commodity.pk, 
                    loading.stock_item.package.pk, 
                    loading.stock_item.allocation_code, 
                    loading.stock_item.quality_code
                ), using)
                
        waybill.sent_compas = True
        waybill.save()
        

def call_db_procedure(name, parameters, using):
    import cx_Oracle
    cursor = connections[using].cursor()
    Response_Message = cursor.var( cx_Oracle.STRING )
    Response_Message.setvalue( 0, u' ' * 200 )
    Response_Code = cursor.var( cx_Oracle.STRING )
    Response_Code.setvalue( 0, u' ' * 2 )
    
    cursor.callproc( name, (Response_Message, Response_Code,)+parameters)