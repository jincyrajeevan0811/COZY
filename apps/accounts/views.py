from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.cache import cache
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.core.forms import StyledFormMixin
from apps.core.utils import client_ip
from apps.notifications.services import notify, notify_staff, send_templated_email

from .forms import AddressForm, LoginForm, ProfileForm, RegisterForm, UserUpdateForm
from .models import Address, User

EMAIL_VERIFY_SALT = "cozy-email-verify"


def _safe_next(request, default):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return nxt
    return default


def send_verification_email(request, user):
    token = signing.dumps({"uid": user.pk, "email": user.email}, salt=EMAIL_VERIFY_SALT)
    link = request.build_absolute_uri(reverse("accounts:verify_email", args=[token]))
    send_templated_email(
        "Verify your COZY account",
        [user.email],
        "emails/verify_email.html",
        {"user": user, "link": link},
    )


def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        user.profile.marketing_opt_in = form.cleaned_data.get("newsletter", False)
        user.profile.save()
        if form.cleaned_data.get("newsletter"):
            from apps.website_settings.models import NewsletterSubscriber

            NewsletterSubscriber.objects.get_or_create(email=user.email)
        login(request, user, backend="apps.accounts.backends.EmailBackend")
        send_verification_email(request, user)
        notify(
            user,
            "Welcome to COZY",
            "Your account has been created. Explore our latest collections!",
            link=reverse("products:list"),
            category="system",
            email_template="emails/welcome.html",
        )
        notify_staff("customers.view", "New customer registered", f"{user.full_name} ({user.email}) joined COZY.",
                     link=reverse("dashboard:customer_detail", args=[user.pk]))
        messages.success(request, "Welcome to COZY! Please check your inbox to verify your email.")
        return redirect(_safe_next(request, reverse("accounts:dashboard")))
    return render(request, "accounts/register.html", {"form": form, "next": request.GET.get("next", "")})


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request, reverse("accounts:dashboard")))
    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST":
        email = (request.POST.get("email") or "").lower()
        key = f"login-attempts:{client_ip(request)}:{email}"
        attempts = cache.get(key, 0)
        if attempts >= settings.LOGIN_RATE_LIMIT_ATTEMPTS:
            minutes = settings.LOGIN_RATE_LIMIT_WINDOW // 60
            messages.error(request, f"Too many failed sign-in attempts. Please try again in {minutes} minutes.")
            return render(request, "accounts/login.html", {"form": form, "next": request.POST.get("next", "")}, status=429)
        if form.is_valid():
            user = form.get_user()
            cache.delete(key)
            login(request, user)
            if not form.cleaned_data.get("remember_me"):
                request.session.set_expiry(0)
            messages.success(request, f"Welcome back, {user.get_short_name()}!")
            default = reverse("dashboard:home") if user.is_staff_member else reverse("accounts:dashboard")
            return redirect(_safe_next(request, default))
        cache.set(key, attempts + 1, settings.LOGIN_RATE_LIMIT_WINDOW)
    return render(request, "accounts/login.html", {"form": form, "next": request.GET.get("next", "")})


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, "You have been signed out.")
    return redirect("home")


def verify_email(request, token):
    try:
        data = signing.loads(token, salt=EMAIL_VERIFY_SALT, max_age=60 * 60 * 72)
        user = User.objects.get(pk=data["uid"], email=data["email"])
    except (signing.BadSignature, User.DoesNotExist, KeyError):
        messages.error(request, "This verification link is invalid or has expired.")
        return redirect("home")
    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=["email_verified"])
    messages.success(request, "Your email address has been verified. Thank you!")
    return redirect("accounts:dashboard" if request.user.is_authenticated else "accounts:login")


@login_required
@require_POST
def resend_verification(request):
    if request.user.email_verified:
        messages.info(request, "Your email is already verified.")
    else:
        key = f"verify-resend:{request.user.pk}"
        if cache.get(key):
            messages.warning(request, "A verification email was sent recently. Please wait a few minutes.")
        else:
            send_verification_email(request, request.user)
            cache.set(key, 1, 300)
            messages.success(request, "Verification email sent.")
    return redirect(_safe_next(request, reverse("accounts:dashboard")))


@login_required
def dashboard(request):
    from apps.orders.models import Order
    from apps.wishlist.models import WishlistItem

    orders = Order.objects.filter(user=request.user)
    context = {
        "recent_orders": orders.prefetch_related("items")[:5],
        "order_count": orders.count(),
        "active_orders": orders.exclude(status__in=["delivered", "cancelled", "returned", "refunded"]).count(),
        "total_spent": orders.filter(payment_status="paid").aggregate(t=Sum("grand_total"))["t"] or 0,
        "wishlist_count": WishlistItem.objects.filter(wishlist__user=request.user).count(),
        "default_address": request.user.addresses.filter(is_default=True).first(),
        "unread_notifications": request.user.notifications.filter(is_read=False, is_staff_alert=False).count(),
    }
    return render(request, "accounts/dashboard.html", context)


@login_required
def profile(request):
    user_form = UserUpdateForm(request.POST or None, instance=request.user)
    profile_form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user.profile)
    if request.method == "POST" and user_form.is_valid() and profile_form.is_valid():
        user_form.save()
        profile_form.save()
        messages.success(request, "Your profile has been updated.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"user_form": user_form, "profile_form": profile_form})


class StyledPasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    pass


@login_required
def change_password(request):
    form = StyledPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Your password has been changed.")
        return redirect("accounts:dashboard")
    return render(request, "accounts/change_password.html", {"form": form})


# ---------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------
@login_required
def address_list(request):
    return render(request, "accounts/addresses.html", {"addresses": request.user.addresses.all()})


@login_required
def address_form(request, pk=None):
    address = get_object_or_404(Address, pk=pk, user=request.user) if pk else None
    initial = {} if address else {"full_name": request.user.full_name, "phone": request.user.phone}
    form = AddressForm(request.POST or None, instance=address, initial=initial)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.user = request.user
        obj.save()
        messages.success(request, "Address saved.")
        return redirect(_safe_next(request, reverse("accounts:addresses")))
    return render(request, "accounts/address_form.html", {"form": form, "address": address, "next": request.GET.get("next", "")})


@login_required
@require_POST
def address_delete(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    was_default = address.is_default
    address.delete()
    if was_default:
        nxt = request.user.addresses.first()
        if nxt:
            nxt.is_default = True
            nxt.save()
    messages.success(request, "Address removed.")
    return redirect("accounts:addresses")


@login_required
@require_POST
def address_set_default(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    address.is_default = True
    address.save()
    messages.success(request, "Default address updated.")
    return redirect(_safe_next(request, reverse("accounts:addresses")))


# ---------------------------------------------------------------------------
# Other account pages
# ---------------------------------------------------------------------------
@login_required
def my_reviews(request):
    reviews = request.user.reviews.select_related("product").prefetch_related("images")
    return render(request, "accounts/reviews.html", {"reviews": reviews})


@login_required
def offers(request):
    from django.db.models import F, Q

    from apps.coupons.models import Coupon

    now = timezone.now()
    coupons = (
        Coupon.objects.filter(is_active=True, is_public=True, valid_from__lte=now)
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=now))
        .filter(Q(usage_limit__isnull=True) | Q(used_count__lt=F("usage_limit")))
    )
    return render(request, "accounts/offers.html", {"coupons": coupons})


@login_required
def payment_history(request):
    from apps.payments.models import Payment

    payments = Payment.objects.filter(order__user=request.user).select_related("order")
    return render(request, "accounts/payments.html", {"payments": payments})


# ---------------------------------------------------------------------------
# Password reset (Django's secure token views with COZY templates)
# ---------------------------------------------------------------------------
class StyledPasswordResetForm(StyledFormMixin, PasswordResetForm):
    pass


class StyledSetPasswordForm(StyledFormMixin, SetPasswordForm):
    pass


password_reset = auth_views.PasswordResetView.as_view(
    template_name="accounts/password_reset.html",
    email_template_name="emails/password_reset.txt",
    html_email_template_name="emails/password_reset.html",
    subject_template_name="emails/password_reset_subject.txt",
    form_class=StyledPasswordResetForm,
    success_url=reverse_lazy("accounts:password_reset_done"),
)
password_reset_done = auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html")
password_reset_confirm = auth_views.PasswordResetConfirmView.as_view(
    template_name="accounts/password_reset_confirm.html",
    form_class=StyledSetPasswordForm,
    success_url=reverse_lazy("accounts:password_reset_complete"),
)
password_reset_complete = auth_views.PasswordResetCompleteView.as_view(
    template_name="accounts/password_reset_complete.html"
)
