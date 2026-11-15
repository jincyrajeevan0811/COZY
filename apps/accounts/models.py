from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.core.validators import IMAGE_VALIDATORS

phone_validator = RegexValidator(r"^\+?[0-9]{10,13}$", "Enter a valid mobile number (10-13 digits).")
pincode_validator = RegexValidator(r"^[1-9][0-9]{5}$", "Enter a valid 6-digit PIN code.")


class AccessPermission(models.Model):
    """A database-driven permission used by COZY's role-based access control."""

    codename = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=150)
    module = models.CharField(max_length=60, db_index=True)

    class Meta:
        ordering = ["module", "codename"]
        verbose_name = "permission"

    def __str__(self):
        return f"{self.module}: {self.name}"


class Role(TimeStampedModel):
    SUPER_ADMIN = "super-admin"
    CUSTOMER = "customer"

    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(AccessPermission, blank=True, related_name="roles")
    is_staff_role = models.BooleanField(default=True, help_text="Staff roles can sign in to the COZY dashboard.")
    is_system = models.BooleanField(default=False, help_text="System roles cannot be deleted.")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        if "role" not in extra:
            extra["role"] = Role.objects.filter(slug=Role.CUSTOMER).first()
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("email_verified", True)
        extra.setdefault("role", Role.objects.filter(slug=Role.SUPER_ADMIN).first())
        if extra.get("is_staff") is not True or extra.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True.")
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=15, blank=True, validators=[phone_validator])
    role = models.ForeignKey(Role, null=True, blank=True, on_delete=models.SET_NULL, related_name="users")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False, help_text="Allows access to the internal Django admin.")
    email_verified = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now, db_index=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["first_name"]

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.first_name or self.email

    # ---- RBAC helpers -------------------------------------------------
    @property
    def is_super_admin(self):
        return self.is_active and (self.is_superuser or (self.role_id and self.role.slug == Role.SUPER_ADMIN))

    @property
    def is_staff_member(self):
        return self.is_active and (self.is_super_admin or bool(self.role_id and self.role.is_staff_role))

    def get_permission_codes(self):
        if not hasattr(self, "_perm_code_cache"):
            if not self.is_active or not self.role_id:
                self._perm_code_cache = set()
            else:
                self._perm_code_cache = set(self.role.permissions.values_list("codename", flat=True))
        return self._perm_code_cache

    def has_access(self, codename):
        """Check a COZY RBAC permission. Super Admin always passes."""
        if not self.is_active:
            return False
        if self.is_super_admin:
            return True
        return codename in self.get_permission_codes()

    @property
    def avatar_url(self):
        profile = getattr(self, "profile", None)
        if profile and profile.avatar:
            return profile.avatar.url
        return ""


class UserProfile(TimeStampedModel):
    GENDER_CHOICES = [("", "Prefer not to say"), ("female", "Female"), ("male", "Male"), ("other", "Other")]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(upload_to="profiles/", blank=True, validators=IMAGE_VALIDATORS)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    marketing_opt_in = models.BooleanField(default=True)

    def __str__(self):
        return f"Profile of {self.user}"

    def save(self, *args, **kwargs):
        from apps.core.utils import optimize_image

        optimize_image(self.avatar, max_size=600)
        super().save(*args, **kwargs)


class Address(TimeStampedModel):
    TYPE_CHOICES = [("home", "Home"), ("work", "Work"), ("other", "Other")]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=15, validators=[phone_validator])
    line1 = models.CharField("Address line 1", max_length=255)
    line2 = models.CharField("Address line 2", max_length=255, blank=True)
    landmark = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    pincode = models.CharField(max_length=6, validators=[pincode_validator])
    country = models.CharField(max_length=60, default="India")
    address_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default="home")
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_default", "-updated_at"]
        verbose_name_plural = "addresses"

    def __str__(self):
        return f"{self.full_name}, {self.city} - {self.pincode}"

    @property
    def one_line(self):
        parts = [self.line1, self.line2, self.landmark, self.city, self.state, self.pincode]
        return ", ".join(p for p in parts if p)

    def save(self, *args, **kwargs):
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).exclude(pk=self.pk).update(is_default=False)
        elif not Address.objects.filter(user=self.user).exclude(pk=self.pk).exists():
            self.is_default = True
        super().save(*args, **kwargs)
