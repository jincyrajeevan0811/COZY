from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.orders.models import Order

from .forms import ReplyForm, TicketForm
from .models import SupportTicket
from .services import add_reply, create_ticket


@login_required
def ticket_list(request):
    tickets = SupportTicket.objects.filter(user=request.user)
    return render(request, "support/ticket_list.html", {"tickets": tickets})


@login_required
def ticket_create(request):
    initial = {"order_number": request.GET.get("order", "")}
    if request.GET.get("order"):
        initial["category"] = "order"
    form = TicketForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        order = None
        if form.cleaned_data.get("order_number"):
            order = Order.objects.filter(order_number=form.cleaned_data["order_number"].strip().upper(),
                                         user=request.user).first()
        ticket = create_ticket(
            user=request.user, name=request.user.full_name, email=request.user.email, phone=request.user.phone,
            subject=form.cleaned_data["subject"], message=form.cleaned_data["message"],
            category=form.cleaned_data["category"], order=order,
        )
        messages.success(request, f"Ticket {ticket.ticket_number} created. Our team will reply shortly.")
        return redirect("support:detail", ticket_number=ticket.ticket_number)
    return render(request, "support/ticket_form.html", {"form": form})


@login_required
def ticket_detail(request, ticket_number):
    ticket = get_object_or_404(SupportTicket, ticket_number=ticket_number, user=request.user)
    form = ReplyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if ticket.status == "closed":
            messages.error(request, "This ticket is closed. Please open a new ticket.")
        else:
            add_reply(ticket, request.user, form.cleaned_data["message"], is_staff=False)
            messages.success(request, "Reply sent.")
        return redirect("support:detail", ticket_number=ticket_number)
    return render(request, "support/ticket_detail.html", {
        "ticket": ticket, "ticket_messages": ticket.messages.select_related("sender"), "form": form,
    })
