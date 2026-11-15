from django import forms

from apps.core.forms import StyledFormMixin
from apps.core.validators import IMAGE_VALIDATORS

from .models import ProductReview


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"multiple": True, "accept": "image/*"}))
        kwargs.setdefault("validators", IMAGE_VALIDATORS)
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(d, initial) for d in data if d][:4]
        return [single(data, initial)] if data else []


class ReviewForm(StyledFormMixin, forms.ModelForm):
    rating = forms.TypedChoiceField(choices=[(i, i) for i in range(5, 0, -1)], coerce=int,
                                    widget=forms.RadioSelect(attrs={"class": "rating-input"}))
    images = MultipleImageField(required=False, label="Add photos (up to 4)")

    class Meta:
        model = ProductReview
        fields = ["rating", "title", "comment"]
        widgets = {"comment": forms.Textarea(attrs={"rows": 4, "placeholder": "What did you love about it?"})}
