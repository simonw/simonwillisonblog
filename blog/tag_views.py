from django.http import JsonResponse
from django.db.models import Q
from .models import Tag

def tags_autocomplete(request):
    query = request.GET.get('q', '')
    if query:
        tags = Tag.objects.filter(tag__icontains=query)[:5]
    else:
        tags = Tag.objects.none()
    tag_list = [tag.tag for tag in tags]
    return JsonResponse({'tags': tag_list})
