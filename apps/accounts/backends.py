from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """Authenticate with a case-insensitive email address."""

    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        UserModel = get_user_model()
        identifier = (email or username or kwargs.get(UserModel.USERNAME_FIELD) or "").strip().lower()
        if not identifier or password is None:
            return None
        try:
            user = UserModel._default_manager.get(email__iexact=identifier)
        except UserModel.DoesNotExist:
            UserModel().set_password(password)  # mitigate timing attacks
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
