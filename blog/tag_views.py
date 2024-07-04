from django.http import JsonResponse
from django.db.models.functions import Length
from .models import Tag


def tags_autocomplete(request):
    query = request.GET.get("q", "")
    # Remove whitespace
    query = "".join(query.split())
    if query:
        tags = (
            Tag.objects.filter(tag__icontains=query)
            .annotate(tag_length=Length("tag"))
            .order_by("tag_length")[:5]
        )
    else:
        tags = Tag.objects.none()
    return JsonResponse(
        {"tags": [{"tag": tag.tag, "count": tag.total_count()} for tag in tags]}
    )
