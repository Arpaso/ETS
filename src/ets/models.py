
import zlib, base64, string
#from urllib import urlencode
from itertools import chain
from functools import wraps
from datetime import datetime

from django.db import models
from django.contrib.auth.models import User
from django.db.models import Sum
from django.core import serializers
from django.conf import settings
from django.utils import simplejson
from django.utils.translation import ugettext, ugettext_lazy as _
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
from django.db.models import Q

from audit_log.models.managers import AuditLog
from autoslug.fields import AutoSlugField
from autoslug.settings import slugify
from .country import COUNTRY_CHOICES

#name = "1234"
DEFAULT_TIMEOUT = 10
API_DOMAIN = "http://localhost:8000"
BULK_NAME = "BULK"

COMPAS_STATION = getattr(settings, 'COMPAS_STATION', None)
LETTER_CODE = getattr(settings, 'WAYBILL_LETTER', 'A')

# like a normal ForeignKey.
try:
    from south.modelsinspector import add_introspection_rules
    add_introspection_rules([], ['^audit_log\.models\.fields\.LastUserField'])
except ImportError:
    pass

def capitalize_slug(func):
    @wraps(func)
    def wrapper(value):
        slug = func(value)
        return slug.upper()
    
    return wrapper

#=======================================================================================================================
# Models based on compas Views & Tables
#=======================================================================================================================

class Place( models.Model ):
    """
    Location model.
    Model based on compas Views & Tables
    """

    org_code = models.CharField(_("Org code"), max_length = 7, primary_key = True )
    name = models.CharField(_("Name"), max_length = 100 )
    geo_point_code = models.CharField(_("Geo point code"), max_length = 4 )
    geo_name = models.CharField(_("Geo name"), max_length = 100 )
    country_code = models.CharField( _("Country code"), max_length = 3 )
    reporting_code = models.CharField(_("Reporting code"), max_length = 7 )
    organization_id = models.CharField( _("Organization id"), max_length = 20, blank=True )

    class Meta:
        db_table = u'epic_geo'
        ordering = ('name',)
        verbose_name=_("place")
        verbose_name_plural = _("places")

    def __unicode__( self ):
        return self.name

    @classmethod
    def update(cls):
        """Executes Imports of Place"""
        for place in cls.objects.using( 'compas' ).filter( country_code__in = settings.COUNTRIES ):
            
            #Create location
            location = Location.objects.get_or_create(code=place.geo_point_code, defaults={
                'name': place.geo_name,
                'country': place.country_code,
                'compas': place.reporting_code,
            })[0]
            
            #Create consignee organization
            organization = Consignee.objects.get_or_create(code=place.organization_id)[0]\
                            if place.organization_id else None
            
            #Update warehouse
            defaults = {
                'location': location,
                'organization': organization,
                'name': place.name,
            }
            
            rows = Warehouse.objects.filter(code=place.org_code).update(**defaults)
            if not rows:
                Warehouse.objects.create(code=place.org_code, **defaults)
            

class Location(models.Model):
    """Location model. City or region"""
    
    code = models.CharField(_("Geo point code"), max_length=4, primary_key=True)
    name = models.CharField(_("Name"), max_length=100)
    country = models.CharField( _("Country code"), max_length=3, choices=COUNTRY_CHOICES)
    compas = models.CharField(_("COMPAS station"), max_length=7)
    
    class Meta:
        ordering = ('code',)
        verbose_name = _('location')
        verbose_name_plural = _("locations")
    
    def __unicode__(self):
        return "%s %s" % (self.country, self.name)
    
class Consignee(models.Model):
    """Consignee organization"""
    
    code = models.CharField(_("Organization identifier"), max_length=20, primary_key=True)
    name = models.CharField(_("Name"), max_length = 100, blank=True)
    
    class Meta:
        ordering = ('code',)
        verbose_name = _('consignee')
        verbose_name_plural = _("consignees")
    
    def __unicode__(self):
        return self.name or self.pk

class Warehouse( models.Model ):
    """
    Dispatch warehouse. Data based
    
    >>> place, created = Place.objects.get_or_create(org_code="completely_unique_code", 
    ...                      name="The best place in the world", 
    ...                      geo_point_code = 'TEST', geo_name="Dubai", country_code="586", 
    ...                      reporting_code="SOME_CODE", )
    >>> wh, c = Warehouse.objects.get_or_create(code="test_wh", title="Perfect warehouse", 
    ...                      place=place, start_date=datetime.now())
    >>> wh
    <Warehouse: test_wh - The best place in the world - Perfect warehouse>
    """
    code = models.CharField(_("code"), max_length = 13, primary_key=True) #origin_wh_code
    name = models.CharField(_("name"),  max_length = 50, blank = True ) #origin_wh_name
    location = models.ForeignKey(Location, verbose_name=_("location"), related_name="warehouses") #origin_location_code
    organization = models.ForeignKey(Consignee, verbose_name=_("Organization"), related_name="warehouses", 
                                     blank=True, null=True)
    start_date = models.DateField(_("start date"), null=True, blank=True)
    
    
    class Meta:
        ordering = ('name',)
        order_with_respect_to = 'location'
        verbose_name = _('warehouse')
        verbose_name_plural = _("warehouses")
        
    def  __unicode__( self ):
        return "%s - %s - %s" % (self.code, self.location.name, self.name)

    @classmethod
    def get_warehouses(cls, location, organization=None):
        return cls.objects.filter(location=location).filter( Q(organization=organization) | Q(organization__isnull=True) )   
    
    #===================================================================================================================
    # def serialize(self):
    #    #wh = DispatchPoint.objects.get( id = warehouse )
    #    return serializers.serialize('json', list( LtiOriginal.objects.filter( origin_wh_code = self.origin_wh_code ) )\
    #                                        + list( EpicStock.objects.filter( wh_code = self.origin_wh_code ) ) )
    #===================================================================================================================

    
class CompasPerson( models.Model ):
    """Compas CompasPerson. We import them directly from compas Oracle using database view"""
    person_pk = models.CharField(_("person identifier"), max_length=20, blank=True, primary_key=True)
    title = models.CharField(_("title"), max_length=50, blank=True)
    last_name = models.CharField(_("last name"), max_length=30)
    first_name = models.CharField(_("first name"), max_length=25)
    code = models.CharField(_("code"), max_length=7)
    type_of_document = models.CharField(_("type of document"), max_length=2, blank=True)
    document_number = models.CharField(_("document number"), max_length=25, blank=True)
    e_mail_address = models.CharField(_("e_mail address"), max_length=100, blank=True)
    mobile_phone_number = models.CharField(_("cell phone number"), max_length=20, blank=True)
    official_tel_number = models.CharField(_("official telephone number"), max_length=20, blank=True)
    fax_number = models.CharField(_("fax_number"), max_length=20, blank=True)
    effective_date = models.DateField(_("effective date"), null=True, blank=True)
    expiry_date = models.DateField(_("expiry date "), null=True, blank=True)
    
    warehouse = models.CharField(_("warehouse"), max_length=13, db_column='org_unit_code')

    #Dummy fields
    organization_id = models.CharField(_("organization identifier"), max_length=12, editable=False)
    location_code = models.CharField(_("location"), max_length=10, editable=False)

    class Meta:
        db_table = u'epic_persons'
        ordering = ('code',)
        verbose_name = _('COMPAS User')
        verbose_name_plural = _("COMPAS users")
    
    def  __unicode__( self ):
        return "%s, %s" % (self.last_name, self.first_name)
    
    @classmethod
    def update(cls):
        warehouses = Warehouse.objects.values_list('pk', flat=True)
        for my_person in cls.objects.using('compas')\
                .filter(warehouse__in=tuple(warehouses)):
            my_person.save(using='default')


class EpicStock( models.Model ):
    """COMPAS stock. We retrieve it from Oracle database view."""
    wh_pk = models.CharField(_("warehouse primary key"), max_length = 90, blank = True, primary_key = True)
    wh_regional = models.CharField(_("warehouse regional"), max_length = 4, blank = True )
    wh_country = models.CharField(_("warehouse country"), max_length = 15 )
    wh_location = models.CharField(_("warehouse location"), max_length = 30 )
    wh_code = models.CharField(_("warehouse code"), max_length = 13 )
    wh_name = models.CharField(_("warehouse name"), max_length = 50, blank = True )
    
    project_wbs_element = models.CharField(_("Project wbs element"), max_length = 24, blank = True )
    si_record_id = models.CharField(_("SI record id "), max_length = 25 )
    si_code = models.CharField(_("SI code"), max_length = 8 )
    origin_id = models.CharField(_("Origin id"), max_length = 23 )
    
    comm_category_code = models.CharField(_("commodity category code"), max_length = 9 )
    commodity_code = models.CharField(_("commodity code "), max_length = 18 )
    cmmname = models.CharField(_("commodity name"), max_length = 100, blank = True )
    
    package_code = models.CharField(_("Package code"), max_length = 17 )
    packagename = models.CharField(_("Package name"), max_length = 50, blank = True )
    
    qualitycode = models.CharField(_("Quality code"), max_length = 1 )
    qualitydescr = models.CharField(_("Quality descr "), max_length = 11, blank = True )
    quantity_net = models.DecimalField(_("Quantity net"), null = True, max_digits = 12, decimal_places = 3, blank = True )
    quantity_gross = models.DecimalField(_("Quantity gross"), null = True, max_digits = 12, decimal_places = 3, blank = True )
    number_of_units = models.IntegerField(_("Number of units"))
    
    allocation_code = models.CharField(_("Allocation code"), max_length = 10 )
    reference_number = models.CharField( _("Reference number"),max_length = 50 )
    
    class Meta:
        db_table = u'epic_stock'
        #managed = False
    
    def is_bulk(self):
        return self.packagename == BULK_NAME and self.quantity_net
    
    @classmethod 
    def update(cls):
        """Executes Imports of Stock"""
        
        now = datetime.now()
        
        for stock in cls.objects.using( 'compas' ):
            
            #Check package type. If 'BULK' then modify number and weight
            number_of_units, quantity_net = (stock.quantity_net, 1) if stock.is_bulk() \
                                            else (stock.number_of_units, stock.quantity_net)
            
            defaults = {
                'warehouse': Warehouse.objects.get(pk=stock.wh_code),
                'project_number': stock.project_wbs_element,
                'si_code': stock.si_code,
                'commodity_code': stock.commodity_code,
                'number_of_units': number_of_units,
                'quantity_net': quantity_net,
                'package_code': stock.package_code,
                'package_name': stock.packagename,
                'quality_code': stock.qualitycode,
                'quality_description': stock.qualitydescr,
                'quantity_gross': stock.quantity_gross,
                'updated': now
            }
            
            rows = StockItem.objects.filter(origin_id=stock.origin_id).update(**defaults)
            if not rows:
                StockItem.objects.create(origin_id=stock.origin_id, **defaults)
        
        #Flush empty stocks
        StockItem.objects.filter(number_of_units__gt=0).exclude(updated=now).update(number_of_units=0)
        
            
class StockManager( models.Manager ):
    
    def get_existing_units( self ):
        return super( StockManager, self ).get_query_set().filter( number_of_units__gt = 0 )

class StockItem( models.Model ):
    """Accessible stocks"""
    origin_id = models.CharField(_("Origin identifier"), max_length=23, primary_key=True)
    
    warehouse = models.ForeignKey(Warehouse, verbose_name=_("Warehouse"), related_name="stock_items")
    
    project_number = models.CharField(_("Project Number"), max_length=24, blank=True) #project_wbs_element
    si_code = models.CharField(_("shipping instruction code"), max_length=8)
    commodity_code = models.CharField(_("Commodity Code "), max_length = 18)
    
    package_code = models.CharField(_("Package code"), max_length=17)
    package_name = models.CharField(_("Package name"), max_length=50, blank=True)
    
    quality_code = models.CharField(_("Quality code"), max_length=1) #qualitycode
    quality_description = models.CharField(_("Quality description "), max_length=11, blank=True) #qualitydescr
    quantity_net = models.DecimalField(_("Quantity net"), max_digits=12, decimal_places=3, blank=True, null=True)
    quantity_gross = models.DecimalField(_("Quantity gross"), max_digits=12, decimal_places=3, blank=True, null=True)
    number_of_units = models.IntegerField(_("Number of units"))
    
    updated = models.DateTimeField(_("update date"), default=datetime.now, editable=False)
    
    objects = StockManager()

    class Meta:
        ordering = ('si_code', 'commodity_name')
        order_with_respect_to = 'warehouse'
        verbose_name = _("stock item")
        verbose_name_plural = _("stocks")

    def  __unicode__( self ):
        return "%s-%s-%s" % (self.warehouse.title, self.commodity_code, self.number_of_units)
        
    def coi_code(self):
        return self.origin_id[7:]
    
    def packaging_description( self ):
        try:
            return PackagingDescriptionShort.objects.get( pk = self.package_code ).description
        except PackagingDescriptionShort.DoesNotExist:
            return self.package_name
    

class PackagingDescriptionShort( models.Model ):
    code = models.CharField(_("Package Code"), primary_key=True, max_length=5)
    description = models.CharField(_("Package Short Name"), max_length=10)
    
    def  __unicode__( self ):
        return "%s - %s" % (self.code, self.description)


class LossDamageType( models.Model ):
    
    LOSS = 'L'
    DAMAGE = 'D'
    
    TYPE_CHOICE = (
        (LOSS, _("Loss")),
        (DAMAGE, _("Damage")),
    )
    
    slug = AutoSlugField(populate_from=lambda instance: "%s%s" % (
                            instance.type, instance.comm_category_code
                         ), unique=True, primary_key=True)
    type = models.CharField(_("Type"), max_length=1, choices=TYPE_CHOICE)
    comm_category_code = models.CharField(_("Commodity category code"), max_length=9)
    cause = models.CharField(_("Cause"), max_length = 100)

    class Meta:
        db_table = u'epic_lossdamagereason'
        verbose_name = _('Loss/Damages Reason')
    
    def  __unicode__( self ):
        cause = self.cause
        length_c = len( cause ) - 10
        if length_c > 20:
            cause = "%s...%s" % (cause[0:20], cause[length_c:])
        return cause
    
    @classmethod
    def update(cls):
        for myrecord in cls.objects.using('compas').all():
            myrecord.save(using='default')


class LtiOriginal( models.Model ):
    """LTIs for office"""
    
    lti_pk = models.CharField( _("LTI primary key"),max_length = 50, primary_key = True, db_column = 'LTI_PK' )
    lti_id = models.CharField(_("LTI ID"), max_length = 40, db_column = 'LTI_ID' )
    code = models.CharField( _("Code"),max_length = 40, db_column = 'CODE' )
    lti_date = models.DateField( _("LTI Date"),db_column = 'LTI_DATE' )
    expiry_date = models.DateField(_("Expiry Date"), blank = True, null = True, db_column = 'EXPIRY_DATE' )
    transport_code = models.CharField(_("Transport Code"), max_length = 4, db_column = 'TRANSPORT_CODE' )
    transport_ouc = models.CharField(_("Transport ouc"), max_length = 13, db_column = 'TRANSPORT_OUC' )
    transport_name = models.CharField(_("Transport Name"), max_length = 30, db_column = 'TRANSPORT_NAME' )
    origin_type = models.CharField(_("Origin Type"), max_length = 1, db_column = 'ORIGIN_TYPE' )
    origintype_desc = models.CharField(_("Origin Type Desc"), max_length = 12, blank = True, db_column = 'ORIGINTYPE_DESC' )
    
    #Warehouse
    origin_location_code = models.CharField( _("Origin location code"),max_length = 10, db_column = 'ORIGIN_LOCATION_CODE' )
    origin_loc_name = models.CharField(_("Origin location name"), max_length = 30, db_column = 'ORIGIN_LOC_NAME' )
    origin_wh_code = models.CharField( _("Origin warehouse code"),max_length = 13, blank = True, db_column = 'ORIGIN_WH_CODE' )
    origin_wh_name = models.CharField( _("Origin warehouse name"),max_length = 50, blank = True, db_column = 'ORIGIN_WH_NAME' )
    
    #Location
    destination_location_code = models.CharField( _("Destination Location Code"),max_length = 10, db_column = 'DESTINATION_LOCATION_CODE' )
    destination_loc_name = models.CharField(_("Destination Loc Name"), max_length = 30, db_column = 'DESTINATION_LOC_NAME' )
    
    #Organization
    consegnee_code = models.CharField(_("Consignee Code"), max_length = 12, db_column = 'CONSEGNEE_CODE' )
    consegnee_name = models.CharField(_("Consignee Name"), max_length = 80, db_column = 'CONSEGNEE_NAME' )
    
    requested_dispatch_date = models.DateField(_("Requested Dispatch Date"), blank = True, null = True, db_column = 'REQUESTED_DISPATCH_DATE' )
    project_wbs_element = models.CharField(_("Project work breakdown structure element"), max_length = 24, blank = True, db_column = 'PROJECT_WBS_ELEMENT' )
    si_record_id = models.CharField( _("SI Record ID "),max_length = 25, blank = True, db_column = 'SI_RECORD_ID' )
    si_code = models.CharField( _("SI Code"),max_length = 8, db_column = 'SI_CODE' )
    comm_category_code = models.CharField(_("Commodity Category Code"), max_length = 9, db_column = 'COMM_CATEGORY_CODE' )
    commodity_code = models.CharField(_("Commodity Code "), max_length = 18, db_column = 'COMMODITY_CODE' )
    cmmname = models.CharField(_("Commodity Name"), max_length = 100, blank = True, db_column = 'CMMNAME' )
    quantity_net = models.DecimalField(_("Quantity Net"), max_digits = 11, decimal_places = 3, db_column = 'QUANTITY_NET' )
    quantity_gross = models.DecimalField( _("Quantity Gross"),max_digits = 11, decimal_places = 3, db_column = 'QUANTITY_GROSS' )
    number_of_units = models.DecimalField( _("Number of Units"),max_digits = 7, decimal_places = 0, db_column = 'NUMBER_OF_UNITS' )
    unit_weight_net = models.DecimalField( _("Unit Weight Net"),max_digits = 8, decimal_places = 3, blank = True, null = True, db_column = 'UNIT_WEIGHT_NET' )
    unit_weight_gross = models.DecimalField( _("Unit Weight Gross"),max_digits = 8, decimal_places = 3, blank = True, null = True, db_column = 'UNIT_WEIGHT_GROSS' )

    class Meta:
        db_table = u'epic_lti'
        #managed = False
    
    @classmethod
    def update(cls):
        """Imports all LTIs from COMPAS"""
        now = datetime.now()

        original = cls.objects.using('compas').filter(requested_dispatch_date__gt = settings.MAX_DATE)
        if not settings.DISABLE_EXPIERED_LTI:
            original = original.filter( expiry_date__gt = now )
        
        for lti in original:
            
            #Update Consignee
            # TODO: correct epic_geo view. It should contain organization name field. Then we will be able to delete this
            consignee = Consignee.objects.get(pk=lti.consegnee_code)
            
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
                'warehouse': Warehouse.objects.get(code=lti.origin_wh_code),
                'consignee': consignee,
                'location': Location.objects.get(pk=lti.destination_location_code),
                'updated': now,
            }
            
            order = Order.objects.get_or_create(code=lti.code, defaults=defaults)[0]
            
            #Create order item
            defaults = {
                'order': order,
                'si_code': lti.si_code,
                'comm_category_code': lti.comm_category_code,
                'commodity_code': lti.commodity_code,
                'commodity_name': lti.cmmname,
                'number_of_units': lti.number_of_units,
                'quantity_net': lti.quantity_net,
                'quantity_gross': lti.quantity_gross,
                'unit_weight_net': lti.unit_weight_net,
                'unit_weight_gross': lti.unit_weight_gross,
            }
            
            rows = OrderItem.objects.filter(lti_pk=lti.lti_pk).update(**defaults)
            if not rows:
                OrderItem.objects.create(lti_pk=lti.lti_pk, **defaults)
            

class Order(models.Model):
    """Delivery order"""
    
    code = models.CharField(_("Code"), max_length=40, primary_key=True)
    
    created = models.DateField(_("Created date")) #lti_date
    expiry = models.DateField(_("expire date"), blank=True, null=True) #expiry_date
    dispatch_date = models.DateField(_("Requested Dispatch Date"), blank=True, null=True)
    
    transport_code = models.CharField(_("Transport Code"), max_length = 4, editable=False)
    transport_ouc = models.CharField(_("Transport ouc"), max_length = 13, editable=False)
    transport_name = models.CharField(_("Transport Name"), max_length = 30)
    
    origin_type = models.CharField(_("Origin Type"), max_length = 1, editable=False)
    
    project_number = models.CharField(_("Project Number"), max_length = 24, blank = True) #project_wbs_element
    
    warehouse = models.ForeignKey(Warehouse, verbose_name=_("dispatch warehouse"), related_name="orders")
    consignee = models.ForeignKey(Consignee, verbose_name=_("consignee"), related_name="orders")
    location = models.ForeignKey(Location, verbose_name=_("consignee's location"), related_name="orders")
    
    updated = models.DateTimeField(_("update date"), default=datetime.now, editable=False)
    
    class Meta:
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        ordering = ('code',)
    
    def  __unicode__(self):
        return self.code
    
    @models.permalink
    def get_absolute_url(self):
        return ('order_detail', (), {'object_id': self.pk})
    
    def get_waybills(self):
        return Waybill.objects.filter(order_code=self.pk, invalidated=False)
    
class DeliveryItem(models.Model):
    """Order item for delivery"""
    
    si_code = models.CharField( _("Shipping Order Code"), max_length = 8)
    
    comm_category_code = models.CharField(_("Commodity Category Code"), max_length = 9)
    commodity_code = models.CharField(_("Commodity Code "), max_length = 18)
    commodity_name = models.CharField(_("Commodity Name"), max_length = 100, blank = True) #cmmname
    
    number_of_units = models.DecimalField(_("Number of Units"), max_digits = 7, decimal_places = 0)

    quantity_net = models.DecimalField(_("Quantity Net"), max_digits = 11, decimal_places = 3)
    quantity_gross = models.DecimalField(_("Quantity Gross"), max_digits = 11, decimal_places = 3)
    unit_weight_net = models.DecimalField(_("Unit Weight Net"), max_digits = 8, decimal_places = 3, 
                                          blank = True, null = True)
    unit_weight_gross = models.DecimalField(_("Unit Weight Gross"), max_digits = 8, decimal_places = 3, 
                                            blank = True, null = True)
    
    class Meta:
        abstract = True


class OrderItem(DeliveryItem):
    """Order item with commodity and counters"""
    
    lti_pk = models.CharField(_("COMPAS LTI identifier"), max_length=50, editable=False, primary_key=True)
    order = models.ForeignKey(Order, verbose_name=_("Order"), related_name="items")
    removed = models.DateField(_("removed date"), blank=True, null=True)
    
    class Meta:
        ordering = ('si_code',)
        order_with_respect_to = 'order'
        verbose_name = _("order item")
        verbose_name_plural = _("order items")
    
    def  __unicode__( self ):
        if self.removed:
            return u"Void %s -  %.0f " % ( self.commodity_name, self.items_left() )
        else:
            return u"%s -  %.0f " % ( self.commodity_name, self.items_left() )

    def get_stock_items(self):
        """Retrieves stock items for current order item through warehouse"""
        return StockItem.objects.filter(warehouse__orders__items=self,
                                        project_number=self.order.project_number,
                                        si_code = self.si_code, 
                                        commodity_code = self.commodity_code,
                                        ).order_by('-number_of_units')
    
    @staticmethod
    def sum_number( queryset ):
        return queryset.aggregate(units_count=Sum('number_of_units'))['units_count'] or 0
    
    def get_similar_dispatches(self):
        """Returns all loading details with such item within any orders"""
        return LoadingDetail.objects.filter(waybill__status__gte=Waybill.SIGNED, 
                                            waybill__project_number=self.order.project_number,
                                            waybill__invalidated=False,
                                            si_code = self.si_code, 
                                            commodity_code = self.commodity_code
                                            ).order_by('-waybill__dispatch_date')
    
    def get_order_dispatches(self):
        """Returns dispatches of current order"""
        return self.get_similar_dispatches().filter(waybill__order_code=self.order.pk)
    
    
    def get_available_stocks(self):
        """Calculates available stocks"""
        return self.sum_number(self.get_stock_items()) - self.sum_number(self.get_similar_dispatches())
        
        
    def items_left( self ):
        """Calculates number of such items supposed to be delivered in this order"""
        return self.number_of_units - self.sum_number(self.get_order_dispatches())
    
    #===================================================================================================================
    # def coi_code( self ):
    #    stock_items_qs = self.stock_items()
    #    if stock_items_qs.count() > 0:
    #        return str( stock_items_qs[0].coi_code() )
    #    else:
    #        stock_items_qs = EpicStock.objects.filter( wh_code = self.origin_wh_code, 
    #                                                   si_code = self.si_code, 
    #                                                   comm_category_code = self.comm_category_code 
    #                                                   ).order_by( '-number_of_units' )
    #        if stock_items_qs.count() > 0:
    #            return str( stock_items_qs[0].coi_code() )
    #        else:
    #            stock_items_qs = EpicStock.objects.filter( si_code = self.si_code, 
    #                                                       comm_category_code = self.comm_category_code 
    #                                                       ).order_by( '-number_of_units' )
    #            if stock_items_qs.count() > 0:
    #                return str( stock_items_qs[0].coi_code() )
    #            else:
    #                return 'No Stock '
    #===================================================================================================================
    
class Waybill( models.Model ):
    """
    Main model in the system. Tracks delivery.
    
    """
    
    TRANSACTION_TYPES = ( 
                        ( u'WIT', _(u'WFP Internal') ),
                        ( u'DEL',_( u'Delivery' )),
                        ( u'SWA', _(u'Swap' )),
                        ( u'REP', _(u'Repayment' )),
                        ( u'SAL', _(u'Sale' )),
                        ( u'ADR', _(u'Air drop' )),
                        ( u'INL', _(u'Inland Shipment' )),
                        ( u'DIS', _(u'Distribution' )),
                        ( u'LON', _(u'Loan' )),
                        ( u'DSP', _(u'Disposal' )),
                        ( u'PUR', _(u'Purchase' )),
                        ( u'SHU', _(u'Shunting' )),
                        ( u'COS', _(u'Costal Transshipment' )),
                )
    TRANSPORT_TYPES = ( 
                        ( u'02', _(u'Road' )),
                        ( u'01', _(u'Rail' )),
                        ( u'04', _(u'Air' )),
                        ( u'I', _(u'Inland Waterways' )),
                        ( u'C', _(u'Costal Waterways' )),
                        ( u'07', _(u'Multi-mode' )),
#                        (u'O', _(u'Other Please Specify'))
                )
    
    NEW = 1
    SIGNED = 2
    SENT = 3
    INFORMED = 4
    DELIVERED = 5
    COMPLETE = 6
    
    STATUSES = (
        (NEW, _("New")),
        (SIGNED, _("Signed")),
        (SENT, _("Sent")),
        (INFORMED, _("Informed")),
        (DELIVERED, _("Delivered")),
        (COMPLETE, _("Complete")),
    )
    
    slug = AutoSlugField(populate_from=lambda instance: "%s%s%s" % (
                            COMPAS_STATION, instance.created.strftime('%y'), LETTER_CODE
                         ), unique=True, slugify=capitalize_slug(slugify),
                         sep='', primary_key=True)
    
    #Data from order
    order_code = models.CharField( _("order code"), max_length = 20, db_index=True)
    project_number = models.CharField(_("Project Number"), max_length = 24, blank = True) #project_wbs_element
    transport_name = models.CharField(_("Transport Name"), max_length = 30) #transport_name
    warehouse = models.ForeignKey(Warehouse, verbose_name=_("Dispatch Warehouse"), related_name="dispatch_waybills")
    destination = models.ForeignKey(Warehouse, verbose_name=_("Receipt Warehouse"), related_name="receipt_waybills")
    
    status = models.IntegerField(_("Status"), choices=STATUSES, default=NEW)
    
    #Dates
    created = models.DateTimeField(_("created date/time"), default=datetime.now)
    loading_date = models.DateField(_("Date of loading"), blank=True, null=True) #dateOfLoading
    dispatch_date = models.DateField( _("Date of dispatch"), blank=True, null=True) #dateOfDispatch
    
    transaction_type = models.CharField( _("Transaction Type"), max_length=10, choices=TRANSACTION_TYPES ) #transactionType
    transport_type = models.CharField(_("Transport Type"), max_length=10, choices=TRANSPORT_TYPES ) #transportType
    
    #Dispatcher
    dispatch_remarks = models.CharField(_("Dispatch Remarks"), max_length=200, blank=True)
    dispatcher_person = models.ForeignKey(CompasPerson, verbose_name=_("Dispatch person"), 
                                          related_name="dispatch_waybills") #dispatcherName
    #dispatcher_title = models.TextField(_("Dispatcher Title")) #dispatcherTitle
    #dispatcher_signed = models.BooleanField(_("Dispatcher Signed"), default=False)
    #dispatch_warehouse = models.ForeignKey( Place, verbose_name=_("Place of dispatch"), 
    #                                        default=COMPAS_STATION, related_name="dispatch_waybills")
    
    #Transporter
    #transport_contractor = models.TextField(_("Transport Contractor"), blank=True ) #transportContractor
    transport_sub_contractor = models.CharField(_("Transport Sub contractor"), max_length=40, blank=True) #transportSubContractor
    transport_driver_name = models.CharField(_("Transport Driver Name"), max_length=40) #transportDriverName
    transport_driver_licence = models.CharField(_("Transport Driver LicenceID "), max_length=40) #transportDriverLicenceID
    transport_vehicle_registration = models.CharField(_("Transport Vehicle Registration "), max_length=40) #transportVehicleRegistration
    transport_trailer_registration = models.CharField( _("Transport Trailer Registration"), max_length=40, blank=True) #transportTrailerRegistration
    #transport_dispach_signed = models.BooleanField( _("Transport Dispatch Signed"), default=False) #transportDispachSigned
    transport_dispach_signed_date = models.DateTimeField( _("Transport Dispach Signed Date"), null=True, blank=True) #transportDispachSignedTimestamp
    #transport_delivery_signed = models.BooleanField( _("Transport Delivery Signed"), default=False) #transportDeliverySigned
    transport_delivery_signed_date = models.DateTimeField( _("Transport Delivery Signed Date"), null=True, blank=True ) #transportDeliverySignedTimestamp

    #Container        
    container_one_number = models.CharField(_("Container One Number"), max_length=40, blank=True) #containerOneNumber
    container_two_number = models.CharField( _("Container Two Number"), max_length=40, blank=True) #containerTwoNumber
    container_one_seal_number = models.CharField(_("Container One Seal Number"), max_length=40, blank=True) #containerOneSealNumber
    container_two_seal_number = models.CharField(_("Container Two Seal Number"), max_length=40, blank=True ) #containerTwoSealNumber
    container_one_remarks_dispatch = models.CharField( _("Container One Remarks Dispatch"), max_length=40, blank=True) #containerOneRemarksDispatch
    container_two_remarks_dispatch = models.CharField( _("Container Two Remarks Dispatch"), max_length=40, blank=True) #containerTwoRemarksDispatch
    container_one_remarks_reciept = models.CharField( _("Container One Remarks Reciept"), max_length=40, blank=True) #containerOneRemarksReciept
    container_two_remarks_reciept = models.CharField(_("Container Two Remarks Reciept"), max_length=40, blank=True) #containerTwoRemarksReciept

    #Receiver
    recipient_person =  models.ForeignKey(CompasPerson, verbose_name=_("Recipient person"), 
                                          related_name="recipient_waybills", blank=True, null=True) #recipientName
    #recipient_name = models.CharField( _("Recipient Name"), max_length=100, blank=True) #recipientName
    #recipient_title = models.CharField(_("Recipient Title "), max_length=100, blank=True) #recipientTitle
    recipient_arrival_date = models.DateField(_("Recipient Arrival Date"), null=True, blank=True) #recipientArrivalDate
    recipient_start_discharge_date = models.DateField(_("Recipient Start Discharge Date"), null=True, blank=True) #recipientStartDischargeDate
    recipient_end_discharge_date = models.DateField(_("Recipient End Discharge Date"), null=True, blank=True) #recipientEndDischargeDate
    recipient_distance = models.IntegerField(_("Recipient Distance"), blank=True, null=True) #recipientDistance
    recipient_remarks = models.CharField(_("Recipient Remarks"), max_length=40, blank=True) #recipientRemarks
    #recipient_signed = models.BooleanField(_("Recipient Signed"), default=True) #recipientSigned
    recipient_signed_date = models.DateTimeField(_("Recipient Signed Date"), null=True, blank=True) #recipientSignedTimestamp
    #===================================================================================================================
    # destinationWarehouse = models.ForeignKey( Place, verbose_name=_("Destination Warehouse"), 
    #                                          related_name="recipient_waybills" )
    #===================================================================================================================

    #Extra Fields
    validated = models.BooleanField( _("Waybill Validated"), default=False) #waybillValidated
    receipt_validated = models.BooleanField( _("Waybill Receipt Validated"), default=False) #waybillReceiptValidated
    sent_compas = models.BooleanField(_("Waybill Sent To Compas"), default=False) #sentToCompas
    rec_sent_compas = models.BooleanField(_("Waybill Reciept Sent to Compas"), default=False) #waybillRecSentToCompas
    processed_for_payment = models.BooleanField(_("Waybill Processed For Payment"), default=False) #waybillProcessedForPayment
    invalidated = models.BooleanField(_("Invalidated"), default=False)
    
    audit_comment = models.TextField(_("Audit Comment"), blank=True) #auditComment
    
    audit_log = AuditLog()

    def  __unicode__( self ):
        return self.slug
    
    @models.permalink
    def get_absolute_url(self):
        return ('waybill_view', (), {'slug': self.slug})
    
    def is_editable(self, user):
        return self.status < self.SIGNED and not user.get_profile().reader_user
    
    def errors(self):
        try:
            return CompasLogger.objects.get( wb = self )
        except CompasLogger.DoesNotExist:
            return ''
    
    def clean(self):
        """Validates Waybill instance. Checks different dates"""
        if self.dateOfDispatch and self.dateOfLoading \
        and self.dateOfLoading > self.dateOfDispatch:
            raise ValidationError(_("Cargo Dispatched before being Loaded"))
    
        if self.recipientArrivalDate and self.dateOfDispatch \
         and self.recipientArrivalDate < self.dateOfDispatch:
            raise ValidationError(_("Cargo arrived before being dispatched"))

        if self.recipientStartDischargeDate and self.recipientArrivalDate \
        and self.recipientStartDischargeDate < self.recipientArrivalDate:
            raise ValidationError(_("Cargo Discharge started before Arrival?"))

        if self.recipientStartDischargeDate and self.recipientEndDischargeDate \
        and self.recipientEndDischargeDate < self.recipientStartDischargeDate:
            raise ValidationError(_("Cargo finished Discharge before Starting?"))

    
    def check_lines( self ):
        lines = LoadingDetail.objects.filter( wbNumber = self )
        for line in lines:
            if not line.check_stock():
                return False
        return True

    def check_lines_receipt( self ):
        lines = LoadingDetail.objects.filter( wbNumber = self )
        for line in lines:
            if not line.check_receipt_item():
                return False
        return True

    @property
    def hasError( self ):
        myerror = self.errors()
        try:
            if ( myerror.errorRec != '' or myerror.errorDisp != '' ):
                return True
        except:
            return None

    def invalidate_waybill_action( self ):
        for lineitem in self.loading_details.select_related():
            lineitem.order_item.lti_line.restore_si( lineitem.numberUnitsLoaded )
            lineitem.numberUnitsLoaded = 0
            lineitem.save()
        self.invalidated = True
        self.save()
    
    def dispatch_sign(self, commit=True):
        """
        Signs the waybill as ready to be sent by setting special status SIGNED. 
        After this system sends it to central server.
        """
        #self.transportDispachSigned = True
        self.transport_dispach_signed_date = datetime.now()
        #self.dispatcherSigned = True
        self.audit_comment = ugettext('Print Dispatch Original')
        
        self.update_status(self.SIGNED)
        
        if commit:
            self.save()
    
    def receipt_sign(self, commit=True):
        """
        Signs the waybill as delivered by setting special status DELIVERED. 
        After this system sends it to central server.
        """
        #self.recipientSigned = True
        self.transport_delivery_signed_date = datetime.now()
        self.recipient_signed_date = datetime.now()
        #self.transportDeliverySigned = True
        self.audit_comment = ugettext('Print Dispatch Receipt')
        
        self.update_status(self.DELIVERED)
        
        if commit:
            self.save()
    
    def serialize(self):
        """
        This method serializes the Waybill with related LoadingDetails, LtiOriginals and EpicStocks.
    
        @param self: the Waybill instance
        @return the serialized json data.
        """
    
        return serializers.serialize( 'json', chain((self,), self.loading_details.all()))
        
    def compress(self):
        """
        This method compress the Waybill using zipBase64 algorithm.
    
        @param self: the Waybill instance
        @return: a string containing the compressed representation of the Waybill with related LoadingDetails, LtiOriginals and EpicStocks
        """
        return base64.b64encode( zlib.compress( simplejson.dumps( self.serialize(), use_decimal=True ) ) )
    
    def decompress(self, data):
        data = string.replace( data, ' ', '+' )
        zippedData = base64.b64decode( data )
        return zlib.decompress( zippedData )
    
    def update_status(self, status):
        if self.status > status:
            raise RuntimeError("You can not decrease status to %s" % status)
        
        self.status = status
        self.save()
    

class LoadingDetail( DeliveryItem ):
    """Item of waybill"""
    waybill = models.ForeignKey( Waybill, verbose_name=_("Waybill Number"), related_name="loading_details")
    slug = AutoSlugField(populate_from='waybill', unique=True, sep='', primary_key=True)
    
    origin_id = models.CharField(_("Origin stock identifier"), max_length=23)
    package = models.CharField(_("Package"), max_length=10)
        
    #Number of delivered units
    number_units_good = models.DecimalField(_("number Units Good"), default=0, 
                                            max_digits=10, decimal_places=3) #numberUnitsGood
    number_units_lost = models.DecimalField(_("number Units Lost"), default=0, 
                                            max_digits=10, decimal_places=3 ) #numberUnitsLost
    number_units_damaged = models.DecimalField(_("number Units Damaged"), default=0, 
                                               max_digits=10, decimal_places=3 ) #numberUnitsDamaged
    
    #Reasons
    units_lost_reason = models.ForeignKey( LossDamageType, verbose_name=_("units Lost Reason"), 
                                           related_name='lost_reason', #LD_LostReason 
                                           blank=True, null=True ) #unitsLostReason
    units_damaged_reason = models.ForeignKey( LossDamageType, verbose_name=_("units Damaged Reason"), 
                                            related_name='damage_reason', #LD_DamagedReason 
                                            blank=True, null=True ) #unitsDamagedReason
    units_damaged_type = models.ForeignKey( LossDamageType, verbose_name=_("units Damaged Type"),
                                          related_name='damage_type', #LD_DamagedType 
                                          blank=True, null=True ) #unitsDamagedType
    units_lost_type = models.ForeignKey( LossDamageType, verbose_name=_("units LostType "), 
                                       related_name='loss_type', #LD_LossType 
                                       blank=True, null=True ) #unitsLostType
    
    overloaded_units = models.BooleanField(_("overloaded Units"), default=False) #overloadedUnits
    loading_detail_sent_compas = models.BooleanField(_("loading Detail Sent to Compas "), default=False) #loadingDetailSentToCompas
    over_offload_units = models.BooleanField(_("over offloaded Units"), default=False) #overOffloadUnits

    audit_log = AuditLog()

    def check_stock( self ):
        stock = self.order_item.stock_item
        if self.order_item.lti_line.is_bulk:
            if self.numberUnitsLoaded <= stock.quantity_net:
                return True
        else:
            if self.numberUnitsLoaded <= stock.number_of_units :
                return True
        
        return False

    def check_receipt_item( self ):
        return True
    
    #===================================================================================================================
    # def get_stock_item( self ):
    #    return EpicStock.objects.get( pk = self.order_item.stock_item.pk )
    #===================================================================================================================

    def calculate_total_net( self ):
        return ( self.number_of_units * self.unit_weight_net ) / 1000

    def calculate_total_gross( self ):
        return ( self.number_of_units * self.unit_weight_gross ) / 1000

    def calculate_net_received_good( self ):
        return ( self.number_units_good * self.unit_weight_net ) / 1000

    def calculate_gross_received_good( self ):
        return ( self.number_units_good * self.unit_weight_gross ) / 1000

    def calculate_net_received_damaged( self ):
        return ( self.number_units_damaged * self.unit_weight_net ) / 1000

    def calculate_gross_received_damaged( self ):
        return ( self.number_units_damaged * self.unit_weight_gross ) / 1000

    def calculate_net_received_lost( self ):
        return ( self.number_units_lost * self.unit_weight_net ) / 1000

    def calculate_gross_received_lost( self ):
        return ( self.number_units_lost * self.unit_weight_gross ) / 1000
    
    def calculate_total_received_units( self ):
        return self.number_units_good + self.number_units_damaged

    def calculate_total_received_net( self ):
        return self.calculate_net_received_good() + self.calculate_net_received_damaged()
    
    def get_coi_code(self):
        return self.origin_id[7:]
    
    def  __unicode__( self ):
        return "%s - %s - %s" % (self.waybill, self.si_code, self.number_of_units)


class UserProfile( models.Model ):
    user = models.ForeignKey( User, unique = True, primary_key = True )#OneToOneField(User, primary_key = True)
    
    dispatch_warehouse = models.ForeignKey( Warehouse, verbose_name=_("Dispatch Warehouse"), 
                                            blank=True, null=True, related_name="dispatcher_profiles")
    reception_warehouse = models.ForeignKey( Warehouse, verbose_name=_("Reception warehouse"), 
                                             blank=True, null=True, related_name="receipient_profiles")
    
    is_compas_user = models.BooleanField(_('Is Compas User'), default=False) #isCompasUser
    is_dispatcher = models.BooleanField(_("Is Dispatcher"), default=False) #is_dispatcher
    is_reciever = models.BooleanField(_("Is Reciever"), default=False) #is_reciever
    is_all_receiver = models.BooleanField( _('Is MoE Receiver (Can Receipt for All Warehouses Beloning to MoE)') ) #isAllReceiver
    compas_person = models.ForeignKey( CompasPerson, verbose_name = _('Use this Compas Person'), 
                                    related_name="profiles",
                                    help_text = _('Select the corrisponding user from Compas'), 
                                    blank=True, null=True)
    super_user = models.BooleanField(_("Super User"), 
            help_text = _('This user has Full Privileges to edit Waybills even after Signatures'), default=False) #super_user
    reader_user = models.BooleanField(_( 'Readonly User' ), default=False) #reader_user

    audit_log = AuditLog()
    
    def __unicode__( self ):
        if self.user.first_name and self.user.last_name:
            return "%s %s's profile (%s)" % ( self.user.first_name, self.user.last_name, self.user.username )
        else:
            return "%s's profile" % self.user.username


def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

post_save.connect(create_user_profile, sender=User)


class CompasLogger( models.Model ):
    timestamp = models.DateTimeField(_("Time stamp"), null = True, blank = True )
    user = models.ForeignKey( User )
    action = models.CharField(_("Action"), max_length = 50, blank = True )
    errorRec = models.CharField(_("Error Record"), max_length = 2000, blank = True )
    errorDisp = models.CharField(_("Error Disp"), max_length = 2000, blank = True )
    wb = models.ForeignKey( Waybill, verbose_name=_("Waybill"), blank = True, primary_key = True )
    lti = models.CharField(_("LTI"), max_length = 50, blank = True )
    data_in = models.CharField(_("Data in"), max_length = 5000, blank = True )
    data_out = models.CharField(_("Data out"), max_length = 5000, blank = True )
    #loggercompas
    
    class Meta:
        db_table = u'loggercompas'


# TODO: Importing of old waybills....
class DispatchMaster( models.Model ):
    code = models.CharField(_("Code"), max_length = 25, primary_key = True )
    document_code = models.CharField(_("Document code"), max_length = 2 )
    dispatch_date = models.DateField(_("Dispatch date"))
    origin_type = models.CharField(_("Origin type"), max_length = 1 )
    origin_location_code = models.CharField(_("Origin location code"), max_length = 13 )
    intvyg_code = models.CharField(_("Intvyg code"), max_length = 25, blank = True )
    intdlv_code = models.IntegerField(_("Intdlv code"), null = True, blank = True )
    origin_code = models.CharField(_("Origin code"), max_length = 13, blank = True )
    origin_descr = models.CharField(_("Origin description"), max_length = 50, blank = True )
    destination_location_code = models.CharField(_("Destination location code"), max_length = 10 )
    destination_code = models.CharField(_("Destination code"), max_length = 13, blank = True )
    pro_activity_code = models.CharField(_("Pro activity code"), max_length = 6, blank = True )
    activity_ouc = models.CharField(_("Activity ouc"), max_length = 13, blank = True )
    lndarrm_code = models.CharField(_("Lndarrm code"), max_length = 25, blank = True )
    lti_id = models.CharField(_("LTI id "), max_length = 25, blank = True )
    loan_id = models.CharField(_("Loan id "), max_length = 25, blank = True )
    loading_date = models.DateField(_("Loading date"))
    organization_id = models.CharField(_("Organization id "), max_length = 12 )
    tran_type_code = models.CharField(_("Tran type code"), max_length = 4 )
    tran_type_descr = models.CharField(_("Tran type descr"), max_length = 50, blank = True )
    modetrans_code = models.CharField(_("Modetrans code"), max_length = 2 )
    comments = models.CharField(_("Comments"), max_length = 250, blank = True )
    person_code = models.CharField(_("Person code"), max_length = 7 )
    person_ouc = models.CharField(_("Person ouc"), max_length = 13 )
    certifing_title = models.CharField(_("Certifing title"), max_length = 50, blank = True )
    trans_contractor_code = models.CharField(_("Trans contractor code"), max_length = 4 )
    supplier1_ouc = models.CharField(_("Supplier1 ouc"), max_length = 13 )
    trans_subcontractor_code = models.CharField(_("Trans subcontractor code"), max_length = 4, blank = True )
    supplier2_ouc = models.CharField(_("Supplier2 ouc "), max_length = 13, blank = True )
    nmbplt_id = models.CharField(_("Nmbplt id"), max_length = 25, blank = True )
    nmbtrl_id = models.CharField(_("Nmbtrl id "), max_length = 25, blank = True )
    driver_name = models.CharField(_("Driver name"), max_length = 50, blank = True )
    license = models.CharField(_("license"), max_length = 20, blank = True )
    vehicle_registration = models.CharField(_("Vehicle registration"), max_length = 20, blank = True )
    trailer_plate = models.CharField(_("Trailer plate"), max_length = 20, blank = True )
    container_number = models.CharField(_("Container number"), max_length = 15, blank = True )
    atl_li_code = models.CharField(_("Atl li code"), max_length = 8, blank = True )
    notify_indicator = models.CharField(_("Notify indicator"), max_length = 1, blank = True )
    customised = models.CharField(_("Customised"), max_length = 50, blank = True )
    org_unit_code = models.CharField(_("Org unit code"), max_length = 13 )
    printed_indicator = models.CharField(_("Printed indicator"), max_length = 1, blank = True )
    notify_org_unit_code = models.CharField(_("Notify org unit code"), max_length = 13, blank = True )
    offid = models.CharField( _("Offid"), max_length = 13, blank = True )
    send_pack = models.BigIntegerField( _("Send pack"), null = True, blank = True )
    recv_pack = models.BigIntegerField( _("Recv pack"), null = True, blank = True )
    last_mod_user = models.CharField( _("Last mod user"), max_length = 30, blank = True )
    last_mod_date = models.DateField( _("Last mod date"), null = True, blank = True )
    
    class Meta:
        db_table = u'dispatch_masters'
    
    def  __unicode__( self ):
        return self.code


class DispatchDetail( models.Model ):
    code = models.ForeignKey(DispatchMaster ,verbose_name=_("Code"))
    document_code = models.CharField( _("Document code "), max_length = 2 )
    si_record_id = models.CharField( _("SI record id"), max_length = 25, blank = True, null = True )
    origin_id = models.CharField( _("Origin id"), max_length = 23, blank = True )
    comm_category_code = models.CharField( _("Commodity category code"), max_length = 9 )
    commodity_code = models.CharField( _("Commodity code"), max_length = 18 )
    package_code = models.CharField( _("Package code"), max_length = 17 )
    allocation_destination_code = models.CharField( _("Allocation destination code"), max_length = 10 )
    quality = models.CharField( _("Quality"), max_length = 1 )
    quantity_net = models.DecimalField( _("Quantity net"), max_digits = 11, decimal_places = 3 )
    quantity_gross = models.DecimalField( _("Quantity gross"), max_digits = 11, decimal_places = 3 )
    number_of_units = models.IntegerField( _("Number of units "))
    unit_weight_net = models.DecimalField( _("Unit Weight net"), null = True, max_digits = 8, decimal_places = 3, blank = True )
    unit_weight_gross = models.DecimalField( _("Unit Weight Gross"), null = True, max_digits = 8, decimal_places = 3, blank = True )
    lonmst_id = models.CharField( _("Lonmst id"), max_length = 25, blank = True )
    londtl_id = models.IntegerField( _("Londtl id"), null = True, blank = True )
    rpydtl_id = models.IntegerField( _("Rpydtl id"), null = True, blank = True )
    offid = models.CharField( _("Offid"), max_length = 13, blank = True )
    send_pack = models.BigIntegerField( _("Send pack"),null = True, blank = True )
    recv_pack = models.BigIntegerField( _("Recv pack"), null = True, blank = True )
    last_mod_user = models.CharField( _("Last mod user"),max_length = 30, blank = True )
    last_mod_date = models.DateField( _("Last modified date"), null = True, blank = True )
    
    class Meta:
        db_table = u'dispatch_details'



def sync_data(waybills):
    load_details = LoadingDetail.objects.filter(waybill__in=waybills)
    #warehouses = Warehouse.objects.filter(dispatch_waybills__in=waybills)
    #consignees = Consignee.objects.filter(receipt_waybills__in=waybills)
    #places = Place.objects.filter(models.Q(warehouses__in=warehouses) | models.Q(consignees__in=consignees))
    
    #return chain(places, waybills, load_details, warehouses, consignees)
    return chain(waybills, load_details)
