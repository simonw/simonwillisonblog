from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from blog.models import Tag, PreviousTagName, Entry, Blogmark, Quotation

@staff_member_required
def merge_tags(request):
    if request.method == "POST":
        winner_tag_id = request.POST.get("winner_tag")
        loser_tag_id = request.POST.get("loser_tag")

        if winner_tag_id and loser_tag_id:
            try:
                winner_tag = Tag.objects.get(id=winner_tag_id)
                loser_tag = Tag.objects.get(id=loser_tag_id)

                with transaction.atomic():
                    # Update entries
                    for entry in Entry.objects.filter(tags=loser_tag):
                        entry.tags.remove(loser_tag)
                        entry.tags.add(winner_tag)

                    # Update blogmarks
                    for blogmark in Blogmark.objects.filter(tags=loser_tag):
                        blogmark.tags.remove(loser_tag)
                        blogmark.tags.add(winner_tag)

                    # Update quotations
                    for quotation in Quotation.objects.filter(tags=loser_tag):
                        quotation.tags.remove(loser_tag)
                        quotation.tags.add(winner_tag)

                    # Delete loser tag and create PreviousTagName record
                    PreviousTagName.objects.create(tag=winner_tag, previous_name=loser_tag.tag)
                    loser_tag.delete()

                return redirect("/admin/merge-tags/")

            except Tag.DoesNotExist:
                pass

    return render(request, "merge_tags.html")
