from django.db import transaction
from django.urls import reverse

from apps.notifications.services import notify, notify_staff, send_templated_email

from .models import SupportMessage, SupportTicket


@transaction.atomic
def create_ticket(*, user, name, email, subject, message, phone="", category="other", order=None):
    ticket = SupportTicket.objects.create(
        user=user, name=name, email=email, phone=phone, subject=subject, category=category, order=order,
    )
    SupportMessage.objects.create(ticket=ticket, sender=user, message=message)
    transaction.on_commit(lambda: notify_staff(
        "support.manage", "New support ticket", f"{ticket.ticket_number}: {subject}",
        link=reverse("dashboard:ticket_detail", args=[ticket.pk]), category="support"))
    transaction.on_commit(lambda: send_templated_email(
        f"We received your request [{ticket.ticket_number}]", [email], "emails/ticket_created.html",
        {"ticket": ticket, "name": name}))
    return ticket


def add_reply(ticket, sender, message, is_staff):
    msg = SupportMessage.objects.create(ticket=ticket, sender=sender, message=message, is_staff_reply=is_staff)
    if is_staff:
        if ticket.status == "open":
            ticket.status = "in_progress"
        ticket.save()
        if ticket.user:
            notify(ticket.user, f"Reply on {ticket.ticket_number}", message[:200],
                   link=reverse("support:detail", args=[ticket.ticket_number]), category="support",
                   email_template="emails/notification.html")
        else:
            send_templated_email(f"Reply on your COZY request [{ticket.ticket_number}]", [ticket.email],
                                 "emails/notification.html",
                                 {"title": f"Reply on {ticket.ticket_number}", "message": message, "link": ""})
    else:
        if ticket.status in ("resolved", "closed"):
            ticket.status = "open"
        ticket.save()
        notify_staff("support.manage", f"Customer replied on {ticket.ticket_number}", message[:200],
                     link=reverse("dashboard:ticket_detail", args=[ticket.pk]), category="support")
    return msg
