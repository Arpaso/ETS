import datetime

from django.forms.models import  BaseModelFormSet, BaseInlineFormSet
from django.forms.formsets import formset_factory, BaseFormSet
from django import forms
#from django.forms.extras.widgets import SelectDateWidget
from django.utils.translation import ugettext, ugettext_lazy as _

from uni_form.helpers import FormHelper, Layout, Fieldset, Row, HTML

from ets import models as ets_models

UNDEFINED_MESSAGE = "N/A"

class WaybillSearchForm( forms.Form ):
    q = forms.CharField(required=False, label=_('Waybill code'))


class DispatchWaybillForm( forms.ModelForm ):
    
    class Meta:
        model = ets_models.Waybill
        exclude = (
            'order',
            'status',
            'validated',
            'sent_compas',
            
            'date_created',
            'date_modified',
            'date_removed',
            'dispatcher_person',
            'transport_dispach_signed_date',
        )
    
    helper = FormHelper()
    
    # create the layout object
    helper.add_layout(Layout(
        Fieldset(ugettext('Date'), Row('loading_date', 'dispatch_date')),
        Fieldset(ugettext('General'),
                'destination',
                Row('transaction_type', 'transport_type'),
                'dispatch_remarks',
                 ),
        Fieldset(ugettext('Transport'),
                 'transport_sub_contractor',
                 Row('transport_driver_name', 'transport_driver_licence'),
                 Row('transport_vehicle_registration', 'transport_trailer_registration'),
                 ),
        Fieldset(ugettext('Container'),
                 Row('container_one_number', 'container_one_seal_number', 'container_one_remarks_dispatch'),
                 Row('container_two_number', 'container_two_seal_number', 'container_two_remarks_dispatch'),
                 )
    ))
                      
    #helper.add_input(Submit('add', _('Create waybill')))
    helper.form_tag = False


class LoadingDetailDispatchForm( forms.ModelForm ):
    
    overload = forms.BooleanField( required = False )

    class Meta:
        model = ets_models.LoadingDetail
        fields = ( 'stock_item', 'number_of_units', 'overloaded_units', 'over_offload_units' )
    

class BaseLoadingDetailFormSet(object):
    
#    def append_non_form_error( self, message ):
#        errors = super( BaseLoadingDetailFormFormSet, self ).non_form_errors()
#        errors.append( message )
#        raise forms.ValidationError( errors )
    
    def clean(self):
        super(BaseLoadingDetailFormSet, self).clean()
        count = 0
        for form in self.forms:
            if not hasattr(form, 'cleaned_data'):
                continue

            if form.is_bound and getattr(form, 'cleaned_data', {}).get('number_of_units'):
                count += 1
        
        if count < 1:
            raise forms.ValidationError( _('You must have at least one commodity') )
    
    helper = FormHelper()
    
    # create the layout object
    helper.add_layout(Layout(Row('stock_item', 'number_of_units', 'overloaded_units', 
                                 'over_offload_units', 'overload',)))
    helper.formset_tag = False


class WaybillRecieptForm( forms.ModelForm ):
    
    class Meta:
        model = ets_models.ReceiptWaybill
        exclude = (
            'waybill',
            'validated',
            'sent_compas',
            'person',
            'signed_date',
        )
    
    helper = FormHelper()
    
    # create the layout object
    helper.add_layout(Layout(
        Fieldset(ugettext('Dates'), Row('arrival_date', 'start_discharge_date', 'end_discharge_date')),
        Fieldset(ugettext('Containers'), Row('container_one_remarks_reciept', 'container_two_remarks_reciept')),
        Fieldset('', Row('distance', 'remarks')),
    ))
    
    helper.form_tag = False


class LoadingDetailRecieptForm( forms.ModelForm ):
    
    def __init__(self, *args, **kwargs):
        super(LoadingDetailRecieptForm, self).__init__(*args, **kwargs)
        
        for field_name in ('units_lost_reason', 'units_damaged_reason'):
            self.fields[field_name].queryset = self.fields[field_name].queryset.filter(category=self.instance.stock_item.commodity.category)
        
    
    class Meta:
        model = ets_models.LoadingDetail
        fields = (
            'stock_item',
            'number_units_good', 
            'number_units_lost', 'units_lost_reason',
            'number_units_damaged', 'units_damaged_reason',
        )
        widgets = {
            'number_units_good': forms.TextInput(attrs={'size': 5}),
            'number_units_lost': forms.TextInput(attrs={'size': 5}),
            'number_units_damaged': forms.TextInput(attrs={'size': 5}),
        }


class BaseRecieptFormFormSet(BaseInlineFormSet):
    
    helper = FormHelper()
    
    # create the layout object
    helper.add_layout(Layout(
        #HTML('<strong>{{ form.instance.origin_id }}</strong> <strong>{{ form.instance.commodity_name }}</strong>'),
        Row(
        'stock_item', 'number_units_good', 
        'number_units_lost', 'units_lost_reason',
        'number_units_damaged', 'units_damaged_reason',
    )))
    helper.formset_tag = False


class WaybillFullForm(forms.ModelForm):
    class Meta:
        model = ets_models.Waybill
    

class WaybillValidationFormset( BaseModelFormSet ):
    def clean( self ):
        issue = ''
        super( WaybillValidationFormset, self ).clean()
        for form in self.forms:
            if not form.check_lines():
                #TODO: Refactor it
                valid = False
                issue += ' WB: ' + str( form )
                raise form.ValidationError( _("You have an error") )
            
            if not valid:
                ##TODO: cleanup such things
                print issue


class MyModelChoiceField( forms.ModelChoiceField ):
    def label_from_instance( self, obj ):
        return "%s - %s" % ( obj.si_code , obj.cmmname )
