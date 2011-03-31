from django.db import models, connection
from django.contrib import admin
from django.forms import ModelForm, ModelChoiceField
from django.contrib.auth.models import User
from django.forms.models import inlineformset_factory
import datetime
from django.template.defaultfilters import stringfilter
from audit_log.models.fields import LastUserField
from audit_log.models.managers import AuditLog


# Create your models here.
class Places( models.Model ):
        org_code = models.CharField( max_length = 7, primary_key = True )
        name = models.CharField( max_length = 100 )
        geo_point_code = models.CharField( max_length = 4 )
        geo_name = models.CharField( max_length = 100 )
        country_code = models.CharField( max_length = 3 )
        reporting_code = models.CharField( max_length = 7 )
        organization_id = models.CharField( max_length = 20 )

        def __unicode__( self ):
                return self.name

        class Meta:
                db_table = u'epic_geo'


class Waybill( models.Model ):
        transaction_type_choice = ( 
                        ( u'WIT', u'WFP Internal' ),
                        ( u'DEL', u'Delivery' ),
                        ( u'SWA', u'Swap' ),
                        ( u'REP', u'Repayment' ),
                        ( u'SAL', u'Sale' ),
                        ( u'ADR', u'Air drop' ),
                        ( u'INL', u'Inland Shipment' ),
                        ( u'DIS', u'Distribution' ),
                        ( u'LON', u'Loan' ),
                        ( u'DSP', u'Disposal' ),
                        ( u'PUR', u'Purchase' ),
                        ( u'SHU', u'Shunting' ),
                        ( u'COS', u'Costal Transshipment' ),
                )
        transport_type = ( 
                        ( u'02', u'Road' ),
                        ( u'01', u'Rail' ),
                        ( u'04', u'Air' ),
                        ( u'I', u'Inland Waterways' ),
                        ( u'C', u'Costal Waterways' ),
                        ( u'07', u'Multi-mode' ),
#                        (u'O', u'Other Please Specify')
                )
        #general
        ltiNumber = models.CharField( max_length = 20 )
        waybillNumber = models.CharField( max_length = 20 )
        dateOfLoading = models.DateField( null = True, blank = True )
        dateOfDispatch = models.DateField( null = True, blank = True )
        transactionType = models.CharField( max_length = 10, choices = transaction_type_choice )
        transportType = models.CharField( max_length = 10, choices = transport_type )
        #Dispatcher
        dispatchRemarks = models.CharField( max_length = 200 )
        dispatcherName = models.TextField( blank = True, null = True )
        dispatcherTitle = models.TextField( blank = True )
        dispatcherSigned = models.BooleanField( blank = True )
        #Transporter
        transportContractor = models.TextField( blank = True )
        transportSubContractor = models.TextField( blank = True )
        transportDriverName = models.TextField( blank = True )
        transportDriverLicenceID = models.TextField( blank = True )
        transportVehicleRegistration = models.TextField( blank = True )
        transportTrailerRegistration = models.TextField( blank = True )
        transportDispachSigned = models.BooleanField( blank = True )
        transportDispachSignedTimestamp = models.DateTimeField( null = True, blank = True )
        transportDeliverySigned = models.BooleanField( blank = True )
        transportDeliverySignedTimestamp = models.DateTimeField( null = True, blank = True )

        #Container        
        containerOneNumber = models.CharField( max_length = 40, blank = True )
        containerTwoNumber = models.CharField( max_length = 40, blank = True )
        containerOneSealNumber = models.CharField( max_length = 40, blank = True )
        containerTwoSealNumber = models.CharField( max_length = 40, blank = True )
        containerOneRemarksDispatch = models.CharField( max_length = 40, blank = True )
        containerTwoRemarksDispatch = models.CharField( max_length = 40, blank = True )
        containerOneRemarksReciept = models.CharField( max_length = 40, blank = True )
        containerTwoRemarksReciept = models.CharField( max_length = 40, blank = True )

        #Reciver
        recipientLocation = models.CharField( max_length = 100, blank = True )
        recipientConsingee = models.CharField( max_length = 100, blank = True )
        recipientName = models.CharField( max_length = 100, blank = True )
        recipientTitle = models.CharField( max_length = 100, blank = True )
        recipientArrivalDate = models.DateField( null = True, blank = True )
        recipientStartDischargeDate = models.DateField( null = True, blank = True )
        recipientEndDischargeDate = models.DateField( null = True, blank = True )
        recipientDistance = models.IntegerField( blank = True, null = True )
        recipientRemarks = models.TextField( blank = True )
        recipientSigned = models.BooleanField( blank = True )
        recipientSignedTimestamp = models.DateTimeField( null = True, blank = True )
        destinationWarehouse = models.ForeignKey( Places, blank = True )

        #Extra Fields
        waybillValidated = models.BooleanField()
        waybillReceiptValidated = models.BooleanField()
        waybillSentToCompas = models.BooleanField()
        waybillRecSentToCompas = models.BooleanField()
        waybillProcessedForPayment = models.BooleanField()
        invalidated = models.BooleanField()
        auditComment = models.TextField( null = True, blank = True )
        audit_log = AuditLog()

        def  __unicode__( self ):
                return self.waybillNumber

        def mydesc( self ):
                return self.waybillNumber

        def errors( self ):
            try:
                return CompasLogger.objects.get( wb = self )
            except:
                return ''

        def check_lines( self ):
            lines = LoadingDetail.objects.filter( wbNumber = self )
            for line in lines:
                if line.check_stock():
                    pass
                else:
                    return False
            return True

        def check_lines_receipt( self ):
            lines = LoadingDetail.objects.filter( wbNumber = self )
            for line in lines:
                if line.check_reciept_item():
                    pass
                else:
                    return False
            return True

        def dispatch_person( self ):
            return EpicPerson.objects.get( person_pk = self.dispatcherName )

        def receipt_person( self ):
            return EpicPerson.objects.get( person_pk = self.recipientName )

        def is_bulk( self ):
            return LtiOriginal.objects.filter( code = self.ltiNumber )[0].is_bulk()

        def consegnee_name( self ):
            try:
                return LtiOriginal.objects.filter( code = self.ltiNumber )[0].consegnee_name
            except:
                return None
        consegnee_name = property( consegnee_name )

        def origin_wh_code( self ):
            try:
                return LtiOriginal.objects.filter( code = self.ltiNumber )[0].origin_wh_code
            except:
                return None

        origin_wh_code = property( origin_wh_code )

        def destination_loc_name( self ):
            try:
                return LtiOriginal.objects.filter( code = self.ltiNumber )[0].destination_loc_name
            except:
                return None

        destination_loc_name = property( destination_loc_name )

        def consegnee_code( self ):
            try:
                return LtiOriginal.objects.filter( code = self.ltiNumber )[0].consegnee_code
            except:
                return None

        consegnee_code = property( consegnee_code )

        def origin_wh_name( self ):
            try:
                return LtiOriginal.objects.filter( code = self.ltiNumber )[0].origin_wh_name
            except:
                return None

        origin_wh_name = property( origin_wh_name )

        def hasError( self ):
            myerror = self.errors()
            try:
                if ( myerror.errorRec != '' or myerror.errorDisp != '' ):
                    return True
            except:
                return None

        hasError = property( hasError )

        def destination_location_code( self ):
            try:
                return LtiOriginal.objects.filter( code = self.ltiNumber )[0].destination_location_code
            except:
                return None

        destination_location_code = property( destination_location_code )



#### Compas Tables Imported


"""
Models based on compas Views & Tables
"""
"""
LTIs for office 
"""
class LtiOriginal( models.Model ):
        lti_pk = models.CharField( max_length = 50, primary_key = True, db_column = 'LTI_PK' )
        lti_id = models.CharField( max_length = 40, db_column = 'LTI_ID' )
        code = models.CharField( max_length = 40, db_column = 'CODE' )
        lti_date = models.DateField( db_column = 'LTI_DATE' )
        expiry_date = models.DateField( blank = True, null = True, db_column = 'EXPIRY_DATE' )
        transport_code = models.CharField( max_length = 4, db_column = 'TRANSPORT_CODE' )
        transport_ouc = models.CharField( max_length = 13, db_column = 'TRANSPORT_OUC' )
        transport_name = models.CharField( max_length = 30, db_column = 'TRANSPORT_NAME' )
        origin_type = models.CharField( max_length = 1, db_column = 'ORIGIN_TYPE' )
        origintype_desc = models.CharField( max_length = 12, blank = True, db_column = 'ORIGINTYPE_DESC' )
        origin_location_code = models.CharField( max_length = 10, db_column = 'ORIGIN_LOCATION_CODE' )
        origin_loc_name = models.CharField( max_length = 30, db_column = 'ORIGIN_LOC_NAME' )
        origin_wh_code = models.CharField( max_length = 13, blank = True, db_column = 'ORIGIN_WH_CODE' )
        origin_wh_name = models.CharField( max_length = 50, blank = True, db_column = 'ORIGIN_WH_NAME' )
        destination_location_code = models.CharField( max_length = 10, db_column = 'DESTINATION_LOCATION_CODE' )
        destination_loc_name = models.CharField( max_length = 30, db_column = 'DESTINATION_LOC_NAME' )
        consegnee_code = models.CharField( max_length = 12, db_column = 'CONSEGNEE_CODE' )
        consegnee_name = models.CharField( max_length = 80, db_column = 'CONSEGNEE_NAME' )
        requested_dispatch_date = models.DateField( blank = True, null = True, db_column = 'REQUESTED_DISPATCH_DATE' )
        project_wbs_element = models.CharField( max_length = 24, blank = True, db_column = 'PROJECT_WBS_ELEMENT' )
        si_record_id = models.CharField( max_length = 25, blank = True, db_column = 'SI_RECORD_ID' )
        si_code = models.CharField( max_length = 8, db_column = 'SI_CODE' )
        comm_category_code = models.CharField( max_length = 9, db_column = 'COMM_CATEGORY_CODE' )
        commodity_code = models.CharField( max_length = 18, db_column = 'COMMODITY_CODE' )
        cmmname = models.CharField( max_length = 100, blank = True, db_column = 'CMMNAME' )
        quantity_net = models.DecimalField( max_digits = 11, decimal_places = 3, db_column = 'QUANTITY_NET' )
        quantity_gross = models.DecimalField( max_digits = 11, decimal_places = 3, db_column = 'QUANTITY_GROSS' )
        number_of_units = models.DecimalField( max_digits = 7, decimal_places = 0, db_column = 'NUMBER_OF_UNITS' )
        unit_weight_net = models.DecimalField( max_digits = 8, decimal_places = 3, blank = True, null = True, db_column = 'UNIT_WEIGHT_NET' )
        unit_weight_gross = models.DecimalField( max_digits = 8, decimal_places = 3, blank = True, null = True, db_column = 'UNIT_WEIGHT_GROSS' )


        class Meta:
                db_table = u'epic_lti'

        def  __unicode__( self ):
            return u"%s %s  %s  %.0f " % ( self.valid(), self.coi_code(), self.cmmname, self.items_left() )

        def mydesc( self ):
            return self.code
        def commodity( self ):
            return self.cmmname
        def valid( self ):
            if RemovedLtis.objects.filter( lti = self.lti_pk ):
                return "Void "
            else:
                return ''
        def items_left( self ):
                lines = LoadingDetail.objects.filter( siNo = self )
                used = 0

                for line in lines:
                    used += line.numberUnitsLoaded
                if self.is_bulk():
                    return self.quantity_net - used
                else:
                    return self.number_of_units - used
        def reduce_si( self, units ):
                self.sitracker.update_units( units )
                return self.items_left()

#        def inStock(self):
#            try:
#                thisItem = EpicStock.objects.filter(wh_code=self.origin_wh_code).filter(si_code=self.si_code).filter(commodity_code=self.commodity_code)
#            except:
#                pass
#            return 
        def restore_si( self, units ):
                self.sitracker.update_units_restore( units )
                return self.items_left()
        def packaging( self ):
            pack = 'Unknown'
            try:
                mypkg = EpicStock.objects.filter( wh_code = self.origin_wh_code ).filter( si_code = self.si_code ).filter( commodity_code = self.commodity_code )
                pack = str( mypkg[0].packagename )
            except:
                pass
            return pack

        def is_bulk( self ):
            mypkg = self.packaging()
            if mypkg == 'BULK':
                return True
            else:
                return False
        def coi_code( self ):
            stock_items_qs = EpicStock.objects.filter( wh_code = self.origin_wh_code ).filter( si_code = self.si_code ).filter( commodity_code = self.commodity_code ).order_by( '-number_of_units' )
            if stock_items_qs.count() > 0:
                return str( stock_items_qs[0].origin_id[7:] )
            else:
                stock_items_qs = EpicStock.objects.filter( wh_code = self.origin_wh_code ).filter( si_code = self.si_code ).filter( comm_category_code = self.comm_category_code ).order_by( '-number_of_units' )
                if stock_items_qs.count() > 0:
                    return str( stock_items_qs[0].origin_id[7:] )
                else:
                    stock_items_qs = EpicStock.objects.filter( si_code = self.si_code ).filter( comm_category_code = self.comm_category_code ).order_by( '-number_of_units' )
                    if stock_items_qs.count() > 0:
                        return str( stock_items_qs[0].origin_id[7:] )
                    else:
                        return 'No Stock '

        def remove_lti( self ):
            all_removed = RemovedLtis.objects.all()
            this_lti = RemovedLtis()
            this_lti.lti = self
            if this_lti not in all_removed:
                this_lti.save()
        def get_stocks( self ):
            return EpicStock.objects.filter( wh_code = self.origin_wh_code ).filter( si_code = self.si_code ).filter( commodity_code = self.commodity_code )



class RemovedLtisManager( models.Manager ):
        def list( self ):
            listExl = []
            listOfExcluded = RemovedLtis.objects.all()
            for exl in listOfExcluded:
                listExl += [exl.lti.lti_pk]
            return listExl

## helper table for nolonger existing lti items
class RemovedLtis( models.Model ):
        lti = models.ForeignKey( LtiOriginal, primary_key = True )
        objects = RemovedLtisManager()
        class Meta:
                db_table = u'waybill_removed_ltis'
        def  __unicode__( self ):
                return self.lti.lti_id

class EpicPerson( models.Model ):
        person_pk = models.CharField( max_length = 20, blank = True, primary_key = True )
        org_unit_code = models.CharField( max_length = 13 )
        code = models.CharField( max_length = 7 )
        type_of_document = models.CharField( max_length = 2, blank = True )
        organization_id = models.CharField( max_length = 12 )
        last_name = models.CharField( max_length = 30 )
        first_name = models.CharField( max_length = 25 )
        title = models.CharField( max_length = 50, blank = True )
        document_number = models.CharField( max_length = 25, blank = True )
        e_mail_address = models.CharField( max_length = 100, blank = True )
        mobile_phone_number = models.CharField( max_length = 20, blank = True )
        official_tel_number = models.CharField( max_length = 20, blank = True )
        fax_number = models.CharField( max_length = 20, blank = True )
        effective_date = models.DateField( null = True, blank = True )
        expiry_date = models.DateField( null = True, blank = True )
        location_code = models.CharField( max_length = 10 )

        class Meta:
                db_table = u'epic_persons'
                verbose_name = 'COMPAS User'

        def  __unicode__( self ):
                return self.last_name + ', ' + self.first_name


class EpicStock( models.Model ):
        wh_pk = models.CharField( max_length = 90, blank = True, primary_key = True )
        wh_regional = models.CharField( max_length = 4, blank = True )
        wh_country = models.CharField( max_length = 15 )
        wh_location = models.CharField( max_length = 30 )
        wh_code = models.CharField( max_length = 13 )
        wh_name = models.CharField( max_length = 50, blank = True )
        project_wbs_element = models.CharField( max_length = 24, blank = True )
        si_record_id = models.CharField( max_length = 25 )
        si_code = models.CharField( max_length = 8 )
        origin_id = models.CharField( max_length = 23 )
        comm_category_code = models.CharField( max_length = 9 )
        commodity_code = models.CharField( max_length = 18 )
        cmmname = models.CharField( max_length = 100, blank = True )
        package_code = models.CharField( max_length = 17 )
        packagename = models.CharField( max_length = 50, blank = True )
        qualitycode = models.CharField( max_length = 1 )
        qualitydescr = models.CharField( max_length = 11, blank = True )
        quantity_net = models.DecimalField( null = True, max_digits = 12, decimal_places = 3, blank = True )
        quantity_gross = models.DecimalField( null = True, max_digits = 12, decimal_places = 3, blank = True )
        number_of_units = models.IntegerField()
        allocation_code = models.CharField( max_length = 10 )
        reference_number = models.CharField( max_length = 50 )

        class Meta:
                db_table = u'epic_stock'


        def  __unicode__( self ):
                return self.wh_name + '\t' + self.cmmname + '\t' + str( self.number_of_units )

        def packaging_description_short( self ):
            try:
                pck = PackagingDescriptonShort.objects.get( pk = self.package_code )
                return pck.packageShortName
            except:
                return self.packagename

class EpicLossReason( models.Model ):
        REASON_CODE = models.CharField( max_length = 5, primary_key = True )
        REASON = models.CharField( max_length = 80 )
        class Meta:
            db_table = u'epic_lossreason'
            verbose_name = 'Loss/Damages Reason'
        def  __unicode__( self ):
                return self.REASON

class LossesDamagesReason( models.Model ):
        compasRC = models.ForeignKey( EpicLossReason )
        compasCode = models.CharField( max_length = 20 )
        description = models.CharField( max_length = 80 )

        def  __unicode__( self ):
                return self.compasRC.REASON
        class Meta:
            verbose_name = 'COMPAS Loss/Damages Reason'


class LossesDamagesType( models.Model ):
        description = models.CharField( max_length = 20 )
        class Meta:
            verbose_name = 'Loss/Damages Type'
        def  __unicode__( self ):
                return self.description

class LoadingDetail( models.Model ):
        wbNumber = models.ForeignKey( Waybill )
        siNo = models.ForeignKey( LtiOriginal )
        numberUnitsLoaded = models.DecimalField( default = 0, blank = False, null = False, max_digits = 10, decimal_places = 3 )
        numberUnitsGood = models.DecimalField( default = 0, blank = True, null = True, max_digits = 10, decimal_places = 3 )
        numberUnitsLost = models.DecimalField( default = 0, blank = True, null = True, max_digits = 10, decimal_places = 3 )
        numberUnitsDamaged = models.DecimalField( default = 0, blank = True, null = True, max_digits = 10, decimal_places = 3 )
        unitsLostReason = models.ForeignKey( LossesDamagesReason, related_name = 'LD_LostReason', blank = True, null = True )
        unitsDamagedReason = models.ForeignKey( LossesDamagesReason, related_name = 'LD_DamagedReason', blank = True, null = True )
        unitsDamagedType = models.ForeignKey( LossesDamagesType, related_name = 'LD_DamagedType', blank = True, null = True )
        unitsLostType = models.ForeignKey( LossesDamagesType, related_name = 'LD_LossType', blank = True, null = True )
        overloadedUnits = models.BooleanField()
        loadingDetailSentToCompas = models.BooleanField()
        overOffloadUnits = models.BooleanField()

        audit_log = AuditLog()

        def check_stock( self ):

            thisStock = EpicStock.objects.filter( si_code = self.siNo.si_code ).filter( wh_code = self.siNo.origin_wh_code ).filter( commodity_code = self.siNo.commodity_code ).order_by( '-number_of_units' )
            for stock in thisStock:
                if self.siNo.is_bulk():
                    print 'HereB'
                    if self.numberUnitsLoaded <= stock.quantity_net:
                        return True
                    else:
                        print 'no b'
                else:
                    print 'HereN'
                    if self.numberUnitsLoaded <= stock.number_of_units :
                        return True
                    else:
                        print 'no n'
            print 'out'
            return False

        def check_reciept_item( self ): # Removed validation for offload!!!
#             totalUnitsOffloaded = self.numberUnitsGood+ self.numberUnitsDamaged + self.numberUnitsLost
#             if totalUnitsOffloaded > self.numberUnitsLoaded:
#                 return False
#             else:
                return True

        def get_stock_item( self ):
            try:
                stockItem = EpicStock.objects.filter( si_code = self.siNo.si_code ).filter( commodity_code = self.siNo.commodity_code ).filter( wh_code = self.siNo.origin_wh_code )
                return stockItem[0]
            except:
                try:
                    stockItem = EpicStock.objects.filter( si_code = self.siNo.si_code ).filter( comm_category_code = self.siNo.comm_category_code )
                    return stockItem[0]
                except:
                    return 'N/A'

        def calculate_total_net( self ):
                totalNet = ( self.numberUnitsLoaded * self.siNo.unit_weight_net ) / 1000
                return totalNet
        def calculate_total_gross( self ):
                totalGross = ( self.numberUnitsLoaded * self.siNo.unit_weight_gross ) / 1000
                return totalGross

        def calculate_net_received_good( self ):
                totalNet = ( self.numberUnitsGood * self.siNo.unit_weight_net ) / 1000
                return totalNet
        def calculate_gross_received_good( self ):
                totalGross = ( self.numberUnitsGood * self.siNo.unit_weight_gross ) / 1000
                return totalGross

        def calculate_net_received_damaged( self ):
                totalNet = ( self.numberUnitsDamaged * self.siNo.unit_weight_net ) / 1000
                return totalNet
        def calculate_gross_received_damaged( self ):
                totalGross = ( self.numberUnitsDamaged * self.siNo.unit_weight_gross ) / 1000
                return totalGross

        def calculate_net_received_lost( self ):
                totalNet = ( self.numberUnitsLost * self.siNo.unit_weight_net ) / 1000
                return totalNet
        def calculate_gross_received_lost( self ):
                totalGross = ( self.numberUnitsLost * self.siNo.unit_weight_gross ) / 1000
                return totalGross
        def calculate_total_received_units( self ):
                total = self.numberUnitsGood + self.numberUnitsDamaged
                return total
        def calculate_total_received_net( self ):
                total = self.calculate_net_received_good() + self.calculate_net_received_damaged()
                return total

        def  __unicode__( self ):
                return self.wbNumber.mydesc() + ' - ' + self.siNo.mydesc() + ' - ' + self.siNo.lti_pk

class DispatchPoint( models.Model ):
        origin_loc_name = models.CharField( 'Location Name', max_length = 40, blank = True )
        origin_location_code = models.CharField( 'Location Code', max_length = 40, blank = True )
        origin_wh_code = models.CharField( 'Warehouse Code', max_length = 40, blank = True )
        origin_wh_name = models.CharField( 'Warehouse Name', max_length = 80, blank = True )
        ACTIVE_START_DATE = models.DateField( 'Start of Service', null = True, blank = True )

        class Meta:
            verbose_name = 'Dispatch Warehouse'
        def  __unicode__( self ):
                return self.origin_wh_code + ' - ' + self.origin_loc_name + ' - ' + self.origin_wh_name

class ReceptionPoint( models.Model ):
        LOC_NAME = models.CharField( 'Location Name', max_length = 40, blank = True )
        LOCATION_CODE = models.CharField( 'Location Code', max_length = 40, blank = True )
        consegnee_code = models.CharField( 'Consengee Code', max_length = 40, blank = True )
        consegnee_name = models.CharField( 'Consengee Name', max_length = 80, blank = True )
        #DESC_NAME = models.CharField(max_length = 80, blank = True)
        ACTIVE_START_DATE = models.DateField( null = True, blank = True )
        def  __unicode__( self ):
                return self.LOC_NAME + ' - ' + self.consegnee_name
        class Meta:
            ordering = ['LOC_NAME', 'consegnee_name']
            verbose_name = 'Reception Warehouse'

class UserProfile( models.Model ):
        user = models.ForeignKey( User, unique = True, primary_key = True )#OneToOneField(User, primary_key = True)
        warehouses = models.ForeignKey( DispatchPoint, blank = True, null = True, verbose_name = 'Dispatch Warehouse' )
        receptionPoints = models.ForeignKey( ReceptionPoint, blank = True, null = True, verbose_name = 'Receipt Warehouse' )
        isCompasUser = models.BooleanField( 'Is Compas User' )
        isDispatcher = models.BooleanField( 'Is Dispatcher' )
        isReciever = models.BooleanField( 'Is Receiver' )
        isAllReceiver = models.BooleanField( 'Is MoE Receiver (Can Receipt for All Warehouses Beloning to MoE)' )
        compasUser = models.ForeignKey( EpicPerson, blank = True, null = True, verbose_name = 'Use this Compas User', help_text = 'Select the corrisponding user from Compas' )
        superUser = models.BooleanField( 'Super User', help_text = 'This user has Full Privileges to edit Waybills even after Signatures' )
        readerUser = models.BooleanField( 'Readonly User' )

        audit_log = AuditLog()
        def __unicode__( self ):
            if self.user.first_name and self.user.last_name:
                return "%s %s's profile (%s)" % ( self.user.first_name, self.user.last_name, self.user.username )
            else:
                return "%s's profile" % self.user.username

User.profile = property( lambda u: UserProfile.objects.get_or_create( user = u )[0] )



class SiTracker( models.Model ):
        LTI = models.OneToOneField( LtiOriginal, primary_key = True )
        number_units_left = models.DecimalField( decimal_places = 3, max_digits = 10 )
        number_units_start = models.DecimalField( decimal_places = 3, max_digits = 10 )

        def update_units( self, ammount ):
                self.number_units_left -= ammount
                self.save()
        def update_units_restore( self, ammount ):
                self.number_units_left += ammount
                self.save()
        def  __unicode__( self ):
                return self.number_units_left

class PackagingDescriptonShort( models.Model ):
        packageCode = models.CharField( primary_key = True, max_length = 5 )
        packageShortName = models.CharField( max_length = 10 )
        def  __unicode__( self ):
                return self.packageCode + ' - ' + self.packageShortName


class CompasLogger( models.Model ):
    timestamp = models.DateTimeField( null = True, blank = True )
    user = models.ForeignKey( User )
    action = models.CharField( max_length = 50, blank = True )
    errorRec = models.CharField( max_length = 2000, blank = True )
    errorDisp = models.CharField( max_length = 2000, blank = True )
    wb = models.ForeignKey( Waybill, blank = True, primary_key = True )
    lti = models.CharField( max_length = 50, blank = True )
    data_in = models.CharField( max_length = 5000, blank = True )
    data_out = models.CharField( max_length = 5000, blank = True )
    #loggercompas
    class Meta:
        db_table = u'loggercompas'

class SIWithRestant:
        SINumber = ''
        StartAmount = 0.0
        CurrentAmount = 0.0
        CommodityName = ''
        def __init__( self, SINumber, StartAmount, CommodityName ):
                self.SINumber = SINumber
                self.StartAmount = StartAmount
                self.CurrentAmount = StartAmount
                self.CommodityName = CommodityName

        def reduce_current( self, reduce ):
            self.CurrentAmount = self.CurrentAmount - reduce
        def get_current_amount( self ):

            return self.CurrentAmount
        def get_start_amount( self ):
                return self.StartAmount
