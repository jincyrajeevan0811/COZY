from django import forms
from django.contrib.auth import authenticate, password_validation

from apps.core.forms import StyledFormMixin

from .models import Address, User, UserProfile


class RegisterForm(StyledFormMixin, forms.ModelForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput, strip=False)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput, strip=False)
    newsletter = forms.BooleanField(label="Send me new arrivals & offers", required=False, initial=True)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Please sign in.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        if p1:
            temp_user = User(email=cleaned.get("email", ""), first_name=cleaned.get("first_name", ""))
            try:
                password_validation.validate_password(p1, temp_user)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned

    def save(self, commit=True):
        user = User.objects.create_user(
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password1"],
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data.get("last_name", ""),
            phone=self.cleaned_data.get("phone", ""),
        )
        return user


class LoginForm(StyledFormMixin, forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}), strip=False)
    remember_me = forms.BooleanField(required=False, initial=True)

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        email = (self.cleaned_data.get("email") or "").lower()
        password = self.cleaned_data.get("password")
        if email and password:
            self.user_cache = authenticate(self.request, email=email, password=password)
            if self.user_cache is None:
                raise forms.ValidationError("Invalid email or password.")
        return self.cleaned_data

    def get_user(self):
        return self.user_cache


class UserUpdateForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone"]


class ProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["avatar", "date_of_birth", "gender", "marketing_opt_in"]
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"})}
        labels = {"marketing_opt_in": "Receive offers and new arrival emails"}


class AddressForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Address
        fields = [
            "full_name", "phone", "line1", "line2", "landmark", "city", "state", "pincode",
            "address_type", "is_default",
        ]
        labels = {"is_default": "Make this my default address"}
