from django import forms

from apps.core.forms import StyledFormMixin

from .models import ReturnRequest


class CancelOrderForm(StyledFormMixin, forms.Form):
    REASONS = [
        ("Ordered by mistake", "Ordered by mistake"),
        ("Found a better price", "Found a better price"),
        ("Delivery is taking too long", "Delivery is taking too long"),
        ("Want to change items / address", "Want to change items / address"),
        ("Other", "Other"),
    ]
    reason = forms.ChoiceField(choices=REASONS)
    details = forms.CharField(required=False, max_length=200, widget=forms.TextInput(attrs={"placeholder": "Anything else? (optional)"}))


class ReturnRequestForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ReturnRequest
        fields = ["reason", "description", "image"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4, "placeholder": "Tell us what went wrong"})}
        labels = {"image": "Photo of the item (optional)"}


class TrackOrderForm(StyledFormMixin, forms.Form):
    order_number = forms.CharField(max_length=20)
    email = forms.EmailField()
