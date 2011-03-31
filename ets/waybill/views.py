# Create your views here.
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import login, logout
from django.core import serializers
from django.core.urlresolvers import reverse
from django.forms.formsets import BaseFormSet
from django.forms.models import inlineformset_factory, modelformset_factory
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import Template, RequestContext, Library, Node, loader, Context
from django.views.decorators.csrf import csrf_exempt
from kiowa.utils.encode import DecimalJSONEncoder
from ets.waybill.compas import *
from ets.waybill.forms import *
from ets.waybill.models import *
from ets.waybill.tools import *
import datetime
import os, StringIO, zlib, base64, string
from django.contrib import messages
import simplejson as json


def prep_req( request ):
    return{'user': request.user}

@login_required
def select_action( request ):
    """
    View: select_action 
    URL: /ets/select-action
    Template: /ets/waybill/templates/select_action.html
    Gives the loggedin user a choise of possible actions sepending on roles
    """

    return render_to_response( 'select_action.html', context_instance = RequestContext( request ) )

@login_required
def listOfLtis( request, origin ):
    """
    View: listOfLtis 
    URL: ets/waybill/list/{{warehouse}}
    Template: /ets/waybill/templates/ltis.html
    Shows the LTIs that are in a specific warehouse
    """
    still_ltis = []
    ltis = LtiOriginal.objects.values( 'code', 'destination_loc_name', 'consegnee_name', 'lti_date' ).distinct().filter( origin_wh_code = origin )

    for lti in ltis:
        listOfSI_withDeduction = restant_si( lti['code'] )
        for item in listOfSI_withDeduction:
            if item.CurrentAmount > 0:
                if not lti in still_ltis:
                    still_ltis.append( lti )

    return render_to_response( 'lti/ltis.html', {'ltis':still_ltis}, context_instance = RequestContext( request ) )

## Show all ltis 
@login_required
def ltis( request ):
    """
    View:
    ltis
    URL: ets/waybill/list
    Shows all the LTIs
    template:
    /ets/waybill/templates/ltis.html
    """
    ltis = LtiOriginal.objects.values( 'code', 'destination_loc_name', 'consegnee_name', 'lti_date', 'requested_dispatch_date', 'origin_loc_name' ).distinct()
    still_ltis = []

    for lti in ltis:
        listOfSI_withDeduction = restant_si( lti['code'] )
        for item in listOfSI_withDeduction:
            if item.CurrentAmount > 0:
                if not lti in still_ltis:
                    still_ltis.append( lti )
    return render_to_response( 'lti/ltis_all_qs.html', {'ltis':still_ltis}, context_instance = RequestContext( request ) )


def import_ltis( request ):
    """
    View: import_ltis 
    URL: ets/waybill/import
    Template: /ets/waybill/templates/status.html
    Executes Imports of LTIs, Persons, Stock, and updates SiTracker,
    add tag to say when last done
    """

    print 'Import Persons'
    update_persons()
    print 'Import GEO'
    import_geo()
    print 'Import Stock'
    import_stock()
    print 'Import Setup'
    import_setup()
    print 'Import LTIs'
    import_lti()
    status = 'Import Finished'
    track_compas_update()
    messages.add_message( request, messages.INFO, status )

    return HttpResponseRedirect( reverse( select_action ) )

def lti_detail_url( request, lti_code ):
    """
    View: lti_detail_url 
    URL: ets/waybill/info/(lti_code)
    Template: /ets/waybill/templates/lti/detailed_lti.html
    Show detail of LTI and link to create waybill
    """
    detailed_lti = LtiOriginal.objects.filter( code = lti_code )
    listOfWaybills = Waybill.objects.filter( invalidated = False ).filter( ltiNumber = lti_code )
    listOfSI_withDeduction = restant_si( lti_code )
    lti_more_wb = False

    for item in listOfSI_withDeduction:
        if item.CurrentAmount > 0:
            lti_more_wb = True
    return render_to_response( 'lti/detailed_lti.html',
                              {'detailed':detailed_lti, 'lti_id':lti_code, 'listOfWaybills':listOfWaybills, 'listOfSI_withDeduction':listOfSI_withDeduction, 'moreWBs':lti_more_wb},
                              context_instance = RequestContext( request ) )

@login_required
def dispatch( request ):
    """
    View: dispatch 
    URL: ets/waybill/dispatch
    Template: None
    Redirects to Lti Details.
    """
    try:
        return HttpResponseRedirect( reverse( listOfLtis, args = [request.user.get_profile().warehouses.origin_wh_code] ) )
    except:
        return HttpResponseRedirect( reverse( select_action ) )

#### Waybill Views
@login_required
def waybill_create( request, lti_pk ):
    try:
        detailed_lti = LtiOriginal.objects.get( lti_pk = lti_pk )
        return render_to_response( 'detailed_waybill.html',
                              {'detailed':detailed_lti, 'lti_id':lti_pk},
                              context_instance = RequestContext( request ) )
    except:
        return HttpResponseRedirect( reverse( select_action ) )

@login_required
def waybill_finalize_dispatch( request, wb_id ):
    """
    View: waybill_finalize_dispatch
    URL: ets/waybill/dispatch
    Templet:None
    called when user pushes Print Original on dispatch
    Redirects to Lti Details
    """
    current_wb = Waybill.objects.get( id = wb_id )
    current_wb.transportDispachSigned = True
    current_wb.transportDispachSignedTimestamp = datetime.datetime.now()
    current_wb.dispatcherSigned = True
    current_wb.auditComment = 'Print Dispatch Original'
    for lineitem in current_wb.loadingdetail_set.select_related():
        lineitem.siNo.reduce_si( lineitem.numberUnitsLoaded )
    current_wb.save()
    status = 'Waybill ' + current_wb.waybillNumber + ' Dispatch Signed'
    messages.add_message( request, messages.INFO, status )
    return HttpResponseRedirect( reverse( lti_detail_url, args = [current_wb.ltiNumber] ) )

@login_required
def    waybill_finalize_receipt( request, wb_id ):
    """
    View: waybill_finalize_receipt 
    URL:ets/waybill/receipt/
    Template:None
    Redirects to Lti Details
    Called when user pushes Print Original on Receipt
    """
    try:
        current_wb = Waybill.objects.get( id = wb_id )
        current_wb.recipientSigned = True
        current_wb.transportDeliverySignedTimestamp = datetime.datetime.now()
        current_wb.recipientSignedTimestamp = datetime.datetime.now()
        current_wb.transportDeliverySigned = True
        current_wb.auditComment = 'Print Dispatch Receipt'
        current_wb.save()
        status = 'Waybill ' + current_wb.waybillNumber + ' Receipt Signed'
        messages.add_message( request, messages.INFO, status )
    except:
        pass
    return HttpResponseRedirect( reverse( waybill_reception_list ) )


@login_required
def singleWBDispatchToCompas( request, wb_id ):
    """
    View: singleWBDispatchToCompas
    URL: 
    
    Sends a single Dipatch into compas
    """
    waybill = Waybill.objects.get( id = wb_id )
    the_compas = compas_write()
    error_message = ''
    error_codes = ''
    status_wb = the_compas.write_dispatch_waybill_compas( wb_id )
    if  status_wb:
        #aok
        try:
            errorlog = CompasLogger.objects.get( wb = waybill )
            errorlog.delete()
        except:
            pass
        waybill.waybillSentToCompas = True
        waybill.save()
        status = 'Waybill ' + waybill.waybillNumber + ' Sucsessfully pushed to COMPAS'
        messages.add_message( request, messages.INFO, status )
    else:
        try:
            errorlog = CompasLogger.objects.get( wb = waybill )
            errorlog.user = request.user
            errorlog.errorDisp = the_compas.ErrorMessages
            errorlog.timestamp = datetime.datetime.now()
            errorlog.save()
        except:
            errorlog = CompasLogger()
            errorlog.wb = waybill
            errorlog.user = request.user
            errorlog.errorDisp = the_compas.ErrorMessages
            errorlog.timestamp = datetime.datetime.now()
            errorlog.save()

        waybill.waybillValidated = False
        status = 'Problem sending to compas: ' + the_compas.ErrorMessages
        messages.add_message( request, messages.ERROR, status )
        waybill.save()
        error_message += waybill.waybillNumber + '-' + the_compas.ErrorMessages
        error_codes += waybill.waybillNumber + '-' + the_compas.ErrorCodes
    # Update stock after submit off waybill
    import_stock()
    return HttpResponseRedirect( reverse( waybill_validate_dispatch_form ) )

@login_required
def singleWBReceiptToCompas( request, wb_id ):
    """
    View: singleWBReceiptToCompas
    URL: ...
    Template: /ets/waybill/templates/compas/status_waybill_compas_rec.html
    Sends a single Receipt into compas
    """
    #profile = getMyProfile(request)
    waybill = Waybill.objects.get( id = wb_id )
    the_compas = compas_write()
    error_message = ''
    error_codes = ''
    status_wb = the_compas.write_receipt_waybill_compas( waybill.id )
    if  status_wb:
        try:
            errorlog = CompasLogger.objects.get( wb = waybill )
            errorlog.delete()
        except:
            pass

        waybill.waybillRecSentToCompas = True
        waybill.save()
    else:
        try:
            errorlog = CompasLogger.objects.get( wb = waybill )
            errorlog.user = request.user
            errorlog.errorDisp = the_compas.ErrorMessages
            errorlog.timestamp = datetime.datetime.now()
            errorlog.save()
        except:
            errorlog = ''
            errorlog = CompasLogger()
            errorlog.wb = waybill
            errorlog.user = request.user
            errorlog.errorRec = the_compas.ErrorMessages
            errorlog.timestamp = datetime.datetime.now()
            errorlog.save()

        waybill.waybillReceiptValidated = False
        waybill.save()
        error_message += waybill.waybillNumber + '-' + the_compas.ErrorMessages
        error_codes += waybill.waybillNumber + '-' + the_compas.ErrorCodes
# add field to say compas error/add logging Change to use messages....
    return render_to_response( 'compas/status_waybill_compas_rec.html',
                              {'waybill':waybill,

                              'error_message':error_message,
                              'error_codes':error_codes},
                              context_instance = RequestContext( request ) )

def listCompasWB( request ):
    list_waybills_disp = Waybill.objects.filter( invalidated = False ).filter( waybillSentToCompas = True )
    list_waybills_rec = Waybill.objects.filter( invalidated = False ).filter( waybillRecSentToCompas = True )
    return render_to_response( 'compas/list_waybills_compas_all.html',
                              {'waybill_list':list_waybills_disp, 'waybill_list_rec':list_waybills_rec},
                              context_instance = RequestContext( request ) )

@login_required
def receiptToCompas( request ):

    list_waybills = Waybill.objects.filter( invalidated = False ).filter( waybillReceiptValidated = True ).filter( waybillRecSentToCompas = False ).filter( waybillSentToCompas = True )
    the_compas = compas_write()
    error_message = ''
    error_codes = ''
    for waybill in list_waybills:
        # call compas and read return
        status_wb = the_compas.write_receipt_waybill_compas( waybill.id )
        if  status_wb:
            waybill.waybillRecSentToCompas = True
            waybill.save()
        else:
            error_message += waybill.waybillNumber + '-' + the_compas.ErrorMessages
            error_codes += waybill.waybillNumber + '-' + the_compas.ErrorCodes
    return render_to_response( 'compas/list_waybills_compas_received.html',
                              {'waybill_list':list_waybills, 'error_message':error_message, 'error_codes':error_codes},
                              context_instance = RequestContext( request ) )

def invalidate_waybill( request, wb_id ):
    #first mark waybill invalidate, then zero the stock usage for each line and update the si table
    invalidate_waybill_action( wb_id )
    current_wb = Waybill.objects.get( id = wb_id )
    status = 'Waybill %s has now been Removed' % ( current_wb.waybillNumber )
    return render_to_response( 'status.html',
                              {'status':status},
                              context_instance = RequestContext( request ) )

def invalidate_waybill_action( wb_id ):
    current_wb = Waybill.objects.get( id = wb_id )
    for lineitem in current_wb.loadingdetail_set.select_related():
        lineitem.siNo.restore_si( lineitem.numberUnitsLoaded )
        lineitem.numberUnitsLoaded = 0
        lineitem.save()
    current_wb.invalidated = True
    current_wb.save()


@login_required
def waybill_validate_form_update( request, wb_id ):
    """
    Admin Edit waybill
    waybill/validate/(.*)
    waybill/waybill_detail.html
    """
    current_wb = Waybill.objects.get( id = wb_id )
    lti_code = current_wb.ltiNumber
    current_lti = LtiOriginal.objects.filter( code = lti_code )
    current_audit = current_wb.audit_log.all()
    current_wb.auditComment = ''
    myerror = current_wb.errors()


    if myerror:
        current_wb.dispError = myerror.errorDisp
        current_wb.recError = myerror.errorRec

    class LoadingDetailDispatchForm( ModelForm ):
        siNo = ModelChoiceField( queryset = LtiOriginal.objects.filter( code = lti_code ), label = 'Commodity' )
        numberUnitsLoaded = forms.CharField( widget = forms.TextInput( attrs = {'size':'5'} ), required = False )
        numberUnitsGood = forms.CharField( widget = forms.TextInput( attrs = {'size':'5'} ), required = False )
        numberUnitsLost = forms.CharField( widget = forms.TextInput( attrs = {'size':'5'} ), required = False )
        numberUnitsDamaged = forms.CharField( widget = forms.TextInput( attrs = {'size':'5'} ), required = False )

        class Meta:
            model = LoadingDetail
            fields = ( 'wbNumber', 'siNo', 'numberUnitsLoaded', 'numberUnitsGood', 'numberUnitsLost', 'numberUnitsDamaged', 'unitsLostReason', 'unitsDamagedReason', 'unitsDamagedType', 'unitsLostType', 'overloadedUnits', 'overOffloadUnits' )

    LDFormSet = inlineformset_factory( Waybill, LoadingDetail, LoadingDetailDispatchForm, fk_name = "wbNumber", extra = 0 )
    qs = Places.objects.filter( geo_name = current_lti[0].destination_loc_name ).filter( organization_id = current_lti[0].consegnee_code )
    if len( qs ) == 0:
        qs = Places.objects.filter( geo_name = current_lti[0].destination_loc_name )

    if request.method == 'POST':

        form = WaybillFullForm( request.POST, instance = current_wb )
        form.fields["destinationWarehouse"].queryset = qs
        formset = LDFormSet( request.POST, instance = current_wb )
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            return HttpResponseRedirect( reverse( waybill_search ) )
    else:
        form = WaybillFullForm( instance = current_wb )
        form.fields["destinationWarehouse"].queryset = qs

        formset = LDFormSet( instance = current_wb )
    return render_to_response( 'waybill/waybill_detail.html', {'form': form, 'lti_list':current_lti, 'formset':formset, 'audit':current_audit}, context_instance = RequestContext( request ) )


@login_required
def waybill_view( request, wb_id ):
    ## TODO: remove dependency of zippedWB
    try:
        waybill_instance = Waybill.objects.get( id = wb_id )
        zippedWB = wb_compress( wb_id )
        lti_detail_items = LtiOriginal.objects.filter( code = waybill_instance.ltiNumber )
        number_of_lines = waybill_instance.loadingdetail_set.select_related().count()
        extra_lines = 5 - number_of_lines
        my_empty = [''] * extra_lines
        try:
            disp_person_object = EpicPerson.objects.get( person_pk = waybill_instance.dispatcherName )
        except:
            disp_person_object = ''
        try:
            rec_person_object = EpicPerson.objects.get( person_pk = waybill_instance.recipientName )
        except:
            rec_person_object = ''
    except:
        return HttpResponseRedirect( reverse( select_action ) )
    data_dict = {
                 'object': waybill_instance,
                 'LtiOriginal': lti_detail_items,
                 'disp_person': disp_person_object,
                 'rec_person': rec_person_object,
                 'extra_lines': my_empty,
                 'zippedWB': zippedWB,
    }
    return render_to_response( 'waybill/print/waybill_detail_view.html', data_dict, context_instance = RequestContext( request ) )


@login_required
def waybill_view_reception( request, wb_id ):
    ## TODO: remove dependency of zippedWB
    rec_person_object = ''
    disp_person_object = ''
    zippedWB = ''
    try:
        waybill_instance = Waybill.objects.get( id = wb_id )
        lti_detail_items = LtiOriginal.objects.filter( code = waybill_instance.ltiNumber )
        number_of_lines = waybill_instance.loadingdetail_set.select_related().count()
        extra_lines = 5 - number_of_lines
        my_empty = [''] * extra_lines
        zippedWB = wb_compress( wb_id )
    except:
        return HttpResponseRedirect( reverse( select_action ) )
    try:
        disp_person_object = EpicPerson.objects.get( person_pk = waybill_instance.dispatcherName )
        rec_person_object = EpicPerson.objects.get( person_pk = waybill_instance.recipientName )
    except:
        pass
    return render_to_response( 'waybill/print/waybill_detail_view_reception.html',
                              {'object':waybill_instance,
                              'LtiOriginal':lti_detail_items,
                              'disp_person':disp_person_object,
                              'rec_person':rec_person_object,
                              'extra_lines':my_empty,
                              'zippedWB':zippedWB},
                              context_instance = RequestContext( request ) )

@login_required
def waybill_reception( request, wb_code ):
    # get the LTI info
    current_wb = Waybill.objects.get( id = wb_code )
    current_lti = current_wb.ltiNumber
    if  request.user.profile.isReciever or request.user.profile.superUser or request.user.profile.compasUser:
        pass
    else:
        return HttpResponseRedirect( reverse( waybill_view , args = [wb_code] ) )
#    current_wb.auditComment = 'Receipt Action'
#    current_wb.save()

    class LoadingDetailRecForm( ModelForm ):
        siNo = ModelChoiceField( queryset = LtiOriginal.objects.filter( code = current_lti ), label = 'Commodity', )
        numberUnitsGood = forms.CharField( widget = forms.TextInput( attrs = {'size':'5'} ), required = False )
        numberUnitsLost = forms.CharField( widget = forms.TextInput( attrs = {'size':'5'} ), required = False )
        numberUnitsDamaged = forms.CharField( widget = forms.TextInput( attrs = {'size':'5'} ), required = False )
        class Meta:
            model = LoadingDetail
            fields = ( 'wbNumber', 'siNo', 'numberUnitsGood', 'numberUnitsLost', 'numberUnitsDamaged', 'unitsLostReason',
                        'unitsDamagedReason', 'unitsDamagedType', 'unitsLostType', 'overloadedUnits', 'overOffloadUnits' )
        def clean_unitsLostReason( self ):
            #cleaned_data = self.cleaned_data
            my_losses = self.cleaned_data.get( 'numberUnitsLost' )
            my_lr = self.cleaned_data.get( 'unitsLostReason' )
            if  float( my_losses ) > 0 :
                if my_lr == None:
                    raise forms.ValidationError( "You have forgotten to select the Loss Reason" )
            return my_lr

        def clean_unitsDamagedReason( self ):
            my_damage = self.cleaned_data.get( 'numberUnitsDamaged' )
            my_dr = self.cleaned_data.get( 'unitsDamagedReason' )
            if float( my_damage ) > 0:
                if my_dr == None:
                    raise forms.ValidationError( "You have forgotten to select the Damage Reason" )
            return my_dr


        def clean_unitsLostType( self ):
            #cleaned_data = self.cleaned_data
            my_losses = self.cleaned_data.get( 'numberUnitsLost' )
            my_lr = self.cleaned_data.get( 'unitsLostType' )
            if  float( my_losses ) > 0 :
                if my_lr == None:
                    raise forms.ValidationError( "You have forgotten to select the Loss Type" )
            return my_lr

        def clean_unitsDamagedType( self ):
            my_damage = self.cleaned_data.get( 'numberUnitsDamaged' )
            my_dr = self.cleaned_data.get( 'unitsDamagedType' )

            if float( my_damage ) > 0:
                if my_dr == None:
                    raise forms.ValidationError( "You have forgotten to select the Damage Type" )
            return my_dr


        def clean( self ):
            cleaned = self.cleaned_data
            numberUnitsGood = float( cleaned.get( 'numberUnitsGood' ) )
            loadedUnits = float( self.instance.numberUnitsLoaded )
            damadgedUnits = float( cleaned.get( 'numberUnitsDamaged' ) )
            lostUnits = float( cleaned.get( 'numberUnitsLost' ) )
            totaloffload = float( numberUnitsGood + damadgedUnits + lostUnits )
            if not cleaned.get( 'overOffloadUnits' ):
                if not totaloffload == loadedUnits:
                    myerror = ''
                    if totaloffload > loadedUnits:
                        myerror = "%.3f Units loaded but %.3f units accounted for" % ( loadedUnits, totaloffload )
                    if totaloffload < loadedUnits:
                        myerror = "%.3f Units loaded but only %.3f units accounted for" % ( loadedUnits, totaloffload )
                    self._errors['numberUnitsGood'] = self._errors.get( 'numberUnitsGood', [] )
                    self._errors['numberUnitsGood'].append( myerror )
                    raise forms.ValidationError( myerror )
            return cleaned
    LDFormSet = inlineformset_factory( Waybill, LoadingDetail, LoadingDetailRecForm, fk_name = "wbNumber", extra = 0 )

    if request.method == 'POST':

        form = WaybillRecieptForm( request.POST, instance = current_wb )

        formset = LDFormSet( request.POST, instance = current_wb )
        if form.is_valid() and formset.is_valid():
            form.recipientTitle = request.user.profile.compasUser.title
            form.recipientName = request.user.profile.compasUser.person_pk


            wb_new = form.save()
            wb_new.recipientTitle = request.user.profile.compasUser.title
            wb_new.recipientName = request.user.profile.compasUser.person_pk
            wb_new.auditComment = 'Receipt Action'
            wb_new.save()
            formset.save()
            return HttpResponseRedirect( '../viewwb_reception/' + str( current_wb.id ) ) #
        else:
            loggit( formset.errors )
            loggit( form.errors )
    else:
        if current_wb.recipientArrivalDate:
            form = WaybillRecieptForm( instance = current_wb )
            #form.instance.auditComment= 'Receipt Action'
            form.recipientTitle = request.user.profile.compasUser.title
            form.recipientName = request.user.profile.compasUser.last_name + ', ' + request.user.profile.compasUser.first_name
            #form.auditComment = 'Receipt Action'
        else:
            form = WaybillRecieptForm( instance = current_wb,
            initial = {
                'recipientArrivalDate':datetime.date.today(),
                'recipientStartDischargeDate':datetime.date.today(),
                'recipientEndDischargeDate':datetime.date.today(),
                'recipientName':       request.user.profile.compasUser.last_name + ', ' + request.user.profile.compasUser.first_name,
                'recipientTitle':       request.user.profile.compasUser.title,
                #'auditComment': 'Receipt Action',
            }
        )
        formset = LDFormSet( instance = current_wb )
    return render_to_response( 'waybill/receiveWaybill.html',
            {'form': form, 'lti_list':current_lti, 'formset':formset},
            context_instance = RequestContext( request ) )

@login_required
def waybill_reception_list( request ):
    waybills = Waybill.objects.filter( invalidated = False ).filter( recipientSigned = False )
    return render_to_response( 'waybill/reception_list.html',
                              {'object_list':waybills},
                              context_instance = RequestContext( request ) )

def waybill_search( request ):
    search_string = ''
    isSuperUser = False
    try:
        search_string = request.GET['wbnumber']
    except:
        pass

    found_wb = Waybill.objects.filter( invalidated = False ).filter( waybillNumber__icontains = search_string )
    my_valid_wb = []

    if request.user.profile != '' :
        for waybill in found_wb:
            if request.user.profile.isCompasUser or request.user.profile.readerUser or ( request.user.profile.warehouses and waybill.origin_wh_code == request.user.profile.warehouses.origin_wh_code ) or ( request.user.profile.receptionPoints and  waybill.consegnee_code == request.user.profile.receptionPoints.consegnee_code and waybill.destination_loc_name == request.user.profile.receptionPoints.LOC_NAME ) or ( request.user.profile.isAllReceiver and waybill.consegnee_code == 'W200000475' ):
                my_valid_wb.append( waybill.id )

    if request.user.profile.superUser or request.user.profile.readerUser or request.user.profile.isCompasUser:
        isSuperUser = True

    return render_to_response( 'waybill/list_waybills.html',
                              {'waybill_list':found_wb, 'my_wb':my_valid_wb, 'isSuperUser':isSuperUser},
                              context_instance = RequestContext( request ) )


### Create Waybill 
@login_required
def waybillCreate( request, lti_code ):
    # get the LTI info 2
    current_lti = LtiOriginal.objects.filter( code = lti_code )

    class LoadingDetailDispatchForm( ModelForm ):
        siNo = ModelChoiceField( queryset = LtiOriginal.objects.filter( code = lti_code ), label = 'Commodity' )
        overload = forms.BooleanField( required = False )
        class Meta:
            model = LoadingDetail
            fields = ( 'siNo', 'numberUnitsLoaded', 'wbNumber', 'overloadedUnits', 'overOffloadUnits' )

        def clean( self ):
            try:
                cleaned = self.cleaned_data
                siNo = cleaned.get( "siNo" )
                units = cleaned.get( "numberUnitsLoaded" )
                overloaded = cleaned.get( 'overloadedUnits' )
                max_items = siNo.items_left()

                if units > max_items + self.instance.numberUnitsLoaded and  overloaded == False: #and not overloaded:
                    myerror = "Overloaded!"
                    self._errors['numberUnitsLoaded'] = self._errors.get( 'numberUnitsLoaded', [] )
                    self._errors['numberUnitsLoaded'].append( myerror )
                    raise forms.ValidationError( myerror )
                return cleaned
            except:
                    myerror = "Value error!"
                    self._errors['numberUnitsLoaded'] = self._errors.get( 'numberUnitsLoaded', [] )
                    self._errors['numberUnitsLoaded'].append( myerror )
                    raise forms.ValidationError( myerror )

    LDFormSet = inlineformset_factory( Waybill, LoadingDetail, form = LoadingDetailDispatchForm, fk_name = "wbNumber", formset = BaseLoadingDetailFormFormSet, extra = 5, max_num = 5 )
    current_wh = ''
    if request.method == 'POST':
        form = WaybillForm( request.POST )
        form.fields["destinationWarehouse"].queryset = Places.objects.filter( geo_name = current_lti[0].destination_loc_name )
        ## Make Better using the organization_id
        formset = LDFormSet( request.POST )
#        tempinstances = formset.save(commit=False)
        if form.is_valid() and formset.is_valid():
            wb_new = form.save()
            instances = formset.save( commit = False )
            wb_new.waybillNumber = new_waybill_no( wb_new )
            for subform in instances:
                subform.wbNumber = wb_new
                subform.save()
            wb_new.save()
            return HttpResponseRedirect( '../viewwb/' + str( wb_new.id ) )
        else:
            loggit( formset.errors )
            loggit( form.errors )
            loggit( formset.non_form_errors )
    else:
        qs = Places.objects.filter( geo_name = current_lti[0].destination_loc_name ).filter( organization_id = current_lti[0].consegnee_code )
        if len( qs ) == 0:
            qs = Places.objects.filter( geo_name = current_lti[0].destination_loc_name )
        else:
            current_wh = qs[0]
        form = WaybillForm( 
            initial = {
                    'dispatcherName':      request.user.profile.compasUser.person_pk,
                    'dispatcherTitle':      request.user.profile.compasUser.title,
                    'ltiNumber':         current_lti[0].code,
                    'dateOfLoading':     datetime.date.today(),
                    'dateOfDispatch':    datetime.date.today(),
                    'recipientLocation': current_lti[0].destination_loc_name,
                    'recipientConsingee':current_lti[0].consegnee_name,
                    'transportContractor': current_lti[0].transport_name,
                    'invalidated':'False',
                    'destinationWarehouse':current_wh,
                    'waybillNumber':'N/A'
                }
        )
        form.fields["destinationWarehouse"].queryset = qs

        formset = LDFormSet()
    return render_to_response( 'waybill/createWaybill.html', {'form': form, 'lti_list':current_lti, 'formset':formset}, context_instance = RequestContext( request ) )

@login_required
def waybill_edit( request, wb_id ):
    try:
        current_wb = Waybill.objects.get( id = wb_id )
        lti_code = current_wb.ltiNumber
        current_lti = LtiOriginal.objects.filter( code = lti_code )
    except:
        current_wb = ''
    class LoadingDetailDispatchForm( ModelForm ):
        siNo = ModelChoiceField( queryset = LtiOriginal.objects.filter( code = lti_code ), label = 'Commodity' )
        class Meta:
            model = LoadingDetail
            fields = ( 'id', 'siNo', 'numberUnitsLoaded', 'wbNumber', 'overloadedUnits' )
        def clean( self ):
            try:
                cleaned = self.cleaned_data
                siNo = cleaned.get( "siNo" )
                units = cleaned.get( "numberUnitsLoaded" )
                overloaded = cleaned.get( 'overloadedUnits' )
                max_items = siNo.items_left()
                if units > max_items + self.instance.numberUnitsLoaded and overloaded == False:
                        myerror = "Overloaded!"
                        self._errors['numberUnitsLoaded'] = self._errors.get( 'numberUnitsLoaded', [] )
                        self._errors['numberUnitsLoaded'].append( myerror )
                        raise forms.ValidationError( myerror )
                return cleaned
            except:
                    myerror = "Value error!"
                    self._errors['numberUnitsLoaded'] = self._errors.get( 'numberUnitsLoaded', [] )
                    self._errors['numberUnitsLoaded'].append( myerror )
                    raise forms.ValidationError( myerror )
    LDFormSet = inlineformset_factory( Waybill, LoadingDetail, LoadingDetailDispatchForm, fk_name = "wbNumber", formset = BaseLoadingDetailFormFormSet, extra = 5, max_num = 5 )
    if request.method == 'POST':
        form = WaybillForm( request.POST, instance = current_wb )
        formset = LDFormSet( request.POST, instance = current_wb )
        if form.is_valid() and formset.is_valid():
            wb_new = form.save()
            formset.save()
            return HttpResponseRedirect( reverse( waybill_view, args = [wb_new.id] ) )
    else:
        form = WaybillForm( instance = current_wb )
        form.fields["destinationWarehouse"].queryset = Places.objects.filter( GEO_NAME = current_lti[0].destination_loc_name )
        formset = LDFormSet( instance = current_wb )
    return render_to_response( 'waybill/createWaybill.html', {'form': form, 'lti_list':current_lti, 'formset':formset}, context_instance = RequestContext( request ) )

@login_required
def waybill_validate_dispatch_form( request ):
    ValidateFormset = modelformset_factory( Waybill, fields = ( 'id', 'waybillValidated', ), extra = 0 )
    validatedWB = Waybill.objects.filter( invalidated = False ).filter( waybillValidated = True ).filter( waybillSentToCompas = False )

    issue = ''
    errorMessage = 'Problems with Stock, Not enough in Dispatch Warehouse'
    if request.method == 'POST':
        formset = ValidateFormset( request.POST, WaybillValidationFormset )
        if  formset.is_valid() :
            instances = formset.save( commit = False )
            for form in  instances:
                try:
                    if form.check_lines():
                        form.auditComment = 'Validated Dispatch'
                        try:
                            errorlog = CompasLogger.objects.get( wb = form )
                            errorlog.user = ''
                            errorlog.errorDisp = ''
                            errorlog.timestamp = datetime.datetime.now()
                            errorlog.save()
                        except:
                            pass
                    else:
                        form.auditComment = 'Tried to Validate Dispatch'
                        issue = 'Problems with Stock on WB:  ' + str( form )
                        form.waybillValidated = False
                        messages.add_message( request, messages.ERROR, issue )
                        try:
                            errorlog = CompasLogger.objects.get( wb = form )
                            errorlog.user = request.user
                            errorlog.errorDisp = errorMessage
                            errorlog.timestamp = datetime.datetime.now()
                            errorlog.save()
                        except:
                            errorlog = CompasLogger()
                            errorlog.wb = form
                            errorlog.user = request.user
                            errorlog.errorDisp = errorMessage
                            errorlog.timestamp = datetime.datetime.now()
                            errorlog.save()
                except:
                        form.auditComment = 'Tried to Validate Dispatch'
                        issue = 'Problems with Stock on WB:  ' + str( form )
                        form.waybillValidated = False
                        messages.add_message( request, messages.ERROR, issue )
                        try:
                            errorlog = CompasLogger.objects.get( wb = form )
                            errorlog.user = request.user
                            errorlog.errorDisp = errorMessage
                            errorlog.timestamp = datetime.datetime.now()
                            errorlog.save()
                        except:
                            errorlog = CompasLogger()
                            errorlog.wb = form
                            errorlog.user = request.user
                            errorlog.errorDisp = errorMessage
                            errorlog.timestamp = datetime.datetime.now()
                            errorlog.save()

            formset.save()
    waybills = Waybill.objects.filter( invalidated = False ).filter( waybillValidated = False ).filter( dispatcherSigned = True )
    formset = ValidateFormset( queryset = waybills )
    return render_to_response( 'validate/validateForm.html', {'formset':formset, 'validatedWB':validatedWB}, context_instance = RequestContext( request ) )

@login_required
def waybill_validate_receipt_form( request ):
    ValidateFormset = modelformset_factory( Waybill, fields = ( 'id', 'waybillReceiptValidated', ), extra = 0 )
    validatedWB = Waybill.objects.filter( invalidated = False ).filter( waybillReceiptValidated = True ).filter( waybillRecSentToCompas = False ).filter( waybillSentToCompas = True )
    issue = ''
    errorMessage = 'Problems with Waybill, More Offloaded than Loaded, Update Dispatched Units!'
    if request.method == 'POST':
        formset = ValidateFormset( request.POST )
        if  formset.is_valid():
            instances = formset.save( commit = False )
            for form in  instances:
                if form.check_lines_receipt():
                    form.auditComment = 'Validated Receipt'
                    try:
                        errorlog = CompasLogger.objects.get( wb = form )
                        errorlog.user = request.user
                        errorlog.errorRec = ''
                        errorlog.timestamp = datetime.datetime.now()
                        errorlog.save()
                    except:
                        pass
                else:
                    form.auditComment = 'Tried to Validate Receipt'
                    issue = 'Problems with Stock on WB:  ' + str( form )
                    messages.add_message( request, messages.ERROR, issue )
                    form.waybillReceiptValidated = False
                    try:
                        errorlog = CompasLogger.objects.get( wb = form )
                        errorlog.user = request.user
                        errorlog.errorRec = errorMessage
                        errorlog.timestamp = datetime.datetime.now()
                        errorlog.save()
                    except:
                        errorlog = CompasLogger()
                        errorlog.wb = form
                        errorlog.user = request.user
                        errorlog.errorRec = errorMessage
                        errorlog.timestamp = datetime.datetime.now()
                        errorlog.save()
            formset.save()

    waybills = Waybill.objects.filter( invalidated = False ).filter( waybillReceiptValidated = False ).filter( recipientSigned = True ).filter( waybillValidated = True )
    formset = ValidateFormset( queryset = waybills )

    return render_to_response( 'validate/validateReceiptForm.html', {'formset':formset, 'validatedWB':validatedWB}, context_instance = RequestContext( request ) )


# Shows a page with the Serialized Waybill in comressed & uncompressed format
@login_required
def serialize( request, wb_code ):
    data = serialize_wb( wb_code )# serializers.serialize('json',list(waybill_to_serialize)+list(items_to_serialize))    
    zippedWB = wb_compress( wb_code )
    return render_to_response( 'blank.html', {'status':data, 'ziped':zippedWB, 'wb_code':wb_code},
                              context_instance = RequestContext( request ) )

## receives a POST with the compressed or uncompressed WB and sends you to the Receive WB 
@login_required
def deserialize( request ):
    waybillnumber = ''
    wb_data = request.POST['wbdata']
    wb_serialized = ''
    if wb_data[0] == '[':
        wb_serialized = wb_data
    else:
        wb_serialized = un64unZip( wb_data )
    for obj in serializers.deserialize( "json", wb_serialized ):
        if type( obj.object ) is Waybill:
            waybillnumber = obj.object.id
    return HttpResponseRedirect( '../receive/' + str( waybillnumber ) )

## Serialization of fixtures    
def fixtures_serialize():
    # serialise each of the fixtures 
    #     DispatchPoint
    dispatchPointsData = DispatchPoint.objects.all()
    receptionPointData = ReceptionPoint.objects.all()
    packagingDescriptonShort = PackagingDescriptonShort.objects.all()
    lossesDamagesReason = LossesDamagesReason.objects.all()
    lossesDamagesType = LossesDamagesType.objects.all()
    serialized_data = serializers.serialize( 'json', list( dispatchPointsData ) + list( receptionPointData ) + list( packagingDescriptonShort ) + list( lossesDamagesReason ) + list( lossesDamagesType ) )
    init_file = open( 'waybill/fixtures/initial_data.json', 'w' )
    init_file.writelines( serialized_data )
    init_file.close()

def custom_show_toolbar( request ):
    return True

def view_stock( request ):
    stocklist = EpicStock.objects.all()
    return render_to_response( 'stock/stocklist.html', {'stocklist':stocklist}, context_instance = RequestContext( request ) )

def viewLogView( request ):
    status = '<h3>Log view</h3><pre>' + viewLog() + '</pre>'
    return render_to_response( 'status.html',
                              {'status':status},
                              context_instance = RequestContext( request ) )

def profile( request ):
    status = request.user.get_profile()
    return render_to_response( 'status.html',
                              {'status':status},
                              context_instance = RequestContext( request ) )

#Reports  
def ltis_report( request ):
    ltis = LtiOriginal.objects.all()
    items = []
    for lti in ltis:
        items += lti.loadingdetail_set.select_related()
    response = HttpResponse( mimetype = 'text/csv' )
    response['Content-Disposition'] = 'attachment; filename=list-' + str( datetime.date.today() ) + '.csv'
    t = loader.get_template( 'reporting/list_ltis.txt' )
    c = Context( {
            'ltis': ltis,
        } )
    response.write( t.render( c ) )
    return response

def dispatch_report_wh( request, wh ):
    ltis = LtiOriginal.objects.filter( origin_wh_code = wh )
    items = []
    for lti in ltis:
        items += lti.loadingdetail_set.select_related()
    response = HttpResponse( mimetype = 'text/csv' )
    response['Content-Disposition'] = 'attachment; filename=list-' + wh + '-' + str( datetime.date.today() ) + '.csv'
    t = loader.get_template( 'reporting/list_ltis.txt' )
    c = Context( {
            'ltis': ltis,
        } )
    response.write( t.render( c ) )
    return response
#    return render_to_response('reporting/list_ltis.txt', context_instance=RequestContext(request))

def receipt_report_wh( request, loc, cons ):
    ltis = LtiOriginal.objects.filter( destination_location_code = loc ).filter( consegnee_code = cons )
    items = []
    for lti in ltis:
        items += lti.loadingdetail_set.select_related()
    response = HttpResponse( mimetype = 'text/csv' )
    response['Content-Disposition'] = 'attachment; filename=receipt-' + loc + '-' + str( datetime.date.today() ) + '.csv'
    t = loader.get_template( 'reporting/list_ltis.txt' )
    c = Context( {
            'ltis': ltis,
        } )
    response.write( t.render( c ) )
    return response

def receipt_report_cons( request, cons ):
    ltis = LtiOriginal.objects.filter( consegnee_code = cons )
    items = []
    for lti in ltis:
        items += lti.loadingdetail_set.select_related()
    response = HttpResponse( mimetype = 'text/csv' )
    response['Content-Disposition'] = 'attachment; filename=list-' + str( datetime.date.today() ) + '.csv'
    t = loader.get_template( 'reporting/list_ltis.txt' )
    c = Context( {
            'ltis': ltis,
        } )
    response.write( t.render( c ) )
    return response

def select_report( request ):
    return render_to_response( 'reporting/select_report.html', context_instance = RequestContext( request ) )
def select_data( request ):
        if request.method == 'POST': # If the form has been submitted...
            form = WarehouseForm( request.POST ) # A form bound to the POST data
            if form.is_valid(): # All validation rules pass
                return render_to_response( 'reporting/select_data.html', context_instance = RequestContext( request ) )
        else:
            form = WarehouseForm() # An unbound form
            return render_to_response( 'reporting/select_data.html', {'form': form, } )

def barcode_qr( request, wb ):
    import sys
    if sys.platform == 'darwin':
        from qrencode import Encoder
        enc = Encoder()
        myz = wb_compress( wb )
        im = enc.encode( myz, { 'width': 350 } )
        response = HttpResponse( mimetype = "image/png" )
        im.save( response, "PNG" )
    else:
        import subprocess
        myz = wb_compress( wb )
        mydata = subprocess.Popen( ['zint', '--directpng', '--barcode=58', '-d%s' % myz ], stdout = subprocess.PIPE )
        image = mydata.communicate()[0]
        #print mydata.communicate()
        response = HttpResponse( image, mimetype = "Image/png" )
    return response

@csrf_exempt
def post_synchronize_waybill( request ):
    '''
    This method is called by the offline application,
    that posts a serialized waybill.
    The waybill is deserialized and stored in the online database.
    '''
    if request.method == 'POST':
        serilized_waybill = request.POST['serilized_waybill']

        # change app_label
        serilized_waybill_str = str( serilized_waybill ).replace( '"offliner.', '"waybill.' )

        wb = None

        # try to deserialize waybill and loadingdetails and store in waybill online db
        is_an_update = False
        for obj in serializers.deserialize( "json", serilized_waybill_str ):
            #from waybill.models import Waybill, LoadingDetail
            if isinstance( obj.object, Waybill ):
                if Waybill.objects.filter( waybillNumber = obj.object.waybillNumber ).count() == 0:
                    # perform an insert
                    try:
                        obj.object.id = None
                        obj.object.save()
                        wb = obj.object
                    except:
                        print 'Exception when inserting Waybill'
                else:
                    is_an_update = True
                    # perform an update
                    try:
                        obj.object.id = Waybill.objects.filter( waybillNumber = obj.object.waybillNumber )[0].id
                        obj.object.save()
                        wb = obj.object
                    except:
                        print 'Exception when updating Waybill'

            elif isinstance( obj.object, LoadingDetail ) and wb is not None and not is_an_update:
                try:
                    obj.object.id = None
                    obj.object.wbNumber = wb
                    obj.object.save()
                except:
                    print 'Exception when saving LoadingDetail'
    response = HttpResponse( 'SYNCHRONIZATION_DONE' )
    return response


@csrf_exempt
def get_synchronize_stock( request ):
    '''
    This method is called by the offline application.
    The stocks identified by the warehouse_code in request are serialized and sended to the offline application.
    '''
    if request.method == 'GET':

        warehouse_code = request.GET['warehouse_code']
        stocks_list = EpicStock.objects.filter( wh_code = warehouse_code )

        from kiowa.db.utils import instance_as_dict
        l = []
        for element in stocks_list:
            l.append( instance_as_dict( element ) )

        serialized_stocks = json.dumps( l, cls = DecimalJSONEncoder )

        response = HttpResponse( serialized_stocks, mimetype = 'application/json' )

    return response


@csrf_exempt
def get_synchronize_lti( request ):
    '''
    This method is called by the offline application.
    The ltis identified by the warehouse_code in request are serialized and sended to the offline application.
    '''
    if request.method == 'GET':

        warehouse_code = request.GET['warehouse_code']

#        from waybill.models import LtiOriginal    
        ltis_list = LtiOriginal.objects.filter( origin_wh_code = warehouse_code )

        from kiowa.db.utils import instance_as_dict
        l = []
        for element in ltis_list:
            l.append( instance_as_dict( element ) )

        serialized_ltis = json.dumps( l, cls = DecimalJSONEncoder )

        response = HttpResponse( serialized_ltis, mimetype = 'application/json' )

    return response

def get_wb_stock( request ):
    print 'Donwload'
    wh = request.GET['warehouse']
    data = serialized_all_wb_stock( wh )
    print data
    response = HttpResponse( mimetype = 'text/csv' )
    response['Content-Disposition'] = 'attachment; filename=data-' + settings.COMPAS_STATION + '-' + str( datetime.date.today() ) + '.csv'
    response.write( data )
    return response


@csrf_exempt
def get_synchronize_waybill( request ):
    '''
    This method is called by the offline application.
    The waybills that has the destinationWarehause equal to warehouse_code in request are serialized and sended to the offline application.
    '''
    if request.method == 'GET':

        warehouse_code = request.GET['warehouse_code']

        #from waybill.models import Waybill    
        waybills_list = Waybill.objects.filter( destinationWarehouse__pk = warehouse_code )
        from kiowa.db.utils import instance_as_dict
        l = []
        for element in waybills_list:
            l.append( instance_as_dict( element ) )
        serialized_waybills = json.dumps( l, cls = DecimalJSONEncoder )
        response = HttpResponse( serialized_waybills, mimetype = 'application/json' )

    return response

def get_synchronize_waybill2( request ):
    '''
    This method is called by the offline application.
    The waybills that has the destinationWarehause equal to warehouse_code in request are serialized and sended to the offline application.
    '''
    try:
        warehouse_code = request.GET['warehouse_code']
    except:
        warehouse_code = 'CCBJ004'
    ld = []
    ltis = []
    stck = []
    #from waybill.models import Waybill    
    waybills_list = Waybill.objects.filter( destinationWarehouse = warehouse_code )
    for waybill_to_serialize in waybills_list:
        loadingdetails_to_serialize = waybill_to_serialize.loadingdetail_set.select_related()
        # Add related LtiOriginals to serialized representation
        ltis_to_serialize = LtiOriginal.objects.filter( code = waybill_to_serialize.ltiNumber )
        # Add related EpicStocks to serialized representation
        stocks_to_serialize = []
        for lti in ltis_to_serialize:
            for s in lti.get_stocks():
                stocks_to_serialize.append( s )
        ld += loadingdetails_to_serialize
        ltis += ltis_to_serialize
        stck += stocks_to_serialize

    data = serializers.serialize( 'json', list( waybills_list ) + list( ld ) + list( ltis ) + list( stck ) )

    ## testing it to see deser
    print data
    for deserialized_object in serializers.deserialize( "json", data ):

        print deserialized_object

    response = HttpResponse( data, mimetype = 'application/json' )

    return response

@csrf_exempt
def get_all_data( request ):
    print 'See'
    data = serialized_all_items()
    response = HttpResponse( data, mimetype = 'application/json' )
    return response
@csrf_exempt
def get_all_data_download( request ):
    print 'Donwload'
    data = serialized_all_items()
    response = HttpResponse( mimetype = 'text/csv' )
    response['Content-Disposition'] = 'attachment; filename=data-' + settings.COMPAS_STATION + '-' + str( datetime.date.today() ) + '.csv'
    response.write( data )
    return response