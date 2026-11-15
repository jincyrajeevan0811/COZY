from django import forms

from apps.core.forms import StyledFormMixin


class NewsletterForm(StyledFormMixin, forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"placeholder": "Your email address"}))


class ContactForm(StyledFormMixin, forms.Form):
    CATEGORY_CHOICES = [
        ("order", "Order related"),
        ("payment", "Payment"),
        ("product", "Product enquiry"),
        ("return", "Return / refund"),
        ("other", "Other"),
    ]

    name = forms.CharField(max_length=120)
    email = forms.EmailField()
    phone = forms.CharField(max_length=15, required=False)
    category = forms.ChoiceField(choices=CATEGORY_CHOICES)
    subject = forms.CharField(max_length=200)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}), max_length=3000)
    website = forms.CharField(required=False, widget=forms.HiddenInput)  # honeypot

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Spam detected.")
        return ""
