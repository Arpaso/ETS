from django.forms import ModelForm
from django.http import HttpResponse, HttpResponseRedirect
from ets.waybill.views import *
from ets.waybill.models import *
from django import forms
from django.forms.extras.widgets import SelectDateWidget

class WaybillForm(ModelForm):

	dateOfLoading = forms.DateField(widget=SelectDateWidget())
	dateOfDispatch = forms.DateField(widget=SelectDateWidget())
	transportType = forms.CharField(widget=forms.RadioSelect(choices=Waybill.transport_type))
	transactionType = forms.CharField(widget=forms.RadioSelect(choices=Waybill.transaction_type_choice))
	dispatchRemarks=forms.CharField(widget=forms.TextInput(attrs={'size':'40'}),required=False)
	ltiNumber = forms.CharField(widget=forms.HiddenInput())
	transportContractor = forms.CharField(widget=forms.HiddenInput())
	transportSubContractor=forms.CharField(widget=forms.TextInput(attrs={'size':'40'}),required=False)
	transportDriverName=forms.CharField(widget=forms.TextInput(attrs={'size':'40'}),required=False)
	transportDriverLicenceID=forms.CharField(widget=forms.TextInput(attrs={'size':'40'}),required=False)
	transportVehicleRegistration=forms.CharField(widget=forms.TextInput(attrs={'size':'40'}),required=False)
	dispatcherName = forms.CharField(widget=forms.HiddenInput(),required=False)
	dispatcherTitle= forms.CharField(widget=forms.HiddenInput(),required=False)
	transportTrailerRegistration=forms.CharField(widget=forms.TextInput(attrs={'size':'40'}),required=False)
	class Meta:
		model = Waybill
		fields = [
			'ltiNumber',
        	'waybillNumber',
        	'dateOfLoading',
         	'dateOfDispatch',
        	'transactionType',
        	'transportType',
        	'dispatchRemarks',
        	'dispatcherName',
        	'dispatcherTitle',
        	'transportContractor',
        	'transportSubContractor',
        	'transportDriverName',
        	'transportDriverLicenceID',
        	'transportVehicleRegistration',
        	'transportTrailerRegistration',
        	'transportDispachSigned',
        	'containerOneNumber',
        	'containerTwoNumber',
        	'containerOneSealNumber',
        	'containerTwoSealNumber',
        	'containerOneRemarksDispatch',
        	'containerTwoRemarksDispatch',
        	'recipientLocation'
        	]

class WaybillRecieptForm(ModelForm):
	recipientArrivalDate = forms.DateField(widget=SelectDateWidget())
	recipientStartDischargeDate = forms.DateField(widget=SelectDateWidget())
	recipientEndDischargeDate = forms.DateField(widget=SelectDateWidget())
	
	
	class Meta:
		model = Waybill
		fields = [
				'waybillNumber',
				'recipientLocation',
				'recipientConsingee',
				'recipientName',
				'recipientTitle',
				'recipientArrivalDate',
				'recipientStartDischargeDate',
				'recipientEndDischargeDate',
				'recipientDistance',
				'recipientRemarks',
				'recipientSigned',
				'recipientSignedTimestamp'
			]


		
class MyModelChoiceField(ModelChoiceField):
    def label_from_instance(self, obj):
        return "%s - %s" % (obj.SI_CODE , obj.CMMNAME )

class LoadingDetailDispatchForm(ModelForm):
	class Meta:
		model = LoadingDetail
		fields = ('siNo','numberUnitsLoaded')

class LoadingDetailRecieptForm(ModelForm):
	class Meta:
		model = LoadingDetail
		fields = ('siNo','numberUnitsLoaded','numberUnitsGood','numberUnitsLost','numberUnitsDamaged','unitsLostReason','unitsDamagedReason',)