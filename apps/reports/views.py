from django.http import Http404
from django.shortcuts import render
from django.utils.dateparse import parse_date

from apps.accounts.rbac import permission_required
from apps.dashboard.audit import log_activity

from .exporters import export_csv, export_pdf, export_xlsx
from .services import REPORTS, default_range, sales_report


@permission_required("reports.view", "inventory.view")
def report_view(request, key="sales"):
    if key not in REPORTS:
        raise Http404
    if key != "inventory" and not request.user.has_access("reports.view"):
        key = "inventory"
    label, builder = REPORTS[key]
    start, end = default_range()
    start = parse_date(request.GET.get("start", "") or "") or start
    end = parse_date(request.GET.get("end", "") or "") or end
    if start > end:
        start, end = end, start
    group = request.GET.get("group", "day")
    report = sales_report(start, end, group) if key == "sales" else builder(start, end)

    export = request.GET.get("export")
    if export in ("csv", "xlsx", "pdf"):
        log_activity(request, "export", None, f"Exported {label} report as {export}", object_type="Report")
        return {"csv": export_csv, "xlsx": export_xlsx, "pdf": export_pdf}[export](report, start, end)

    return render(request, "dashboard/reports.html", {
        "report": report, "key": key, "reports": [(k, v[0]) for k, v in REPORTS.items()],
        "start": start, "end": end, "group": group,
    })
