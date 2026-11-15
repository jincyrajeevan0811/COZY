from django import forms

from apps.core.forms import StyledFormMixin

from .models import SupportTicket


class TicketForm(StyledFormMixin, forms.Form):
    category = forms.ChoiceField(choices=SupportTicket.CATEGORY_CHOICES)
    order_number = forms.CharField(max_length=20, required=False, label="Order number (optional)")
    subject = forms.CharField(max_length=200)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}), max_length=3000)


class ReplyForm(StyledFormMixin, forms.Form):
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Write a reply…"}), max_length=3000)
