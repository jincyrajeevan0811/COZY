from django import forms


class StyledFormMixin:
    """Adds Bootstrap 5 classes to every widget so templates stay clean."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            css = widget.attrs.get("class", "")
            if isinstance(widget, (forms.CheckboxInput,)):
                widget.attrs["class"] = f"{css} form-check-input".strip()
            elif isinstance(widget, (forms.CheckboxSelectMultiple, forms.RadioSelect)):
                widget.attrs["class"] = css
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs["class"] = f"{css} form-select".strip()
            elif isinstance(widget, forms.ClearableFileInput) or isinstance(widget, forms.FileInput):
                widget.attrs["class"] = f"{css} form-control".strip()
                widget.attrs.setdefault("accept", "image/*" if isinstance(field, forms.ImageField) else "")
            else:
                widget.attrs["class"] = f"{css} form-control".strip()
            if field.required and not isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("required", "required")
            if not widget.attrs.get("placeholder") and isinstance(widget, (forms.TextInput, forms.EmailInput, forms.NumberInput, forms.Textarea)):
                widget.attrs["placeholder"] = field.label or name.replace("_", " ").title()
