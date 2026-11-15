from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.notifications.services import notify_staff
from apps.orders.models import Order, OrderItem
from apps.products.models import Product

from .forms import ReviewForm
from .models import ProductReview, ReviewImage


@login_required
def write_review(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    review = ProductReview.objects.filter(product=product, user=request.user).first()
    form = ReviewForm(request.POST or None, request.FILES or None, instance=review)
    if request.method == "POST" and form.is_valid():
        purchased = (
            OrderItem.objects.filter(order__user=request.user, product=product, order__status=Order.DELIVERED)
            .order_by("-order__created_at").first()
        )
        obj = form.save(commit=False)
        obj.product = product
        obj.user = request.user
        obj.order_item = purchased
        obj.is_verified_purchase = purchased is not None  # only real delivered purchases get the badge
        obj.status = "pending"
        obj.save()
        for image in form.cleaned_data.get("images") or []:
            ReviewImage.objects.create(review=obj, image=image)
        notify_staff("reviews.manage", "New review awaiting approval", f"{obj.rating}★ for {product.name}",
                     link=reverse("dashboard:review_list") + "?status=pending", category="review")
        messages.success(request, "Thank you! Your review will appear once approved.")
        return redirect(product.get_absolute_url() + "#reviews")
    return render(request, "products/review_form.html", {"form": form, "product": product, "review": review})
