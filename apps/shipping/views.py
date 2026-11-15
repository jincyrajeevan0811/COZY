from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .services import check_pincode, estimate_delivery


@require_GET
def pincode_check(request):
    result = check_pincode(request.GET.get("pincode"))
    if result["serviceable"]:
        start, end = estimate_delivery(extra_days=result["extra_days"])
        result["estimate"] = f"{start:%a, %d %b} – {end:%a, %d %b}"
        request.session["pincode"] = request.GET.get("pincode")
    return JsonResponse(result)
